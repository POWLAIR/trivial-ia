# 02 — Ingestion : scraping de l'Open Trivia Database

**Objectif** : récupérer l'**intégralité** du dataset OpenTDB et l'écrire tel quel
dans `data/bronze/questions_raw.csv`.

Module : `src/trivia_bench/ingest/opentdb.py`

---

## 1. Comprendre l'API

OpenTDB est une API publique sans authentification. Quatre endpoints nous
intéressent.

| Endpoint | Rôle |
| --- | --- |
| `https://opentdb.com/api_category.php` | Liste des catégories et de leurs identifiants |
| `https://opentdb.com/api_count.php?category=<id>` | Nombre de questions par catégorie et par difficulté |
| `https://opentdb.com/api_token.php?command=request` | Ouverture d'un jeton de session |
| `https://opentdb.com/api.php` | Récupération des questions |

### Contraintes structurantes

Trois limites de l'API dictent toute la stratégie d'ingestion :

1. **50 questions maximum par appel** (`amount=50`). Il faut donc paginer.
2. **Pas de paramètre d'offset.** L'API ne permet pas de demander « les questions
   51 à 100 ». La seule façon de balayer le dataset sans doublon est le **jeton de
   session** : tant qu'un jeton est actif, l'API ne renvoie jamais deux fois la
   même question, jusqu'à épuisement. Le jeton est **supprimé après 6 h
   d'inactivité** ; `api_token.php?command=reset&token=…` remet sa mémoire à zéro
   sans en demander un nouveau. Une collecte de 15 minutes ne risque rien, mais
   une reprise le lendemain exige un jeton neuf.
3. **Limite de débit : 1 requête toutes les 5 secondes** par IP. Au-delà, l'API
   répond `response_code = 5`.

### Codes de réponse

Chaque réponse JSON porte un `response_code` qu'il faut tester avant de lire
`results` :

| Code | Signification officielle | Traitement |
| --- | --- | --- |
| 0 | Succès | Ajouter les résultats |
| 1 | Pas assez de questions pour ces critères | Réduire `amount` |
| 2 | Paramètre invalide | Bug d'appel — échouer bruyamment |
| 3 | Jeton inexistant / expiré | Redemander un jeton |
| 4 | Jeton épuisé pour cette requête | ⚠️ **ambigu, voir ci-dessous** |
| 5 | Limite de débit dépassée | Attendre puis réessayer |

### ⚠️ Le code 4 n'est pas un signal d'arrêt fiable

La documentation annonce un **code 1** quand on demande plus de questions qu'il
n'en existe (« Ex. Asking for 50 Questions in a Category that only has 20 »).
**Le comportement réel avec un jeton est un code 4**, celui-là même qui signale
l'épuisement. Constaté sur la catégorie 13, qui compte 36 questions :

```
amount=50 → response_code=4, results=0     ← la doc annonce un code 1
amount=36 → response_code=0, results=36    ← les questions sont bien là
amount=50 → response_code=4, results=0     ← là, réellement épuisée
```

Traiter le code 4 comme un arrêt **collecterait zéro question dans cette
catégorie**, et perdrait le dernier lot partiel de toutes les autres. Les
effectifs étant rarement des multiples de 50, la perte est d'environ
**600 questions, soit 11 % du dataset — sans aucun message d'erreur.**

**La parade** : ne jamais demander plus que ce qu'il reste réellement,
`min(50, attendu − collecté)`, l'attendu venant de `api_count_global.php`. Le
code 4 ne conclut à l'épuisement qu'après une dichotomie descendante restée
infructueuse.

### ⚠️ La limite de débit se manifeste aussi en HTTP 429

Un appel trop rapproché lève un **HTTP 429**, sans corps JSON, donc sans
`response_code` à tester. Il faut l'intercepter au niveau du transport, et pas
seulement guetter le code 5.

---

## 2. Stratégie de collecte

```
1. GET api_token.php?command=request   → jeton de session
2. GET api_category.php               → 24 catégories (ids 9 à 32)
3. GET api_count_global.php           → effectif VÉRIFIÉ attendu par catégorie
4. Pour chaque catégorie :
     Tant que collecté < attendu :
       amount = min(50, attendu − collecté)      ← la clé : jamais plus que le reste
       GET api.php?amount=<amount>&category=<id>&token=<t>&encode=url3986
       - code 0    → accumuler, continuer
       - code 1|4  → dichotomie descendante ; si elle échoue, épuisement réel
       - code 3    → renouveler le jeton, réessayer
       - code 5    → backoff, réessayer
       - HTTP 429  → backoff, réessayer
     Consigner attendu / collecté / écart
5. Écrire data/bronze/questions_raw.csv et _ingestion_report.json
```

