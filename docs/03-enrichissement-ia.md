# 03 — Enrichissement par LLM local

**Objectif** : pour chaque question de la couche silver, interroger un modèle local
et produire les colonnes `ai_answer`, `ai_correct` et `response_time`.

Modules : `src/trivia_bench/enrich/{prompts,runner,matching}.py`

---

## 1. Runtime : LM Studio

Le sujet laisse le choix entre Ollama et LM Studio. Le projet utilise **LM Studio**
en mode *headless* : son CLI `lms` et son serveur local suffisent, l'interface
graphique n'est pas nécessaire.

### Installation

```bash
curl -fsSL https://lmstudio.ai/install.sh | bash
export PATH="/home/paul/.lmstudio/bin:$PATH"   # à ajouter au ~/.zshrc

lms daemon up            # démarre le démon llmster
lms server start         # expose l'API locale sur le port 1234
lms server status        # vérification
```

| Commande | Rôle |
| --- | --- |
| `lms daemon up` / `down` / `status` | Cycle de vie du démon |
| `lms server start` / `stop` / `status` | Serveur d'inférence local (port 1234) |
| `lms get <modèle>` | Téléchargement d'un modèle |
| `lms ls` | Modèles présents sur le disque |
| `lms ps` | Modèles actuellement chargés en mémoire |
| `lms load` / `unload <clé>` | Chargement explicite en mémoire |
| `lms log` | Journal des requêtes entrantes/sortantes |

### Choix des modèles

Le benchmark ne vaut que si les modèles sont comparables *à contraintes égales*.
On retient des modèles quantifiés qui tiennent en mémoire sur les machines de
l'équipe :

| Modèle | Taille | Empreinte | Rôle dans le benchmark |
| --- | --- | --- | --- |
| `google/gemma-3-1b` | 1B | 720 Mo (Q4_0, QAT) | Référence rapide |
| `google/gemma-3-4b` | 4B | 3,34 Go (Q4_K_M) | Effet de la taille du modèle |
| `gemma-3-4b-qat` | 4B | 2,36 Go (Q4_0, QAT) | Effet de la quantification, à taille constante |

```bash
lms get -y --gguf google/gemma-3-1b
lms get -y --gguf google/gemma-3-4b
lms get -y --gguf lmstudio-community/gemma-3-4B-it-qat-GGUF
lms ls                      # relever les clés exactes
```

### Pourquoi pas de modèle à raisonnement

Le catalogue LM Studio ne propose plus Llama 3.2 ni Qwen 2.5. Les candidats
restants d'autres familles — `qwen/qwen3-1.7b`, `qwen/qwen3-4b`,
`microsoft/phi-4-mini-reasoning` — sont des **modèles à raisonnement**, et ils
sont inexploitables ici. Mesuré sur `qwen/qwen3-1.7b` :

| Configuration | Résultat |
| --- | --- |
| Prompt v3, `max_tokens=32` | `content` **vide** ; les 32 tokens partent dans `reasoning_content` |
| Prompt v3, `max_tokens=256` | `content` toujours vide : le modèle n'a pas fini de réfléchir |
| Prompt v3 + `/no_think` | Contenu débloqué, mais réponses erratiques : vide, ou « AUSTRALIA » pour la capitale de l'Australie |

Leur faire réserver un budget de tokens suffisant pour raisonner coûterait
~10 s par question, soit plus de 15 h pour un seul modèle sur ce CPU. Un score
obtenu avec `/no_think` mesurerait la suppression de leur mode natif, pas leur
culture générale.

La famille **gemma-3** répond en 4-5 tokens, sans préambule, et se prête donc au
protocole. Le benchmark compare deux tailles de cette famille (1B et 4B), et deux
quantifications du même 4B (Q4_K_M et Q4_0-QAT) : les axes « effet de la taille
du modèle » et « effet de la quantification » restent analysables, l'axe
inter-familles est abandonné et signalé dans les limites.

Ce trio est **calibré pour la machine du projet** : un i7-8550U (4 cœurs à
1,8 GHz, sans GPU exploitable) et 12 Go alloués à WSL. Sur ce processeur,
l'inférence est limitée par la bande passante mémoire : un modèle 7B tournerait
à 2-3 tokens par seconde, ce qui rendrait le dataset complet hors de portée.
Les deux tailles restent nettement séparées, donc l'axe « effet de la taille du
modèle » demeure analysable.

> **Ne pas recopier les noms ci-dessus en dur dans le code.** La clé réellement
> exposée par le serveur dépend de la quantification téléchargée. C'est la sortie
> de `lms ls` qui fait foi : c'est cette chaîne qui part dans `--model` et qui est
> stockée dans la colonne `model`.

