{#
    Le bloc de mesures qui accompagne tout taux de bonnes réponses.

    Écrit à la main dans chaque mart, il offrirait autant d'occasions de se
    tromper sur la formule de Wald — et un intervalle de confiance faux ne se
    voit pas à la relecture, contrairement à une requête qui plante.

    À utiliser dans un `select ... group by` dont la source porte `ai_correct`
    et `random_baseline` (c'est-à-dire `fct_answers`).
#}
{% macro accuracy_metrics() %}
    count(*)                                                    as n_questions,
    sum(ai_correct::int)                                        as n_correct,
    round(avg(ai_correct::int) * 100, 2)                        as accuracy_pct,
    -- Référence au hasard : 1/n_choices, moyennée car un échantillon mêle des
    -- QCM à 4 choix (25 %) et des vrai/faux (50 %).
    round(avg(random_baseline) * 100, 2)                        as random_baseline_pct,
    -- Demi-largeur de l'intervalle de Wald à 95 % (docs/06 §3). Deux taux dont
    -- les intervalles se recouvrent ne sont pas départagés.
    round(
        1.96 * sqrt(
            avg(ai_correct::int) * (1 - avg(ai_correct::int)) / count(*)
        ) * 100,
        2
    )                                                           as ci95_margin_pct
{% endmacro %}
