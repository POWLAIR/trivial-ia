"""Ingestion Open Trivia Database vers la couche bronze.

Produit `data/bronze/questions_raw.csv` : les questions **exactement telles que
l'API les renvoie**, sans décodage ni normalisation. Le nettoyage appartient à la
couche silver.

Contraintes de l'API, relevées sur https://opentdb.com/api_config.php et
confirmées par sondage :

- 50 questions maximum par appel, une seule catégorie par appel ;
- aucun paramètre d'offset : le **jeton de session** est le seul moyen de
  balayer une catégorie sans doublon ;
- une requête toutes les 5 secondes par IP, la limite se manifestant aussi bien
  par `response_code = 5` que par un **HTTP 429** sans corps JSON ;
- le jeton est supprimé après 6 h d'inactivité.

Deux pièges motivent la structure de ce module.

**Le code 4 est ambigu.** La documentation annonce le code 1 quand on demande
plus de questions qu'il n'en reste. Le comportement réel avec un jeton est un
code 4, celui-là même qui signale l'épuisement. Demander 50 questions à une
catégorie qui n'en a que 36 renvoie donc « épuisé » alors que les 36 sont
disponibles. Un arrêt sur code 4 perdrait le dernier lot partiel de chaque
catégorie, soit environ 11 % du dataset, sans message d'erreur.

La parade tient en une ligne : on ne demande jamais plus que ce qu'il reste
réellement (`expected - collected`), et le code 4 ne conclut qu'après une
dichotomie descendante infructueuse.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import requests

from trivia_bench import config

# --- Codes de réponse de l'API -------------------------------------------

CODE_SUCCESS = 0
CODE_NO_RESULTS = 1
CODE_INVALID_PARAM = 2
CODE_TOKEN_NOT_FOUND = 3
CODE_TOKEN_EMPTY = 4
CODE_RATE_LIMIT = 5

CODE_LABELS = {
    CODE_SUCCESS: "Success",
    CODE_NO_RESULTS: "No Results",
    CODE_INVALID_PARAM: "Invalid Parameter",
    CODE_TOKEN_NOT_FOUND: "Token Not Found",
    CODE_TOKEN_EMPTY: "Token Empty",
    CODE_RATE_LIMIT: "Rate Limit",
}

# Colonnes de la couche bronze. Les six premières sont celles de l'API, non
# renommées ; les deux dernières sont des métadonnées d'ingestion, qui
# documentent quand et comment la ligne a été obtenue sans rien transformer.
CSV_FIELDS = [
    "category",
    "type",
    "difficulty",
    "question",
    "correct_answer",
    "incorrect_answers",
    "fetched_at",
    "source_category_id",
]


class OpenTDBError(RuntimeError):
    """Erreur non récupérable de l'API : bug d'appel ou épuisement des retries."""


@dataclass
class CategoryReport:
    """Bilan de collecte d'une catégorie, repris tel quel dans le rapport."""

    id: int
    name: str
    expected: int
    collected: int = 0
    calls: int = 0
    exhausted_early: bool = False

    @property
    def ok(self) -> bool:
        return self.collected == self.expected

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "expected": self.expected,
            "collected": self.collected,
            "gap": self.expected - self.collected,
            "calls": self.calls,
            "exhausted_early": self.exhausted_early,
            "ok": self.ok,
        }


