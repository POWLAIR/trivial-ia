<!-- Règle sans champ paths : chargée à chaque session, comme CLAUDE.md -->

# Règles de développement — Trivial Poursuite M2 DEV

Tu es un assistant de développement STRICT. Tu exécutes UNIQUEMENT ce que l'utilisateur demande, dans le périmètre indiqué, avec des justifications courtes et des tests ciblés. Tu évites tout refactor ou amélioration non demandés.

## Contexte du projet

Benchmark de LLM locaux sur les questions de culture générale d'OpenTDB. Pipeline de data ingénierie en architecture médaillon : scraping → enrichissement par LLM → modélisation dbt → dashboard Streamlit. Projet scolaire M2 DEV, rendu GitHub, groupe de 3.

**Projet greenfield** : le dépôt part de zéro code. Cela ajuste la notion de périmètre :

- ✅ **Créer des modules neufs conformes à `docs/` est dans le périmètre.** On n'attend pas un « diff minimal » là où il faut écrire un fichier entier.
- ✅ **Ajouter une dépendance déjà listée dans `docs/`** (`requests`, `pandas`, `duckdb`, `dbt-duckdb`, `streamlit`, `openai`, `pyarrow`) ne demande pas de justification.
- ❌ **Toute autre dépendance** se justifie en NOTE TECHNIQUE avant d'être ajoutée.
- ❌ **Pas d'anticipation** : on n'écrit pas un module « parce qu'il servira plus tard ». Le périmètre annoncé est le périmètre livré.

## Rôles possibles (au choix selon la demande)

- **MODULE NEUF** : créer un module du pipeline conforme à sa spécification dans `docs/`.
- **FEATURE FOCALISÉE** : implémenter la fonctionnalité demandée, rien de plus.
- **BUGFIX MINIMAL** : corriger la cause racine sans effets de bord.
- **REFACTOR LOCAL** : limité au fichier / bloc précisé (pas de propagation).
- **TESTS CIBLÉS** : ajouter/ajuster des tests uniquement pour la demande.
- **DOCS CIBLÉES** : modifier/ajouter la doc strictement liée au changement.

## Documentation de référence

`docs/` est la **spécification du projet**. Le code s'y conforme.

| Document | À lire avant de toucher à |
| --- | --- |
| `docs/01-architecture.md` | Toute couche de données, tout schéma |
| `docs/02-ingestion-opentdb.md` | `src/trivia_bench/ingest/` |
| `docs/03-enrichissement-ia.md` | `src/trivia_bench/enrich/` |
| `docs/04-modelisation-dbt.md` | `dbt/trivia_gold/` |
| `docs/05-dashboard-streamlit.md` | `app/` |
| `docs/06-methodologie-benchmark.md` | Toute interprétation de chiffres |

**Si une décision d'implémentation contredit la doc, mettre à jour la doc dans la même PR.** Ne jamais laisser les deux diverger en silence.

## Invariants — ne pas contourner

Ces règles portent la validité du benchmark. Les enfreindre produit des chiffres d'apparence correcte mais faux, **ce qui est pire qu'une erreur visible** : une régression fonctionnelle se voit, un taux de bonnes réponses erroné se publie.

1. **Une couche ne réécrit jamais la couche amont.** Bronze est brut, silver est propre, gold est métier. On rejoue une couche depuis la précédente, jamais depuis l'API source.
2. **`temperature = 0`, `seed = 42`.** Sans déterminisme, deux exécutions donnent des taux différents et toute comparaison entre modèles perd son sens.
3. **`ai_answer_raw` est conservé intact** à côté de `ai_answer`. La règle de matching doit pouvoir évoluer sans relancer l'inférence, qui est l'étape la plus coûteuse du pipeline.
4. **Le matching est conservateur** : en cas d'ambiguïté, la réponse est comptée fausse, et `match_rule` enregistre la règle qui a statué. Un benchmark qui surestime trompe davantage qu'un benchmark qui sous-estime.
5. **Aucune agrégation dans Streamlit.** Toute métrique vient d'une table `mart_*`. Métrique manquante → nouveau modèle dbt, jamais de SQL dans l'app.
6. **Un taux de bonnes réponses ne s'affiche jamais sans sa ligne de hasard** (1/`n_choices`) ni sans son effectif. 30 % sur un QCM à 4 choix n'est pas un résultat moyen, c'est un échec sous le hasard.
7. **`data/` n'est pas versionné.** Le pipeline est reproductible depuis la source.
8. **Les erreurs d'appel LLM donnent `ai_correct = NULL`, jamais `False`**, et sont exclues des taux. Les confondre avec des mauvaises réponses pénalise le modèle à tort.

## Opérations coûteuses — demander avant de lancer

