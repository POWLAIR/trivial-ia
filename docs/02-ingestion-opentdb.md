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
   même question, jusqu'à épuisement.
3. **Limite de débit : 1 requête toutes les 5 secondes** par IP. Au-delà, l'API
   répond `response_code = 5`.

### Codes de réponse

Chaque réponse JSON porte un `response_code` qu'il faut tester avant de lire
`results` :

| Code | Signification | Traitement |
| --- | --- | --- |
| 0 | Succès | Ajouter les résultats |
| 1 | Pas assez de questions pour ces critères | Réduire `amount`, sinon passer à la suite |
| 2 | Paramètre invalide | Bug d'appel — échouer bruyamment |
| 3 | Jeton inexistant / expiré | Redemander un jeton |
| 4 | Jeton épuisé : toutes les questions ont été servies | **Catégorie terminée** |
| 5 | Limite de débit dépassée | Attendre puis réessayer |

Le code **4 est le signal d'arrêt** : il indique que le balayage exhaustif de la
catégorie est terminé. C'est lui qui garantit qu'on a bien récupéré *l'intégralité*
du dataset, et non un échantillon aléatoire.

---

## 2. Stratégie de collecte

```
1. GET api_category.php               → liste des catégories (id, nom)
2. GET api_token.php?command=request  → jeton de session
3. Pour chaque catégorie :
     GET api_count.php?category=<id>  → total attendu (contrôle)
     Boucle :
       GET api.php?amount=50&category=<id>&token=<t>&encode=url3986
       - code 0 → accumuler, continuer
       - code 4 → catégorie épuisée, sortir de la boucle
       - code 5 → backoff, réessayer
       - code 3 → renouveler le jeton, réessayer
     Comparer le nombre collecté au total de api_count.php
4. Écrire data/bronze/questions_raw.csv
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

> **Conséquence pratique.** À ~4 000 questions, 50 par appel, 5 s entre appels, la
> collecte complète dure de l'ordre de **7 à 10 minutes**. C'est incompressible :
> prévoyez-le dans le planning et ne relancez pas l'ingestion sans raison.

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