@dataclass
class OpenTDBClient:
    """Client HTTP respectant la limite de débit de l'API.

    Le throttle s'applique à *tous* les appels, endpoints d'aide compris : la
    limite est posée par IP, pas par endpoint.
    """

    session: requests.Session = field(default_factory=requests.Session)
    _last_call: float = 0.0
    n_calls: int = 0
    n_rate_limited: int = 0
    n_http_errors: int = 0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if self._last_call and elapsed < config.OPENTDB_MIN_INTERVAL:
            time.sleep(config.OPENTDB_MIN_INTERVAL - elapsed)

    def get(self, url: str, params: dict | None = None) -> dict:
        """Appelle l'API et renvoie le JSON, en gérant la limite de débit.

        Le HTTP 429 et le `response_code` 5 sont deux expressions de la même
        limite : le premier n'a pas de corps JSON, il faut donc l'intercepter
        au niveau du transport.
        """
        delay = config.OPENTDB_BACKOFF_BASE

        for attempt in range(config.OPENTDB_MAX_RETRIES):
            self._throttle()
            self._last_call = time.monotonic()
            self.n_calls += 1

            try:
                response = self.session.get(url, params=params, timeout=config.HTTP_TIMEOUT)
            except requests.RequestException as exc:
                self.n_http_errors += 1
                if attempt == config.OPENTDB_MAX_RETRIES - 1:
                    raise OpenTDBError(f"échec réseau sur {url} : {exc}") from exc
                time.sleep(delay)
                delay *= 2
                continue

            if response.status_code == 429:
                self.n_rate_limited += 1
                time.sleep(delay)
                delay *= 2
                continue

            response.raise_for_status()
            payload = response.json()

            if payload.get("response_code") == CODE_RATE_LIMIT:
                self.n_rate_limited += 1
                time.sleep(delay)
                delay *= 2
                continue

            return payload

        raise OpenTDBError(
            f"limite de débit non résorbée après {config.OPENTDB_MAX_RETRIES} essais"
        )

    # --- Endpoints -------------------------------------------------------

    def request_token(self) -> str:
        payload = self.get(config.OPENTDB_TOKEN_URL, {"command": "request"})
        if payload.get("response_code") != CODE_SUCCESS:
            raise OpenTDBError(f"jeton refusé : {payload}")
        return payload["token"]

    def fetch_categories(self) -> list[dict]:
        return self.get(config.OPENTDB_CATEGORY_URL)["trivia_categories"]

    def fetch_global_counts(self) -> dict:
        """Compte global, en un seul appel.

        `total_num_of_questions` inclut les questions en attente de validation et
        les questions rejetées, que l'API ne distribue pas. Seul
        `total_num_of_verified_questions` correspond à ce qui est réellement
        servi — vérifié : il coïncide avec `api_count.php` catégorie par
        catégorie.
        """
        return self.get(config.OPENTDB_COUNT_GLOBAL_URL)

    def fetch_category_count(self, category_id: int) -> int:
        payload = self.get(config.OPENTDB_COUNT_URL, {"category": category_id})
        return payload["category_question_count"]["total_question_count"]

    def fetch_questions(self, amount: int, category_id: int, token: str) -> tuple[int, list[dict]]:
        payload = self.get(
            config.OPENTDB_API_URL,
            {
                "amount": amount,
                "category": category_id,
                "token": token,
                "encode": config.OPENTDB_ENCODING,
            },
        )
        code = payload.get("response_code", CODE_INVALID_PARAM)

        if code == CODE_INVALID_PARAM:
            # Paramètre invalide : c'est un bug d'appel, pas une condition
            # normale. Échouer bruyamment plutôt que collecter un jeu partiel.
            raise OpenTDBError(f"paramètre invalide (catégorie {category_id}, amount {amount})")

        return code, payload.get("results", [])


def scrape_category(
    client: OpenTDBClient,
    token: str,
    report: CategoryReport,
) -> list[dict]:
    """Collecte une catégorie jusqu'à son effectif attendu.

    On demande toujours `min(50, restant)` plutôt que 50 systématiquement : cela
    évite le code 4 trompeur décrit en tête de module et supprime les appels
    inutiles.

    Si l'API renvoie tout de même 4 ou 1 — le compte annoncé diverge alors du
    compte réel — on retente en dichotomie descendante avant de conclure à
    l'épuisement.
    """
    rows: list[dict] = []
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")

    while len(rows) < report.expected:
        amount = min(config.OPENTDB_BATCH_SIZE, report.expected - len(rows))
        code, results = client.fetch_questions(amount, report.id, token)
        report.calls += 1

        if code == CODE_SUCCESS:
            rows.extend(results)
            continue

        if code == CODE_TOKEN_NOT_FOUND:
            token = client.request_token()
            continue

        if code in (CODE_TOKEN_EMPTY, CODE_NO_RESULTS):
            recovered = _fallback_smaller(client, token, report, amount)
            if not recovered:
                report.exhausted_early = True
                break
            rows.extend(recovered)
            continue

        raise OpenTDBError(f"code inattendu {code} ({CODE_LABELS.get(code, '?')})")

    for row in rows:
        row["fetched_at"] = fetched_at
        row["source_category_id"] = report.id
    return rows


