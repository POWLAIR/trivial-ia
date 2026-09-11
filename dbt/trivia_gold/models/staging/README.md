# staging

Un modèle par source (`source(...)`), **sans logique métier** : typage et
renommage seulement. La couche silver a déjà nettoyé — refaire ici une partie de
son travail reviendrait à réécrire la couche amont, ce que l'architecture
médaillon interdit (`docs/01`).

Matérialisation : `view`, déclarée dans `dbt_project.yml`. Aucune duplication de
données.
