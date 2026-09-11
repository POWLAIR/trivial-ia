-- Quelle règle de la cascade a statué, et avec quel verdict ?
--
-- Sans cette table, le matching n'est pas auditable : un taux de bonnes réponses
-- ne dit pas si le modèle a échoué ou si la règle a mal tranché. `none` est la
-- ligne à surveiller — ce sont les réponses comptées fausses sans qu'aucune
-- règle n'ait rien reconnu, donc l'endroit où se logent les faux négatifs.
--
-- Pas de `random_baseline_pct` ici : `pct_correct_within_rule` est un taux
-- conditionnel à une règle, pas une performance face au hasard.
with by_rule as (
    select
        model,
        prompt_version,
        format_family,
        match_rule,
        count(*)             as n_answers,
        sum(ai_correct::int) as n_correct
    from {{ ref('fct_answers') }}
    group by 1, 2, 3, 4
)

select
    *,
    round(n_answers * 100.0 / sum(n_answers) over w, 2) as pct_of_answers,
    round(n_correct * 100.0 / n_answers, 2)             as pct_correct_within_rule
from by_rule
window w as (partition by model, prompt_version)
