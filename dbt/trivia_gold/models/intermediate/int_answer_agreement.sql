-- Accord entre modèles, question par question, **à prompt constant**.
--
-- Le grain inclut `prompt_version` : agréger l'accord tous prompts confondus
-- mélangerait de la génération libre et du QCM, dont les taux n'ont pas le même
-- sens. On ne retient que les questions posées à *tous* les modèles ayant
-- utilisé ce prompt — sinon « ratée par tous » dépendrait du nombre de modèles
-- interrogés sur cette question, pas de sa difficulté.
--
-- 🔴 Les prompts qu'un seul modèle a utilisés sont **exclus**. L'accord entre un
-- modèle et lui-même n'existe pas : `missed_by_all` y serait un simple taux
-- d'échec affublé d'un nom qui promet davantage, et le lecteur y verrait un
-- consensus là où il n'y a qu'une mesure.
with models_per_prompt as (
    select
        prompt_version,
        count(distinct model) as n_models_total
    from {{ ref('stg_ai_answers') }}
    group by 1
    having count(distinct model) >= 2
),

agreement as (
    select
        question_id,
        prompt_version,
        count(distinct model)  as n_models,
        sum(ai_correct::int)   as n_models_correct
    from {{ ref('stg_ai_answers') }}
    group by 1, 2
)

select
    a.question_id,
    a.prompt_version,
    a.n_models,
    a.n_models_correct,
    a.n_models_correct = 0          as missed_by_all,
    a.n_models_correct = a.n_models as solved_by_all
from agreement a
inner join models_per_prompt m using (prompt_version)
where a.n_models = m.n_models_total
