"""Décide si la réponse d'un modèle est correcte.

C'est l'étape la plus délicate du projet. Une comparaison naïve `==` compterait
faux `"Leonardo da Vinci."` face à la vérité terrain `"Leonardo da Vinci"`, et
**sous-estimerait tous les modèles** — d'une façon qui ne se voit pas à la
relecture, puisque le taux produit reste plausible.

La cascade ci-dessous applique cinq règles dans l'ordre ; la première qui statue
l'emporte, et la règle retenue est toujours renvoyée dans `match_rule`. Sans
cette traçabilité, le matching ne serait pas auditable : on ne pourrait pas
distinguer un taux obtenu par égalité stricte d'un taux gonflé par la
similarité floue.

Principe directeur : **en cas de doute réel, on compte faux**. Un benchmark qui
surestime trompe davantage qu'un benchmark qui sous-estime.
"""

from __future__ import annotations

import html
import re
import unicodedata
from difflib import SequenceMatcher

from trivia_bench import config

LEADING_ARTICLE = re.compile(r"^(?:the|a|an)\s+")
PUNCTUATION = re.compile(r"[^\w\s]")
WHITESPACE = re.compile(r"\s+")

# Marqueurs des questions vrai/faux. L'anglais suffit pour OpenTDB, mais les
# modèles multilingues répondent parfois dans une autre langue.
TRUE_WORDS = frozenset({"true", "yes", "vrai", "correct", "t"})
FALSE_WORDS = frozenset({"false", "no", "faux", "incorrect", "f"})

# Verdicts possibles, dans l'ordre de la cascade.
RULE_EXACT = "exact"
RULE_BOOLEAN = "boolean"
RULE_OPTION = "option_substring"
RULE_FUZZY = "fuzzy"
RULE_NONE = "none"


def normalize(text: str) -> str:
    """Ramène une chaîne à une forme comparable.

    Appliquée **aux deux côtés** de la comparaison. Chaque passe absorbe une
    différence qui n'en est pas une pour un correcteur humain : accents,
    majuscules, article initial, ponctuation, espaces multiples.
    """
    if not isinstance(text, str):
        return ""
    text = html.unescape(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = LEADING_ARTICLE.sub("", text)
    text = PUNCTUATION.sub(" ", text)
    return WHITESPACE.sub(" ", text).strip()


def _find_options(answer: str, options: list[str]) -> list[tuple[int, int, str]]:
    """Localise les options citées dans la réponse.

    Renvoie des triplets `(début, longueur, option)`. La recherche impose des
    **frontières de mots** : sans elles, l'option « 1979 » serait trouvée dans
    « 11979 », et « art » dans « Bart Simpson ».
    """
    found: list[tuple[int, int, str]] = []
    for option in options:
        normalized = normalize(option)
        if not normalized:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)")
        match = pattern.search(answer)
        if match:
            found.append((match.start(), len(normalized), option))
    return found


def _resolve_overlaps(found: list[tuple[int, int, str]]) -> list[str]:
    """Écarte les options englobées par une autre au même endroit.

    Sans cette étape, « Dark Red » déclencherait deux correspondances — « Red »
    étant contenu dedans — et la bonne réponse serait rejetée pour ambiguïté.
    Le biais ne serait pas aléatoire : il frapperait systématiquement les
    catégories aux options emboîtées, qui paraîtraient plus difficiles qu'elles
    ne le sont.

    On ne garde donc qu'une option par zone de texte, la plus longue. Deux
    options réellement disjointes restent, elles, deux correspondances — et la
    réponse est bien ambiguë.
    """
    kept: list[tuple[int, int, str]] = []
    for start, length, option in sorted(found, key=lambda item: -item[1]):
        end = start + length
        overlaps = any(start < k_start + k_len and k_start < end for k_start, k_len, _ in kept)
        if not overlaps:
            kept.append((start, length, option))
    return [option for _, _, option in kept]


def _boolean_verdict(answer: str) -> bool | None:
    """Lit un vrai/faux dans une réponse, ou `None` si elle n'en contient pas."""
    words = set(answer.split())
    says_true = bool(words & TRUE_WORDS)
    says_false = bool(words & FALSE_WORDS)
    if says_true == says_false:  # les deux, ou aucun des deux
        return None
    return says_true


def match(
    ai_answer_raw: str,
    correct_answer: str,
    incorrect_answers: list[str],
    question_type: str,
) -> tuple[bool, str, str]:
    """Compare une réponse de modèle à la vérité terrain.

    Renvoie `(correct, match_rule, ai_answer_normalisee)`.
    """
    answer = normalize(ai_answer_raw)
    truth = normalize(correct_answer)

    if not answer:
        return False, RULE_NONE, answer

    # 1. Égalité stricte après normalisation.
    if answer == truth:
        return True, RULE_EXACT, answer

    # 2. Vrai/faux : le modèle peut répondre « yes » là où la vérité est « True ».
    if question_type == "boolean":
        said = _boolean_verdict(answer)
        if said is not None:
            return said == (truth == "true"), RULE_BOOLEAN, answer

    # 3. Une seule option citée : c'est le choix du modèle, même s'il a bavardé.
    options = [correct_answer, *incorrect_answers]
    cited = _resolve_overlaps(_find_options(answer, options))
    if len(cited) == 1:
        return normalize(cited[0]) == truth, RULE_OPTION, answer
    if len(cited) > 1:
        # Plusieurs options distinctes : impossible de savoir laquelle le modèle
        # a choisie. On tranche contre lui.
        return False, RULE_OPTION, answer

    # 4. Similarité : absorbe fautes de frappe et variantes orthographiques.
    if SequenceMatcher(None, answer, truth).ratio() >= config.FUZZY_THRESHOLD:
        return True, RULE_FUZZY, answer

    return False, RULE_NONE, answer
