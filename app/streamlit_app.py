"""Rapport de benchmark interactif — point d'entrée de l'application.

L'application **lit** la couche gold, elle ne calcule rien. Toute métrique
affichée provient d'une table `mart_*` construite et testée par dbt. Deux
conséquences pratiques : les chiffres affichés sont exactement ceux que
`dbt test` a validés, et l'application reste rapide quel que soit le volume de la
couche silver.

Entrée unique plutôt que le répertoire `pages/` de Streamlit : la barre latérale
de filtres doit être construite une fois et son état survivre à la navigation.
"""

from __future__ import annotations

import streamlit as st

import filters
from data_access import database_is_available, missing_database_message
from views import (
    categories,
    difficulty,
    explorer,
    latency,
    methodology,
    overview,
    prompt_impact,
    reliability,
)

# Le chemin d'URL est explicite : les sept vues exposent toutes une fonction
# nommée `render`, dont Streamlit déduirait le même pathname pour chacune.
PAGES = [
    # La méthodologie ouvre la navigation : les chiffres des pages suivantes ne
    # sont pas interprétables sans le protocole qui les a produits ni les limites
    # qui les bornent.
    ("Méthodologie et limites", "📐", "methodologie", methodology.render),
    ("Vue d'ensemble", "📊", "vue-ensemble", overview.render),
    ("Par catégorie", "🗂️", "categories", categories.render),
    ("Par difficulté", "🎚️", "difficulte", difficulty.render),
    ("Temps de réponse", "⏱️", "latence", latency.render),
    ("Impact du prompt", "✍️", "prompt", prompt_impact.render),
    ("Explorateur de réponses", "🔍", "explorateur", explorer.render),
    ("Fiabilité", "🧪", "fiabilite", reliability.render),
]


def main() -> None:
    st.set_page_config(
        page_title="Benchmark de LLM — culture générale",
        page_icon="📊",
        layout="wide",
    )

    if not database_is_available():
        missing_database_message()
        return

    filters.render_sidebar()
    _sidebar_footer()

    navigation = st.navigation(
        [
            st.Page(render, title=title, icon=icon, url_path=path, default=index == 0)
            for index, (title, icon, path, render) in enumerate(PAGES)
        ]
    )
    navigation.run()


def _sidebar_footer() -> None:
    st.sidebar.divider()
    st.sidebar.caption(
        "Tous les chiffres proviennent de tables `mart_*` construites par dbt et "
        "validées par `dbt test`. L'application ne calcule aucune agrégation."
    )
    with st.sidebar.expander("Comment lire les taux"):
        st.markdown(
            "- Un taux ne se lit **jamais** sans sa **ligne de hasard** "
            "(1/nombre de choix) : 30 % sur un QCM à 4 options est un échec, "
            "pas un résultat moyen.\n"
            "- Les **barres d'erreur** portent l'intervalle de Wald à 95 %. Deux "
            "modèles dont les intervalles se recouvrent ne sont pas départagés.\n"
            "- Les axes de pourcentage sont bornés à 0–100 % : un axe tronqué "
            "exagérerait les écarts.\n"
            "- En deçà de 30 observations, aucun taux n'est publié.\n"
            "- Les trois **formats de tâche** ne se comparent pas entre eux."
        )


main()
