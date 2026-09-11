-- Isole les tentatives valides. Un appel LLM en erreur porte `ai_correct = NULL`
-- et non `False` : le compter comme une mauvaise réponse pénaliserait le modèle
-- pour une panne d'infrastructure. Il est donc écarté ici, une fois, plutôt que
-- dans chaque mart.
select
    question_id,
    model,
    prompt_version,
    ai_answer,
    ai_correct,
    response_time,
    n_eval_tokens,
    match_rule,
    run_id,
    answered_at
from {{ source('silver', 'ai_answers') }}
where error is null
