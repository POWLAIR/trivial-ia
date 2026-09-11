"""Accès en lecture seule à la couche gold.

L'application **lit** la couche gold, elle ne calcule rien : toute métrique
affichée provient d'une table `mart_*` construite et testée par dbt. Ce module
est donc le seul point de contact avec DuckDB, et il n'expose aucun moyen
d'écrire.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from trivia_bench import config

DB_PATH = config.BENCHMARK_DUCKDB


@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection:
    """Connexion unique, en lecture seule.

    `read_only=True` permet à plusieurs sessions Streamlit d'ouvrir la base
    simultanément et interdit toute écriture depuis l'application — y compris par
    accident, ce qui est le vrai enjeu : une écriture depuis l'app ferait
    diverger les chiffres affichés de ceux que `dbt test` a validés.
    """
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def load(table: str) -> pd.DataFrame:
    """Charge une table gold entière.

    Les marts sont petits par construction — une ligne par combinaison analysée —
    donc les charger en entier et filtrer côté pandas coûte moins qu'une requête
    par interaction.
    """
    return get_connection().execute(f"select * from {table}").df()


def database_is_available() -> bool:
    return DB_PATH.exists()


def missing_database_message() -> None:
    """Affiche la marche à suivre plutôt qu'une trace d'erreur."""
    st.title("Benchmark de LLM — culture générale")
    st.warning(
        f"La couche gold est absente : `{DB_PATH}` n'existe pas encore.\n\n"
        "Elle se construit depuis la couche silver, sans réinterroger aucun modèle."
    )
    st.code("make gold", language="bash")
    st.caption(
        "`make gold` enchaîne `dbt deps`, `dbt seed`, `dbt run` et `dbt test` "
        "sur `dbt/trivia_gold/`."
    )
