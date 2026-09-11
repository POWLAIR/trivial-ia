# intermediate

Précalculs : construits sur `staging`, partagés par plusieurs marts, **non
destinés à être consommés tels quels** par le dashboard.

Ce qui justifie la couche ici, c'est `int_common_questions`. La restriction d'un
modèle à ses questions communes porte la validité de *toutes* les comparaisons
de prompts : dès que deux versions ne tournent pas sur le même échantillon, un
taux comparé hors de cet ensemble compare deux populations différentes sans le
signaler nulle part. Laissée en CTE dans un seul mart, cette règle serait
invisible et non testable ; ici elle est nommée, testée et réutilisable.

Matérialisation : `view`.
