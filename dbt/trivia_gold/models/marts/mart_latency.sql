-- Quel est le coût en temps de réponse ?
--
-- Le grain inclut `prompt_version` : `v4_letter` génère un seul token contre
-- quatre ou cinq pour `v3_mcq`. Agrégé au seul modèle, le temps médian
-- mélangerait deux régimes de génération et ne décrirait aucun des deux.
--
-- La médiane prime sur la moyenne — la distribution est asymétrique à droite —
-- mais les deux sont publiées, avec p90 et p99.
select
    model,
    prompt_version,
    format_family,
    count(*)                                        as n_questions,
    round(avg(response_time), 3)                    as avg_response_time,
    round(median(response_time), 3)                 as median_response_time,
    round(quantile_cont(response_time, 0.90), 3)    as p90_response_time,
    round(quantile_cont(response_time, 0.99), 3)    as p99_response_time,
    round(stddev_samp(response_time), 3)            as stddev_response_time,
    round(avg(n_eval_tokens), 2)                    as avg_eval_tokens,
    -- Sépare un modèle *lent* d'un modèle simplement *bavard*.
    round(avg(response_time / nullif(n_eval_tokens, 0)), 4) as avg_time_per_token
from {{ ref('fct_answers') }}
group by 1, 2, 3