Documenter dans le rapport la **machine d'exécution** (CPU/GPU, RAM) et la
quantification retenue : les `response_time` ne sont comparables qu'entre modèles
exécutés sur le même poste, dans la même précision.

### Appel depuis Python

LM Studio expose une API **compatible OpenAI** sur `http://localhost:1234/v1`.
C'est la voie retenue :

```python
import time
from openai import OpenAI

client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

started = time.perf_counter()
response = client.chat.completions.create(
    model="llama-3.2-3b-instruct",
    messages=[{"role": "user", "content": build_prompt(question, version="v3")}],
    temperature=0,      # déterminisme : indispensable pour un benchmark
    max_tokens=32,      # réponse courte attendue
    seed=42,
)
duration = time.perf_counter() - started

answer = response.choices[0].message.content
n_eval_tokens = response.usage.completion_tokens
```

`api_key` est ignorée par le serveur local mais reste obligatoire côté client
OpenAI : n'importe quelle chaîne convient, et il ne s'agit pas d'un secret.

Ce choix a un intérêt qui dépasse LM Studio : **Ollama expose la même interface**
sur `http://localhost:11434/v1`. Changer de runtime revient à changer une URL de
base, sans toucher au runner ni au format de `ai_answers.parquet`. L'URL est donc
lue depuis `.env` (`LLM_BASE_URL`) et non codée en dur.

Le SDK natif `lmstudio` (`pip install lmstudio`) est une alternative, avec des
statistiques d'inférence plus riches via `result.stats`. Il lie en revanche le
code à LM Studio : à réserver si l'on veut exploiter ces métriques
supplémentaires, en vérifiant les noms de champs dans la version installée.

**`temperature = 0`** est un choix méthodologique, pas un détail : avec une
température non nulle, deux exécutions du même benchmark donnent des taux
différents et les comparaisons entre modèles perdent leur sens.

### Mesure du temps de réponse

`response_time` est mesuré côté client avec `time.perf_counter()`, autour du seul
appel réseau. Le serveur étant local, la latence réseau est négligeable devant le
temps d'inférence.

On enregistre également `n_eval_tokens` (`usage.completion_tokens`), qui permet de
distinguer un modèle *lent* d'un modèle simplement *verbeux* — deux défauts que le
temps brut confond.

Le premier appel à un modèle inclut son chargement en mémoire, parfois plusieurs
secondes. Deux précautions :

1. précharger explicitement avec `lms load <clé>` avant le batch ;
2. effectuer un **appel de préchauffage**, exclu des mesures.

Vérifier avec `lms ps` que le modèle attendu — et lui seul — est chargé : deux
modèles résidents se disputent la mémoire et dégradent les temps mesurés.

## 2. Catalogue de prompts

Le sujet insiste sur l'importance de la formulation. On la traite comme une
**variable expérimentale versionnée** : chaque réponse stockée porte son
`prompt_version`, ce qui permet de comparer les formulations sur exactement le
même jeu de questions.

Le catalogue vit dans `src/trivia_bench/enrich/prompts.py` :

```python
PROMPTS = {
    "v1": "{question}",

    "v2": (
        "Answer with the exact answer only, no sentence, no explanation.\n"
        "Question: {question}\n"
        "Answer:"
    ),

    "v3": (
        "You are answering a trivia quiz. Reply with the shortest possible "
        "answer: a name, a date, a word or a number. Do not add punctuation, "
        "explanation or a full sentence.\n"
        "Question: {question}\n"
        "Answer:"
    ),

    "v3_mcq": (
        "You are answering a multiple-choice trivia question. "
        "Reply with exactly one of the proposed options, copied verbatim.\n"
        "Question: {question}\n"
        "Options:\n{options}\n"
        "Answer:"
    ),
}
```

| Version | Intention | Hypothèse testée |
| --- | --- | --- |
| `v1` | Question nue, sans consigne | Base de référence |
| `v2` | Consigne de format minimale | La contrainte de format réduit le bavardage |
| `v3` | Consigne de format explicite + typologie de réponse attendue | Gain supplémentaire sur les réponses ambiguës |
| `v3_mcq` | Options fournies (questions `multiple` et `boolean`) | Choix contraint ≫ génération libre |
| `v4_letter` | Options étiquetées A/B/C/D, **sortie contrainte par grammaire** à une seule lettre | Supprimer le parsing élimine-t-il de l'erreur de mesure ? |

### `v4_letter` : contraindre au lieu de demander

Le moteur llama.cpp accepte une grammaire GBNF par requête. En passant
`root ::= [A-D]` avec `max_tokens=1`, **le modèle ne peut physiquement produire
qu'une lettre valide**. Le domaine s'adapte au nombre d'options : `[A-B]` pour
une question vrai/faux.

Trois conséquences, dont une seule concerne la vitesse :

