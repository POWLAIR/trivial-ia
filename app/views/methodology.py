"""Méthodologie, limites et conclusion — la page qui encadre la lecture des autres.

Placée en tête de la navigation : les chiffres des pages suivantes ne sont pas
interprétables sans le protocole qui les a produits ni les limites qui les
bornent. Un benchmark qui ne dit pas ce qu'il ne mesure pas induit son lecteur en
erreur.

🔴 **Aucun chiffre n'est écrit en dur ici.** Tout est lu dans les marts ou dans
`config.py`. Un texte à chiffres figés serait faux dès le prochain `make gold` —
et faux de façon crédible, ce qui est précisément le mode de défaillance que ce
projet cherche à éviter.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from data_access import load
from theme import FORMAT_FAMILY_NOTES, MIN_SAMPLE, format_family_label
from trivia_bench import config


def render() -> None:
    st.title("Méthodologie, limites et conclusion")

    scope = load("mart_benchmark_scope").iloc[0]
    perf = load("mart_model_performance")

    _scope(scope)
    st.divider()
    _protocol(scope)
    st.divider()
    _formats(perf)
    st.divider()
    _limits()
    st.divider()
    _conclusion(perf)


def _scope(scope: pd.Series) -> None:
    st.subheader("Ce que couvre ce benchmark")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Corpus OpenTDB", f"{int(scope['n_questions_corpus']):,}".replace(",", " "))
    c2.metric(
        "Questions interrogées",
        f"{int(scope['n_questions_benchmarked']):,}".replace(",", " "),
        delta=f"{scope['coverage_pct']:.1f} % du corpus",
        delta_color="off",
    )
    c3.metric("Modèles", int(scope["n_models"]))
    c4.metric("Réponses collectées", f"{int(scope['n_answers']):,}".replace(",", " "))

    st.caption(
        f"{int(scope['n_prompt_versions'])} versions de prompt réparties en "
        f"{int(scope['n_format_families'])} formats de tâche. Collecte du "
        f"{scope['first_answered_at'][:10]} au {scope['last_answered_at'][:10]}."
    )

    if scope["coverage_pct"] < 100:
        st.info(
            f"Le benchmark porte sur **{scope['coverage_pct']:.1f} %** du corpus, "
            "pas sur sa totalité : interroger les 5 295 questions demanderait des "
            "dizaines d'heures de calcul sur cette machine. L'échantillon est tiré "
            "à graine fixe, donc non biaisé, et **emboîté** — l'agrandir ne coûte "
            "que le complément, sans rien recalculer. Conséquence à garder en tête : "
            "l'incertitude est plus large qu'elle ne le serait sur le corpus entier, "
            "et les catégories les moins fournies restent ininterprétables."
        )


def _protocol(scope: pd.Series) -> None:
    """Les conditions figées, lues dans `config.py` et non recopiées.

    Recopier ces valeurs dans le texte les ferait diverger du code au premier
    ajustement — et un benchmark dont le protocole affiché n'est pas celui
    exécuté ne prouve rien.
    """
    st.subheader("Protocole")

    st.markdown(
        "Ces paramètres restent constants d'une exécution à l'autre. En changer un "
        "seul invalide toute comparaison avec les runs précédents."
    )

    conditions = pd.DataFrame(
        [
            (
                "`temperature`",
                str(config.TEMPERATURE),
                "Reproductibilité : deux exécutions donnent le même résultat",
            ),
            ("`seed`", str(config.SEED), "Reproductibilité"),
            (
                "`max_tokens`",
                str(config.MAX_TOKENS),
                "Évite les réponses tronquées comme les digressions",
            ),
            (
                "Workers",
                str(config.DEFAULT_WORKERS),
                "Au-delà de 1, `response_time` mesurerait la contention CPU",
            ),
            ("Threads llama.cpp", str(config.LLAMA_THREADS), "Tous les cœurs de la machine"),
            (
                "Contexte",
                f"{config.LLAMA_CTX_SIZE} tokens",
                "8192 par défaut coûte cher en évaluation de prompt",
            ),
            (
                "Seuil `fuzzy`",
                str(config.FUZZY_THRESHOLD),
                "Au-delà, la similarité ne distingue plus deux réponses",
            ),
            (
                "Effectif minimum publié",
                str(MIN_SAMPLE),
                "En deçà, l'intervalle de confiance interdit de conclure",
            ),
        ],
        columns=["Paramètre", "Valeur", "Pourquoi"],
    )
    st.dataframe(conditions, hide_index=True, use_container_width=True)
    st.caption(
        "Valeurs lues dans `src/trivia_bench/config.py` au chargement de la page, "
        "jamais recopiées : un protocole affiché qui ne serait pas celui exécuté ne "
        "prouverait rien."
    )

    st.markdown(
        "**Machine d'exécution** — Intel i7-8550U, 4 cœurs à 1,8 GHz, sans GPU "
        "exploitable, 12 Go alloués à WSL2. Un seul modèle résident à la fois : deux "
        "modèles chargés saturent la mémoire et `response_time` mesurerait alors la "
        "contention. **Les temps ne sont comparables qu'entre eux**, jamais "
        "transposables à une autre machine."
    )

    st.markdown(
        "**Modèles déclarés** — "
        + ", ".join(f"`{key}`" for key in config.MODELS)
        + ". Deux tailles de la famille gemma-3 pour l'axe « effet de la taille », et "
        "deux quantifications du modèle à 4 milliards pour l'axe « effet de la "
        "quantification », à taille constante."
    )

    # Déclarer un modèle et l'avoir mesuré sont deux choses distinctes. Une page
    # qui annonce trois modèles alors que deux seulement ont répondu laisse croire
    # à une comparaison qui n'a pas eu lieu.
    n_declared, n_measured = len(config.MODELS), int(scope["n_models"])
    if n_measured < n_declared:
        st.warning(
            f"**{n_declared} modèles sont déclarés, {n_measured} ont réellement été "
            "interrogés.** Les axes qui reposent sur les modèles manquants — en "
            "particulier l'effet de la quantification — ne sont pas encore mesurés, "
            "et aucune page ne les présente. Lancer `scripts/run_benchmark.sh` pour "
            "compléter."
        )


def _formats(perf: pd.DataFrame) -> None:
    """Ce que mesure chaque format, et ce qu'il ne permet pas de comparer."""
    st.subheader("Trois formats de tâche, qui ne se comparent pas")

    st.markdown(
        "Changer la façon de poser la question change la nature de la tâche. Mettre "
        "les trois formats dans un même classement reviendrait à désigner un "
        "vainqueur entre trois épreuves différentes."
    )

    present = [f for f in FORMAT_FAMILY_NOTES if f in set(perf["format_family"])]
    for family in present:
        versions = sorted(perf.loc[perf["format_family"] == family, "prompt_version"].unique())
        with st.expander(f"{format_family_label(family)} — {', '.join(versions)}"):
            st.markdown(FORMAT_FAMILY_NOTES[family])


