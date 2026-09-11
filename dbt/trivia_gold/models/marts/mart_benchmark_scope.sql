-- Sur quoi porte ce benchmark ?
--
-- Une seule ligne. Ce mart existe pour que la page « Méthodologie » puisse
-- annoncer son périmètre — taille du corpus, part réellement interrogée, nombre
-- de modèles et de versions — sans compter quoi que ce soit côté application.
--
-- L'écart entre `n_questions_corpus` et `n_questions_benchmarked` est la première
-- limite à afficher : le benchmark porte sur un échantillon, et un lecteur qui
-- l'ignore surestime la portée des taux.
with corpus as (
    select count(*) as n_questions_corpus
    from {{ ref('stg_questions') }}
),

benchmarked as (
    select
        count(distinct question_id)     as n_questions_benchmarked,
        count(distinct model)           as n_models,
        count(distinct prompt_version)  as n_prompt_versions,
        count(distinct format_family)   as n_format_families,
        count(*)                        as n_answers,
        min(answered_at)                as first_answered_at,
        max(answered_at)                as last_answered_at
    from {{ ref('fct_answers') }}
)

select
    c.n_questions_corpus,
    b.n_questions_benchmarked,
    round(b.n_questions_benchmarked * 100.0 / c.n_questions_corpus, 2) as coverage_pct,
    b.n_models,
    b.n_prompt_versions,
    b.n_format_families,
    b.n_answers,
    b.first_answered_at,
    b.last_answered_at
from corpus c
cross join benchmarked b