| Bénéfice | Détail |
| --- | --- |
| **Matching exact** | Une lettre → un index → une option. Ni `fuzzy`, ni sous-chaîne ambiguë. C'est le gain principal : il retire au benchmark sa dernière source d'erreur de mesure |
| **1 token généré** | Contre 4 à 5 pour `v3_mcq` |
| **Zéro sortie hors format** | Pas de « B) Paris », pas de lettre hors domaine, pas de réponse vide |

**L'instruction est volontairement laconique** (« Answer with one letter. »), mais
**pas pour la raison qu'on croyait**.

Mesuré en alternant les deux variantes question par question, pour annuler toute
dérive du serveur : entre un prompt de 53 tokens et un prompt de 67 tokens,
l'écart de temps par question est de **0,04 s**, pour une justesse identique aux
marges près. L'évaluation du prompt **ne domine pas** le temps de calcul à cette
échelle : 14 tokens d'instruction en plus ne se paient pratiquement pas.

La décision tient — une instruction courte reste préférable, à justesse égale —
mais son motif est le confort de lecture et non la vitesse. Le gain de vitesse de
`v4_letter` vient d'ailleurs : **un seul token généré** au lieu de quatre ou cinq.
C'est la génération qui coûte, pas la relecture de la consigne.

> ⚠️ Deux mesures fausses ont précédé celle-ci, et elles se contredisaient.
>
> La première, faite en exécutant les variantes l'une après l'autre, donnait
> l'instruction courte **deux fois plus lente** — artefact de l'ordre
> d'exécution, la machine ayant ralenti entre les deux passages.
>
> La seconde, corrigée par alternance mais lue trop vite, a été publiée ici comme
> « 0,58 s d'écart » puis reprise ailleurs comme « 40 % plus rapide ». Les deux
> chiffres étaient faux, et ils ont circulé dans trois fichiers du dépôt avant
> d'être vérifiés.
>
> La leçon porte au-delà du détail : **un chiffre commode se recopie plus vite
> qu'il ne se vérifie**. Sur ce projet, un résultat qui arrange doit être mesuré
> deux fois, pas une.

`v3_mcq` mérite une lecture prudente : fournir les options transforme la tâche en
QCM et **augmente mécaniquement** le taux de bonnes réponses (25 % de réussite au
hasard sur 4 choix, 50 % sur un vrai/faux). Il ne se compare donc pas directement
à `v1`–`v3`, qui mesurent une restitution en génération libre. Ces deux familles
sont présentées séparément dans le dashboard.

### Protocole de sélection

1. Tirer un **échantillon stratifié** de 300 questions (par catégorie et difficulté).
2. Exécuter les 4 versions de prompt sur cet échantillon avec un seul modèle.
3. Comparer taux de bonnes réponses, longueur moyenne de sortie et temps.
4. Retenir la meilleure version comme **prompt standard**, et lancer le benchmark
   complet multi-modèles avec elle.

On conserve les résultats de l'échantillon : ils constituent l'axe d'analyse
« performance des prompts » de la couche gold.

---

## 3. Matching : calcul de `ai_correct`

C'est l'étape la plus délicate du projet. Un modèle qui répond
`"Leonardo da Vinci."` là où la vérité terrain est `"Leonardo da Vinci"` a raison ;
une comparaison naïve `==` le compterait faux et **sous-estimerait tous les
modèles**.

### Normalisation appliquée aux deux chaînes

```python
def normalize(text: str) -> str:
    text = html.unescape(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))  # accents
    text = text.lower().strip()
    text = re.sub(r"^(the|a|an)\s+", "", text)      # articles initiaux
    text = re.sub(r"[^\w\s]", " ", text)            # ponctuation
    return re.sub(r"\s+", " ", text).strip()
```

### Cascade de règles

Appliquées dans l'ordre, la première qui statue l'emporte :

0. **`letter`** — pour les versions à réponse par lettre uniquement. La lettre est
   convertie en index, puis comparée à la position de la bonne réponse **dans la
   liste telle qu'elle a été présentée au modèle**. Cet ordre est reconstruit par
   `shuffled_options()`, déterministe pour un `question_id` donné : sans lui, une
   lettre serait ininterprétable. Une lettre hors domaine donne `none`.
1. **Égalité stricte** après normalisation → correct.
2. **Questions `boolean`** : détection de `true`/`false`, `yes`/`no`, `vrai`/`faux`
   dans la sortie, puis comparaison booléenne.
