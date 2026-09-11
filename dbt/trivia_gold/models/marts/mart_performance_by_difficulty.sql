-- La difficulté déclarée par OpenTDB discrimine-t-elle vraiment ?
--
-- `has_inversion` signale toute rupture de la décroissance attendue
-- easy >= medium >= hard. Comparer seulement `hard` à `easy` laisserait passer
-- le cas medium < hard, qui est tout autant une anomalie : c'est soit le
-- matching, soit l'étiquetage de la source qu'il faut alors interroger.
--
-- La détection appartient à dbt et non à l'application : elle compare des
-- agrégats entre eux, et le dashboard n'a le droit que de filtrer et mettre en
-- forme. L'anomalie doit être affichée, jamais lissée.
with by_difficulty as (
    select
        model,
        prompt_version,
        format_family,
        difficulty,
        {{ accuracy_metrics() }}
    from {{ ref('fct_answers') }}
    group by 1, 2, 3, 4
),

with_extremes as (
    select
        *,
        max(case when difficulty = 'easy' then accuracy_pct end) over w   as easy_pct,
        max(case when difficulty = 'medium' then accuracy_pct end) over w as medium_pct,
        max(case when difficulty = 'hard' then accuracy_pct end) over w   as hard_pct
    from by_difficulty
    window w as (partition by model, prompt_version)
)

select
    model,
    prompt_version,
    format_family,
    difficulty,
    n_questions,
    n_correct,
    accuracy_pct,
    random_baseline_pct,
    ci95_margin_pct,
    coalesce(
        easy_pct < medium_pct or medium_pct < hard_pct,
        false
    ) as has_inversion
from with_extremes
