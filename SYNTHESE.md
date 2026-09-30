# Synthèse — Trivial Poursuite M2 DEV

## La question de départ

Que valent des petites IA, qui tournent sur un simple ordinateur portable, sur des questions de culture générale ? Et est-ce que la taille du modèle, la façon de poser la question ou la compression du modèle changent le résultat ?

## Démarche

### 1. Collecte (couche bronze)

- On a récupéré toutes les questions de la base publique OpenTDB, en respectant sa limite d'une requête toutes les 5 secondes.
- Le site annonce 21 617 questions, mais n'en distribue que les ~5 300 vérifiées. On a contrôlé que le nombre de questions reçues correspondait exactement, catégorie par catégorie, pour pouvoir dire que la collecte est complète.

### 2. Nettoyage (couche silver)

Les textes arrivent encodés pour le web (`&quot;` à la place des guillemets, etc.). On les décode, on supprime les doublons, et on donne à chaque question un identifiant stable.

### 3. Faire répondre les IA

C'est l'étape la plus longue.

- **Modèles** : Gemma 3 en 1B et en 4B pour l'effet de la taille, et deux versions compressées du 4B pour l'effet de la compression. Les modèles qui « réfléchissent » avant de répondre (Qwen3, Phi-4) ont été écartés : ils épuisaient leur budget de réponse à réfléchir et ne rendaient rien.
- **Reproductibilité** : les paramètres sont fixés (`temperature=0`, `seed=42`), donc un même run donne toujours le même résultat.
- **Vitesse** : on a court-circuité le serveur de LM Studio, bridé à un seul cœur sur cette machine, pour piloter directement son moteur llama.cpp sur les quatre cœurs. Le débit a été multiplié par trois.
- **Formulations testées** :
  - réponse libre (`v1`, `v2`, `v3`) ;
  - QCM avec les options fournies (`v3_mcq`) ;
  - réponse par une seule lettre, imposée techniquement (`v4_letter`).
- **Correction automatique** : les règles sont prudentes. En cas de doute, la réponse est comptée fausse, et chaque verdict enregistre la règle qui l'a décidé. La réponse brute de l'IA est gardée intacte, ce qui permet de changer les règles sans tout relancer.
- **Taille de l'échantillon** : interroger les 5 295 questions aurait pris environ 25 h par modèle. On a donc tiré 550 questions au hasard, avec une graine fixe. Cet échantillon peut être agrandi plus tard sans rien refaire.

### 4. Modélisation (couche gold, dbt)

Les réponses deviennent des tables d'analyse : performance par modèle, par catégorie, par difficulté, par prompt, temps de réponse, fiabilité de la correction. Chaque taux porte son effectif, sa marge d'erreur et sa ligne de hasard. 80 tests vérifient la cohérence.

### 5. Restitution (Streamlit)

Le dashboard a 8 pages et ne fait aucun calcul lui-même : il lit uniquement les tables dbt.

- Les trois formats de question ne sont jamais classés ensemble, parce qu'un QCM est bien plus facile qu'une réponse libre.
- Tout taux est affiché avec la ligne du hasard.

## Ce que ça montre

- **La taille compte beaucoup.** En QCM, on passe de 43 % avec le 1B à 63 % avec le 4B, là où le hasard donne 29 %.
- **Le format compte encore plus.** En réponse libre, les deux modèles restent autour de 18 à 31 %.
- **La compression QAT ne coûte rien en justesse** et fait gagner du temps.
- **Les étiquettes de difficulté d'OpenTDB semblent peu fiables** : les questions « moyennes » sont moins bien réussies que les « difficiles ».

Taux de bonnes réponses, n = 550 questions par ligne, intervalle de confiance à 95 %. Le hasard (1/nombre de choix, moyenné sur l'échantillon) vaut 28,8 %. Les trois formats ne se comparent pas entre eux.

| Format | Modèle | Prompt | Justesse | ± IC95 | Hasard | Temps médian |
| --- | --- | --- | --- | --- | --- | --- |
| Réponse libre | gemma-3-1b | v1 | 25,6 % | 3,7 pts | 28,8 % | 2,05 s |
| Réponse libre | gemma-3-1b | v2 | 21,3 % | 3,4 pts | 28,8 % | 0,80 s |
| Réponse libre | gemma-3-1b | v3 | 17,6 % | 3,2 pts | 28,8 % | 1,13 s |
| Réponse libre | gemma-3-4b | v3 | 30,9 % | 3,9 pts | 28,8 % | 5,01 s |
| Réponse libre | gemma-3-4b-qat | v3 | 30,6 % | 3,9 pts | 28,8 % | 3,66 s |
| QCM, options fournies | gemma-3-1b | v3_mcq | 43,1 % | 4,1 pts | 28,8 % | 1,17 s |
| QCM, options fournies | gemma-3-4b | v3_mcq | 63,5 % | 4,0 pts | 28,8 % | 5,14 s |
| QCM, options fournies | gemma-3-4b-qat | v3_mcq | 63,3 % | 4,0 pts | 28,8 % | 3,87 s |
| QCM, une lettre | gemma-3-1b | v4_letter | 42,7 % | 4,1 pts | 28,8 % | 0,77 s |
| QCM, une lettre | gemma-3-4b | v4_letter | 58,7 % | 4,1 pts | 28,8 % | 3,45 s |
| QCM, une lettre | gemma-3-4b-qat | v4_letter | 58,4 % | 4,1 pts | 28,8 % | 2,74 s |

Source : `mart_model_performance`. Temps mesurés sur un i7-8550U (4 cœurs, sans GPU), comparables uniquement entre eux.

---

Détails : [docs/01](docs/01-architecture.md) à [docs/07](docs/07-demarche.md). Rapport interactif : `make dashboard`.