Le passage catégorie par catégorie n'est pas obligatoire — un jeton sans filtre
finit par tout servir — mais il apporte deux garanties :

- **Vérifiabilité** : `api_count.php` donne le total attendu par catégorie, ce qui
  permet d'affirmer que la collecte est complète, catégorie par catégorie.
- **Reprise** : une interruption ne coûte que la catégorie en cours.

### Encodage

L'API renvoie par défaut du HTML encodé (`&quot;`, `&#039;`). Le paramètre
`encode=url3986` renvoie de l'URL-encoding, plus simple à décoder de manière
déterministe. **Le décodage a lieu en couche silver, pas en bronze** : la couche
bronze conserve la sortie brute de l'API.

---

## 2 bis. Combien de questions au juste ?

`api_count_global.php` distingue quatre compteurs, et la nuance est décisive :

| Mesure | Valeur |
| --- | --- |
| Questions en base | 21 617 |
| En attente de validation | 10 911 |
| Rejetées | 5 425 |
| **Vérifiées — les seules servies par l'API** | **5 298** |

**C'est 5 298 questions qu'il faut viser**, pas 21 617. `api_count.php?category=9`
renvoie 469, exactement le compte *vérifié* de cette catégorie : les deux
endpoints concordent, ce qui confirme que le compteur « vérifié » est bien la
cible.

Le dataset est **très déséquilibré** :

| Catégorie | Questions | Part |
| --- | --- | --- |
| Entertainment: Video Games | 1 185 | 22,4 % |
| Entertainment: Music | 495 | 9,3 % |
| General Knowledge | 469 | 8,9 % |
| … | | |
| Entertainment: Musicals & Theatres | 36 | 0,7 % |

Conséquence méthodologique : **le taux de bonnes réponses global est une moyenne
dominée par le divertissement**, et les jeux vidéo à eux seuls en font le quart.
C'est à signaler dans les limites du rapport, et à corriger par stratification
dans l'échantillon de comparaison des prompts.

---

## 3. Gestion du débit

Un throttle simple garantit un intervalle minimum entre deux requêtes :

```python
MIN_INTERVAL = 5.2  # marge au-dessus de la limite annoncée de 5 s

def _throttle(state):
    elapsed = time.monotonic() - state.last_call
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    state.last_call = time.monotonic()
```

En cas de `response_code = 5` malgré le throttle, on applique un **backoff
exponentiel** (5 s, 10 s, 20 s, 40 s) plafonné à 5 tentatives.

> **Conséquence pratique.** À 5 298 questions, 50 par appel, 5,2 s entre appels,
> la collecte complète demande ~145 appels et dure de l'ordre de **13 à
> 15 minutes**. C'est incompressible : prévoyez-le dans le planning et ne
> relancez pas l'ingestion sans raison.

---

## 4. Journalisation

L'ingestion écrit un rapport dans `data/bronze/_ingestion_report.json` :

```json
{
  "run_id": "2026-09-10T09:14:02",
  "categories": [
    {"id": 9, "name": "General Knowledge", "expected": 314, "collected": 314, "ok": true}
  ],
  "total_expected": 4123,
  "total_collected": 4123,
  "duration_seconds": 512.4,
  "http_errors": 0
}
```

Ce rapport est la **preuve d'exhaustivité** de l'étape 1 : il est repris tel quel
dans le rapport de benchmark final.

---

## 5. Vérifications à faire après l'ingestion

```bash
wc -l data/bronze/questions_raw.csv          # ≈ total_collected + 1
python - <<'PY'
import pandas as pd
df = pd.read_csv("data/bronze/questions_raw.csv")
print(df.shape)
print(df["category"].value_counts())
print(df["difficulty"].value_counts())
print("doublons énoncés :", df.duplicated("question").sum())
PY
```

Les doublons repérés ici sont **normaux** et traités en couche silver : ils ne
justifient pas de relancer l'ingestion.
