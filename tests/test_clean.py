"""Tests du nettoyage bronze → silver.

Ces tests portent sur ce qui casserait silencieusement le pipeline aval : un
`question_id` instable rendrait l'enrichissement non reprenable, et un décodage
incomplet ferait comparer au modèle une chaîne différente de celle affichée.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from trivia_bench.silver.clean import (
    clean,
    decode,
    make_question_id,
    parse_incorrect_answers,
    split_category,
)


class TestDecode:
    def test_url3986(self):
        assert decode("When%20was%20Hubba%20Bubba%20first%20introduced%3F") == (
            "When was Hubba Bubba first introduced?"
        )

    def test_html_entities(self):
        """La base contient des entités HTML en dur, indépendamment du transport."""
        assert decode("Don%27t%20forget%20%26amp%3B%20this") == "Don't forget & this"

    def test_accents_and_unicode(self):
        assert decode("Qui%20a%20peint%20la%20Joconde%20%3A%20L%C3%A9onard%20%3F") == (
            "Qui a peint la Joconde : Léonard ?"
        )

    def test_whitespace_collapsed(self):
        assert decode("trop%20%20%20d%27espaces%20") == "trop d'espaces"

    def test_non_string_is_safe(self):
        assert decode(None) == ""
        assert decode(float("nan")) == ""


class TestQuestionId:
    def test_deterministic(self):
        """Le déterminisme porte la reprise de l'enrichissement."""
        a = make_question_id("Who painted the Mona Lisa?", "Leonardo da Vinci")
        b = make_question_id("Who painted the Mona Lisa?", "Leonardo da Vinci")
        assert a == b

    def test_answer_changes_id(self):
        a = make_question_id("Same question", "Answer A")
        b = make_question_id("Same question", "Answer B")
        assert a != b

    def test_separator_prevents_collision(self):
        """Sans séparateur, « ab » + « c » et « a » + « bc » donneraient le même hash."""
        assert make_question_id("ab", "c") != make_question_id("a", "bc")


class TestParseIncorrectAnswers:
    def test_decodes_each_item(self):
        raw = json.dumps(["Pablo%20Picasso", "Claude%20Monet"])
        assert parse_incorrect_answers(raw) == ["Pablo Picasso", "Claude Monet"]

    def test_malformed_json_is_empty(self):
        assert parse_incorrect_answers("pas du json") == []

    def test_empty_input(self):
        assert parse_incorrect_answers("") == []


class TestSplitCategory:
    @pytest.mark.parametrize(
        ("category", "expected"),
        [
            ("Entertainment: Video Games", "Entertainment"),
            ("Science: Computers", "Science"),
            ("General Knowledge", "General Knowledge"),
            ("Science & Nature", "Science & Nature"),
        ],
    )
    def test_group(self, category, expected):
        assert split_category(category) == expected


def _bronze_row(**overrides) -> dict:
    row = {
        "category": "Entertainment%3A%20Video%20Games",
        "type": "multiple",
        "difficulty": "easy",
        "question": "What%20year%3F",
        "correct_answer": "1999",
        "incorrect_answers": json.dumps(["1998", "2000", "2001"]),
        "fetched_at": "2026-09-10T09:00:00+00:00",
        "source_category_id": 15,
    }
    row.update(overrides)
    return row


class TestClean:
    def test_schema_and_types(self):
        df = clean(pd.DataFrame([_bronze_row()]))
        assert list(df.columns) == [
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
        row = df.iloc[0]
        assert row["category"] == "Entertainment: Video Games"
        assert row["category_group"] == "Entertainment"
        assert row["question"] == "What year?"
        assert row["n_choices"] == 4
        assert row["question_length"] == len("What year?")

    def test_boolean_question_has_two_choices(self):
        row = _bronze_row(
            type="boolean", correct_answer="True", incorrect_answers=json.dumps(["False"])
        )
        df = clean(pd.DataFrame([row]))
        assert df.iloc[0]["n_choices"] == 2

    def test_deduplicates_across_categories(self):
        """Une même question servie dans deux catégories ne doit compter qu'une fois."""
        rows = [
            _bronze_row(source_category_id=15),
            _bronze_row(category="General%20Knowledge", source_category_id=9),
        ]
        df = clean(pd.DataFrame(rows))
        assert len(df) == 1
        assert df.attrs["duplicates_removed"] == 1

    def test_question_ids_are_unique(self):
        rows = [_bronze_row(question=f"Question%20{i}%3F") for i in range(20)]
        df = clean(pd.DataFrame(rows))
        assert df["question_id"].is_unique
