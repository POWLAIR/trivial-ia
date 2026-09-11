"""Par difficulté — l'étiquette OpenTDB discrimine-t-elle vraiment ?"""

from __future__ import annotations

import streamlit as st

import filters
from charts import grouped_accuracy_figure, sample_caption
from data_access import load
from filters import DIFFICULTY_ORDER
from theme import format_family_label


def render() -> None:
    st.title("Par difficulté")

    data, ignored = filters.apply(load("mart_performance_by_difficulty"))
    filters.report_ignored(ignored)

    if data.empty:
        filters.empty_state()
        return

    _inversions(data)
    st.divider()

    for family, group in data.groupby("format_family", sort=False):
        st.subheader(format_family_label(family))
        order = [d for d in DIFFICULTY_ORDER if d in set(group["difficulty"])]

        for prompt, prompt_group in group.groupby("prompt_version", sort=False):
            st.markdown(f"**{prompt}**")
            st.plotly_chart(
                grouped_accuracy_figure(prompt_group, "difficulty", order),
                use_container_width=True,
            )
            sample_caption(prompt_group)


def _inversions(data) -> None:
    """Signale explicitement les ruptures de monotonie.

    Le score devrait décroître de `easy` à `hard`. Une inversion n'est pas un
    détail de présentation à lisser : c'est soit le matching, soit l'étiquetage
    de la source qu'elle met en cause. La masquer produirait un dashboard
    d'apparence propre reposant sur une hypothèse fausse.

    La détection vient de la colonne `has_inversion` calculée par dbt — comparer
    des agrégats entre eux n'est pas le rôle de l'application.
    """
    flagged = (
        data[data["has_inversion"]][["model", "prompt_version"]]
        .drop_duplicates()
        .sort_values(["model", "prompt_version"])
    )
    total = data[["model", "prompt_version"]].drop_duplicates()

    if flagged.empty:
        st.success(
            "Aucune inversion : pour chaque combinaison affichée, le score décroît "
            "bien de `easy` à `hard`."
        )
        return

    st.warning(
        f"**Inversion de monotonie sur {len(flagged)} combinaison(s) sur {len(total)}.** "
        "Le score devrait décroître avec la difficulté déclarée ; ce n'est pas le cas "
        "ici. Deux explications possibles, qu'il faut départager avant de conclure "
        "quoi que ce soit de ces étiquettes : le matching se trompe davantage sur "
        "certaines questions, ou la difficulté attribuée par les contributeurs "
        "d'OpenTDB n'est pas calibrée."
    )

    detail = flagged.copy()
    detail.columns = ["Modèle", "Version de prompt"]
    st.dataframe(detail, hide_index=True, use_container_width=True)

    st.caption(
        "Le cas rencontré est `medium` < `hard`, et non `hard` > `easy` : les "
        "questions étiquetées « moyennes » sont moins bien réussies que les "
        "« difficiles ». Noter que `hard` repose sur un effectif nettement plus "
        "petit, donc sur un intervalle de confiance plus large — voir les barres "
        "d'erreur ci-dessous avant de conclure."
    )
