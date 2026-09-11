# Raccourcis du pipeline. Chaque cible correspond à une couche de docs/01.
.PHONY: help install bronze silver enrich gold dashboard test lint clean-gold

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Installe les dépendances et le package en mode editable
	pip install -r requirements.txt
	pip install -e .

bronze:  ## Étape 1 : scraping OpenTDB -> data/bronze/questions_raw.csv (~10 min)
	python -m trivia_bench.ingest.opentdb

silver:  ## Nettoyage : bronze -> data/silver/questions.parquet
	python -m trivia_bench.silver.clean

enrich:  ## Étape 2 : inférence LLM -> data/silver/ai_answers.parquet
	python -m trivia_bench.enrich.runner $(ARGS)

# DBT_PROFILES_DIR : le profil est versionné dans le projet, pas dans ~/.dbt.
# TRIVIA_SILVER_DIR : chemin absolu des Parquet source, inscrit tel quel dans les
# vues de staging — relatif, elles ne seraient lisibles que depuis ce répertoire.
gold:  ## Étape 3 : dbt seed + run + test -> data/gold/benchmark.duckdb
	cd dbt/trivia_gold && DBT_PROFILES_DIR=. TRIVIA_SILVER_DIR=$(abspath data/silver) \
		sh -c 'dbt deps && dbt seed && dbt run && dbt test'

dashboard:  ## Lance le rapport interactif
	streamlit run app/streamlit_app.py

test:  ## Tests unitaires
	pytest

lint:  ## Vérification du style
	ruff check src tests app
	ruff format --check src tests app

clean-gold:  ## Supprime la base gold (reconstruite par `make gold`)
	rm -f data/gold/benchmark.duckdb
