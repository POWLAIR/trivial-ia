-- Quel modèle / prompt est le meilleur globalement ?
select
    model,
    prompt_version,
    format_family,
    {{ accuracy_metrics() }},
    round(avg(response_time), 3)    as avg_response_time,
    round(median(response_time), 3) as median_response_time
from {{ ref('fct_answers') }}
group by 1, 2, 3
