"""Fiabilité — le benchmark mesure-t-il ce qu'il prétend mesurer ?

Deux questions y sont traitées, toutes deux exploratoires au sens de
`docs/06` §2 : quelle règle de matching a statué, et les questions ratées par
tous les modèles se regroupent-elles par thème.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import filters
from data_access import load
from theme import MIN_SAMPLE, color_for, format_family_label

RULE_ORDER = ["exact", "boolean", "option_substring", "fuzzy", "letter", "none"]

RULE_HELP = {
    "exact": "Égalité après normalisation.",
    "boolean": "Reconnaissance de true/false, yes/no sur les questions vrai-faux.",
    "option_substring": "Une option retrouvée dans la phrase, aux frontières de mots.",
    "fuzzy": "Similarité ≥ 0,90, pour les fautes de frappe.",
    "letter": "Lettre contrainte par grammaire, puis index vers l'option. Sans interprétation.",
    "none": "Aucune règle n'a reconnu la réponse : comptée fausse.",
}


def render() -> None:
    st.title("Fiabilité")

    _matching()
    st.divider()
    _agreement()


def _matching() -> None:
    """Répartition des verdicts par règle de la cascade.

    `none` est la ligne à surveiller : ces réponses sont comptées fausses sans
    qu'aucune règle n'ait rien reconnu. Un taux de `none` élevé ne dit pas que le
    modèle a échoué, il dit que le benchmark n'a pas su trancher — et il tranche
    alors contre le modèle.
    """
    st.subheader("Quelle règle a statué ?")

    data, ignored = filters.apply(load("mart_matching_reliability"))
    filters.report_ignored(ignored)

    if data.empty:
        filters.empty_state()
        return

    data = data.copy()
    data["label"] = data["model"] + " · " + data["prompt_version"]
    order = [r for r in RULE_ORDER if r in set(data["match_rule"])]

    fig = go.Figure()
    for rule in order:
        subset = data[data["match_rule"] == rule]
        fig.add_trace(
            go.Bar(
                y=subset["label"],
                x=subset["pct_of_answers"],
                orientation="h",
                name=rule,
                customdata=subset[["n_answers", "n_correct", "pct_correct_within_rule"]],
                hovertemplate=(
                    f"<b>%{{y}}</b> — {rule}<br>"
                    "%{x:.2f} % des réponses<br>"
                    "%{customdata[1]} correctes sur %{customdata[0]} "
                    "(%{customdata[2]:.1f} %)<extra></extra>"
                ),
            )
        )

    fig.update_xaxes(range=[0, 100], title="Part des réponses (%)", ticksuffix=" %")
    fig.update_layout(
        barmode="stack",
        height=max(300, 42 * data["label"].nunique() + 150),
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("\n".join(f"- **`{rule}`** — {RULE_HELP[rule]}" for rule in order))

    none_share = data[data["match_rule"] == "none"]
    if not none_share.empty:
        worst = none_share.loc[none_share["pct_of_answers"].idxmax()]
        st.warning(
            f"Jusqu'à **{worst['pct_of_answers']:.1f} %** des réponses "
            f"({worst['model']} · {worst['prompt_version']}) sont comptées fausses "
            "sans qu'aucune règle n'ait rien reconnu. Ce taux borne la "
            "sous-estimation possible : chacune de ces réponses est peut-être "
            "correcte mais formulée autrement. C'est ce que l'annotation manuelle "
            "doit chiffrer."
        )


def _agreement() -> None:
    """Les échecs se regroupent-ils par thème ?

    Un taux élevé de questions ratées par tous les modèles sur un thème ne dit pas
    seulement que les modèles l'ignorent : c'est aussi là que se voient les
    défauts du dataset source — énoncés ambigus, réponses datées, étiquetage
    douteux.
    """
    st.subheader("Questions ratées par tous les modèles")

    data, ignored = filters.apply(load("mart_answer_agreement"))
    filters.report_ignored(ignored)

    if data.empty:
        st.info(
            "Aucun groupe de catégories n'atteint "
            f"{MIN_SAMPLE} questions posées à tous les modèles avec les filtres actuels."
        )
        return

    prompts = sorted(data["prompt_version"].unique())
    chosen = st.selectbox("Version de prompt", prompts, key="reliability_prompt")
    subset = data[data["prompt_version"] == chosen].sort_values("pct_missed_by_all")

    if subset.empty:
        filters.empty_state()
        return

    family = subset["format_family"].iloc[0]
    n_models = int(subset["n_models"].max())
    st.caption(
        f"Format : {format_family_label(family)}. Accord calculé sur {n_models} "
        "modèle(s), uniquement sur les questions posées à tous."
    )

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=subset["category_group"],
            x=subset["pct_missed_by_all"],
            orientation="h",
            name="Ratées par tous",
            marker_color="#E45756",
            customdata=subset[["n_missed_by_all", "n_questions"]],
            hovertemplate=(
                "<b>%{y}</b><br>Ratées par tous : %{x:.2f} %<br>"
                "%{customdata[0]} sur %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Bar(
            y=subset["category_group"],
            x=subset["pct_solved_by_all"],
            orientation="h",
            name="Réussies par tous",
            marker_color=color_for("gemma-3-4b"),
            customdata=subset[["n_solved_by_all", "n_questions"]],
            hovertemplate=(
                "<b>%{y}</b><br>Réussies par tous : %{x:.2f} %<br>"
                "%{customdata[0]} sur %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(range=[0, 100], title="Part des questions (%)", ticksuffix=" %")
    fig.update_layout(
        barmode="group",
        height=max(300, 44 * len(subset) + 150),
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"n de {int(subset['n_questions'].min())} à {int(subset['n_questions'].max())} "
        f"par groupe. Les groupes sous {MIN_SAMPLE} questions ne sont pas construits "
        "par dbt. Un groupe très « raté par tous » mérite d'être inspecté dans "
        "l'explorateur avant d'en conclure quoi que ce soit sur les modèles."
    )
