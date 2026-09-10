# 05 — Dashboard Streamlit

**Objectif** : restituer le benchmark sous forme d'un rapport interactif, livrable
final du projet.

Application : `app/streamlit_app.py`

---

## 1. Principe

Le dashboard **lit** la couche gold, il ne calcule rien. Toute agrégation
appartient à dbt. Cette séparation a deux conséquences pratiques :

- les chiffres affichés sont exactement ceux que `dbt test` a validés ;
- l'application reste rapide, quel que soit le volume de la couche silver.

Si une visualisation demande une métrique absente de la couche gold, la réponse
est **d'ajouter un modèle dbt**, pas une requête SQL dans Streamlit.

---

## 2. Accès aux données

```python
import duckdb
import streamlit as st

DB_PATH = "data/gold/benchmark.duckdb"

@st.cache_resource
def get_connection():
    return duckdb.connect(DB_PATH, read_only=True)

@st.cache_data(ttl=300)
def load(table: str):
    return get_connection().execute(f"select * from {table}").df()
```

`read_only=True` permet à plusieurs sessions Streamlit d'ouvrir la base
simultanément et interdit toute écriture depuis l'application. `cache_resource`
garde une connexion unique ; `cache_data` met en cache les DataFrames retournés.

---

## 3. Pages

### Vue d'ensemble

- Bandeau d'indicateurs : nombre de questions, de modèles évalués, meilleur taux
  de bonnes réponses, temps de réponse médian.
- Classement des modèles (barres horizontales), avec une **ligne de référence au
  niveau du hasard** (`random_baseline_pct`) — sans elle, un score de 30 % sur un
  QCM à 4 choix se lit comme un résultat alors que c'est un échec.
- Nuage de points **précision × temps de réponse** : le compromis qualité/coût,
  un point par modèle.

Source : `mart_model_performance`.

### Par catégorie

- Heatmap catégorie × modèle, colorée par taux de bonnes réponses.
- Classement des catégories les mieux et les moins bien traitées.
- Filtre sur `category_group` pour agréger les sous-catégories (« Science: … »).

Source : `mart_performance_by_category`.

### Par difficulté

- Barres groupées `easy` / `medium` / `hard` par modèle.
- Contrôle de monotonie : le score doit décroître avec la difficulté. Toute
  inversion est signalée explicitement dans la page comme une anomalie à
  interpréter, et non masquée.

Source : `mart_performance_by_difficulty`.

### Temps de réponse

- Distribution des temps par modèle (boîtes à moustaches ou histogrammes).
- Table des percentiles : moyenne, médiane, p90, p99.
- Temps par token généré, qui distingue lenteur et verbosité.

Source : `mart_latency`.

### Impact du prompt

- Taux de bonnes réponses par version de prompt, à modèle constant.
- Longueur moyenne des réponses par version — la mesure directe de l'effet
  « consigne de format ».
- Texte intégral de chaque prompt, affiché dans un `st.expander` : le lecteur doit
  pouvoir juger la formulation, pas seulement son identifiant.
- Rappel visible que `v3_mcq` fournit les options et n'est donc **pas comparable**
  aux versions en génération libre.

Source : `mart_prompt_impact` et le catalogue de
[03 — Enrichissement IA](03-enrichissement-ia.md#2-catalogue-de-prompts).

### Explorateur de réponses

Table filtrable sur `fct_answers` : modèle, prompt, catégorie, difficulté,
correct / incorrect. Colonnes question, bonne réponse, réponse IA, `match_rule`.

C'est la page qui rend le benchmark **auditable** : elle permet de vérifier à la
main pourquoi une réponse a été comptée fausse, et c'est là qu'on repère les
défauts de matching.

---

## 4. Filtres transversaux

Dans la barre latérale, appliqués à toutes les pages :

- modèle(s) — multi-sélection ;
- version de prompt ;
- catégorie / groupe de catégories ;
- difficulté ;
- type de question (`multiple` / `boolean`).

L'état des filtres est conservé dans `st.session_state` pour survivre à la
navigation entre pages.

---

## 5. Lancement

```bash
streamlit run app/streamlit_app.py
```

Accessible sur `http://localhost:8501`.

Prérequis : `data/gold/benchmark.duckdb` doit exister. L'application vérifie sa
présence au démarrage et affiche la commande à lancer (`make gold`) plutôt qu'une
trace d'erreur si le fichier est absent.

---

## 6. Conventions de visualisation

- Une **couleur par modèle**, identique sur toutes les pages : la comparaison
  visuelle entre pages n'a de sens que si le codage couleur est stable.
- Axe des taux de bonnes réponses toujours borné à `[0, 100]` — un axe tronqué
  exagère les écarts entre modèles.
- Tout taux calculé sur moins de 30 observations est affiché en grisé ou masqué :
  l'intervalle de confiance y est trop large pour conclure.
- Chaque graphique porte en légende le nombre d'observations sur lequel il repose.
