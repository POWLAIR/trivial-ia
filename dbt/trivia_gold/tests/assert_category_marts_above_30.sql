-- Garde-fou exécutable de la règle des 30 observations.
--
-- En deçà, l'intervalle de confiance est trop large pour conclure, et un taux
-- affiché comme les autres tromperait le lecteur. La règle vit déjà dans le
-- `having` de chaque mart concerné ; ce test garantit qu'un `having` supprimé ne
-- passera pas inaperçu — c'est le dashboard qui mentirait, sans rien casser.
select 'mart_performance_by_category' as mart, model, prompt_version, category as grouping, n_questions
from {{ ref('mart_performance_by_category') }}
where n_questions < 30

union all

select 'mart_performance_by_category_group', model, prompt_version, category_group, n_questions
from {{ ref('mart_performance_by_category_group') }}
where n_questions < 30

union all

select 'mart_answer_agreement', 'tous modèles', prompt_version, category_group, n_questions
from {{ ref('mart_answer_agreement') }}
where n_questions < 30
