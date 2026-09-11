"""Temps de réponse — quel est le coût en calcul de chaque combinaison ?"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import filters
from data_access import load
from theme import color_for, format_family_label


def render() -> None:
    st.title("Temps de réponse")

    data, ignored = filters.apply(load("mart_latency"))
    filters.report_ignored(ignored)

    if data.empty:
        filters.empty_state()
        return

    st.caption(
        "Mesures prises sur une seule machine (i7-8550U, 4 cœurs, sans GPU), un "
        "modèle résident à la fois et un seul worker. Elles ne sont comparables "
        "qu'entre elles."
    )

    _distribution(data)
    st.divider()
    _per_token(data)
    st.divider()
    _table(data)


def _distribution(data) -> None:
    """Médiane, p90 et p99 par combinaison.

    La médiane prime sur la moyenne : la distribution est asymétrique à droite,
    quelques réponses très lentes tirent la moyenne vers le haut. Les deux sont
    publiées, avec les percentiles hauts, pour que l'asymétrie soit visible plutôt
    que résumée.
    """
    st.subheader("Médiane et percentiles hauts")

    data = data.sort_values("median_response_time").copy()
    data["label"] = data["model"] + " · " + data["prompt_version"]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=data["label"],
            x=data["median_response_time"],
            orientation="h",
            marker_color=[color_for(m) for m in data["model"]],
            name="Médiane",
            customdata=data[["avg_response_time", "p90_response_time", "n_questions"]],
            hovertemplate=(
                "<b>%{y}</b><br>Médiane : %{x:.3f} s<br>"
                "Moyenne : %{customdata[0]:.3f} s<br>"
                "p90 : %{customdata[1]:.3f} s<br>"
                "n = %{customdata[2]}<extra></extra>"
            ),
        )
    )
    for column, symbol, label in [
        ("p90_response_time", "line-ns", "p90"),
        ("p99_response_time", "x-thin", "p99"),
    ]:
        fig.add_trace(
            go.Scatter(
                y=data["label"],
                x=data[column],
                mode="markers",
                marker={"symbol": symbol, "size": 14, "line": {"width": 2, "color": "#444444"}},
                name=label,
                hovertemplate=f"{label} : %{{x:.3f}} s<extra></extra>",
            )
        )

    fig.update_xaxes(title="Temps de réponse (s)", rangemode="tozero")
    fig.update_layout(
        height=max(260, 42 * len(data) + 130),
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    st.plotly_chart(fig, use_container_width=True)


def _per_token(data) -> None:
    """Temps par token généré : sépare la lenteur de la verbosité.

    Deux combinaisons peuvent afficher le même temps total pour des raisons
    opposées — l'une calcule lentement, l'autre parle beaucoup. Rapporter le
    temps au nombre de tokens produits les distingue.
    """
    st.subheader("Lenteur ou verbosité ?")

    data = data.copy()
    data["label"] = data["model"] + " · " + data["prompt_version"]

    fig = go.Figure()
    for family, group in data.groupby("format_family", sort=False):
        fig.add_trace(
            go.Scatter(
                x=group["avg_eval_tokens"],
                y=group["avg_time_per_token"],
                mode="markers+text",
                text=group["prompt_version"],
                textposition="top center",
                marker={
                    "size": 14,
                    "color": [color_for(m) for m in group["model"]],
                    "line": {"width": 1, "color": "#333333"},
                },
                name=format_family_label(family),
                customdata=group[["model", "median_response_time"]],
                hovertemplate=(
                    "<b>%{customdata[0]}</b> — %{text}<br>"
                    "Tokens générés : %{x:.2f}<br>"
                    "Temps par token : %{y:.4f} s<br>"
                    "Temps médian : %{customdata[1]:.3f} s<extra></extra>"
                ),
            )
        )

    fig.update_xaxes(title="Tokens générés en moyenne", rangemode="tozero")
    fig.update_yaxes(title="Temps par token généré (s)", rangemode="tozero")
    fig.update_layout(
        height=420,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "À droite, les combinaisons bavardes. En haut, celles dont chaque token "
        "coûte cher. `v4_letter` ne génère qu'un token : son coût total est le plus "
        "bas sans que le modèle soit plus rapide."
    )


def _table(data) -> None:
    st.subheader("Percentiles")

    table = data[
        [
            "model",
            "prompt_version",
            "n_questions",
            "avg_response_time",
            "median_response_time",
            "p90_response_time",
            "p99_response_time",
            "stddev_response_time",
            "avg_eval_tokens",
            "avg_time_per_token",
        ]
    ].sort_values(["model", "prompt_version"])

    table.columns = [
        "Modèle",
        "Prompt",
        "n",
        "Moyenne (s)",
        "Médiane (s)",
        "p90 (s)",
        "p99 (s)",
        "Écart-type (s)",
        "Tokens générés",
        "s / token",
    ]
    st.dataframe(table, hide_index=True, use_container_width=True)
