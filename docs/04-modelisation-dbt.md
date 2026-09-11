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

Le profil vivant dans le projet et non dans `~/.dbt`, toutes les commandes
s'exécutent avec `DBT_PROFILES_DIR=.` — c'est ce que fait la cible `gold` du
`Makefile`.

### `dbt_project.yml`

```yaml
name: trivia_gold
version: 1.0.0
config-version: 2
profile: trivia_gold

model-paths: ["models"]
seed-paths: ["seeds"]
test-paths: ["tests"]
macro-paths: ["macros"]

models:
  trivia_gold:
    staging:
      +materialized: view
    intermediate:
      +materialized: view
    marts:
      +materialized: table
```

Staging et intermediate sont des **vues** (pas de duplication de données), les
marts des **tables** (lecture instantanée depuis Streamlit). Les
matérialisations sont déclarées ici et nulle part ailleurs : cinq
`{{ config(materialized=...) }}` locaux finissent toujours par diverger.

---

## 2. Sources : lire le Parquet directement

`dbt-duckdb` sait lire un fichier Parquet comme une source, sans étape de
chargement.

`models/sources.yml` :

```yaml
version: 2

sources:
  - name: silver
    meta:
      external_location: "{{ env_var('TRIVIA_SILVER_DIR', '../../data/silver') }}/{name}.parquet"
    tables:
      - name: questions
      - name: ai_answers
```

`{{ source('silver', 'questions') }}` se résout alors en
`read_parquet('.../questions.parquet')`.

🔴 **Le chemin doit être absolu**, d'où la variable `TRIVIA_SILVER_DIR` que le
`Makefile` renseigne. Il est inscrit tel quel dans la définition des vues de
staging : laissé relatif, il rendait ces vues interrogeables *uniquement* depuis
`dbt/trivia_gold/`, et un `duckdb data/gold/benchmark.duckdb` lancé depuis la
racine échouait sur un `No files found that match the pattern`. `benchmark.duckdb`
n'étant pas versionné et se reconstruisant sur chaque machine, y inscrire un
chemin absolu local ne coûte rien à la reproductibilité.

---

## 3. Modèles de staging

Un modèle par source, **sans logique métier** : typage et renommage seulement. La
couche silver a déjà nettoyé, et en refaire une partie ici reviendrait à réécrire
la couche amont.

### `stg_questions`

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

Filtre les appels en erreur et isole les tentatives valides. Un appel LLM qui
échoue porte `ai_correct = NULL` et non `False` : le compter comme une mauvaise
réponse pénaliserait le modèle pour une panne d'infrastructure. L'exclusion est
faite ici **une fois**, pas dans chaque mart.

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

## 4. Modèles intermédiaires

Précalculs construits sur `staging`, partagés par plusieurs marts, **non
destinés à être consommés tels quels** par le dashboard.

### `int_common_questions`

Grain : **modèle × question**. Les questions auxquelles *toutes* les versions de
prompt d'un modèle ont répondu.

```sql
with versions_per_model as (
    select
        model,
        count(distinct prompt_version) as n_versions
    from {{ ref('stg_ai_answers') }}
    group by 1
)

select
    a.model,
    a.question_id
from {{ ref('stg_ai_answers') }} a
inner join versions_per_model v using (model)
group by a.model, a.question_id, v.n_versions
having count(distinct a.prompt_version) = v.n_versions
```

C'est la condition de validité de **toutes** les comparaisons entre versions :
sans elle, une version évaluée sur un sous-ensemble plus facile paraîtrait
meilleure alors qu'elle n'a pas été testée sur les mêmes questions.

🔴 Le compte de référence est pris **par modèle**, jamais globalement. Les
modèles n'ont pas tous le même nombre de versions — `gemma-3-1b` en a cinq,
`gemma-3-4b` trois : un seuil global ne renverrait aucune ligne pour celui qui en
a le moins, et la comparaison disparaîtrait en silence.

