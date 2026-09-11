"""Tests de la cascade de matching.

C'est le test le plus important du projet. Une erreur ici ne fait rien planter :
elle produit un taux de bonnes réponses plausible mais faux, que personne ne
peut détecter à la relecture du rapport.
"""

from __future__ import annotations

import pytest

from trivia_bench.enrich.matching import (
    RULE_BOOLEAN,
    RULE_EXACT,
    RULE_FUZZY,
    RULE_LETTER,
    RULE_NONE,
    RULE_OPTION,
    match,
    match_letter,
    normalize,
)
from trivia_bench.enrich.prompts import build_prompt, letter_grammar, shuffled_options

MCQ = "multiple"
BOOL = "boolean"


class TestNormalize:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Leonardo da Vinci.", "leonardo da vinci"),
            ("  LEONARDO   da Vinci  ", "leonardo da vinci"),
            ("Léonard", "leonard"),
            ("The Beatles", "beatles"),
            ("A Clockwork Orange", "clockwork orange"),
            ("An Inspector Calls", "inspector calls"),
            ("Don&#039;t Stop", "don t stop"),
        ],
    )
    def test_cases(self, raw, expected):
        assert normalize(raw) == expected

    def test_non_string(self):
        assert normalize(None) == ""


class TestExact:
    def test_trailing_punctuation(self):
        """Le cas fondateur : la ponctuation ne doit pas coûter un point."""
        ok, rule, _ = match("Leonardo da Vinci.", "Leonardo da Vinci", ["Picasso"], MCQ)
        assert ok is True
        assert rule == RULE_EXACT

    def test_accents_ignored(self):
        ok, rule, _ = match("Leonard", "Léonard", ["Picasso"], MCQ)
        assert (ok, rule) == (True, RULE_EXACT)

    def test_leading_article_ignored(self):
        ok, rule, _ = match("Beatles", "The Beatles", ["The Who"], MCQ)
        assert (ok, rule) == (True, RULE_EXACT)

    def test_case_insensitive(self):
        ok, _, _ = match("PARIS", "Paris", ["Lyon"], MCQ)
        assert ok is True


class TestBoolean:
    @pytest.mark.parametrize("said", ["True", "true", "Yes", "yes.", "Vrai"])
    def test_true_synonyms(self, said):
        ok, _, _ = match(said, "True", ["False"], BOOL)
        assert ok is True

    def test_synonym_uses_boolean_rule(self):
        """« Yes » face à « True » n'est pas une égalité : c'est la règle booléenne."""
        ok, rule, _ = match("Yes", "True", ["False"], BOOL)
        assert (ok, rule) == (True, RULE_BOOLEAN)

    @pytest.mark.parametrize("said", ["False", "No", "no", "Faux"])
    def test_false_synonyms(self, said):
        ok, _, _ = match(said, "False", ["True"], BOOL)
        assert ok is True

    def test_wrong_boolean(self):
        ok, rule, _ = match("Yes", "False", ["True"], BOOL)
        assert (ok, rule) == (False, RULE_BOOLEAN)

    def test_contradictory_answer_is_not_boolean(self):
        """« true or false » ne tranche rien : la règle booléenne passe la main."""
        ok, rule, _ = match("true or false", "True", ["False"], BOOL)
        assert rule != RULE_BOOLEAN
        assert ok is False


class TestOptionSubstring:
    def test_verbose_answer_with_single_option(self):
        """Une réponse bavarde citant une seule option reste exploitable."""
        ok, rule, _ = match(
            "The answer is definitely Paris, the capital of France.",
            "Paris",
            ["Lyon", "Marseille", "Nice"],
            MCQ,
        )
        assert (ok, rule) == (True, RULE_OPTION)

    def test_verbose_answer_with_wrong_option(self):
        ok, rule, _ = match("I believe it is Lyon.", "Paris", ["Lyon", "Marseille", "Nice"], MCQ)
        assert (ok, rule) == (False, RULE_OPTION)

    def test_two_distinct_options_is_ambiguous(self):
        """Deux options réellement distinctes : on ne peut pas trancher, donc faux."""
        ok, rule, _ = match("It is either Paris or Lyon.", "Paris", ["Lyon", "Marseille"], MCQ)
        assert (ok, rule) == (False, RULE_OPTION)

    def test_nested_option_longest_wins(self):
        """Régression : « Dark Red » contient « Red » et était compté faux.

        Sans la résolution des chevauchements, la bonne réponse déclenchait deux
        correspondances et tombait dans la branche « ambigu ». Le biais frappait
        systématiquement les catégories aux options emboîtées.
        """
        ok, rule, _ = match("I would say Dark Red.", "Dark Red", ["Red", "Blue", "Green"], MCQ)
        assert (ok, rule) == (True, RULE_OPTION)

    def test_nested_option_short_answer_still_wrong(self):
        """Le miroir du cas précédent : répondre « Red » quand il faut « Dark Red »."""
        ok, rule, _ = match("Red", "Dark Red", ["Red", "Blue"], MCQ)
        assert (ok, rule) == (False, RULE_OPTION)

    def test_word_boundaries_on_numbers(self):
        """« 1979 » ne doit pas être trouvé dans « 11979 »."""
        ok, _, _ = match("11979", "1979", ["1984", "1972"], MCQ)
        assert ok is False

    def test_word_boundaries_on_words(self):
        """« Art » ne doit pas matcher dans « Bart »."""
        ok, _, _ = match("Bart", "Art", ["Science"], MCQ)
        assert ok is False


