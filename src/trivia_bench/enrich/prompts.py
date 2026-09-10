"""Catalogue versionné des prompts.

La formulation de la question influence fortement le résultat : c'est donc une
**variable expérimentale**, pas un détail d'implémentation. Chaque réponse
stockée porte son `prompt_version`, ce qui permet de comparer les formulations
sur exactement le même jeu de questions.

⚠️ **Règle absolue : on ajoute une version, on n'en modifie jamais une
existante.** Éditer `v2` invaliderait en silence toutes les réponses déjà
collectées sous ce nom, sans qu'aucun test ne le détecte.
"""

from __future__ import annotations

import random

PROMPTS: dict[str, str] = {
    # Question nue : la base de référence, sans aucune consigne.
    "v1": "{question}",
    # Consigne de format minimale.
    "v2": (
        "Answer with the exact answer only, no sentence, no explanation.\n"
        "Question: {question}\n"
        "Answer:"
    ),
    # Consigne explicite, avec la typologie de réponse attendue.
    "v3": (
        "You are answering a trivia quiz. Reply with the shortest possible "
        "answer: a name, a date, a word or a number. Do not add punctuation, "
        "explanation or a full sentence.\n"
        "Question: {question}\n"
        "Answer:"
    ),
    # Options fournies : la tâche devient un QCM.
    "v3_mcq": (
        "You are answering a multiple-choice trivia question. "
        "Reply with exactly one of the proposed options, copied verbatim.\n"
        "Question: {question}\n"
        "Options:\n{options}\n"
        "Answer:"
    ),
}

# Les versions qui fournissent les options au modèle. Elles ne se comparent pas
# aux autres : donner les choix transforme une restitution en reconnaissance et
# relève mécaniquement le taux de bonnes réponses (25 % au hasard sur 4 choix).
MCQ_VERSIONS = frozenset({"v3_mcq"})


def shuffled_options(
    correct_answer: str,
    incorrect_answers: list[str],
    question_id: str,
) -> list[str]:
    """Mélange les options de façon déterministe.

    La graine dérive du `question_id` : l'ordre est donc **stable d'une
    exécution à l'autre** — sans quoi le benchmark ne serait pas reproductible —
    tout en variant d'une question à l'autre, ce qui évite que la bonne réponse
    occupe toujours la même position et récompense un modèle qui aurait un biais
    positionnel.
    """
    options = [correct_answer, *incorrect_answers]
    random.Random(question_id).shuffle(options)
    return options


def build_prompt(row: dict, version: str) -> str:
    """Construit le prompt d'une question pour une version donnée.

    `row` est une ligne de la couche silver : `question`, `correct_answer`,
    `incorrect_answers`, `question_id`.
    """
    try:
        template = PROMPTS[version]
    except KeyError:
        raise ValueError(
            f"version de prompt inconnue : {version!r} (connues : {sorted(PROMPTS)})"
        ) from None

    if version not in MCQ_VERSIONS:
        return template.format(question=row["question"])

    options = shuffled_options(
        row["correct_answer"],
        list(row["incorrect_answers"]),
        row["question_id"],
    )
    rendered = "\n".join(f"- {option}" for option in options)
    return template.format(question=row["question"], options=rendered)