Laissée en CTE dans un seul mart, cette règle serait invisible et non testable.
Nommée, elle est réutilisable et porte ses propres tests.

### `int_answer_agreement`

Grain : **question × version de prompt**. Nombre de modèles ayant tenté et réussi
la question, plus les drapeaux `missed_by_all` et `solved_by_all`.

Le grain inclut `prompt_version` : agréger l'accord tous prompts confondus
mélangerait de la génération libre et du QCM, dont les taux n'ont pas le même
sens. Seules sont retenues les questions posées à *tous* les modèles ayant
utilisé ce prompt — sinon « ratée par tous » dépendrait du nombre de modèles
interrogés sur cette question, et non de sa difficulté.

🔴 **Les prompts qu'un seul modèle a utilisés sont exclus** (`having
count(distinct model) >= 2`). L'accord entre un modèle et lui-même n'existe pas :
`missed_by_all` y serait un simple taux d'échec affublé d'un nom qui promet
davantage, et le lecteur y verrait un consensus là où il n'y a qu'une mesure.
C'est le cas de `v1` et `v2`, que seul `gemma-3-1b` a exécutés.

---

## 5. Table de faits

### `fct_answers`

Grain : **une ligne par (question, modèle, version de prompt)**. C'est la table
sur laquelle reposent tous les marts.

```sql
select
    a.question_id,
    a.model,
    a.prompt_version,
    p.format_family,
    q.category,
    q.category_group,
    q.difficulty,
    q.question_type,
    q.n_choices,
    q.question_length,
    q.question,
    q.correct_answer,
    a.ai_answer,
    a.ai_correct,
    a.match_rule,
    a.response_time,
    a.n_eval_tokens,
    a.run_id,
    a.answered_at,
    -- performance attendue d'un répondant aléatoire, pour référence
    1.0 / q.n_choices as random_baseline
from {{ ref('stg_ai_answers') }} a
inner join {{ ref('stg_questions') }} q using (question_id)
inner join {{ ref('prompt_catalog') }} p using (prompt_version)
```

`random_baseline` matérialise une comparaison qui revient dans toutes les
analyses : un modèle à 30 % sur des QCM à 4 choix fait **moins bien que le
hasard**. Sans cette colonne, la lecture des taux bruts est trompeuse.

`question` et `correct_answer` sont portées ici parce que `fct_answers` est
**consommée directement** par l'explorateur du dashboard : un verdict sans son
énoncé n'est pas auditable, et l'app n'a pas le droit d'aller rejoindre elle-même
les questions.

`format_family` vient du seed `prompt_catalog` et rend la séparation des familles
de prompts disponible dans tous les marts.

---

## 6. Seed `prompt_catalog`

`seeds/prompt_catalog.csv` porte la métadonnée de format des prompts :

```csv
prompt_version,format_family,is_mcq,is_letter
v1,generation_libre,false,false
v2,generation_libre,false,false
v3,generation_libre,false,false
v3_mcq,qcm_options,true,false
v4_letter,qcm_lettre,true,true
```

Il existe pour que le dashboard puisse séparer les familles **sans rien
calculer** : donner les options transforme une restitution en reconnaissance, et
les deux ne se comparent pas. À garder cohérent avec `MCQ_VERSIONS` et
`LETTER_VERSIONS` de `src/trivia_bench/enrich/prompts.py`.

Le **texte** des prompts n'est pas dupliqué ici : l'application le lit depuis
`PROMPTS`, source unique.

---

## 7. Macro `accuracy_metrics()`

Le même bloc de mesures accompagne tout taux de bonnes réponses : `n_questions`,
`n_correct`, `accuracy_pct`, `random_baseline_pct`, `ci95_margin_pct`.

```sql
{% macro accuracy_metrics() %}
    count(*)                              as n_questions,
    sum(ai_correct::int)                  as n_correct,
    round(avg(ai_correct::int) * 100, 2)  as accuracy_pct,
    round(avg(random_baseline) * 100, 2)  as random_baseline_pct,
    round(
        1.96 * sqrt(
            avg(ai_correct::int) * (1 - avg(ai_correct::int)) / count(*)
        ) * 100,
        2
    )                                     as ci95_margin_pct
{% endmacro %}
```

`ci95_margin_pct` est la demi-largeur de l'intervalle de Wald à 95 % exigé par
[06 — Méthodologie](06-methodologie-benchmark.md#taux-de-bonnes-réponses) : deux
taux dont les intervalles se recouvrent ne sont pas départagés.

Écrite à la main dans chaque mart, cette formule offrirait autant d'occasions de
se tromper — et un intervalle de confiance faux ne se voit pas à la relecture,
contrairement à une requête qui plante.

---

## 8. Marts

Une table par question métier. Chacune est directement affichable.

### `mart_model_performance` — performance globale

Grain : modèle × prompt.

```sql
select
    model,
    prompt_version,
    format_family,
    {{ accuracy_metrics() }},
    round(avg(response_time), 3)    as avg_response_time,
    round(median(response_time), 3) as median_response_time
