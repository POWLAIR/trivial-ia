-- Quel est l'effet de la formulation du prompt, à modèle constant ?
--
-- La jointure sur `int_common_questions` est la clé de validité de cette
-- comparaison : sans elle, une version évaluée sur un sous-ensemble plus facile
-- paraîtrait meilleure alors qu'elle n'a pas été testée sur les mêmes questions.
--
-- `avg_answer_length` est la mesure directe de l'effet « consigne de format » :
-- c'est ce que la consigne cherche à contraindre.
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