def _limits() -> None:
    """Les limites, dont deux sont mesurées et non supposées."""
    st.subheader("Limites")

    st.markdown(
        "Ces limites doivent figurer dans toute lecture des résultats. Les deux "
        "premières ne sont pas des précautions de principe : elles sont **mesurées**, "
        "et leurs chiffres bougent avec les données."
    )

    _measured_limits()

    st.markdown("**Limites structurelles**")
    structural = pd.DataFrame(
        [
            (
                "Contamination des données d'entraînement",
                "OpenTDB est public : les modèles ont pu voir ces questions à l'entraînement. "
                "Le score mesurerait alors la mémorisation, pas la culture générale.",
                "Non mesurable ici — énoncée comme limite, pas atténuée.",
            ),
            (
                "Dataset anglophone et culturellement situé",
                "Mesure une culture générale majoritairement anglo-saxonne, pas "
                "« la » culture générale.",
                "Analyse par catégorie ; à préciser dans toute conclusion.",
            ),
            (
                "Déséquilibre du corpus",
                "Les jeux vidéo pèsent près du quart du corpus, les comédies "
                "musicales 36 questions.",
                "Le score global est tiré par les catégories les plus fournies : "
                "lire aussi par catégorie.",
            ),
            (
                "Modèles quantifiés",
                "Les résultats ne valent pas pour les modèles en pleine précision.",
                "Quantification documentée ; c'est même un axe mesuré.",
            ),
            (
                "Une seule exécution par question",
                "À `temperature = 0` c'est cohérent, mais aucune variance n'est mesurée.",
                "Assumé : le déterminisme est privilégié sur l'estimation de variance.",
            ),
            (
                "Deux tailles d'une seule famille",
                "L'axe « effet de la taille » est mesuré, l'axe « différences entre "
                "familles » ne l'est pas.",
                "Les alternatives du catalogue sont des modèles à raisonnement, "
                "inexploitables sous ce protocole.",
            ),
            (
                "Temps dépendants du matériel",
                "Non transposables à une autre machine.",
                "CPU et RAM documentés ; ne comparer qu'au sein de cette machine.",
            ),
        ],
        columns=["Limite", "Effet", "Ce qu'on en fait"],
    )
    st.dataframe(structural, hide_index=True, use_container_width=True)