from {{ ref('fct_answers') }}
group by 1, 2, 3
```

### `mart_performance_by_category`

Même agrégation, avec `category` et `category_group` dans le `group by`. Un
`having count(*) >= 30` écarte les catégories trop petites pour porter une
conclusion.

### `mart_performance_by_category_group`

Même agrégation au niveau du groupe de catégories (« Science »,
« Entertainment »).

Ce modèle existe parce que [05 — Dashboard](05-dashboard-streamlit.md) demande un
« filtre sur `category_group` pour agréger les sous-catégories » : c'est une
agrégation, et l'application n'a pas le droit d'en faire. Il rend aussi la page
lisible quand l'échantillon est trop petit pour que les sous-catégories
atteignent 30 — à 550 questions, 6 catégories sur 24 y parviennent, contre 5
groupes sur 13.

### `mart_performance_by_difficulty`

`group by model, prompt_version, difficulty`. Sert à vérifier que la difficulté
déclarée par OpenTDB est **monotone** pour le modèle.

La colonne `has_inversion` signale toute rupture de la décroissance attendue
`easy >= medium >= hard`.

🔴 Ne pas se contenter de comparer `hard` à `easy` : le cas `medium < hard` est
tout autant une anomalie, et c'est en pratique **celui qui se produit** — six
combinaisons sur huit. Une détection limitée aux extrêmes les laissait toutes
passer.

Détecter appartient à dbt et non à l'application : c'est une comparaison entre
agrégats, et le dashboard n'a le droit que de filtrer et mettre en forme.

### `mart_latency`

Grain : **modèle × prompt**. Distribution des temps — moyenne, médiane, p90, p99,
écart-type — et `avg(response_time / nullif(n_eval_tokens, 0))`, le temps par
token généré, qui sépare un modèle *lent* d'un modèle simplement *bavard*.

Le grain inclut `prompt_version` : `v4_letter` génère un seul token contre quatre
ou cinq pour `v3_mcq`. Agrégée au seul modèle, la médiane mélangerait deux
régimes de génération et n'en décrirait aucun.

### `mart_prompt_impact`

Comparaison des versions de prompt à modèle constant, restreinte aux questions
communes :

```sql
select
    f.model,
    f.prompt_version,
    f.format_family,
    {{ accuracy_metrics() }},
    round(avg(length(f.ai_answer)), 1) as avg_answer_length,
    round(avg(f.response_time), 3)     as avg_response_time