3. **Questions `multiple`** : on cherche chaque option (bonne réponse ou
   distracteur) dans la réponse normalisée, **avec frontières de mots**. Si
   exactement une option est citée, c'est le choix du modèle. C'est cette règle
   qui rattrape les réponses bavardes.

   Deux précautions, sans lesquelles la règle produit des faux négatifs
   systématiques :

   - **Frontières de mots** (`\b`) : sans elles, l'option « 1979 » serait
     trouvée dans « 11979 », et « Art » dans « Bart ».
   - **La plus longue l'emporte en cas de chevauchement** : « Dark Red »
     contient « Red ». Sans cette résolution, la bonne réponse « Dark Red »
     déclencherait deux correspondances et tomberait dans la branche
     « ambiguë ». Le biais ne serait pas aléatoire : il frapperait précisément
     les catégories aux options emboîtées, qui paraîtraient plus difficiles
     qu'elles ne le sont.

   L'ambiguïté n'est donc déclarée que pour deux options **disjointes** →
   incorrect.
4. **Similarité de chaîne** : ratio `difflib.SequenceMatcher` ≥ **0,90** → correct.
   Absorbe fautes de frappe et variantes orthographiques mineures.
5. Sinon → incorrect.

La règle 3 est volontairement **conservatrice** : en cas de doute, on compte faux.
Un benchmark qui surestime est plus trompeur qu'un benchmark qui sous-estime.

### Traçabilité

La règle qui a statué est enregistrée dans une colonne `match_rule`
(`letter`, `exact`, `boolean`, `option_substring`, `fuzzy`, `none`). Elle permet d'auditer
le matching et d'estimer sa fiabilité : si une part importante des `True` vient
de la règle `fuzzy`, le seuil mérite d'être resserré.

### Validation manuelle

Avant de lancer le benchmark complet, **annoter à la main 100 réponses tirées au
hasard** et comparer au verdict automatique. Reporter le taux d'accord dans le
rapport final : c'est la mesure de confiance dans tous les chiffres qui suivent.

---

## 4. Exécution du batch

```bash
python -m trivia_bench.enrich.runner \
    --model llama-3.2-3b-instruct \
    --prompt-version v3 \
    --limit 300 \            # optionnel : échantillon
    --workers 1
```

### Reprise sur interruption

Au démarrage, le runner lit `ai_answers.parquet` et retire de la file d'attente
les triplets `(question_id, model, prompt_version)` déjà traités. Les résultats
sont écrits **par lots de 100** dans des fragments
`data/silver/_ai_answers_parts/<run_id>_<n>.parquet`, consolidés en fin
d'exécution. Une coupure ne fait perdre au plus que le lot en cours.

### Parallélisme

`--workers 1` par défaut. Au-delà, plusieurs requêtes concurrentes se disputent le
même GPU/CPU et **faussent `response_time`**, qui mesurerait alors la contention
plutôt que la performance du modèle. Ne monter les workers que pour les
exécutions dont on n'exploite pas les temps.

### Gestion des erreurs

Timeout, modèle non chargé (`lms ps` vide), sortie vide : la ligne est écrite avec `error` renseigné
et `ai_correct = NULL` (pas `False`). Les lignes en erreur sont **exclues des taux
de réussite** et comptées à part — les confondre avec des mauvaises réponses
pénaliserait à tort le modèle.

---

## 5. Coût en temps

**Mesures réelles** sur l'i7-8550U (4 cœurs @ 1,8 GHz, sans GPU), un seul modèle
résident, `max_tokens=32`, prompt v3 :

| Modèle | temps/question **mesuré** | Dataset complet (5 295) |
| --- | --- | --- |
| `google/gemma-3-1b` | **3,4 s** | ~5 h 00 |
| `google/gemma-3-4b` | **14,0 s** | ~20 h 30 |

Ces chiffres sont des **mesures**, pas des estimations. Ils ont invalidé les
prévisions initiales — 0,9 s et 2 s — d'un facteur 4 à 7.

Décomposition du coût, mesurée séparément : la génération tourne à ~0,19 s par
token, mais la réponse ne fait que 4 tokens. **L'essentiel du temps part dans
l'évaluation du prompt** — environ 21 tokens/s, soit ~3 s pour les 62 tokens de
l'instruction v3. Passer l'instruction en message `system` pour bénéficier du
cache de préfixe fait gagner 21 % (4,74 → 3,74 s), ce qui n'a pas paru justifier
de restructurer le catalogue de prompts.

**Conséquence sur le protocole** : le dataset complet demanderait ~25 h pour deux
modèles. Le benchmark porte donc sur un **échantillon**, dont la taille est
choisie selon le budget de calcul disponible. L'échantillonnage est **emboîté**
(mélange déterministe puis `head(N)`) : agrandir l'échantillon plus tard ne coûte
que le complément, la reprise ne retraitant jamais une question déjà posée.

Stratégie recommandée : itérer sur un **échantillon de 300 questions** pendant tout
le développement, et ne lancer le run complet qu'une fois le matching validé.
