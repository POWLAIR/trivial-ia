# 06 — Méthodologie de benchmark

Ce document décrit le protocole expérimental, les axes d'analyse et — surtout —
les limites qui encadrent la lecture des résultats.

---

## 1. Protocole

1. **Collecte exhaustive** du dataset OpenTDB (étape 1), avec preuve
   d'exhaustivité par catégorie via `api_count.php`.
2. **Sélection du prompt standard** sur un échantillon stratifié de 300 questions,
   un seul modèle, quatre versions de prompt.
3. **Validation du matching** : annotation manuelle de 100 réponses en
   **génération libre** (`v1`/`v2`/`v3`), mesure du taux d'accord avec le verdict
   automatique.

   Le choix de la génération libre n'est pas neutre : sous `v4_letter`, la
   grammaire réduit le matching à une correspondance lettre → index, qui ne peut
   pas se tromper — il n'y a rien à y annoter. En génération libre au contraire,
   `mart_matching_reliability` montre que jusqu'à **73,8 %** des réponses portent
   `match_rule = none`, c'est-à-dire sont comptées fausses sans qu'aucune règle
   n'ait rien reconnu. Ce taux borne la sous-estimation possible du benchmark, et
   c'est lui que l'annotation doit chiffrer.
4. **Exécution complète** : le prompt retenu, sur l'intégralité du dataset, pour
   chaque modèle, sur la **même machine**.
5. **Construction de la couche gold** et rédaction du rapport.

### Conditions à figer

Pour que les modèles soient comparables, ces paramètres restent constants d'un
run à l'autre :

| Paramètre | Valeur | Raison |
| --- | --- | --- |
| `temperature` | 0 | Reproductibilité |
| `seed` | 42 | Reproductibilité |
| `max_tokens` | 32 | Évite les réponses tronquées comme les digressions |
| Prompt | version retenue à l'étape 2 | Comparaison à formulation constante |
| Machine | Intel i7-8550U, 4 cœurs @ 1,8 GHz, pas de GPU, 12 Go alloués à WSL2 | Les temps ne sont comparables qu'à matériel égal |
| Modèle résident | **Un seul à la fois** (`lms unload --all` avant chaque `lms load`) | Deux modèles chargés saturent la RAM : `response_time` mesurerait alors la contention |
| Quantification | Q4 pour tous les modèles | Comparer des précisions différentes fausserait l'axe « effet de la taille ». Exception assumée : `gemma-3-4b-qat` est le **même** modèle que `gemma-3-4b` dans une autre variante Q4 (Q4_0 issu d'un entraînement conscient de la quantification, contre Q4_K_M). C'est précisément l'objet de l'axe « effet de la quantification », à taille de modèle constante |
| Workers | 1 | Pas de contention faussant `response_time` |

Le changement d'un seul de ces paramètres invalide la comparaison avec les runs
précédents : dans ce cas, tout relancer.

---

## 2. Axes d'analyse

### Obligatoires

| Axe | Métrique | Table gold |
| --- | --- | --- |
| Performance globale | Taux de bonnes réponses (%) | `mart_model_performance` |
| Par catégorie | Précision par thème | `mart_performance_by_category` |
| Par difficulté | `easy` vs `medium` vs `hard` | `mart_performance_by_difficulty` |
| Temps de réponse | Moyenne, médiane, p90 | `mart_latency` |
| Comparaison de modèles | Toutes les métriques ci-dessus, par modèle | toutes |

### Exploratoires

Pistes supplémentaires exploitables à partir des données déjà collectées :

- **Précision vs longueur de la question** : les énoncés longs sont-ils plus
  difficiles, ou seulement plus informatifs ?
- **QCM vs vrai/faux** : l'écart au hasard est-il le même sur `n_choices = 2` et
  `n_choices = 4` ?
- **Distracteur préféré** : quand le modèle se trompe sur un QCM, choisit-il un
  distracteur particulier ? Un biais de position (premier / dernier item) ?
- **Verbosité et justesse** : les réponses longues sont-elles plus souvent fausses ?
  Un modèle qui « explique » est souvent un modèle qui hésite.
- **Compromis taille / performance** : gain de précision par milliard de paramètres,
  rapporté au coût en temps.
- **Accord inter-modèles** : les questions ratées par tous les modèles forment-elles
  un groupe cohérent (questions ambiguës, datées, mal étiquetées) ? C'est souvent
  là que se cachent les défauts du dataset source.
- **Fiabilité du matching** : répartition des `True` par `match_rule`.

---

## 3. Métriques et leur lecture

### Taux de bonnes réponses

```
accuracy = n_correct / n_questions
```

Ne se lit **jamais** seul. Deux références à afficher systématiquement :