from {{ ref('fct_answers') }} f
inner join {{ ref('int_common_questions') }} c using (model, question_id)
group by 1, 2, 3
```

La jointure sur `int_common_questions` est la clé de validité de cette
comparaison. Elle porte sur `(model, question_id)` : chaque modèle est restreint
à **ses** questions communes, et non à celles d'un modèle de référence.

`avg_answer_length` est la mesure directe de l'effet « consigne de format » —
c'est précisément ce que la consigne cherche à contraindre.

### `mart_matching_reliability` — exploratoire

Grain : modèle × prompt × `match_rule`. Répartition des verdicts par règle de la
cascade, avec `pct_of_answers` et `pct_correct_within_rule`.

Sans cette table, le matching n'est pas auditable : un taux de bonnes réponses ne
dit pas si le modèle a échoué ou si la règle a mal tranché. `none` est la ligne à
surveiller — ce sont les réponses comptées fausses sans qu'aucune règle n'ait
rien reconnu, donc l'endroit où se logent les faux négatifs. C'est aussi la table
que confronte l'annotation manuelle de
[06 — Méthodologie](06-methodologie-benchmark.md).

Pas de `random_baseline_pct` ici : `pct_correct_within_rule` est un taux
conditionnel à une règle, pas une performance face au hasard.

### `mart_answer_agreement` — exploratoire

Grain : prompt × groupe de catégories. Part des questions `missed_by_all` et
`solved_by_all`, construite sur `int_answer_agreement`.

Un taux élevé de `missed_by_all` sur un thème ne dit pas seulement que les
modèles l'ignorent : c'est aussi là que se voient les défauts du dataset source —
énoncés ambigus, réponses datées, étiquetage douteux.

Agrégé au groupe et non à la catégorie : au grain fin, presque aucune cellule
n'atteint 30 observations.

---

## 9. Tests

`dbt_utils` est déclaré dans `packages.yml` puis installé par `dbt deps`.

Ces tests sont l'implémentation exécutable des contrats de données décrits en
[01 — Architecture](01-architecture.md#contrats-de-données) : un contrat rompu
fait échouer `dbt test`, pas le dashboard en démonstration.

Attendu au minimum :

| Modèle | Tests |
| --- | --- |
| `stg_questions` | `unique` + `not_null` sur `question_id` ; `accepted_values` sur `question_type`, `difficulty`, `n_choices` |
| `stg_ai_answers` | `not_null` sur `ai_correct` (les erreurs sont filtrées) ; `relationships` de `prompt_version` vers le seed ; `accepted_range` `response_time` > 0 |
| `int_common_questions` | `unique_combination_of_columns` sur `(model, question_id)` |
| `int_answer_agreement` | `unique_combination_of_columns` sur `(question_id, prompt_version)` |
| `fct_answers` | `unique_combination_of_columns` sur `(question_id, model, prompt_version)` ; `not_null` + `relationships` sur `question_id` ; `not_null` sur `question`, `correct_answer`, `ai_correct` ; `accepted_values` sur `difficulty`, `question_type`, `format_family` |
| tout `mart_*` | `unique_combination_of_columns` sur son grain ; `accepted_range` 0–100 sur chaque colonne `_pct` |

Un test singulier, `tests/assert_category_marts_above_30.sql`, vérifie qu'aucune
ligne des marts par catégorie ne repose sur moins de 30 observations. La règle
vit déjà dans le `having` de chaque mart ; ce test garantit qu'un `having`
supprimé ne passera pas inaperçu — c'est le dashboard qui mentirait, sans rien
casser.

**Écrire les tests d'un nouveau modèle en même temps que le modèle.** Sur ce
projet, une agrégation fausse ne plante pas : elle publie un chiffre crédible.

---

## 10. Commandes

```bash
cd dbt/trivia_gold
export DBT_PROFILES_DIR=.
export TRIVIA_SILVER_DIR="$(cd ../../data/silver && pwd)"

dbt deps        # installe dbt_utils
dbt seed        # charge prompt_catalog
dbt run         # construit vues + tables dans benchmark.duckdb
dbt test        # vérifie les contrats
dbt docs generate && dbt docs serve   # documentation et lignage
```

Ou simplement `make gold`, qui enchaîne les quatre et renseigne les deux
variables.

Inspection directe de la base, depuis la racine du dépôt :

```bash
duckdb data/gold/benchmark.duckdb -c "select * from mart_model_performance"
```
