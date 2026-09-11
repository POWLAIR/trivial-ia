# marts

Données finales, directement affichables. **Une table = une question métier**,
sans agrégation laissée à l'aval : un mart qui oblige le dashboard à regrouper ou
recalculer est mal découpé.

Deux règles de validité s'appliquent à tout mart portant un taux :

- il expose son effectif (`n_questions`) et sa référence au hasard
  (`random_baseline_pct`) — un taux publié seul est trompeur ;
- il expose son incertitude (`ci95_margin_pct`), calculée par la macro
  `accuracy_metrics()` et nulle part ailleurs.

Matérialisation : `table`, pour une lecture instantanée depuis Streamlit.