- le **hasard** : 1/`n_choices` (25 % sur un QCM à 4 choix, 50 % sur un vrai/faux) ;
- l'**incertitude** : intervalle de Wald à 95 %, `1,96 × sqrt(p(1-p)/n)`.
  Sur 300 questions à p ≈ 0,5, la marge est d'environ **±5,7 points** — deux
  modèles séparés par 3 points ne sont pas départagés.

### Temps de réponse

La **médiane** prime sur la moyenne : la distribution est asymétrique à droite
(quelques réponses très lentes tirent la moyenne). On publie les deux, plus p90.

---

## 4. Biais et limites

Ces limites doivent figurer dans le rapport final. Un benchmark qui ne dit pas ce
qu'il ne mesure pas induit son lecteur en erreur.

| Limite | Effet | Atténuation |
| --- | --- | --- |
| **Le matching automatique se trompe** | Sous-estime les modèles (réponse correcte mal formulée comptée fausse) | Cascade de règles, validation manuelle, `match_rule` traçable |
| **Dataset anglophone et culturellement situé** | Mesure une culture générale majoritairement anglo-saxonne, pas « la » culture générale | Le préciser explicitement ; analyser par catégorie |
| **Contamination des données d'entraînement** | OpenTDB est public : les modèles ont pu voir ces questions à l'entraînement. Le score mesure alors la mémorisation, pas le raisonnement | Non mesurable ici — à énoncer comme limite |
| **Modèles quantifiés** | Les résultats ne valent pas pour les modèles pleine précision | Documenter la quantification exacte |
| **Temps dépendants du matériel** | Non transposables à une autre machine | Documenter CPU/GPU/RAM ; ne comparer qu'intra-machine |
| **Une seule exécution par question** | À `temperature = 0` c'est cohérent, mais aucune variance n'est mesurée | Assumé ; le déterminisme est privilégié |
| **Étiquettes de difficulté OpenTDB** | Attribuées par des contributeurs, non calibrées. **Mesuré : 6 combinaisons modèle × prompt sur 8 présentent une inversion**, toujours la même — les questions `medium` sont moins bien réussies que les `hard`. La régularité du phénomène écarte le simple bruit d'échantillonnage | `has_inversion` dans `mart_performance_by_difficulty`, affiché explicitement par le dashboard. Ne pas fonder de conclusion sur ces étiquettes sans avoir départagé les deux causes possibles : défaut de matching, ou étiquetage non calibré |
| **`v3_mcq` et `v4_letter` fournissent les options** | Gonflent mécaniquement le score : la tâche devient une reconnaissance et non une restitution | Présentés séparément, jamais comparés aux prompts en génération libre. Le dashboard facette sur `format_family` : les trois formats ne partagent jamais un classement |
| **`v4_letter` contraint la sortie** | Troisième format, plus facile encore : la grammaire force une réponse **même quand le modèle ignore tout**, ce qui plaque le score sur la ligne du hasard par le bas au lieu de le laisser tomber en dessous | Toujours lu avec sa ligne de hasard (1/`n_choices`) ; jamais comparé aux formats en génération libre |
| **Benchmark sur un échantillon, pas sur les 5 295 questions** | L'incertitude est plus large, et les catégories les moins fournies deviennent ininterprétables | Échantillon aléatoire à graine fixe, donc non biaisé ; effectif affiché sur chaque taux ; échantillonnage **emboîté**, donc extensible sans tout recalculer |
| **Deux modèles d'une seule famille (gemma-3)** | L'axe « effet de la taille » est mesuré, l'axe « différences entre familles » ne l'est pas | Assumé : les alternatives du catalogue sont des modèles à raisonnement, inexploitables sous ce protocole (voir `docs/03` §1) |
| **Modèles à raisonnement écartés** | Le benchmark ne dit rien des modèles de type Qwen3 ou Phi-4-reasoning | Documenté et mesuré : avec `max_tokens=32` leur `content` est vide, ce qui mesurerait leur format de sortie et non leur culture générale |

---

## 5. Contenu du rapport final

Le rapport, porté par l'application Streamlit et résumé dans le README, comporte :

1. **Contexte et méthodologie** — dataset, modèles, protocole, machine d'exécution.
2. **Résultats** — les cinq axes obligatoires, chiffrés et commentés.
3. **Analyses exploratoires** — deux ou trois pistes de la section 2 menées à terme.
4. **Fiabilité** — taux d'accord du matching, tailles d'échantillon, incertitudes.
5. **Limites** — le tableau de la section 4.
6. **Conclusion** — quel modèle pour quel usage, à quel coût en temps.

Une conclusion utile est **conditionnelle** : « le modèle A domine sur les
catégories scientifiques mais coûte trois fois plus de temps que B, qui reste
préférable à volume élevé » vaut mieux qu'un classement unique qui masque le
compromis.