class TestFuzzy:
    def test_typo_accepted(self):
        ok, rule, _ = match("Leonardo da Vinchi", "Leonardo da Vinci", ["Picasso"], MCQ)
        assert (ok, rule) == (True, RULE_FUZZY)

    def test_different_answer_rejected(self):
        ok, rule, _ = match("Vincent van Gogh", "Leonardo da Vinci", ["Picasso"], MCQ)
        assert (ok, rule) == (False, RULE_NONE)


class TestDegenerate:
    def test_empty_answer(self):
        ok, rule, _ = match("", "Paris", ["Lyon"], MCQ)
        assert (ok, rule) == (False, RULE_NONE)

    def test_whitespace_only(self):
        ok, rule, _ = match("   \n  ", "Paris", ["Lyon"], MCQ)
        assert (ok, rule) == (False, RULE_NONE)

    def test_normalized_answer_is_returned(self):
        _, _, normalized = match("  PARIS!  ", "Paris", ["Lyon"], MCQ)
        assert normalized == "paris"


class TestLetter:
    """Règle `letter` : la réponse est l'indice d'une option, pas son texte.

    Ces tests portent sur la version `v4_letter`, où la sortie du modèle est
    contrainte par une grammaire côté moteur. La règle reste tolérante aux
    formes bavardes pour rester utilisable si la contrainte est désactivée.
    """

    OPTIONS = ["Lyon", "Paris", "Marseille", "Nice"]  # la bonne est en B

    def test_correct_letter(self):
        ok, rule, chosen = match_letter("B", "Paris", self.OPTIONS)
        assert (ok, rule, chosen) == (True, RULE_LETTER, "Paris")

    def test_wrong_letter(self):
        ok, rule, chosen = match_letter("A", "Paris", self.OPTIONS)
        assert (ok, rule, chosen) == (False, RULE_LETTER, "Lyon")

    def test_lowercase(self):
        ok, _, _ = match_letter("b", "Paris", self.OPTIONS)
        assert ok is True

    def test_verbose_form_still_parsed(self):
        """La grammaire l'empêche, mais la règle doit rester robuste sans elle."""
        for said in ["B) Paris", "B. Paris", "(B)", " B "]:
            ok, rule, _ = match_letter(said, "Paris", self.OPTIONS)
            assert (ok, rule) == (True, RULE_LETTER), said

    def test_letter_out_of_range(self):
        """« E » désigne une option qui n'existe pas : on ne devine pas."""
        ok, rule, _ = match_letter("E", "Paris", self.OPTIONS)
        assert (ok, rule) == (False, RULE_NONE)

    def test_empty_answer(self):
        ok, rule, _ = match_letter("", "Paris", self.OPTIONS)
        assert (ok, rule) == (False, RULE_NONE)

    def test_boolean_two_options(self):
        ok, _, chosen = match_letter("A", "True", ["True", "False"])
        assert (ok, chosen) == (True, "True")


class TestLetterGrammar:
    def test_domain_matches_option_count(self):
        assert letter_grammar(4) == "root ::= [A-D]"
        assert letter_grammar(2) == "root ::= [A-B]"

    def test_rejects_impossible_counts(self):
        with pytest.raises(ValueError):
            letter_grammar(1)
        with pytest.raises(ValueError):
            letter_grammar(99)


class TestLetterPrompt:
    def test_options_are_lettered_and_deterministic(self):
        row = {
            "question": "Capital of France?",
            "correct_answer": "Paris",
            "incorrect_answers": ["Lyon", "Marseille", "Nice"],
            "question_id": "q1",
        }
        first = build_prompt(row, "v4_letter")
        assert first == build_prompt(row, "v4_letter"), "l'ordre doit être reproductible"
        for letter in "ABCD":
            assert f"\n{letter}. " in first

    def test_letter_order_matches_matching(self):
        """Le prompt et le matching doivent voir exactement le même ordre.

        C'est l'invariant central de la règle `letter` : si les deux mélanges
        divergeaient, chaque réponse serait évaluée contre la mauvaise option
        et le benchmark serait faux sans rien signaler.
        """
        row = {
            "question": "Capital of France?",
            "correct_answer": "Paris",
            "incorrect_answers": ["Lyon", "Marseille", "Nice"],
            "question_id": "q1",
        }
        options = shuffled_options(
            row["correct_answer"], row["incorrect_answers"], row["question_id"]
        )
        prompt = build_prompt(row, "v4_letter")
        good_letter = "ABCD"[options.index("Paris")]
        assert f"{good_letter}. Paris" in prompt
        ok, _, _ = match_letter(good_letter, "Paris", options)
        assert ok is True
