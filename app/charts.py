"""Constructeurs de graphiques qui appliquent les règles de lecture honnête.

Ces règles ne sont pas cosmétiques : elles empêchent le dashboard de mentir. Un
taux de bonnes réponses sans sa ligne de hasard, sans son effectif ou sur un axe
tronqué se lit faux — et il se lit faux de façon crédible, ce qui est pire qu'un
graphique manifestement cassé.

Les centraliser ici est ce qui les rend tenables : répétées à la main dans six
pages, l'une d'elles finit par en oublier une.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from theme import CHANCE_COLOR, MIN_SAMPLE, color_for

CHANCE_LABEL = "Hasard (1/nombre de choix)"


def accuracy_figure(
    df: pd.DataFrame,
    label_col: str,
    title: str = "",
) -> go.Figure:
    """Barres horizontales de taux de bonnes réponses, avec tout ce qui les rend lisibles.

    Trois éléments sont ajoutés systématiquement, et ne sont pas optionnels :
    la ligne de hasard par barre, les barres d'erreur à 95 %, et l'axe borné à
    `[0, 100]`. Un axe tronqué exagère les écarts entre modèles ; un taux sans
    intervalle laisse croire que trois points séparent deux modèles.
    """
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            y=df[label_col],
            x=df["accuracy_pct"],
            orientation="h",
            marker_color=[color_for(m) for m in df["model"]],
            error_x={
                "type": "data",
                "array": df["ci95_margin_pct"],
                "visible": True,
                "color": "#444444",
                "thickness": 1,
            },
            customdata=df[["n_questions", "n_correct", "ci95_margin_pct"]],
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Taux : %{x:.2f} %<br>"
                "Intervalle 95 % : ± %{customdata[2]:.2f} pts<br>"
                "%{customdata[1]} bonnes réponses sur %{customdata[0]}"
                "<extra></extra>"
            ),
            name="Taux de bonnes réponses",
            showlegend=False,
        )
    )

    # Un marqueur par barre plutôt qu'une ligne unique : la référence au hasard
    # dépend du nombre de choix, et un échantillon mêle des QCM à 4 options
    # (25 %) et des vrai/faux (50 %). Une ligne unique serait fausse dès que la
    # composition varie d'une barre à l'autre.
    fig.add_trace(
        go.Scatter(
            y=df[label_col],
            x=df["random_baseline_pct"],
            mode="markers",
            marker={
                "symbol": "line-ns",
                "size": 20,
                "line": {"width": 2.5, "color": CHANCE_COLOR},
            },
            name=CHANCE_LABEL,
            hovertemplate="Hasard : %{x:.2f} %<extra></extra>",
        )
    )

    fig.update_xaxes(range=[0, 100], title="Taux de bonnes réponses (%)", ticksuffix=" %")
    fig.update_layout(
        title=title,
        height=max(240, 42 * len(df) + 130),
        margin={"l": 10, "r": 10, "t": 50 if title else 30, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        bargap=0.25,
    )
    return fig


def grouped_accuracy_figure(
    df: pd.DataFrame,
    x_col: str,
    x_order: list[str],
    title: str = "",
) -> go.Figure:
    """Barres verticales groupées par modèle, sur un axe ordonné (difficulté)."""
    fig = go.Figure()

    for model, group in df.groupby("model", sort=False):
        group = group.set_index(x_col).reindex(x_order).reset_index()
        fig.add_trace(
            go.Bar(
                x=group[x_col],
                y=group["accuracy_pct"],
                name=model,
                marker_color=color_for(model),
                error_y={
                    "type": "data",
                    "array": group["ci95_margin_pct"],
                    "visible": True,
                    "color": "#444444",
                    "thickness": 1,
                },
                customdata=group[["n_questions", "ci95_margin_pct"]],
                hovertemplate=(
                    f"<b>{model}</b> — %{{x}}<br>"
                    "Taux : %{y:.2f} %<br>"
                    "Intervalle 95 % : ± %{customdata[1]:.2f} pts<br>"
                    "n = %{customdata[0]}"
                    "<extra></extra>"
                ),
            )
        )

    baseline = df.groupby(x_col)["random_baseline_pct"].mean().reindex(x_order)
    fig.add_trace(
        go.Scatter(
            x=list(baseline.index),
            y=baseline.to_numpy(),
            mode="lines",
            line={"dash": "dash", "width": 2, "color": CHANCE_COLOR},
            name=CHANCE_LABEL,
            hovertemplate="Hasard : %{y:.2f} %<extra></extra>",
        )
    )

    fig.update_yaxes(range=[0, 100], title="Taux de bonnes réponses (%)", ticksuffix=" %")
    fig.update_layout(
        title=title,
        barmode="group",
        height=420,
        margin={"l": 10, "r": 10, "t": 50 if title else 30, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    return fig


def sample_caption(df: pd.DataFrame, extra: str = "") -> None:
    """Rappelle sous chaque graphique l'effectif sur lequel il repose.

    Un taux sans son effectif ne se lit pas : 30 % sur 10 questions et 30 % sur
    2 000 ne disent pas la même chose, et rien à l'écran ne les distingue.
    """
    if df.empty:
        return
    n_min, n_max = int(df["n_questions"].min()), int(df["n_questions"].max())
    effectif = f"n = {n_min}" if n_min == n_max else f"n de {n_min} à {n_max}"
    barres = "Barres d'erreur : intervalle de Wald à 95 %."
    st.caption(" ".join(part for part in (f"{effectif} par barre.", barres, extra) if part))


def separable(a: pd.Series, b: pd.Series) -> bool:
    """Vrai si les intervalles de confiance de deux taux ne se recouvrent pas.

    En deçà, l'écart peut tenir au seul tirage de l'échantillon : désigner un
    gagnant serait affirmer ce que les données ne montrent pas.
    """
    gap = abs(a["accuracy_pct"] - b["accuracy_pct"])
    return gap > a["ci95_margin_pct"] + b["ci95_margin_pct"]


def chance_verdict(row: pd.Series, subject: str) -> str:
    """Situe un taux par rapport au hasard, intervalle de confiance compris.

    Trois cas, pas deux : un taux peut être significativement sous le hasard, ce
    qui ne dit pas la même chose qu'un taux simplement indiscernable du hasard.
    Chaîne vide si le taux est nettement au-dessus.
    """
    low = row["accuracy_pct"] - row["ci95_margin_pct"]
    high = row["accuracy_pct"] + row["ci95_margin_pct"]
    baseline = row["random_baseline_pct"]
    if high < baseline:
        return (
            f"Sur {subject}, le modèle fait nettement **moins bien que le hasard** "
            f"({baseline:.1f} %)."
        )
    if low <= baseline:
        return f"Sur {subject}, le modèle ne se distingue pas du hasard ({baseline:.1f} %)."
    return ""


def takeaway(lines: list[str]) -> None:
    """Une ou deux phrases qui disent ce que montre le graphique au-dessus.

    Les phrases sont composées par l'appelant à partir des lignes du mart
    affichées, jamais écrites avec des chiffres en dur : elles suivent ainsi les
    filtres et le prochain `make gold`.
    """
    lines = [line for line in lines if line]
    if lines:
        st.markdown("**À retenir** — " + " ".join(lines))


def warn_small_samples(df: pd.DataFrame) -> pd.DataFrame:
    """Écarte les lignes sous le seuil d'effectif, et le dit.

    En deçà de 30 observations, l'intervalle de confiance est trop large pour
    conclure. Masquer sans prévenir serait une autre façon de tromper : on
    annonce ce qui a été retiré.
    """
    if df.empty or "n_questions" not in df:
        return df
    too_small = df[df["n_questions"] < MIN_SAMPLE]
    if not too_small.empty:
        st.caption(
            f"{len(too_small)} ligne(s) écartée(s) : moins de {MIN_SAMPLE} observations, "
            "l'intervalle de confiance y est trop large pour conclure."
        )
    return df[df["n_questions"] >= MIN_SAMPLE]
