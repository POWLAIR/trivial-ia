-- Même question, au niveau du groupe de catégories (« Science », « Entertainment »).
--
-- Ce modèle existe parce que le dashboard ne peut pas agréger lui-même : toute
-- métrique affichée vient d'un mart. Il rend aussi la page lisible quand
-- l'échantillon est trop petit pour que les sous-catégories atteignent 30.
select
    model,
    prompt_version,
    format_family,
    category_group,
    {{ accuracy_metrics() }}
from {{ ref('fct_answers') }}
group by 1, 2, 3, 4
having count(*) >= 30
