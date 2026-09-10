# 01 — Architecture médaillon

L'architecture médaillon organise les données en trois couches successives, chacune
avec une responsabilité unique. La règle structurante : **une couche ne réécrit
jamais la couche amont**. En cas d'erreur de traitement, on rejoue la couche
concernée à partir de la précédente, sans jamais retourner à l'API source.

```
OpenTDB ──▶ BRONZE ──▶ SILVER ──▶ GOLD ──▶ Streamlit
            (CSV)     (Parquet)  (DuckDB)
```

---

## Couche bronze — données brutes

**Emplacement** : `data/bronze/questions_raw.csv`
**Format** : CSV, une ligne par question, tel que renvoyé par l'API.
**Règle** : aucune transformation. Les entités HTML (`&quot;`, `&#039;`) et
l'encodage d'origine sont **conservés**. La couche bronze est la photographie de
la source à un instant donné.

| Colonne | Type | Description |
| --- | --- | --- |
| `category` | string | Catégorie OpenTDB (« Science: Computers », …) |
| `type` | string | `multiple` ou `boolean` |
| `difficulty` | string | `easy`, `medium` ou `hard` |
| `question` | string | Énoncé, entités HTML incluses |
| `correct_answer` | string | Réponse attendue |
| `incorrect_answers` | string | Liste JSON des distracteurs |
| `fetched_at` | timestamp | Date de collecte (ajoutée par l'ingestion) |
| `source_category_id` | int | Identifiant de catégorie interrogé |

Les deux dernières colonnes sont des métadonnées d'ingestion, pas des
transformations : elles documentent *quand* et *comment* la ligne a été obtenue.

---

## Couche silver — données propres et exploitables

**Emplacement** : `data/silver/`
**Format** : Parquet (typage préservé, compression, lecture directe par DuckDB).

### `questions.parquet`

Issu de `questions_raw.csv` par nettoyage et normalisation.

| Colonne | Type | Description |
| --- | --- | --- |
| `question_id` | string | **Clé primaire** — hash SHA-256 de `question` + `correct_answer` |
| `category` | string | Catégorie complète, décodée |
| `category_group` | string | Racine de la catégorie (« Science », « Entertainment ») |
| `type` | string | `multiple` / `boolean` |
| `difficulty` | string | `easy` / `medium` / `hard` |
| `question` | string | Énoncé décodé (HTML unescape), espaces normalisés |
| `correct_answer` | string | Réponse décodée |
| `incorrect_answers` | list\<string\> | Distracteurs décodés |
| `n_choices` | int | 2 ou 4 |
| `question_length` | int | Longueur de l'énoncé en caractères |

Règles de nettoyage appliquées :

1. Décodage des entités HTML (`html.unescape`).
2. Normalisation Unicode NFKC et des espaces (`\s+` → espace simple, `strip`).
3. Éclatement de `category` sur `": "` pour dériver `category_group`.
4. `incorrect_answers` parsé depuis sa représentation JSON vers une vraie liste.
5. Déduplication sur `question_id` : OpenTDB expose des doublons entre catégories.

`question_id` est **déterministe** : le même énoncé produit toujours le même
identifiant, ce qui rend l'enrichissement reprenable et les jointures stables
entre exécutions.

### `ai_answers.parquet`

Une ligne par **(question, modèle, version de prompt)**.

| Colonne | Type | Description |
| --- | --- | --- |
| `question_id` | string | **Clé étrangère** vers `questions.parquet` |
| `model` | string | Clé du modèle telle qu'exposée par `lms ls` (`llama-3.2-3b-instruct`) |
| `prompt_version` | string | Identifiant du prompt (`v1`, `v2`, `v3`) |
| `ai_answer_raw` | string | Sortie brute du modèle, non modifiée |
| `ai_answer` | string | Réponse normalisée pour comparaison |
| `ai_correct` | boolean | `True` si `ai_answer` correspond à `correct_answer` |
| `response_time` | double | Temps de génération en secondes |
| `n_eval_tokens` | int | Nombre de tokens générés (`usage.completion_tokens`) |
| `run_id` | string | Identifiant d'exécution du batch |
| `answered_at` | timestamp | Horodatage de la génération |
| `error` | string | Message d'erreur si l'appel a échoué, sinon `null` |

`ai_answer_raw` est conservé à côté de `ai_answer` : si la règle de matching
évolue, on recalcule `ai_correct` sans relancer l'inférence — l'étape la plus
coûteuse du pipeline.

La clé unique de la table est le triplet `(question_id, model, prompt_version)`.

---

## Couche gold — données métier

**Emplacement** : `data/gold/benchmark.duckdb`
**Construction** : `dbt run` (adaptateur `dbt-duckdb`), qui lit directement les
Parquet silver via `read_parquet()`.

Chaque table gold répond à **une** question métier ; elle est directement
consommable par le dashboard sans agrégation supplémentaire.

| Modèle | Grain | Question métier |
| --- | --- | --- |
| `fct_answers` | question × modèle × prompt | Table de faits, jointure silver enrichie |
| `mart_model_performance` | modèle × prompt | Quel modèle / prompt est le meilleur globalement ? |
| `mart_performance_by_category` | modèle × catégorie | Sur quels thèmes le modèle échoue-t-il ? |
| `mart_performance_by_difficulty` | modèle × difficulté | La difficulté OpenTDB discrimine-t-elle ? |
| `mart_latency` | modèle | Quel est le coût en temps de réponse ? |
| `mart_prompt_impact` | prompt × modèle | Quel est l'effet de la formulation du prompt ? |

Le détail des modèles est documenté dans [04 — Modélisation dbt](04-modelisation-dbt.md).

---

## Contrats de données

Ces contrats permettent aux trois membres du groupe de travailler en parallèle.
Toute modification se discute en PR, car elle casse l'étage aval.

| Frontière | Contrat |
| --- | --- |
| bronze → silver | Les 6 colonnes de l'API sont présentes et non renommées |
| silver → enrichissement | `questions.parquet` expose `question_id` unique et non nul |
| enrichissement → gold | `ai_answers.parquet` est unique sur `(question_id, model, prompt_version)` et `response_time > 0` |
| gold → dashboard | Les tables `mart_*` sont lues en **lecture seule**, sans agrégation côté Streamlit |

Ces contrats sont vérifiés automatiquement par les tests dbt
(`unique`, `not_null`, `relationships`) décrits en [04](04-modelisation-dbt.md).

---

## Idempotence et rejouabilité

- **Bronze** : réécrit intégralement à chaque exécution ; l'ancien fichier est
  archivé sous `data/bronze/archive/questions_raw_<date>.csv`.
- **Silver questions** : fonction pure de bronze — rejouable à volonté.
- **Silver ai_answers** : écrit en mode *append idempotent*. Au démarrage, le
  runner lit les triplets `(question_id, model, prompt_version)` déjà présents et
  ne réinterroge que le complément. Une exécution interrompue reprend où elle
  s'est arrêtée.
- **Gold** : `dbt run` reconstruit les modèles en `table` — pas d'état résiduel.
