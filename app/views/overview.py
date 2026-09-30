"""Vue d'ensemble — quel modèle, avec quel prompt, répond le mieux ?"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import filters
from charts import accuracy_figure, chance_verdict, sample_caption, separable, takeaway
from data_access import load
from theme import FORMAT_FAMILY_NOTES, color_for, format_family_label


def render() -> None:
    st.title("Vue d'ensemble")

    perf, ignored = filters.apply(load("mart_model_performance"))
    filters.report_ignored(ignored)

    if perf.empty:
        filters.empty_state()
        return

    _headline(perf)
    st.divider()
    _ranking(perf)
    st.divider()
    _tradeoff(perf)


def _headline(perf) -> None:
    """Bandeau d'indicateurs.

    Le meilleur taux est annoncé avec son format de tâche : « 63 % » ne veut rien
    dire si l'on ignore que les options étaient fournies.
    """
    best = perf.loc[perf["accuracy_pct"].idxmax()]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Questions posées", f"{int(perf['n_questions'].max()):,}".replace(",", " "))
    c2.metric("Modèles évalués", perf["model"].nunique())
    c3.metric(
        "Meilleur taux",
        f"{best['accuracy_pct']:.1f} %",
        delta=f"{best['accuracy_pct'] - best['random_baseline_pct']:+.1f} pts vs hasard",
    )
    c4.metric("Temps de réponse médian", f"{perf['median_response_time'].median():.2f} s")

    st.caption(
        f"Meilleur taux : **{best['model']}** avec **{best['prompt_version']}** "
        f"({format_family_label(best['format_family'])}), "
        f"± {best['ci95_margin_pct']:.2f} pts à 95 % sur {int(best['n_questions'])} questions."
    )


def _ranking(perf) -> None:
    """Classement, une section par format de tâche.

    Les trois formats ne partagent jamais un même classement : fournir les
    options transforme la tâche, et les mettre côte à côte reviendrait à déclarer
    un vainqueur entre deux épreuves différentes.
    """
    st.subheader("Classement des modèles")

    for family, group in perf.groupby("format_family", sort=False):
        st.markdown(f"**{format_family_label(family)}**")
        note = FORMAT_FAMILY_NOTES.get(family)
        if note:
            st.caption(note)

        group = group.sort_values("accuracy_pct", ascending=True).copy()
        group["label"] = group["model"] + " · " + group["prompt_version"]
        st.plotly_chart(accuracy_figure(group, "label"), use_container_width=True)
        sample_caption(group)
        takeaway(_ranking_lines(group))


def _ranking_lines(group) -> list[str]:
    """Le meilleur d'un format, et s'il se distingue vraiment du suivant."""
    best = group.iloc[-1]
    gap = best["accuracy_pct"] - best["random_baseline_pct"]
    lines = [
        f"`{best['label']}` arrive en tête avec **{best['accuracy_pct']:.1f} %**, "
        f"soit {gap:+.1f} pts par rapport au hasard ({best['random_baseline_pct']:.1f} %)."
    ]
    verdict = chance_verdict(best, "cette combinaison")
    if verdict:
        lines.append(verdict)
        return lines
    if len(group) > 1:
        second = group.iloc[-2]
        if separable(best, second):
            lines.append(f"Son avance sur `{second['label']}` dépasse la marge d'erreur.")
        else:
            lines.append(
                f"Il n'est pas départageable de `{second['label']}` à cet effectif : "
                "les intervalles de confiance se recouvrent."
            )
    return lines


def _tradeoff(perf) -> None:
    """Précision contre temps de réponse : le compromis qualité / coût."""
    st.subheader("Précision et temps de réponse")

    fig = go.Figure()
    for family, group in perf.groupby("format_family", sort=False):
        fig.add_trace(
            go.Scatter(
                x=group["median_response_time"],
                y=group["accuracy_pct"],
                mode="markers+text",
                text=group["prompt_version"],
                textposition="top center",
                marker={
                    "size": 14,
                    "color": [color_for(m) for m in group["model"]],
                    "symbol": ["circle", "diamond", "square"][
                        list(perf["format_family"].unique()).index(family) % 3
                    ],
                    "line": {"width": 1, "color": "#333333"},
                },
                name=format_family_label(family),
                customdata=group[["model", "n_questions", "ci95_margin_pct"]],
                hovertemplate=(
                    "<b>%{customdata[0]}</b> — %{text}<br>"
                    "Taux : %{y:.2f} % (± %{customdata[2]:.2f})<br>"
                    "Temps médian : %{x:.2f} s<br>"
                    "n = %{customdata[1]}<extra></extra>"
                ),
            )
        )

    fig.update_yaxes(range=[0, 100], title="Taux de bonnes réponses (%)", ticksuffix=" %")
    fig.update_xaxes(title="Temps de réponse médian (s)", rangemode="tozero")
    fig.update_layout(
        height=460,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Couleur : modèle. Forme : format de tâche. En haut à gauche, le meilleur "
        "compromis — précis et rapide."
    )
    takeaway(_tradeoff_lines(perf))


def _tradeoff_lines(perf) -> list[str]:
    """Par format, ce que coûte en temps le gain de justesse du plus précis."""
    lines = []
    for family, group in perf.groupby("format_family", sort=False):
        best = group.loc[group["accuracy_pct"].idxmax()]
        fastest = group.loc[group["median_response_time"].idxmin()]
        if best.name == fastest.name:
            lines.append(
                f"{format_family_label(family)} : `{best['model']}` · "
                f"`{best['prompt_version']}` est à la fois le plus précis et le plus rapide."
            )
            continue
        ratio = best["median_response_time"] / fastest["median_response_time"]
        lines.append(
            f"{format_family_label(family)} : le plus précis (`{best['model']}` · "
            f"`{best['prompt_version']}`) répond **{ratio:.1f}×** plus lentement que "
            f"le plus rapide (`{fastest['model']}` · `{fastest['prompt_version']}`), pour "
            f"{best['accuracy_pct'] - fastest['accuracy_pct']:+.1f} pts."
        )
    return lines
