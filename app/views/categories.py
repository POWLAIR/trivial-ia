"""Par catégorie — sur quels thèmes les modèles échouent-ils ?"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import filters
from charts import accuracy_figure, sample_caption
from data_access import load
from theme import MIN_SAMPLE, format_family_label

GRAINS = {
    "Groupe de catégories": ("mart_performance_by_category_group", "category_group"),
    "Catégorie détaillée": ("mart_performance_by_category", "category"),
}


def render() -> None:
    st.title("Par catégorie")

    grain = st.radio(
        "Niveau d'agrégation",
        options=list(GRAINS),
        horizontal=True,
        key="categories_grain",
        help=(
            "Les deux niveaux sont deux tables gold distinctes : l'application "
            "n'agrège rien elle-même."
        ),
    )
    table, dim = GRAINS[grain]

    data, ignored = filters.apply(load(table))
    filters.report_ignored(ignored)

    st.caption(
        f"Seules les combinaisons reposant sur au moins {MIN_SAMPLE} questions sont "
        "construites par dbt : en deçà, l'intervalle de confiance est trop large "
        "pour conclure."
    )

    if data.empty:
        filters.empty_state()
        return

    _heatmap(data, dim)
    st.divider()
    _extremes(data, dim)


def _heatmap(data, dim: str) -> None:
    """Carte de chaleur catégorie × (modèle · prompt).

    L'échelle est fixée à `[0, 100]` : une échelle recalée sur les valeurs
    présentes ferait passer un écart de trois points pour un contraste franc.
    """
    st.subheader("Carte de chaleur")

    data = data.copy()
    data["colonne"] = data["model"] + " · " + data["prompt_version"]
    pivot = data.pivot_table(index=dim, columns="colonne", values="accuracy_pct")

    if pivot.empty:
        st.info("Pas assez de données pour cette carte avec les filtres actuels.")
        return

    counts = data.pivot_table(index=dim, columns="colonne", values="n_questions")

    fig = go.Figure(
        go.Heatmap(
            z=pivot.to_numpy(),
            x=list(pivot.columns),
            y=list(pivot.index),
            zmin=0,
            zmax=100,
            colorscale="RdYlGn",
            colorbar={"title": "% bonnes<br>réponses", "ticksuffix": " %"},
            customdata=counts.to_numpy(),
            hovertemplate=(
                "<b>%{y}</b><br>%{x}<br>Taux : %{z:.2f} %<br>n = %{customdata}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        height=max(320, 30 * len(pivot) + 180),
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        xaxis={"tickangle": -30},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Cases vides : moins de {MIN_SAMPLE} questions pour cette combinaison, "
        "donc non publiable. Échelle fixée à 0–100 % — une échelle ajustée aux "
        "valeurs présentes exagérerait les contrastes."
    )


def _extremes(data, dim: str) -> None:
    """Catégories les mieux et les moins bien traitées, à combinaison choisie.

    Le classement se fait à modèle et prompt constants : mélanger les
    combinaisons ferait remonter les catégories testées sous le format le plus
    facile, pas les plus faciles.
    """
    st.subheader("Catégories les mieux et les moins bien traitées")

    data = data.copy()
    data["combinaison"] = data["model"] + " · " + data["prompt_version"]
    choices = sorted(data["combinaison"].unique())
    chosen = st.selectbox("Combinaison modèle · prompt", choices, key="categories_combo")

    subset = data[data["combinaison"] == chosen].copy()
    if subset.empty:
        filters.empty_state()
        return

    family = subset["format_family"].iloc[0]
    st.caption(f"Format de tâche : {format_family_label(family)}.")

    subset = subset.sort_values("accuracy_pct", ascending=True)
    st.plotly_chart(accuracy_figure(subset, dim), use_container_width=True)
    sample_caption(subset)
