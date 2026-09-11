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
    # Réponse par lettre, contrainte par grammaire côté moteur.
    #
    # L'instruction est volontairement laconique. Mesuré en alternant les deux
    # variantes question par question : la formulation longue (« Answer the
    # multiple-choice question with the letter of the correct option. Reply with
    # a single letter. ») coûte 15 tokens de prompt de plus et 0,58 s de médiane
    # par question, pour une justesse identique aux marges près. L'évaluation du
    # prompt dominant le temps de calcul, chaque token d'instruction se paie à
    # toutes les questions.
    "v4_letter": ("Answer with one letter.\nQuestion: {question}\n{options}\nAnswer:"),
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
MCQ_VERSIONS = frozenset({"v3_mcq", "v4_letter"})

# Les versions où le modèle répond par une lettre. La sortie est contrainte par
# une grammaire côté moteur : le modèle ne *peut* produire qu'une lettre valide.
# Conséquence méthodologique : il répond toujours, même quand il ignore tout, ce
# qui plaque le score sur la ligne du hasard par le bas au lieu de le laisser
# tomber en dessous. À lire impérativement avec cette ligne affichée.
LETTER_VERSIONS = frozenset({"v4_letter"})

LETTERS = "ABCDEFGH"


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
    if version in LETTER_VERSIONS:
        rendered = "\n".join(f"{LETTERS[i]}. {opt}" for i, opt in enumerate(options))
    else:
        rendered = "\n".join(f"- {option}" for option in options)
    return template.format(question=row["question"], options=rendered)


def letter_grammar(n_options: int) -> str:
    """Grammaire GBNF restreignant la sortie à une lettre d'option valide.

    Passée au moteur llama.cpp, elle rend toute autre sortie **impossible** :
    pas de « B) Paris », pas de lettre hors domaine, pas de réponse vide. Le
    matching devient une simple correspondance lettre → index, sans parsing.

    Le domaine s'adapte au nombre d'options : `[A-D]` pour un QCM à quatre
    choix, `[A-B]` pour une question vrai/faux.
    """
    if not 2 <= n_options <= len(LETTERS):
        raise ValueError(f"nombre d'options hors domaine : {n_options}")
    return f"root ::= [A-{LETTERS[n_options - 1]}]"
