# Trivial Poursuite — Benchmark de LLM sur des questions de culture générale

> Projet M2 DEV — évaluation des performances d'un ou plusieurs modèles d'IA locaux
> sur l'intégralité du dataset [Open Trivia Database](https://opentdb.com/).

Le projet met en œuvre un **pipeline complet de data ingénierie** : collecte des
questions depuis une API publique, enrichissement par appel à des LLM exécutés en
local, modélisation en **architecture médaillon** (bronze / silver / gold) et
restitution via un **dashboard Streamlit** interactif.

---

## 1. Objectif

Produire un **rapport de benchmark** répondant à des questions métier :

- Quel modèle répond le mieux aux questions de culture générale ?
- Sur quelles catégories / quels niveaux de difficulté les modèles échouent-ils ?
- Quel est le coût en temps de réponse de chaque modèle ?
- Quel est l'impact de la **formulation du prompt** sur le taux de bonnes réponses ?

Le dernier point est traité comme une variable d'expérimentation à part entière :
chaque réponse est tracée avec la version de prompt qui l'a produite
(voir [docs/03-enrichissement-ia.md](docs/03-enrichissement-ia.md)).

---

## 2. Stack technique

| Couche | Outil | Rôle |
| --- | --- | --- |
| Collecte | Python + `requests` | Scraping de l'API OpenTDB |
| Stockage brut (bronze) | CSV | `questions_raw.csv` |
| Stockage propre (silver) | Parquet | Questions nettoyées + réponses des modèles |
| Inférence | [LM Studio](https://lmstudio.ai/) (`lms`, headless) | Exécution locale des LLM |
| Transformation (gold) | [dbt](https://docs.getdbt.com/) + `dbt-duckdb` | Modèles métier |
| Entrepôt gold | [DuckDB](https://duckdb.org/) | `benchmark.duckdb` |
| Restitution | [Streamlit](https://streamlit.io/) | Dashboard interactif |

---

## 3. Architecture médaillon

```
                  ┌─────────────────────────────────────────────┐
   OpenTDB API ──▶│ BRONZE   data/bronze/questions_raw.csv      │  brut, non modifié
                  └────────────────────┬────────────────────────┘
                                       │  nettoyage, normalisation
                  ┌────────────────────▼────────────────────────┐
                  │ SILVER   data/silver/questions.parquet      │  observations propres
LM Studio ───────▶│          data/silver/ai_answers.parquet    │  réponses brutes des modèles
                  └────────────────────┬────────────────────────┘
                                       │  dbt run
                  ┌────────────────────▼────────────────────────┐
                  │ GOLD     data/gold/benchmark.duckdb         │  réponses métier
                  └────────────────────┬────────────────────────┘
                                       │
                                  Streamlit
```

Le détail des schémas, des règles de nettoyage et des contrats entre couches est
documenté dans [docs/01-architecture.md](docs/01-architecture.md).

---

## 4. Arborescence du dépôt

```
trivial-ia/
├── README.md                   ← ce fichier
├── CLAUDE.md                   ← point d'entrée assistants (renvoie vers .claude/rules/)
├── .claude/rules/              ← règles de développement, portées par `paths:`
├── docs/                       ← documentation détaillée (voir §8)
├── requirements.txt
├── .env.example
├── Makefile                    ← raccourcis de pipeline
├── data/                       ← non versionné (cf. .gitignore), régénérable
│   ├── bronze/questions_raw.csv
│   ├── silver/questions.parquet
│   ├── silver/ai_answers.parquet
│   └── gold/benchmark.duckdb
├── src/trivia_bench/
│   ├── config.py               ← chemins, modèles, paramètres d'exécution
│   ├── ingest/opentdb.py       ← étape 1 : scraping → bronze
│   ├── silver/clean.py         ← bronze → silver (questions)
│   ├── enrich/prompts.py       ← catalogue versionné des prompts
│   ├── enrich/runner.py        ← étape 2 : silver + LM Studio → ai_answers
│   └── enrich/matching.py      ← calcul de `ai_correct`
├── dbt/trivia_gold/            ← étape 3 : silver → gold
│   ├── dbt_project.yml
│   ├── profiles.yml
│   └── models/{staging,marts}/
└── app/streamlit_app.py        ← dashboard de restitution
```

---

## 5. Setup complet

### 5.1 Prérequis

- Python **3.11+**
- [LM Studio](https://lmstudio.ai/) installé, démon et serveur lancés
  (`lms daemon up && lms server start`, API sur le port 1234)
- ~4 Go de RAM libre pour le plus gros modèle du benchmark (3B quantifié Q4)
- Sous WSL : vérifier `free -h`. Si moins de 8 Go, relever `memory=` dans
  `.wslconfig` puis `wsl --shutdown` (voir [docs/07](docs/07-demarche.md))

### 5.2 Installation

```bash
git clone <url-du-depot> trivial-ia && cd trivial-ia

python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # ajuster si besoin
```

### 5.3 Récupération des modèles

```bash
lms get llama-3.2-1b-instruct
lms get qwen2.5-1.5b-instruct
lms get llama-3.2-3b-instruct
lms ls                             # relever les clés exactes des modèles
```

Les clés listées par `lms ls` dépendent de la quantification téléchargée : ce sont
elles qui sont passées à `--model`, jamais les noms recopiés ci-dessus.

### 5.4 Exécution du pipeline

```bash
make bronze     # scraping OpenTDB       → data/bronze/questions_raw.csv
make silver     # nettoyage              → data/silver/questions.parquet
make enrich     # inférence LLM          → data/silver/ai_answers.parquet
make gold       # dbt run + dbt test     → data/gold/benchmark.duckdb
make dashboard  # streamlit run app/streamlit_app.py
```

Ou, sans `make` :

```bash
python -m trivia_bench.ingest.opentdb
python -m trivia_bench.silver.clean
python -m trivia_bench.enrich.runner --model llama-3.2-1b-instruct --prompt-version v3
cd dbt/trivia_gold && dbt run && dbt test && cd -
streamlit run app/streamlit_app.py
```

> **Durée indicative.** Le scraping complet prend ~10 min (limite de débit de
> l'API OpenTDB, cf. [docs/02-ingestion-opentdb.md](docs/02-ingestion-opentdb.md)).
> L'enrichissement est l'étape longue : compter ~0,5 à 3 s par question et par
> modèle, soit plusieurs heures pour le dataset complet sur CPU. Les stratégies
> pour rendre l'étape reprenable et échantillonnable sont décrites dans
> [docs/03-enrichissement-ia.md](docs/03-enrichissement-ia.md).

---

## 6. Organisation du projet

### 6.1 Équipe

Groupe de 3. Découpage par étage du pipeline, chacun responsable de son
périmètre et du contrat de données qu'il expose à l'étage suivant :

| Rôle | Périmètre | Livrable |
| --- | --- | --- |
| Data ingestion | Étape 1 + couche silver questions | `questions_raw.csv`, `questions.parquet` |
| Data enrichment | Étape 2, prompts, matching | `ai_answers.parquet` |
| Analytics & viz | Étape 3, dbt, Streamlit | `benchmark.duckdb`, dashboard |

Les contrats entre étages (colonnes, types, clés) sont figés dans
[docs/01-architecture.md](docs/01-architecture.md) : chacun peut travailler en
parallèle sur des données factices tant que le contrat est respecté.

### 6.2 Workflow Git

- `main` protégée, une branche par fonctionnalité : `feat/ingest-opentdb`,
  `feat/dbt-marts`, `docs/readme`…
- Une Pull Request par branche, relue par un autre membre du groupe.
- Commits conventionnels : `feat:`, `fix:`, `docs:`, `chore:`.
- Les artefacts de `data/` ne sont **pas** versionnés : le pipeline est
  reproductible depuis la source.

### 6.3 Jalons

| Date | Jalon |
| --- | --- |
| 10 septembre 2026 | Cadrage, setup, étape 1 (bronze) et squelette silver |
| 11 septembre 2026 | Étape 2 : enrichissement IA, premières mesures, choix des prompts |
| 30 septembre 2026 | Étape 3 : couche gold dbt, dashboard Streamlit, rapport final |

---

## 7. Livrables

- [x] Architecture de projet complète (médaillon bronze / silver / gold)
- [x] `README.md` : méthodologie, organisation, setup complet
- [ ] Application Streamlit — rapport de benchmark interactif

---

## 8. Licence et attribution

Les questions proviennent de l'[Open Trivia Database](https://opentdb.com/) et
sont distribuées sous licence
[Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/)
(CC BY-SA 4.0).

Cette licence impose deux obligations, que ce dépôt respecte :

- **Attribution** : la source est créditée ici et dans
  `data/bronze/_ingestion_report.json`, produit à chaque collecte.
- **Partage dans les mêmes conditions** : toute redistribution des données, y
  compris transformées, reste sous CC BY-SA 4.0.

Le code du projet en est indépendant. Les données elles-mêmes ne sont pas
versionnées (voir `.gitignore`) : le dépôt ne redistribue que le moyen de les
reconstituer.

---

## 9. Documentation détaillée

| Document | Contenu |
| --- | --- |
| [01 — Architecture](docs/01-architecture.md) | Couches médaillon, schémas, contrats de données |
| [02 — Ingestion OpenTDB](docs/02-ingestion-opentdb.md) | API, pagination, jetons de session, limites de débit |
| [03 — Enrichissement IA](docs/03-enrichissement-ia.md) | LM Studio, catalogue de prompts, matching des réponses |
| [04 — Modélisation dbt](docs/04-modelisation-dbt.md) | Modèles gold, tests, conventions de nommage |
| [05 — Dashboard Streamlit](docs/05-dashboard-streamlit.md) | Pages, filtres, lecture DuckDB |
| [06 — Méthodologie de benchmark](docs/06-methodologie-benchmark.md) | Protocole, axes d'analyse, biais et limites |
| [07 — La démarche expliquée simplement](docs/07-demarche.md) | Vue d'ensemble sans jargon, obstacles rencontrés et solutions |
