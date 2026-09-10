"""Nettoyage bronze → silver.

Transforme `data/bronze/questions_raw.csv` en `data/silver/questions.parquet` :
décodage, normalisation, typage, déduplication.

C'est ici — et nulle part ailleurs — que les questions sont décodées. La couche
bronze conserve l'encodage `url3986` de l'API, ce qui permet de rejouer ce
nettoyage autant de fois que nécessaire sans jamais réinterroger la source.

La clé `question_id` est un hash **déterministe** de l'énoncé et de la bonne
réponse. Ce déterminisme porte deux propriétés du pipeline : l'enrichissement
peut reprendre là où il s'est arrêté, et les jointures restent stables entre
deux exécutions.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from urllib.parse import unquote

import pandas as pd

from trivia_bench import config

WHITESPACE = re.compile(r"\s+")


def decode(text: str) -> str:
    """Décode une chaîne renvoyée par l'API et normalise ses espaces.

    Trois passes successives, chacune nécessaire :

    1. `unquote` défait l'encodage `url3986` demandé à l'ingestion ;
    2. `html.unescape` rattrape les entités HTML que la base contient parfois
       en dur, indépendamment de l'encodage de transport ;
    3. NFKC unifie les variantes Unicode (guillemets typographiques, ligatures),
       sans quoi deux chaînes visuellement identiques produiraient deux
       `question_id` différents.
    """
    if not isinstance(text, str):
        return ""
    text = unquote(text)
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    return WHITESPACE.sub(" ", text).strip()


def make_question_id(question: str, correct_answer: str) -> str:
    """Identifiant stable d'une question.

    Le séparateur `\\x1f` (unit separator) ne peut pas apparaître dans le texte :
    il évite qu'une question se terminant par le début d'une réponse produise
    le même hash qu'une autre combinaison.
    """
    payload = f"{question}\x1f{correct_answer}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def parse_incorrect_answers(raw: str) -> list[str]:
    """Reconstruit la liste des distracteurs, sérialisée en JSON par l'ingestion."""
    if not isinstance(raw, str) or not raw:
        return []
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [decode(v) for v in values]


def split_category(category: str) -> str:
    """Dérive le groupe de catégorie.

    OpenTDB préfixe ses sous-catégories : « Entertainment: Video Games » devient
    « Entertainment ». Regrouper permet d'analyser les grands thèmes sans être
    noyé par les 24 catégories de détail.
    """
    return category.split(":", 1)[0].strip() if ":" in category else category


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Applique le nettoyage complet et renvoie la table silver."""
    df = pd.DataFrame(
        {
            "category": raw["category"].map(decode),
            "type": raw["type"].astype("string"),
            "difficulty": raw["difficulty"].astype("string"),
            "question": raw["question"].map(decode),
            "correct_answer": raw["correct_answer"].map(decode),
            "incorrect_answers": raw["incorrect_answers"].map(parse_incorrect_answers),
            "source_category_id": raw["source_category_id"].astype("int64"),
            "fetched_at": raw["fetched_at"].astype("string"),
        }
    )

    df["category_group"] = df["category"].map(split_category).astype("string")
    df["question_id"] = [
        make_question_id(q, a) for q, a in zip(df["question"], df["correct_answer"], strict=True)
    ]
    df["n_choices"] = df["incorrect_answers"].map(len) + 1
    df["question_length"] = df["question"].str.len().astype("int64")

    # OpenTDB expose la même question dans plusieurs catégories. Le doublon est
    # normal côté source ; il devient un biais côté benchmark, où la question
    # serait posée deux fois au modèle et pèserait double dans le taux.
    before = len(df)
    df = df.drop_duplicates(subset="question_id", keep="first").reset_index(drop=True)
    duplicates = before - len(df)

    columns = [
        "question_id",
        "category",
        "category_group",
        "type",
        "difficulty",
        "question",
        "correct_answer",
        "incorrect_answers",
        "n_choices",
        "question_length",
        "source_category_id",
        "fetched_at",
    ]
    df = df[columns]
    df.attrs["duplicates_removed"] = duplicates
    return df


def main() -> None:
    source = config.QUESTIONS_RAW_CSV
    if not source.exists():
        raise SystemExit(f"{source} est absent. Lancez d'abord `make bronze`.")

    raw = pd.read_csv(source)
    print(f"Bronze : {len(raw)} lignes")

    df = clean(raw)
    duplicates = df.attrs["duplicates_removed"]

    config.SILVER_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.QUESTIONS_PARQUET, index=False)

    print(f"Doublons retirés : {duplicates}")
    print(f"Silver : {len(df)} questions uniques")
    print(f"  types       : {dict(df['type'].value_counts())}")
    print(f"  difficultés : {dict(df['difficulty'].value_counts())}")
    print(
        f"  groupes     : {df['category_group'].nunique()} groupes, "
        f"{df['category'].nunique()} catégories"
    )
    print(f"→ {config.QUESTIONS_PARQUET}")


if __name__ == "__main__":
    main()
