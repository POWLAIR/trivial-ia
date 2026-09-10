---
paths:
  - "dbt/**/*.sql"
  - "dbt/**/*.yml"
---

<!-- Règle à portée limitée : chargée quand Claude lit `dbt/**/*.sql` `dbt/**/*.yml` -->

# Couche gold — dbt sur DuckDB

Spécification de référence : `docs/04-modelisation-dbt.md`.

## Matérialisations

- `staging` → **`view`** : pas de duplication de données.
- `marts` → **`table`** : lecture instantanée depuis Streamlit.
- Ne pas surcharger `+materialized` dans un modèle sans raison énoncée en NOTE TECHNIQUE.

## Sources

- Les Parquet silver sont lus via `source()` et `external_location`, déclarés dans `models/staging/_sources.yml`.
- **Jamais de chemin de fichier en dur dans un modèle.** Un `read_parquet('...')` écrit à la main dans un `select` est un défaut à corriger.

## Répartition des responsabilités

- **`stg_*`** : typage et renommage uniquement. Aucune logique métier — la couche silver a déjà nettoyé.
- **`fct_answers`** : table de faits, grain `(question_id, model, prompt_version)`. C'est la seule jointure entre questions et réponses.
- **`mart_*`** : une table = **une** question métier, directement affichable, sans agrégation laissée à l'aval.

Un mart qui oblige le dashboard à regrouper ou recalculer est mal découpé.

## Validité des agrégats

- **`random_baseline`** (1/`n_choices`) est portée par `fct_answers` et reste disponible partout où un taux est calculé. Un taux publié sans sa référence au hasard est trompeur.
- **`having count(*) >= 30`** sur les agrégats par catégorie : en deçà, l'intervalle de confiance est trop large pour conclure.
- Tout mart expose son effectif (`n_questions`), jamais un taux seul.
- Les lignes en erreur sont déjà exclues par `stg_ai_answers` (`where error is null`). Ne pas les réintroduire.
- **Comparaison de versions de prompt** : le filtre `common_questions` est **obligatoire**. Sans lui, une version évaluée sur un sous-ensemble plus facile paraît meilleure alors qu'elle n'a pas été testée sur les mêmes questions.

## Tests

**Tout nouveau modèle arrive avec ses tests.** Les tests dbt sont l'implémentation exécutable des contrats de `docs/01-architecture.md` : un contrat rompu doit faire échouer `dbt test`, pas le dashboard en démonstration.

Minimum attendu :

- `fct_answers` : `unique_combination_of_columns` sur `(question_id, model, prompt_version)`, `not_null` et `relationships` sur `question_id`, `accepted_range` sur `response_time` (> 0).
- `accepted_values` sur `difficulty` (`easy`, `medium`, `hard`) et sur `question_type`.
- `mart_*` : `accepted_range` 0–100 sur tout pourcentage.

`dbt_utils` est déclaré dans `packages.yml` ; lancer `dbt deps` avant `dbt run`.

## Conventions SQL

- Nommage : `stg_` pour le staging, `fct_` pour les faits, `mart_` pour les tables métier.
- Références par `ref()` et `source()` uniquement, jamais de nom de table en dur.
- Colonnes de pourcentage suffixées `_pct`, colonnes de durée `_time` en secondes, effectifs préfixés `n_`.
- `round(..., 2)` sur les pourcentages, `round(..., 3)` sur les temps.
- Mots-clés SQL en minuscules, une colonne par ligne dans les `select` longs.

## Commandes

```bash
cd dbt/trivia_gold
dbt deps && dbt run && dbt test
duckdb ../../data/gold/benchmark.duckdb -c "select * from mart_model_performance"
```

Ne pas lancer `dbt run --full-refresh` ni supprimer `benchmark.duckdb` sans demande : le dashboard peut être ouvert dessus.
