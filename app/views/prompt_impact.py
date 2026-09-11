"""Impact du prompt — la formulation change-t-elle le résultat ?"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import filters
from charts import accuracy_figure, sample_caption
from data_access import load
from theme import FORMAT_FAMILY_NOTES, color_for, format_family_label
from trivia_bench.enrich.prompts import LETTER_VERSIONS, MCQ_VERSIONS, PROMPTS


def render() -> None:
    st.title("Impact du prompt")

    st.info(
        "Les taux de cette page sont calculés sur les **questions communes** à "
        "toutes les versions de prompt d'un même modèle. Sans cette restriction, "
        "une version évaluée sur un sous-ensemble plus facile paraîtrait meilleure "
        "alors qu'elle n'aurait pas été testée sur les mêmes questions."
    )

    data, ignored = filters.apply(load("mart_prompt_impact"))
    filters.report_ignored(ignored)

    if data.empty:
        filters.empty_state()
        return

    _accuracy(data)
    st.divider()
    _answer_length(data)
    st.divider()
    _catalogue()


def _accuracy(data) -> None:
    """Taux par version, à modèle constant et par format de tâche."""
    st.subheader("Taux de bonnes réponses par version")

    for family, group in data.groupby("format_family", sort=False):
        st.markdown(f"**{format_family_label(family)}**")
        note = FORMAT_FAMILY_NOTES.get(family)
        if note:
            st.caption(note)

        group = group.sort_values(["model", "accuracy_pct"]).copy()
        group["label"] = group["model"] + " · " + group["prompt_version"]
        st.plotly_chart(accuracy_figure(group, "label"), use_container_width=True)
        sample_caption(group)


def _answer_length(data) -> None:
    """Longueur moyenne des réponses : la mesure directe de l'effet « consigne ».

    C'est précisément ce que la consigne de format cherche à contraindre, donc la
    variable sur laquelle son effet se lit sans ambiguïté — contrairement au taux
    de bonnes réponses, qui mêle l'effet de la consigne et celui du matching.
    """
    st.subheader("Longueur des réponses")

    data = data.copy()
    data["label"] = data["model"] + " · " + data["prompt_version"]
    data = data.sort_values("avg_answer_length")

    fig = go.Figure(
        go.Bar(
            y=data["label"],
            x=data["avg_answer_length"],
            orientation="h",
            marker_color=[color_for(m) for m in data["model"]],
            customdata=data[["accuracy_pct", "n_questions"]],
            hovertemplate=(
                "<b>%{y}</b><br>Longueur moyenne : %{x:.1f} caractères<br>"
                "Taux : %{customdata[0]:.2f} %<br>n = %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title="Longueur moyenne de la réponse (caractères)", rangemode="tozero")
    fig.update_layout(
        height=max(260, 42 * len(data) + 120),
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Une consigne de format agit d'abord ici : elle raccourcit la réponse. "
        "Sans consigne (`v1`), le modèle répond par une phrase, que le matching "
        "doit ensuite interpréter."
    )


def _catalogue() -> None:
    """Texte intégral des prompts.

    Le lecteur doit pouvoir juger la formulation, pas seulement son identifiant :
    l'effet mesuré n'est interprétable qu'en regard de ce qui a été demandé au
    modèle. Le texte est lu depuis `enrich/prompts.py`, source unique — le
    recopier ici le ferait diverger silencieusement du texte réellement envoyé.
    """
    st.subheader("Texte des prompts")
    st.caption(
        "Lu directement depuis `src/trivia_bench/enrich/prompts.py`, le catalogue "
        "qui a produit les réponses."
    )

    for version, template in PROMPTS.items():
        marques = []
        if version in MCQ_VERSIONS:
            marques.append("options fournies")
        if version in LETTER_VERSIONS:
            marques.append("sortie contrainte par grammaire à une lettre")
        suffixe = f" — {', '.join(marques)}" if marques else " — génération libre"

        with st.expander(f"`{version}`{suffixe}"):
            st.code(template, language="text")
            if version in LETTER_VERSIONS:
                st.caption(
                    "`{options}` est remplacé par les options étiquetées A/B/C/D, "
                    "mélangées de façon déterministe à partir du `question_id`."
                )
            elif version in MCQ_VERSIONS:
                st.caption("`{options}` est remplacé par la liste des options mélangées.")
