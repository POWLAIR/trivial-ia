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

- **50 questions maximum par appel** (`amount=50`), et **l'API n'a pas d'offset**.
- Le **jeton de session** est donc obligatoire : c'est la seule façon de balayer le dataset sans doublon.
- **`response_code = 4` est le signal d'arrêt** : il prouve l'exhaustivité de la catégorie. Ne pas le traiter comme une erreur.
- Codes à gérer : `0` succès, `1` pas assez de questions, `2` paramètre invalide (échouer bruyamment), `3` jeton expiré (renouveler), `4` épuisé (sortir), `5` débit dépassé (backoff).
- **Throttle 5,2 s** entre requêtes, backoff exponentiel (5, 10, 20, 40 s) plafonné à 5 tentatives.
- Toujours tester `response_code` avant de lire `results`.
- Contrôle d'exhaustivité par `api_count.php`, tracé dans `data/bronze/_ingestion_report.json`.

## Enrichissement LM Studio

- Endpoint compatible OpenAI lu depuis **`LLM_BASE_URL`** (`.env`), jamais en dur. Ollama expose la même interface : changer de runtime ne doit coûter qu'une variable.
- Paramètres figés : **`temperature=0`, `seed=42`, `max_tokens=32`**.
- `response_time` mesuré par `time.perf_counter()` **autour du seul appel réseau**.
- `n_eval_tokens` = `usage.completion_tokens` : distingue un modèle lent d'un modèle verbeux.
- **Appel de préchauffage exclu des mesures** ; précharger via `lms load`. Vérifier `lms ps` : un seul modèle chargé, sinon les temps mesurent la contention mémoire.
- **`--workers 1` par défaut.** Le parallélisme fausse `response_time`.
- Clé de modèle = sortie de `lms ls`, jamais un nom recopié depuis la doc.

## Prompts

- Catalogue **versionné** dans `enrich/prompts.py`. Chaque réponse stockée porte son `prompt_version`.
- Ajouter une version, ne jamais éditer une version existante : cela invaliderait silencieusement les résultats déjà collectés.
- `v3_mcq` fournit les options : il n'est **pas comparable** aux prompts en génération libre.

## Matching — `ai_correct`

Cascade, première règle qui statue :

1. `exact` — égalité après normalisation
2. `boolean` — `true`/`false`, `yes`/`no` pour les questions `boolean`
3. `option_substring` — **une seule** option présente dans la réponse ; plusieurs → ambigu → incorrect
4. `fuzzy` — `difflib.SequenceMatcher` ≥ 0,90
5. `none` — incorrect

- Normalisation appliquée **aux deux chaînes** : unescape, NFKD sans diacritiques, minuscules, article initial retiré, ponctuation retirée, espaces normalisés.
- **`match_rule` toujours enregistrée** : sans elle, le matching n'est pas auditable.
- En cas de doute, compter faux.

## Reprise et robustesse

- Au démarrage, lire `ai_answers.parquet` et retirer les triplets déjà traités : une exécution interrompue reprend où elle s'est arrêtée.
- Écriture par lots de 100 dans `data/silver/_ai_answers_parts/`, consolidés en fin de run.
- Timeout, modèle non chargé, sortie vide : écrire la ligne avec `error` renseigné et `ai_correct = NULL`.