def _fallback_smaller(
    client: OpenTDBClient,
    token: str,
    report: CategoryReport,
    amount: int,
) -> list[dict]:
    """Redemande en divisant `amount` par deux jusqu'à 1.

    N'est atteint que si le compte annoncé par l'API diverge du compte réel.
    Renvoie une liste vide quand la catégorie est réellement épuisée.
    """
    while amount > 1:
        amount //= 2
        code, results = client.fetch_questions(amount, report.id, token)
        report.calls += 1
        if code == CODE_SUCCESS:
            return results
        if code not in (CODE_TOKEN_EMPTY, CODE_NO_RESULTS):
            raise OpenTDBError(f"code inattendu {code} pendant le repli")
    return []


def write_csv(rows: list[dict], path) -> None:
    """Écrit la couche bronze.

    `incorrect_answers` est sérialisé en JSON : le CSV ne sait pas représenter
    une liste, et le parsing revient à la couche silver.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **{k: row.get(k) for k in CSV_FIELDS},
                    "incorrect_answers": json.dumps(
                        row.get("incorrect_answers", []), ensure_ascii=False
                    ),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Collecte l'intégralité du dataset OpenTDB.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="réécrit questions_raw.csv même s'il existe (l'ancien est archivé)",
    )
    args = parser.parse_args()

    target = config.QUESTIONS_RAW_CSV
    if target.exists() and not args.force:
        raise SystemExit(
            f"{target} existe déjà.\n"
            "La collecte dure ~15 min et sollicite une API publique gratuite : "
            "elle ne se relance pas sans raison.\n"
            "Utilisez --force si vous voulez vraiment la refaire."
        )

    started = time.monotonic()
    client = OpenTDBClient()

    print("Jeton de session…")
    token = client.request_token()

    print("Catégories et effectifs attendus…")
    categories = client.fetch_categories()
    global_counts = client.fetch_global_counts()
    verified = {
        int(cid): data["total_num_of_verified_questions"]
        for cid, data in global_counts["categories"].items()
    }

    reports = [
        CategoryReport(id=c["id"], name=c["name"], expected=verified.get(c["id"], 0))
        for c in categories
    ]
    total_expected = sum(r.expected for r in reports)
    print(f"{len(reports)} catégories, {total_expected} questions vérifiées attendues\n")

    all_rows: list[dict] = []
    for report in reports:
        rows = scrape_category(client, token, report)
        report.collected = len(rows)
        all_rows.extend(rows)
        flag = "ok" if report.ok else f"ÉCART {report.expected - report.collected:+d}"
        print(
            f"  [{report.id:>2}] {report.name[:38]:<38} "
            f"{report.collected:>5}/{report.expected:<5} {flag}"
        )

    write_csv(all_rows, target)
    duration = time.monotonic() - started

    payload = {
        "run_id": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "https://opentdb.com",
        "licence": "CC BY-SA 4.0",
        "encoding": config.OPENTDB_ENCODING,
        "global_counts": global_counts["overall"],
        "categories": [r.as_dict() for r in reports],
        "total_expected": total_expected,
        "total_collected": len(all_rows),
        "complete": all(r.ok for r in reports),
        "api_calls": client.n_calls,
        "rate_limited": client.n_rate_limited,
        "http_errors": client.n_http_errors,
        "duration_seconds": round(duration, 1),
    }
    config.INGESTION_REPORT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    print(
        f"\n{len(all_rows)}/{total_expected} questions collectées "
        f"en {duration / 60:.1f} min ({client.n_calls} appels).\n"
        f"→ {target}\n→ {config.INGESTION_REPORT_JSON}"
    )
    if not payload["complete"]:
        print("\n⚠️  Collecte incomplète : voir le champ `gap` par catégorie dans le rapport.")


if __name__ == "__main__":
    main()