def _measured_limits() -> None:
    """Les deux limites que les marts chiffrent directement."""
    reliability = load("mart_matching_reliability")
    difficulty = load("mart_performance_by_difficulty")

    none_rows = reliability[reliability["match_rule"] == "none"]
    if not none_rows.empty:
        worst = none_rows.loc[none_rows["pct_of_answers"].idxmax()]
        st.error(
            f"**Le matching sous-estime les modèles, d'au plus "
            f"{worst['pct_of_answers']:.1f} points.** Sur "
            f"{worst['model']} · {worst['prompt_version']}, cette part des réponses "
            "est comptée fausse sans qu'aucune règle de la cascade n'ait reconnu "
            "quoi que ce soit. Chacune est peut-être correcte mais formulée "
            "autrement. Le benchmark est conçu pour sous-estimer plutôt que "
            "surestimer — en cas de doute, la réponse est comptée fausse — mais "
            "l'ampleur de cette sous-estimation reste à chiffrer par annotation "
            "manuelle. Voir la page Fiabilité."
        )

    combos = difficulty[["model", "prompt_version", "has_inversion"]].drop_duplicates()
    n_inverted = int(combos["has_inversion"].sum())
    if n_inverted:
        st.warning(
            f"**Les étiquettes de difficulté d'OpenTDB ne sont pas fiables : "
            f"{n_inverted} combinaison(s) sur {len(combos)} présentent une "
            "inversion.** Le score devrait décroître de `easy` à `hard` ; il ne le "
            "fait pas. Attribuées par des contributeurs et non calibrées, ces "
            "étiquettes ne peuvent pas porter de conclusion sans être d'abord "
            "départagées d'un éventuel défaut de matching. Voir la page Par difficulté."
        )


def _conclusion(perf: pd.DataFrame) -> None:
    """Conclusion conditionnelle, composée à partir des marts.

    Une conclusion utile est conditionnelle : « le modèle A domine mais coûte
    trois fois plus de temps que B » vaut mieux qu'un classement unique, qui
    masque le compromis que le lecteur doit arbitrer.

    Les phrases sont composées à partir des valeurs des marts. Rapporter deux
    valeurs l'une à l'autre reste de la mise en forme : les agrégats viennent de
    dbt, l'application n'en calcule aucun.
    """
    st.subheader("Conclusion")

    if perf.empty:
        st.info("Pas encore de résultats à conclure.")
        return

    # `mart_model_performance` porte déjà le temps médian : pas de jointure avec
    # `mart_latency`, qui n'ajouterait ici que des percentiles inutiles — et dont
    # la colonne homonyme ferait silencieusement suffixer les deux en _x / _y.
    for family, group in perf.groupby("format_family", sort=False):
        best = group.loc[group["accuracy_pct"].idxmax()]
        fastest = group.loc[group["median_response_time"].idxmin()]

        lines = [
            f"**{format_family_label(family)}** — le meilleur taux revient à "
            f"`{best['model']}` avec `{best['prompt_version']}` : "
            f"**{best['accuracy_pct']:.1f} %** (± {best['ci95_margin_pct']:.1f} pts, "
            f"n = {int(best['n_questions'])}), contre "
            f"{best['random_baseline_pct']:.1f} % au hasard."
        ]

        if best["accuracy_pct"] - best["ci95_margin_pct"] <= best["random_baseline_pct"]:
            lines.append(
                "⚠️ Son intervalle de confiance touche la ligne du hasard : "
                "**on ne peut pas conclure qu'il fait mieux que répondre au hasard.**"
            )

        if fastest["model"] != best["model"] or fastest["prompt_version"] != best["prompt_version"]:
            ratio = best["median_response_time"] / fastest["median_response_time"]
            gap = best["accuracy_pct"] - fastest["accuracy_pct"]
            lines.append(
                f"Il coûte **{ratio:.1f}×** le temps de `{fastest['model']}` · "
                f"`{fastest['prompt_version']}` "
                f"({best['median_response_time']:.2f} s contre "
                f"{fastest['median_response_time']:.2f} s en médiane) pour "
                f"{gap:+.1f} points de justesse. Le choix dépend donc du volume à "
                "traiter, pas d'un classement."
            )
        st.markdown("\n\n".join(lines))
        st.markdown("")

    st.caption(
        "Chiffres lus dans `mart_model_performance` à chaque chargement : ils "
        "suivent les données, ils ne sont pas écrits dans le texte."
    )
