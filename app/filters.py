"""Filtres transversaux de la barre latérale.

Filtrer, trier et mettre en forme sont les seules opérations autorisées côté
application : toute agrégation appartient à dbt. Ce module ne fait donc que
restreindre des lignes déjà agrégées.

Son état vit dans `st.session_state`, ce qui lui permet de survivre à la
navigation entre pages.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from data_access import load
from theme import FORMAT_FAMILY_LABELS

# Clé d'état -> colonne filtrée dans les DataFrames.
FILTERS: dict[str, str] = {
    "f_models": "model",
    "f_prompts": "prompt_version",
    "f_families": "format_family",
    "f_groups": "category_group",
    "f_difficulties": "difficulty",
    "f_types": "question_type",
}

LABELS = {
    "model": "modèle",
    "prompt_version": "version de prompt",
    "format_family": "format de tâche",
    "category_group": "groupe de catégories",
    "difficulty": "difficulté",
    "question_type": "type de question",
}

DIFFICULTY_ORDER = ["easy", "medium", "hard"]


def _multiselect(key: str, label: str, options: list, default_all: bool = True) -> None:
    if key not in st.session_state:
        st.session_state[key] = list(options) if default_all else []
    st.sidebar.multiselect(label, options=options, key=key)


def render_sidebar() -> None:
    """Construit la barre latérale à partir des valeurs réellement présentes.

    Les options sont lues dans `fct_answers` plutôt que codées en dur : un modèle
    ou une version de prompt ajoutés au benchmark apparaissent alors sans toucher
    à l'application.
    """
    facts = load("fct_answers")

    st.sidebar.header("Filtres")

    _multiselect("f_models", "Modèles", sorted(facts["model"].unique()))
    _multiselect("f_prompts", "Versions de prompt", sorted(facts["prompt_version"].unique()))

    families = [f for f in FORMAT_FAMILY_LABELS if f in set(facts["format_family"])]
    _multiselect("f_families", "Formats de tâche", families)

    _multiselect("f_groups", "Groupes de catégories", sorted(facts["category_group"].unique()))

    difficulties = [d for d in DIFFICULTY_ORDER if d in set(facts["difficulty"])]
    _multiselect("f_difficulties", "Difficultés", difficulties)

    _multiselect("f_types", "Types de question", sorted(facts["question_type"].unique()))

    if st.sidebar.button("Réinitialiser les filtres", use_container_width=True):
        for key in FILTERS:
            st.session_state.pop(key, None)
        st.rerun()


def apply(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Applique les filtres pertinents et **signale ceux qui ne le sont pas**.

    Un mart agrégé au modèle ne porte pas de colonne `category_group` : le filtre
    correspondant n'a alors rien à restreindre. Le passer sous silence laisserait
    croire que les chiffres affichés portent sur la sélection, alors qu'ils
    portent sur tout. Les filtres inapplicables sont donc retournés, à charge
    pour la vue de les afficher.
    """
    ignored: list[str] = []
    out = df

    for key, column in FILTERS.items():
        selected = st.session_state.get(key)
        if selected is None:
            continue
        if column not in df.columns:
            # Le filtre n'est « ignoré » que s'il restreint réellement quelque chose.
            if _is_restrictive(key, column):
                ignored.append(LABELS[column])
            continue
        out = out[out[column].isin(selected)]

    return out, ignored


def _is_restrictive(key: str, column: str) -> bool:
    """Vrai si l'utilisateur a réduit la sélection par rapport à tout le jeu."""
    selected = set(st.session_state.get(key) or [])
    available = set(load("fct_answers")[column].unique())
    return bool(selected) and selected != available


def report_ignored(ignored: list[str]) -> None:
    if ignored:
        st.info(
            "Filtres sans effet sur cette page, faute de colonne correspondante "
            f"dans la table lue : {', '.join(ignored)}. Les chiffres affichés "
            "portent donc sur l'ensemble."
        )


def empty_state() -> None:
    st.warning("Aucune ligne ne correspond aux filtres sélectionnés.")
