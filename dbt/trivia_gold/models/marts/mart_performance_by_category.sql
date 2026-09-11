-- Sur quels thèmes le modèle échoue-t-il ?
--
-- `having count(*) >= 30` : en deçà, l'intervalle de confiance est trop large
-- pour conclure quoi que ce soit d'une catégorie. Mieux vaut une ligne absente
-- qu'un taux ininterprétable affiché comme les autres.
select
    model,
    prompt_version,
    format_family,
    category,
    category_group,
    {{ accuracy_metrics() }}
from {{ ref('fct_answers') }}
group by 1, 2, 3, 4, 5
having count(*) >= 30
