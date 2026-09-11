-- Typage et renommage. Aucune logique métier : la couche silver a déjà nettoyé.
select
    question_id,
    category,
    category_group,
    type            as question_type,
    difficulty,
    question,
    correct_answer,
    n_choices,
    question_length
from {{ source('silver', 'questions') }}
