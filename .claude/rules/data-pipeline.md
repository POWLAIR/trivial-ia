---
paths:
  - "src/trivia_bench/**/*.py"
---

<!-- Règle à portée limitée : chargée quand Claude lit `src/trivia_bench/**/*.py` -->

# Pipeline de données — bronze, silver, enrichissement

Spécifications de référence : `docs/01-architecture.md`, `docs/02-ingestion-opentdb.md`, `docs/03-enrichissement-ia.md`.

## Contrats de données — ne pas modifier sans PR dédiée

Ces schémas sont le contrat entre les trois membres du groupe. Les changer casse l'étage aval.

### Bronze — `data/bronze/questions_raw.csv`

- Colonnes API conservées **non renommées** : `category`, `type`, `difficulty`, `question`, `correct_answer`, `incorrect_answers`.
- Métadonnées d'ingestion autorisées : `fetched_at`, `source_category_id`.
- **Aucune transformation.** Les entités HTML (`&quot;`, `&#039;`) restent telles quelles : le décodage appartient à la couche silver. Bronze est la photographie de la source.

### Silver — `data/silver/questions.parquet`

- Clé primaire `question_id` : hash SHA-256 de `question` + `correct_answer`. **Déterministe** — c'est ce qui rend l'enrichissement reprenable et les jointures stables entre exécutions.
- Nettoyage : `html.unescape`, normalisation NFKC, espaces normalisés, `incorrect_answers` parsé en vraie liste, `category` éclatée sur `": "` pour dériver `category_group`.
- Déduplication sur `question_id` : OpenTDB expose des doublons entre catégories, c'est normal.

### Silver — `data/silver/ai_answers.parquet`

- Grain et clé unique : **`(question_id, model, prompt_version)`**.
- `ai_answer_raw` conservé intact à côté de `ai_answer` normalisée.
- `ai_correct` booléen, `NULL` si l'appel a échoué — **jamais `False`**.
- `response_time` en secondes, strictement positif.
- Colonnes obligatoires également : `n_eval_tokens`, `match_rule`, `run_id`, `answered_at`, `error`.

## Ingestion OpenTDB

- **50 questions maximum par appel** (`amount=50`), **une seule catégorie par appel**, et **l'API n'a pas d'offset**.
- Le **jeton de session** est donc obligatoire : c'est la seule façon de balayer le dataset sans doublon. Il expire après **6 h d'inactivité** (`api_token.php?command=reset` pour le réinitialiser).
- 🔴 **`response_code = 4` n'est PAS un signal d'arrêt fiable.** La doc annonce un code 1 quand on demande plus de questions qu'il n'en reste ; l'API renvoie en réalité un code 4, identique à celui de l'épuisement. Vérifié : demander 50 questions à une catégorie qui en a 36 renvoie `code=4, results=0`, alors que `amount=36` renvoie les 36. **S'arrêter sur le code 4 perdrait le dernier lot partiel de chaque catégorie, soit ~11 % du dataset, en silence.**
- **Parade** : ne jamais demander plus que `expected - collected`, l'effectif attendu venant de `api_count_global.php`. Le code 4 ne conclut à l'épuisement qu'après une dichotomie descendante infructueuse.
- Codes à gérer : `0` succès, `1` et `4` → repli sur un `amount` plus petit, `2` paramètre invalide (échouer bruyamment), `3` jeton expiré (renouveler), `5` débit dépassé (backoff).
- **Throttle 5,2 s** entre *tous* les appels, endpoints d'aide compris : la limite est par IP, pas par endpoint.
- 🔴 **La limite de débit se manifeste aussi en HTTP 429**, sans corps JSON donc sans `response_code` à tester. L'intercepter au niveau du transport, pas seulement via le code 5. Backoff exponentiel (5, 10, 20, 40 s), 5 tentatives.
- Toujours tester `response_code` avant de lire `results`.
- **Volumétrie réelle : 5 298 questions**, pas les 21 617 annoncées — 10 911 sont en attente de validation et 5 425 rejetées, et l'API ne sert que les questions *vérifiées*.
- Contrôle d'exhaustivité par catégorie, tracé dans `data/bronze/_ingestion_report.json`.

