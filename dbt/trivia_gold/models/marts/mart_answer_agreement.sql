-- Les questions ratées par tous les modèles forment-elles un groupe cohérent ?
--
-- Un taux élevé de `missed_by_all` sur un thème ne dit pas seulement que les
-- modèles l'ignorent : c'est aussi là que se voient les défauts du dataset
-- source — énoncés ambigus, réponses datées, étiquetage douteux. Piste
-- exploratoire de `docs/06` §2.
--
-- Agrégé au groupe de catégories et non à la catégorie : au grain fin, presque
-- aucune cellule n'atteint 30 observations.
select
    a.prompt_version,
    p.format_family,
    q.category_group,
    count(*)                                    as n_questions,
    max(a.n_models)                             as n_models,
    sum(a.missed_by_all::int)                   as n_missed_by_all,
    round(avg(a.missed_by_all::int) * 100, 2)   as pct_missed_by_all,
    sum(a.solved_by_all::int)                   as n_solved_by_all,
    round(avg(a.solved_by_all::int) * 100, 2)   as pct_solved_by_all
from {{ ref('int_answer_agreement') }} a
inner join {{ ref('stg_questions') }} q using (question_id)
inner join {{ ref('prompt_catalog') }} p using (prompt_version)
group by 1, 2, 3
having count(*) >= 30
