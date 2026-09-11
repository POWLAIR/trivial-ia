-- Table de faits. Grain : une ligne par (question, modèle, version de prompt).
-- C'est la seule jointure entre questions et réponses, et la table sur laquelle
-- reposent tous les marts.
--
-- Elle est aussi consommée directement par l'explorateur du dashboard, ce qui
-- justifie qu'elle porte `question` et `correct_answer` : c'est ce qui rend le
-- benchmark auditable à la main, verdict par verdict.
select
    a.question_id,
    a.model,
    a.prompt_version,
    p.format_family,
    q.category,
    q.category_group,
    q.difficulty,
    q.question_type,
    q.n_choices,
    q.question_length,
    q.question,
    q.correct_answer,
    a.ai_answer,
    a.ai_correct,
    a.match_rule,
    a.response_time,
    a.n_eval_tokens,
    a.run_id,
    a.answered_at,
    -- Performance attendue d'un répondant aléatoire. Sans cette colonne, un
    -- modèle à 30 % sur des QCM à 4 choix se lit comme un résultat moyen alors
    -- qu'il fait moins bien que le hasard.
    1.0 / q.n_choices as random_baseline
from {{ ref('stg_ai_answers') }} a
inner join {{ ref('stg_questions') }} q using (question_id)
inner join {{ ref('prompt_catalog') }} p using (prompt_version)
