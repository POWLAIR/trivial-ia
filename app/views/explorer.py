"""Explorateur de réponses — la page qui rend le benchmark auditable.

C'est ici qu'on vérifie à la main pourquoi une réponse a été comptée fausse, et
c'est là que se repèrent les défauts de matching. Un taux global ne dit jamais si
un modèle a échoué ou si la règle a mal tranché ; cette table le dit, verdict par
verdict.
"""

from __future__ import annotations

import streamlit as st

import filters
from data_access import load

COLUMNS = {
    "model": "Modèle",
    "prompt_version": "Prompt",
    "category": "Catégorie",
    "difficulty": "Difficulté",
    "question": "Question",
    "correct_answer": "Bonne réponse",
    "ai_answer": "Réponse du modèle",
    "ai_correct": "Correct",
    "match_rule": "Règle",
    "response_time": "Temps (s)",
}

VERDICTS = {
    "Toutes": None,
    "Comptées correctes": True,
    "Comptées incorrectes": False,
}


def render() -> None:
    st.title("Explorateur de réponses")

    facts, ignored = filters.apply(load("fct_answers"))
    filters.report_ignored(ignored)

    col1, col2 = st.columns([1, 2])
    verdict = col1.selectbox("Verdict", list(VERDICTS), key="explorer_verdict")
    rules = sorted(facts["match_rule"].unique()) if not facts.empty else []
    chosen_rules = col2.multiselect(
        "Règle de matching ayant statué",
        options=rules,
        default=rules,
        key="explorer_rules",
        help=(
            "`none` : aucune règle n'a reconnu la réponse, elle est comptée fausse. "
            "C'est là que se logent les faux négatifs."
        ),
    )

    if VERDICTS[verdict] is not None:
        facts = facts[facts["ai_correct"] == VERDICTS[verdict]]
    if chosen_rules:
        facts = facts[facts["match_rule"].isin(chosen_rules)]

    search = st.text_input(
        "Recherche dans l'énoncé ou les réponses",
        key="explorer_search",
        placeholder="mot-clé…",
    )
    if search:
        pattern = search.strip()
        mask = (
            facts["question"].str.contains(pattern, case=False, na=False)
            | facts["correct_answer"].str.contains(pattern, case=False, na=False)
            | facts["ai_answer"].str.contains(pattern, case=False, na=False)
        )
        facts = facts[mask]

    if facts.empty:
        filters.empty_state()
        return

    st.caption(
        f"{len(facts)} réponse(s) affichée(s). Les colonnes `Règle` et "
        "`Réponse du modèle` sont ce qui permet de contester un verdict."
    )

    table = facts[list(COLUMNS)].rename(columns=COLUMNS)
    st.dataframe(
        table,
        hide_index=True,
        use_container_width=True,
        height=560,
        column_config={
            "Correct": st.column_config.CheckboxColumn(disabled=True),
            "Temps (s)": st.column_config.NumberColumn(format="%.3f"),
        },
    )

    st.download_button(
        "Télécharger la sélection (CSV)",
        data=table.to_csv(index=False).encode("utf-8"),
        file_name="reponses_selection.csv",
        mime="text/csv",
        help="Pour annoter à la main hors de l'application.",
    )
