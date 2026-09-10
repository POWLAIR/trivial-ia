"""Interroge un modèle local sur les questions de la couche silver.

Produit `data/silver/ai_answers.parquet`, une ligne par
`(question_id, model, prompt_version)`.

Trois propriétés portent la validité du benchmark :

- **déterminisme** : `temperature=0` et `seed` fixe, sans quoi deux exécutions
  donneraient des taux différents et la comparaison entre modèles n'aurait plus
  de sens ;
- **mesure honnête du temps** : le chronomètre encadre le seul appel réseau, et
  l'appel de préchauffage — qui inclut le chargement du modèle en mémoire — est
  exclu ;
- **reprise** : les résultats sont écrits par fragments, et un run relancé ne
  réinterroge que ce qui manque. L'inférence coûte des heures : une interruption
  ne doit jamais faire repartir de zéro.
"""

from __future__ import annotations

import argparse
import time
import uuid
from datetime import UTC, datetime

import pandas as pd
from openai import OpenAI

from trivia_bench import config
from trivia_bench.enrich.matching import match
from trivia_bench.enrich.prompts import PROMPTS, build_prompt

ANSWER_COLUMNS = [
    "question_id",
    "model",
    "prompt_version",
    "ai_answer_raw",
    "ai_answer",
    "ai_correct",
    "match_rule",
    "response_time",
    "n_eval_tokens",
    "run_id",
    "answered_at",
    "error",
]


def make_client() -> OpenAI:
    """Client pointant sur le runtime local.

    `LLM_BASE_URL` vient de `.env` : LM Studio et Ollama exposent la même
    interface compatible OpenAI, donc changer de runtime ne coûte qu'une
    variable. La clé est ignorée par un serveur local mais exigée par le client.
    """
    return OpenAI(
        base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=config.LLM_TIMEOUT
    )


def ask(client: OpenAI, model: str, prompt: str) -> tuple[str, float, int, str | None]:
    """Pose une question et mesure le temps de génération.

    Le chronomètre encadre **uniquement** l'appel réseau. Le serveur étant
    local, la latence de transport est négligeable devant l'inférence.
    """
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
            seed=config.SEED,
        )
    except Exception as exc:  # noqa: BLE001 - toute panne d'appel se trace pareil
        return "", time.perf_counter() - started, 0, f"{type(exc).__name__}: {exc}"

    elapsed = time.perf_counter() - started
    content = response.choices[0].message.content or ""
    tokens = response.usage.completion_tokens if response.usage else 0
    return content, elapsed, tokens, None


def load_questions(limit: int | None) -> pd.DataFrame:
    if not config.QUESTIONS_PARQUET.exists():
        raise SystemExit(f"{config.QUESTIONS_PARQUET} est absent. Lancez d'abord `make silver`.")

    df = pd.read_parquet(config.QUESTIONS_PARQUET)

    # Mélange déterministe, puis on prend les N premières. Deux propriétés en
    # découlent, et les deux comptent :
    #
    # - l'échantillon ne suit pas l'ordre du fichier, qui est trié par catégorie
    #   et donnerait une estimation de vitesse comme de justesse non
    #   représentative ;
    # - les échantillons sont **emboîtés** : les 200 premières font partie des
    #   500 premières. On peut donc agrandir l'échantillon plus tard sans rien
    #   recalculer, la reprise ne traitant que le complément. `sample(n=N)`
    #   n'offre pas cette garantie : deux tailles donnent deux tirages disjoints.
    df = df.sample(frac=1.0, random_state=config.SEED).reset_index(drop=True)
    if limit is not None and limit < len(df):
        df = df.head(limit)
    return df


def already_done(model: str, prompt_version: str) -> set[str]:
    """Questions déjà traitées pour ce couple modèle / prompt."""
    done: set[str] = set()
    sources = [config.AI_ANSWERS_PARQUET] if config.AI_ANSWERS_PARQUET.exists() else []
    if config.AI_ANSWERS_PARTS_DIR.exists():
        sources.extend(sorted(config.AI_ANSWERS_PARTS_DIR.glob("*.parquet")))

    for path in sources:
        frame = pd.read_parquet(path, columns=["question_id", "model", "prompt_version"])
        mask = (frame["model"] == model) & (frame["prompt_version"] == prompt_version)
        done.update(frame.loc[mask, "question_id"])
    return done


def consolidate() -> pd.DataFrame:
    """Fusionne les fragments dans le Parquet final et les supprime."""
    frames = []
    if config.AI_ANSWERS_PARQUET.exists():
        frames.append(pd.read_parquet(config.AI_ANSWERS_PARQUET))

    parts = (
        sorted(config.AI_ANSWERS_PARTS_DIR.glob("*.parquet"))
        if config.AI_ANSWERS_PARTS_DIR.exists()
        else []
    )
    frames.extend(pd.read_parquet(p) for p in parts)
    if not frames:
        return pd.DataFrame(columns=ANSWER_COLUMNS)

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(
        subset=["question_id", "model", "prompt_version"], keep="last"
    ).reset_index(drop=True)
    merged.to_parquet(config.AI_ANSWERS_PARQUET, index=False)

    for part in parts:
        part.unlink()
    return merged


