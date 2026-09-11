---
paths:
  - "dbt/**/*.sql"
  - "dbt/**/*.yml"
---

<!-- Règle à portée limitée : chargée quand Claude lit `dbt/**/*.sql` `dbt/**/*.yml` -->

# Couche gold — dbt sur DuckDB

Spécification de référence : `docs/04-modelisation-dbt.md`.

## Matérialisations

- `staging` et `intermediate` → **`view`** : pas de duplication de données.
- `marts` → **`table`** : lecture instantanée depuis Streamlit.
- Déclarées dans `dbt_project.yml`, **jamais** en `{{ config(materialized=...) }}` local : cinq déclarations locales finissent toujours par diverger. Ne pas surcharger sans raison énoncée en NOTE TECHNIQUE.

## Sources

- Les Parquet silver sont lus via `source()` et `external_location`, déclarés dans `models/sources.yml`.
- **Jamais de chemin de fichier en dur dans un modèle.** Un `read_parquet('...')` écrit à la main dans un `select` est un défaut à corriger.
- 🔴 **`external_location` doit résoudre en chemin absolu** (`TRIVIA_SILVER_DIR`, renseigné par le `Makefile`). Le chemin est inscrit tel quel dans les vues de staging : relatif, ces vues ne sont interrogeables que depuis `dbt/trivia_gold/` et toute lecture de la base depuis la racine échoue.

## Répartition des responsabilités

- **`stg_*`** : typage et renommage uniquement. Aucune logique métier — la couche silver a déjà nettoyé.
- **`int_*`** : précalculs construits sur le staging, **partagés par plusieurs marts**, non consommés tels quels par le dashboard. Une règle de validité utilisée par plusieurs marts appartient ici, pas en CTE dans l'un d'eux : enterrée, elle est invisible et non testable.
- **`fct_answers`** : table de faits, grain `(question_id, model, prompt_version)`. C'est la seule jointure entre questions et réponses. Elle porte `question` et `correct_answer` parce que l'explorateur la consomme directement — un verdict sans son énoncé n'est pas auditable.
- **`mart_*`** : une table = **une** question métier, directement affichable, sans agrégation laissée à l'aval.

Un mart qui oblige le dashboard à regrouper ou recalculer est mal découpé.

## Validité des agrégats

- **`random_baseline`** (1/`n_choices`) est portée par `fct_answers` et reste disponible partout où un taux est calculé. Un taux publié sans sa référence au hasard est trompeur.
- **La macro `accuracy_metrics()` produit tout taux**, avec son effectif, sa ligne de hasard et son `ci95_margin_pct` (intervalle de Wald à 95 %, `docs/06` §3). Ne pas réécrire la formule à la main : un intervalle de confiance faux ne se voit pas à la relecture.
- **`having count(*) >= 30`** sur les agrégats par catégorie : en deçà, l'intervalle de confiance est trop large pour conclure.
- Tout mart expose son effectif (`n_questions`), jamais un taux seul.
- Les lignes en erreur sont déjà exclues par `stg_ai_answers` (`where error is null`). Ne pas les réintroduire.
- **Comparaison de versions de prompt** : la jointure sur **`int_common_questions`** est **obligatoire**. Sans elle, une version évaluée sur un sous-ensemble plus facile paraît meilleure alors qu'elle n'a pas été testée sur les mêmes questions. Le compte de référence se prend **par modèle** : les modèles n'ont pas tous le même nombre de versions, et un seuil global ne renvoie rien pour celui qui en a le moins.
- **Monotonie de la difficulté** : `has_inversion` teste toute rupture de `easy >= medium >= hard`, pas seulement `hard > easy`. En pratique c'est `medium < hard` qui se produit — six combinaisons sur huit —, et une détection limitée aux extrêmes les laisse toutes passer.

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
make gold          # dbt deps + seed + run + test, variables d'environnement incluses
duckdb data/gold/benchmark.duckdb -c "select * from mart_model_performance"
```

À la main, depuis `dbt/trivia_gold/` : `DBT_PROFILES_DIR=.` et `TRIVIA_SILVER_DIR` sont requis.

Ne pas lancer `dbt run --full-refresh` ni supprimer `benchmark.duckdb` sans demande : le dashboard peut être ouvert dessus.