## Enrichissement LM Studio

- Endpoint compatible OpenAI lu depuis **`LLM_BASE_URL`** (`.env`), jamais en dur. Ollama expose la même interface : changer de runtime ne doit coûter qu'une variable.
- Paramètres figés : **`temperature=0`, `seed=42`, `max_tokens=32`**.
- `response_time` mesuré par `time.perf_counter()` **autour du seul appel réseau**.
- `n_eval_tokens` = `usage.completion_tokens` : distingue un modèle lent d'un modèle verbeux.
- **Appel de préchauffage exclu des mesures** ; précharger via `lms load`. Vérifier `lms ps` : un seul modèle chargé, sinon les temps mesurent la contention mémoire.
- **`--workers 1` par défaut.** Le parallélisme fausse `response_time`.
- Clé de modèle = sortie de `lms ls`, jamais un nom recopié depuis la doc.
- 🔴 **Écarter les modèles à raisonnement.** Qwen3 et Phi-4-mini-reasoning émettent leur réflexion dans `reasoning_content` et laissent `content` **vide** : avec `max_tokens=32` ils scorent 0 %, ce qui mesure leur format de sortie, pas leur culture générale. Vérifié sur `qwen/qwen3-1.7b`. Le suffixe `/no_think` débloque le contenu mais dégrade nettement les réponses. Modèles retenus : famille **gemma-3**, qui répond en 4-5 tokens.
- **Un seul modèle résident.** `lms unload --all` avant chaque `lms load` (attention : `--all` n'accepte pas `-y`). Deux modèles chargés saturent la RAM et faussent `response_time`.

## Prompts

- Catalogue **versionné** dans `enrich/prompts.py`. Chaque réponse stockée porte son `prompt_version`.
- Ajouter une version, ne jamais éditer une version existante : cela invaliderait silencieusement les résultats déjà collectés.
- `v3_mcq` fournit les options : il n'est **pas comparable** aux prompts en génération libre.

## Matching — `ai_correct`

Cascade, première règle qui statue :

1. `exact` — égalité après normalisation
2. `boolean` — `true`/`false`, `yes`/`no` pour les questions `boolean`
3. `option_substring` — recherche des options avec **frontières de mots** (`\b`), sinon « 1979 » matcherait dans « 11979 ». Quand plusieurs options se chevauchent au même endroit, **la plus longue l'emporte** : sans cela « Dark Red » déclencherait deux correspondances (« Red » y est contenu) et la bonne réponse serait rejetée pour ambiguïté — un faux négatif systématique sur les catégories aux options emboîtées. L'ambiguïté n'est déclarée que pour deux options **disjointes** → incorrect
4. `fuzzy` — `difflib.SequenceMatcher` ≥ 0,90
5. `none` — incorrect

- Normalisation appliquée **aux deux chaînes** : unescape, NFKD sans diacritiques, minuscules, article initial retiré, ponctuation retirée, espaces normalisés.
- **`match_rule` toujours enregistrée** : sans elle, le matching n'est pas auditable.
- En cas de doute, compter faux.

## Reprise et robustesse

- Au démarrage, lire `ai_answers.parquet` et retirer les triplets déjà traités : une exécution interrompue reprend où elle s'est arrêtée.
- **`--limit N` doit produire des échantillons emboîtés** : mélange déterministe puis `head(N)`, jamais `sample(n=N)`. Les 200 premières font alors partie des 500 premières, et agrandir l'échantillon plus tard ne coûte que le complément. Avec `sample(n=N)`, deux tailles donnent deux tirages disjoints et tout serait à recalculer.
- Écriture par lots de 100 dans `data/silver/_ai_answers_parts/`, consolidés en fin de run.
- Timeout, modèle non chargé, sortie vide : écrire la ligne avec `error` renseigné et `ai_correct = NULL`.
