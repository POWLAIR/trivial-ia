-- Les questions auxquelles *toutes* les versions de prompt d'un modèle ont
-- répondu.
--
-- C'est la condition de validité de toute comparaison entre versions : une
-- version évaluée sur un sous-ensemble plus facile paraîtrait meilleure sans
-- l'avoir été. Le compte de référence est pris **par modèle** et non
-- globalement : les modèles n'ont pas tous le même nombre de versions, et un
-- seuil global ne renverrait rien pour ceux qui en ont moins.
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
group by
    a.model,
    a.question_id,
    v.n_versions
having count(distinct a.prompt_version) = v.n_versions
