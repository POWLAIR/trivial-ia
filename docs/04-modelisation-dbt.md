# 04 — Couche gold : modélisation dbt sur DuckDB

**Objectif** : transformer les Parquet silver en tables métier interrogeables,
stockées dans `data/gold/benchmark.duckdb`.

Projet : `dbt/trivia_gold/`

---

## 1. Configuration

### Dépendances

```
dbt-core>=1.8
dbt-duckdb>=1.8
duckdb>=1.0
```

### `profiles.yml`

Versionné dans le projet (aucun secret : la cible est un fichier local).

```yaml
trivia_gold:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: ../../data/gold/benchmark.duckdb
      threads: 4
      extensions: [parquet]
```

### `dbt_project.yml`

```yaml
name: trivia_gold
version: 1.0.0
profile: trivia_gold

model-paths: ["models"]

models:
  trivia_gold:
    staging:
      +materialized: view
    marts:
      +materialized: table
```

Les modèles de staging sont des **vues** (pas de duplication de données), les marts
des **tables** (lecture instantanée depuis Streamlit).

---

## 2. Sources : lire le Parquet directement

`dbt-duckdb` sait lire un fichier Parquet comme une source, sans étape de chargement.

`models/staging/_sources.yml` :

```yaml
version: 2

sources:
  - name: silver
    meta:
      external_location: "../../data/silver/{name}.parquet"
    tables:
      - name: questions
      - name: ai_answers
```

`{{ source('silver', 'questions') }}` se résout alors en
`read_parquet('../../data/silver/questions.parquet')`.

---

## 3. Modèles de staging

### `stg_questions`

Typage et renommage. Aucune logique métier — la couche silver a déjà nettoyé.

```sql
select
    question_id,
    category,
    category_group,
    type            as question_type,
    difficulty,
    question,
    correct_answer,
    n_choices,
    question_length
from {{ source('silver', 'questions') }}
```

### `stg_ai_answers`

Filtre les appels en erreur et isole les tentatives valides.

```sql
select
    question_id,
    model,
    prompt_version,
    ai_answer,
    ai_correct,
    response_time,
    n_eval_tokens,
    match_rule,
    run_id,
    answered_at
from {{ source('silver', 'ai_answers') }}
where error is null
```

---

## 4. Table de faits

### `fct_answers`

Grain : **une ligne par (question, modèle, version de prompt)**. C'est la table
sur laquelle reposent tous les marts.

```sql
select
    a.question_id,
    a.model,
    a.prompt_version,
    q.category,
    q.category_group,
    q.difficulty,
    q.question_type,
    q.n_choices,
    q.question_length,
    a.ai_answer,
    a.ai_correct,
    a.response_time,
    a.n_eval_tokens,
    a.match_rule,
    -- performance attendue d'un répondant aléatoire, pour référence
    1.0 / q.n_choices as random_baseline
from {{ ref('stg_ai_answers') }} a
inner join {{ ref('stg_questions') }} q using (question_id)
```

`random_baseline` matérialise une comparaison qui revient dans toutes les
analyses : un modèle à 30 % sur des QCM à 4 choix fait **moins bien que le
hasard**. Sans cette colonne, la lecture des taux bruts est trompeuse.

---

## 5. Marts

Une table par question métier. Chacune est directement affichable.

### `mart_model_performance` — performance globale

```sql
select
    model,
    prompt_version,
    count(*)                                  as n_questions,
    sum(ai_correct::int)                      as n_correct,
    round(avg(ai_correct::int) * 100, 2)      as accuracy_pct,
    round(avg(random_baseline) * 100, 2)      as random_baseline_pct,
    round(avg(response_time), 3)              as avg_response_time,
    round(median(response_time), 3)           as median_response_time
from {{ ref('fct_answers') }}
group by 1, 2
```

### `mart_performance_by_category`

Même agrégation, avec `category` et `category_group` dans le `group by`. Un
`having count(*) >= 30` écarte les catégories trop petites pour porter une
conclusion.

### `mart_performance_by_difficulty`

`group by model, prompt_version, difficulty`. Sert à vérifier que la difficulté
déclarée par OpenTDB est **monotone** pour le modèle : si `hard` obtient un
meilleur score que `easy`, c'est soit le matching, soit l'étiquetage de la source
qu'il faut interroger.

### `mart_latency`

Distribution des temps : moyenne, médiane, p90, p99, écart-type, et
`avg(response_time / nullif(n_eval_tokens, 0))` — le temps par token généré,
qui sépare un modèle *lent* d'un modèle simplement *bavard*.

### `mart_prompt_impact`

Comparaison des versions de prompt à modèle constant, restreinte aux questions
répondues par **toutes** les versions comparées :

```sql
with common_questions as (
    select question_id
    from {{ ref('fct_answers') }}
    where model = '{{ var("reference_model") }}'
    group by question_id
    having count(distinct prompt_version) = (
        select count(distinct prompt_version) from {{ ref('fct_answers') }}
    )
)
select
    prompt_version,
    model,
    count(*)                             as n_questions,
    round(avg(ai_correct::int) * 100, 2) as accuracy_pct,
    round(avg(length(ai_answer)), 1)     as avg_answer_length,
    round(avg(response_time), 3)         as avg_response_time
from {{ ref('fct_answers') }}
where question_id in (select question_id from common_questions)
group by 1, 2
```

Le filtre `common_questions` est la clé de validité de cette comparaison : sans
lui, une version de prompt évaluée sur un sous-ensemble plus facile paraîtrait
meilleure alors qu'elle n'a pas été testée sur les mêmes questions.

---

## 6. Tests

`models/marts/_marts.yml` :

```yaml
version: 2

models:
  - name: fct_answers
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [question_id, model, prompt_version]
    columns:
      - name: question_id
        tests:
          - not_null
          - relationships:
              to: ref('stg_questions')
              field: question_id
      - name: response_time
        tests:
          - dbt_utils.accepted_range: {min_value: 0, inclusive: false}
      - name: difficulty
        tests:
          - accepted_values: {values: [easy, medium, hard]}

  - name: mart_model_performance
    columns:
      - name: accuracy_pct
        tests:
          - dbt_utils.accepted_range: {min_value: 0, max_value: 100}
```

`dbt_utils` est déclaré dans `packages.yml` puis installé par `dbt deps`.

Ces tests sont l'implémentation exécutable des contrats de données décrits en
[01 — Architecture](01-architecture.md#contrats-de-données) : un contrat rompu
fait échouer `dbt test`, pas le dashboard en démonstration.

---

## 7. Commandes

```bash
cd dbt/trivia_gold

dbt deps        # installe dbt_utils
dbt run         # construit vues + tables dans benchmark.duckdb
dbt test        # vérifie les contrats
dbt docs generate && dbt docs serve   # documentation et lignage
```

Inspection directe de la base :

```bash
duckdb data/gold/benchmark.duckdb -c "select * from mart_model_performance"
```