def run(model: str, prompt_version: str, limit: int | None) -> None:
    if prompt_version not in PROMPTS:
        raise SystemExit(f"prompt inconnu : {prompt_version} (connus : {sorted(PROMPTS)})")

    questions = load_questions(limit)
    done = already_done(model, prompt_version)
    todo = questions[~questions["question_id"].isin(done)].reset_index(drop=True)

    print(f"Modèle    : {model}")
    print(f"Prompt    : {prompt_version}")
    print(f"Questions : {len(todo)} à traiter ({len(done)} déjà faites)")
    if todo.empty:
        print("Rien à faire.")
        return

    client = make_client()
    run_id = uuid.uuid4().hex[:12]
    config.AI_ANSWERS_PARTS_DIR.mkdir(parents=True, exist_ok=True)

    # Préchauffage : le premier appel inclut le chargement du modèle en mémoire,
    # parfois plusieurs secondes. Il est exclu des mesures.
    print("Préchauffage…")
    _, warmup_time, _, warmup_error = ask(client, model, "Say OK.")
    if warmup_error:
        raise SystemExit(f"le modèle ne répond pas : {warmup_error}")
    print(f"  prêt en {warmup_time:.1f} s\n")

    buffer: list[dict] = []
    started = time.perf_counter()
    n_errors = 0

    for index, row in enumerate(todo.to_dict("records"), start=1):
        prompt = build_prompt(row, prompt_version)
        raw, elapsed, tokens, error = ask(client, model, prompt)

        if error:
            n_errors += 1
            correct, rule, normalized = None, None, ""
        else:
            correct, rule, normalized = match(
                raw, row["correct_answer"], list(row["incorrect_answers"]), row["type"]
            )

        buffer.append(
            {
                "question_id": row["question_id"],
                "model": model,
                "prompt_version": prompt_version,
                "ai_answer_raw": raw,
                "ai_answer": normalized,
                # NULL et non False sur erreur : une panne d'appel n'est pas une
                # mauvaise réponse, et la confondre pénaliserait le modèle.
                "ai_correct": correct,
                "match_rule": rule,
                "response_time": elapsed,
                "n_eval_tokens": tokens,
                "run_id": run_id,
                "answered_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "error": error,
            }
        )

        if len(buffer) >= config.BATCH_SIZE:
            _flush(buffer, run_id, index)
            rate = (time.perf_counter() - started) / index
            remaining = (len(todo) - index) * rate
            print(
                f"  {index}/{len(todo)} — {rate:.2f} s/question — reste ~{remaining / 60:.0f} min"
            )

    if buffer:
        _flush(buffer, run_id, len(todo))

    merged = consolidate()
    duration = time.perf_counter() - started
    subset = merged[(merged["model"] == model) & (merged["prompt_version"] == prompt_version)]
    scored = subset[subset["ai_correct"].notna()]

    print(
        f"\n{len(todo)} questions en {duration / 60:.1f} min "
        f"({duration / len(todo):.2f} s/question)"
    )
    if n_errors:
        print(f"Erreurs   : {n_errors} (exclues du taux)")
    if len(scored):
        print(f"Justesse  : {scored['ai_correct'].mean() * 100:.1f} % sur {len(scored)} réponses")
        print(f"Règles    : {dict(scored['match_rule'].value_counts())}")
    print(f"→ {config.AI_ANSWERS_PARQUET}")


def _flush(buffer: list[dict], run_id: str, index: int) -> None:
    path = config.AI_ANSWERS_PARTS_DIR / f"{run_id}_{index:06d}.parquet"
    pd.DataFrame(buffer, columns=ANSWER_COLUMNS).to_parquet(path, index=False)
    buffer.clear()


def main() -> None:
    parser = argparse.ArgumentParser(description="Interroge un modèle local sur le dataset.")
    parser.add_argument(
        "--model", required=True, help="clé du modèle, telle que listée par `lms ls`"
    )
    parser.add_argument("--prompt-version", default="v3", choices=sorted(PROMPTS))
    parser.add_argument("--limit", type=int, help="échantillon aléatoire à graine fixe")
    parser.add_argument(
        "--workers",
        type=int,
        default=config.DEFAULT_WORKERS,
        help="laisser à 1 : la concurrence fausse response_time",
    )
    args = parser.parse_args()

    if args.workers != 1:
        raise SystemExit(
            "--workers > 1 fausse la mesure de response_time (contention CPU).\n"
            "Le parallélisme n'est pas implémenté volontairement."
        )

    run(args.model, args.prompt_version, args.limit)


if __name__ == "__main__":
    main()
