# CLAUDE.md — Trivial Poursuite M2 DEV

Benchmark de LLM locaux sur les questions de culture générale d'OpenTDB. Pipeline
de data ingénierie en architecture médaillon : scraping → enrichissement par LLM →
modélisation dbt → dashboard Streamlit. Projet scolaire M2 DEV, rendu GitHub,
groupe de 3.

## Où sont les règles

Les règles de développement vivent dans [.claude/rules/](.claude/rules/).

| Fichier | Chargement |
| --- | --- |
| [dev.md](.claude/rules/dev.md) | **À chaque session** — cadre général, invariants, Git, conventions, outillage rtk |
| [data-pipeline.md](.claude/rules/data-pipeline.md) | À la lecture de `src/trivia_bench/**/*.py` — contrats bronze/silver, OpenTDB, LM Studio, matching |
| [dbt.md](.claude/rules/dbt.md) | À la lecture de `dbt/**/*.sql` et `dbt/**/*.yml` — couche gold, matérialisations, tests |
| [streamlit.md](.claude/rules/streamlit.md) | À la lecture de `app/**/*.py` — lecture seule de gold, visualisation honnête |

Les trois dernières portent un champ `paths:` : elles ne se chargent que sur les
fichiers concernés, et restent hors contexte le reste du temps.

## Où est la spécification

[docs/](docs/) — `docs/01` à `docs/06`. Le code s'y conforme. Si une décision
d'implémentation contredit la doc, mettre à jour la doc dans la même PR : ne
jamais laisser les deux diverger en silence.

| Document | À lire avant de toucher à |
| --- | --- |
| [01 — Architecture](docs/01-architecture.md) | Toute couche de données, tout schéma |
| [02 — Ingestion OpenTDB](docs/02-ingestion-opentdb.md) | `src/trivia_bench/ingest/` |
| [03 — Enrichissement IA](docs/03-enrichissement-ia.md) | `src/trivia_bench/enrich/` |
| [04 — Modélisation dbt](docs/04-modelisation-dbt.md) | `dbt/trivia_gold/` |
| [05 — Dashboard Streamlit](docs/05-dashboard-streamlit.md) | `app/` |
| [06 — Méthodologie](docs/06-methodologie-benchmark.md) | Toute interprétation de chiffres |