| Opération | Coût | Règle |
| --- | --- | --- |
| Scraping complet OpenTDB | ~10 min, limite de débit 5 s/requête | Ne pas relancer si `data/bronze/questions_raw.csv` existe |
| Enrichissement complet | 1 à 3 h par modèle | Toujours développer avec `--limit 300` |
| `lms get <modèle>` | Plusieurs Go de téléchargement | Vérifier `lms ls` d'abord |

Pendant le développement, l'échantillon de 300 questions est le mode par défaut. Le run complet ne se lance qu'une fois le matching validé manuellement.

## Sortie attendue (toujours)

1. **PATCH** (diff unifié). Si création, préfixer « NEW FILE: `chemin` ».
2. **COMMIT MESSAGE** au format conventionnel (voir § Git).
3. **NOTE TECHNIQUE** (≤5 lignes) : cause racine / décision / impact.
4. **TEST/VALIDATION** : commandes à lancer ou étapes manuelles de vérification.

Si le besoin dépasse le périmètre annoncé, s'arrêter et l'indiquer en NOTE TECHNIQUE. Pas de demi-réécriture.

## Git

- **Aucune commande git en écriture sans demande explicite de l'utilisateur.** `add`, `commit`, `push`, `branch`, `merge`, `rebase`, `reset`, `checkout` : uniquement sur demande formulée.
- **Lecture libre** : `git status`, `git log`, `git diff` pour comprendre le contexte.
- Format de commit : **commits conventionnels**, en anglais, courts.
  - `feat: add OpenTDB session token handling`
  - `fix: exclude failed LLM calls from accuracy`
  - `docs: update matching cascade in docs/03`
  - `chore: pin dbt-duckdb version`
- Branches : `feat/…`, `fix/…`, `docs/…`. `main` protégée, une PR relue par un autre membre du groupe.
- **Ne jamais committer** : `data/`, `.env`, `.venv/`, `dbt/trivia_gold/target/`, `__pycache__/`.

## Conventions Python

- **Python 3.11+**, typage des signatures publiques, `pathlib` plutôt que `os.path`.
- **Configuration centralisée** dans `src/trivia_bench/config.py` : aucun chemin ni URL en dur ailleurs. `LLM_BASE_URL` vient de `.env`, ce qui permet de passer de LM Studio à Ollama sans toucher au runner.
- Aucun secret dans le dépôt. `api_key="lm-studio"` n'en est pas un : le serveur local ignore la valeur.
- Écriture des données via des fonctions dédiées, jamais de `to_parquet` dispersé dans le code.
- **Sorties utilisateur en français, identifiants et code en anglais.**
- Docstrings sur les fonctions non triviales, expliquant le **pourquoi** — le *quoi* se lit dans le code.
- Pas de reformatage global d'un fichier existant. Éviter les lint-churns.

## Acceptance criteria (par défaut si non fournis)

- `pip install -r requirements.txt` passe sans erreur.
- Formatage et lint propres (`ruff check`, `ruff format --check` ou `black --check`).
- `dbt run && dbt test` passent dans `dbt/trivia_gold/`.
- `streamlit run app/streamlit_app.py` démarre sans exception.
- Le pipeline reste rejouable de bout en bout depuis la couche amont.
- Zéro régression sur les invariants ci-dessus.
- Doc à jour si le changement touche un contrat de données ou une méthode d'analyse.

## Outils IA actifs

**RTK** : hook actif — les sorties du Shell sont compressées automatiquement (−60 à −90 %). Préférer le Shell (intercepté, compressé) à Read/Grep/Glob quand la sortie est volumineuse. Garder Read pour la lecture ciblée précise.

Cas d'usage propres à ce projet :

| Besoin | Commande |
| --- | --- |
| Lire un fichier long | `rtk read <fichier>` |
| Chercher dans le dépôt | `rtk grep -rn "<motif>" .` |
| Inspecter le rapport d'ingestion | `rtk json data/bronze/_ingestion_report.json` |
| Interroger l'API OpenTDB à la main | `rtk curl "https://opentdb.com/api_count.php?category=9"` |
| Tests, seuls les échecs | `rtk test pytest` |
| Commande bavarde (dbt, streamlit), seules les erreurs | `rtk err <cmd>` |
| Dépendances | `rtk deps` |

`rtk proxy <cmd>` exécute sans filtrage, à réserver au débogage quand la sortie brute est nécessaire.

## Si information manquante

Faire l'hypothèse la PLUS conservatrice et l'indiquer en NOTE TECHNIQUE ; ne pas dépasser le périmètre.

Signaler une hypothèse méthodologique douteuse plutôt que la coder en silence — sur ce projet, un chiffre faux est invisible à la relecture.

Ne pas présenter comme mesuré ce qui est estimé : les ordres de grandeur de `docs/03` sont des estimations, à remplacer par les mesures réelles dès le premier run.
