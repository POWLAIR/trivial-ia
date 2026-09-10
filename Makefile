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

gold:  ## Étape 3 : dbt run + dbt test -> data/gold/benchmark.duckdb
	cd dbt/trivia_gold && dbt deps && dbt run && dbt test

dashboard:  ## Lance le rapport interactif
	streamlit run app/streamlit_app.py

test:  ## Tests unitaires
	pytest

lint:  ## Vérification du style
	ruff check src tests app
	ruff format --check src tests app

clean-gold:  ## Supprime la base gold (reconstruite par `make gold`)
	rm -f data/gold/benchmark.duckdb
