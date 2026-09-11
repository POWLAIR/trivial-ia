---
paths:
  - "app/**/*.py"
---

<!-- Règle à portée limitée : chargée quand Claude lit `app/**/*.py` -->

# Dashboard Streamlit

Spécification de référence : `docs/05-dashboard-streamlit.md`.

## Règle fondamentale : l'app lit, elle ne calcule pas

**Aucune agrégation dans Streamlit.** Toute métrique affichée provient d'une table `mart_*` construite par dbt.

Métrique manquante → **ajouter un modèle dbt**, jamais un `groupby` pandas ni un `select ... group by` dans l'app.

Deux raisons : les chiffres affichés sont alors exactement ceux que `dbt test` a validés, et l'application reste rapide quel que soit le volume de la couche silver.

Seules opérations autorisées côté app : filtrer les lignes, trier, mettre en forme.

## Accès aux données

```python
@st.cache_resource
def get_connection():
    return duckdb.connect(DB_PATH, read_only=True)

@st.cache_data(ttl=300)
def load(table: str):
    return get_connection().execute(f"select * from {table}").df()
```

- **`read_only=True` obligatoire** : plusieurs sessions Streamlit doivent pouvoir ouvrir la base, et l'app ne doit jamais écrire.
- Connexion sous `@st.cache_resource`, DataFrames sous `@st.cache_data`.
- Si `data/gold/benchmark.duckdb` est absent : afficher un message indiquant `make gold`, **pas une trace d'erreur**.

## Visualisation honnête

Ces règles ne sont pas cosmétiques : elles empêchent le dashboard de mentir.

- **Jamais un taux sans sa ligne de hasard** (`random_baseline_pct`). Un modèle à 30 % sur un QCM à 4 choix est sous le hasard, pas « moyen ».
- **Jamais un taux sans son effectif.** Chaque graphique porte en légende le `n` sur lequel il repose.
- **Jamais un taux sans son incertitude.** Barres d'erreur portant `ci95_margin_pct` (Wald 95 %). Deux modèles dont les intervalles se recouvrent ne sont pas départagés.
- **Axe des pourcentages borné à `[0, 100]`.** Un axe tronqué exagère les écarts entre modèles.
- **`n < 30` grisé ou masqué** : l'intervalle de confiance y est trop large pour conclure.
- **Une couleur par modèle, identique sur toutes les pages.** La comparaison visuelle entre pages n'a de sens que si le codage couleur est stable — palette définie une fois dans `app/theme.py`.
- **La ligne de hasard se trace par barre, pas une fois par graphique.** Elle vaut 1/`n_choices`, et un échantillon mêle QCM à 4 options (25 %) et vrai/faux (50 %).
- Les inversions de monotonie sur la difficulté (`hard` > `easy`) sont **signalées explicitement** comme anomalies, jamais lissées ni masquées.
- **Trois formats de tâche, jamais mélangés dans un classement** : `generation_libre`, `qcm_options` (`v3_mcq`) et `qcm_lettre` (`v4_letter`). Fournir les options transforme une restitution en reconnaissance ; contraindre la sortie par grammaire force en plus une réponse même sans connaissance. Les mettre côte à côte revient à désigner un vainqueur entre trois épreuves différentes. Le mart porte `format_family` : l'app facette dessus, elle ne le déduit pas.
- Ces règles vivent dans `app/charts.py`, pas répétées dans chaque page : énoncées six fois à la main, l'une des six finit par en oublier une.

## Structure

- Pages : **Méthodologie et limites**, Vue d'ensemble, Par catégorie, Par difficulté, Temps de réponse, Impact du prompt, Explorateur de réponses, Fiabilité. La méthodologie ouvre la navigation.
- 🔴 **Aucun chiffre en dur dans le texte des pages.** Taux, effectifs, nombres de modèles et paramètres du protocole se lisent dans les marts ou dans `config.py`. Un chiffre recopié devient faux au prochain `make gold`, et faux de façon crédible.
- Entrée unique `app/streamlit_app.py` avec `st.navigation`, pas de répertoire `pages/` : la barre latérale de filtres doit être construite une fois et son état survivre à la navigation. Donner à chaque `st.Page` un `url_path` explicite — les vues exposent toutes une fonction `render`, dont Streamlit déduirait le même chemin.
- Un filtre sans colonne correspondante dans la table lue doit être **signalé**, jamais ignoré en silence : le lecteur croirait sinon que les chiffres portent sur sa sélection.
- Filtres transversaux en barre latérale (modèle, prompt, catégorie, difficulté, type), état conservé dans `st.session_state` pour survivre à la navigation.
- L'explorateur de réponses affiche `match_rule` : c'est ce qui rend le benchmark auditable à la main.
- Le texte intégral de chaque prompt est consultable dans un `st.expander` — le lecteur doit pouvoir juger la formulation, pas seulement son identifiant.

## Lancement

```bash
streamlit run app/streamlit_app.py   # http://localhost:8501
```

🔴 **Fermer le dashboard avant `make gold`.** Même en `read_only`, une connexion DuckDB verrouille le fichier et fait échouer `dbt run` sur un `Could not set lock on file`.
