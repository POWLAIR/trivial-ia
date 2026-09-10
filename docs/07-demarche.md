# 07 — La démarche expliquée simplement

> Ce document raconte, sans jargon, ce que nous avons construit et quels
> obstacles nous avons dû lever. Il s'adresse à quelqu'un qui n'a jamais ouvert
> le code. Les détails techniques sont dans `docs/01` à `docs/06`.

---

## 1. Ce qu'on cherchait à savoir

Les intelligences artificielles dont tout le monde parle tournent sur d'énormes
serveurs. Mais il existe des versions réduites, capables de fonctionner sur un
ordinateur portable ordinaire, sans connexion internet.

Notre question est simple : **est-ce que ces petites IA connaissent leurs
classiques ?** Sont-elles capables de répondre à des questions de culture
générale — histoire, sciences, cinéma, géographie ?

Et derrière cette question, trois autres :

- Laquelle s'en sort le mieux ?
- Combien de temps met-elle à répondre ?
- Est-ce que la **façon de poser la question** change ses résultats ?

Pour répondre, il ne suffit pas d'essayer trois questions à la main. Il faut
poser des milliers de questions, de manière identique à chaque modèle, et
compter. C'est ce qu'on appelle un **benchmark**.

---

## 2. Comment on s'y est pris

Le principe tient en cinq étapes.

**Étape 1 — Rassembler les questions.** Il existe un site public, Open Trivia
Database, qui met à disposition des milliers de questions de quiz avec leur
bonne réponse. On les récupère toutes, automatiquement.

**Étape 2 — Ranger les données proprement.** On stocke l'information en trois
étages, un peu comme une cuisine :

| Étage | Ce qu'il contient | L'analogie |
| --- | --- | --- |
| **Bronze** | Les questions exactement comme le site nous les a envoyées | Les courses telles qu'elles sortent du sac |
| **Silver** | Les mêmes questions, nettoyées et rangées | Les légumes lavés et épluchés |
| **Gold** | Les résultats calculés, prêts à être lus | Le plat servi dans l'assiette |

L'intérêt de ce découpage : si on se trompe dans le nettoyage, on recommence à
partir de l'étage précédent, **sans jamais avoir à retourner faire les courses**.
On ne redemande donc jamais les questions au site.

**Étape 3 — Interroger les IA.** On installe les modèles sur l'ordinateur, puis
un programme leur pose chaque question, l'une après l'autre, et note trois
choses : la réponse donnée, si elle est juste, et le temps mis pour répondre.

**Étape 4 — Calculer les résultats.** On compte les bonnes réponses, globalement,
par thème, par niveau de difficulté, et on mesure les temps.

**Étape 5 — Afficher.** Un tableau de bord interactif permet de naviguer dans
les résultats, de filtrer par modèle ou par catégorie, et d'aller lire une
réponse précise pour comprendre pourquoi elle a été comptée fausse.

---

## 3. Les obstacles et ce qu'on a fait

<!-- À alimenter au fil des lots, pendant que le souvenir est précis. -->

### L'ordinateur ne donnait que 4 Go de mémoire à Linux

**Le problème.** Le projet tourne sous WSL, un Linux installé à l'intérieur de
Windows. En vérifiant les ressources disponibles avant de choisir les modèles,
nous avons découvert que WSL ne disposait que de **4 Go de mémoire vive**, dont
seulement 591 Mo réellement libres — alors que la machine en possède **32 Go**.

**Pourquoi ça bloquait.** Une IA doit être chargée entièrement en mémoire pour
fonctionner. Avec 4 Go, même un modèle de taille moyenne ne rentrait pas, et le
système compensait en écrivant sur le disque dur, ce qui est des dizaines de
fois plus lent.

**Ce qu'on a fait.** La limite ne venait pas du matériel mais d'un fichier de
configuration, `.wslconfig`, qui contenait `memory=4GB`. Nous l'avons porté à
12 Go, en laissant 20 Go à Windows, puis redémarré WSL. Le diagnostic initial
visait l'espace disque : il était erroné, 90 Go restaient libres. **C'était bien
la mémoire, et c'était un réglage, pas une fatalité.**

### Les modèles choisis au départ étaient trop gros

**Le problème.** La documentation prévoyait initialement des modèles de 3, 4 et
7 milliards de paramètres.

**Pourquoi ça bloquait.** Même avec la mémoire corrigée, le processeur de la
machine — un i7-8550U de 2017, quatre cœurs à 1,8 GHz, sans carte graphique
utilisable — reste le facteur limitant. La vitesse d'une IA sur processeur
dépend surtout de la rapidité avec laquelle la mémoire peut être lue : plus le
modèle est gros, plus il est lent. Un modèle de 7 milliards de paramètres aurait
produit deux à trois mots par seconde, soit plus de cinq heures pour un seul
passage sur le jeu de questions.

**Ce qu'on a fait.** Nous avons choisi trois modèles plus petits — 1, 1,5 et
3 milliards de paramètres — et mis à jour la documentation en conséquence. Les
trois tailles restent suffisamment différentes pour que la comparaison
« est-ce qu'un modèle plus gros répond mieux ? » garde tout son sens.

### Le site ne donne pas ses questions d'un bloc

**Le problème.** Le site public ne permet pas de dire « donne-moi les questions
1 000 à 1 050 ». Il n'y a pas de numéro de page.

**Pourquoi ça bloquait.** Sans repère, redemander des questions revient à tirer
au hasard : on récupère cent fois les mêmes et jamais les autres.

**Ce qu'on a fait.** Le site propose un « jeton de session » : une sorte de
ticket qui mémorise ce qu'il nous a déjà donné et ne le redonne jamais. On en
demande un au début, on le présente à chaque appel, et le site nous sert les
questions sans doublon jusqu'à épuisement.

### Une demande toutes les cinq secondes, pas plus

**Le problème.** Le site n'accepte qu'un appel toutes les 5 secondes par
utilisateur. Au-delà, il refuse de répondre.

**Pourquoi ça bloquait.** Récupérer 5 000 questions par paquets de 50 demande
plus de cent appels. Sans attente entre chacun, tout s'arrête au troisième.

**Ce qu'on a fait.** Le programme attend 5,2 secondes entre deux demandes, et
double son temps d'attente s'il se fait tout de même refouler. La collecte dure
donc une dizaine de minutes, ce qui est irréductible. Sur la collecte réelle,
ce mécanisme a servi : quatre incidents réseau ou refus ont été rattrapés
automatiquement, sans perdre une seule question.

### Le site annonce « j'ai tout donné » alors qu'il lui reste des questions

**Le problème.** C'est l'obstacle le plus sournois du projet. La documentation
du site dit : si vous demandez plus de questions qu'il n'en existe, vous
recevrez le message « pas assez de questions ». En réalité, le site renvoie un
message différent : « j'ai déjà tout donné » — le même que lorsqu'une catégorie
est réellement épuisée.

**Pourquoi ça bloquait.** Nous demandions les questions par paquets de 50. Une
catégorie comme « Comédies musicales » n'en compte que 36 : dès le premier
appel, le site répondait « j'ai tout donné », et le programme serait passé à la
catégorie suivante en croyant avoir terminé. Résultat : **zéro question
récupérée** dans cette catégorie, et le dernier paquet incomplet perdu dans
toutes les autres — environ **11 % du jeu de données, sans le moindre message
d'erreur**.

C'est précisément ce qui rend ce type de bug dangereux : rien ne plante, rien ne
s'affiche en rouge. On obtient simplement un benchmark calculé sur un jeu de
données amputé, sans savoir qu'il l'est.

**Ce qu'on a fait.** Nous avons d'abord découvert le problème en testant l'API à
la main avant d'écrire le programme, plutôt qu'en faisant confiance à la
documentation. Puis nous avons changé de stratégie : au lieu de demander
systématiquement 50 questions, le programme demande **exactement ce qu'il lui
reste à récupérer**. Pour les comédies musicales, il demande 36, et il obtient
36. Le message « j'ai tout donné » n'est cru qu'après une seconde vérification.

Bénéfice inattendu : cette méthode ne gaspille aucun appel. La collecte a
utilisé 124 appels, soit le minimum théorique.

### Sur 21 617 questions annoncées, seules 5 298 sont distribuées

**Le problème.** Le site annonce plus de 21 000 questions. Nous n'en avons
récupéré que 5 298.

**Pourquoi ce n'est pas une erreur.** Les questions du site sont proposées par
ses utilisateurs, puis relues. À la date de la collecte, 10 911 attendaient
encore une validation et 5 425 avaient été rejetées. Le site ne distribue que
les questions **vérifiées**.

**Ce qu'on a fait.** Nous avons pris le compteur « vérifiées » comme objectif,
catégorie par catégorie, et vérifié à l'arrivée que les 24 comptes
correspondaient exactement. C'est ce qui nous permet d'affirmer que la collecte
est complète, et non « à peu près complète ».

Ce chiffrage a aussi révélé un déséquilibre important : les jeux vidéo pèsent
1 185 questions, soit près du quart du jeu de données, quand les comédies
musicales en comptent 36. Le score global d'une IA sera donc fortement
influencé par sa connaissance des jeux vidéo — une limite à garder en tête au
moment de lire les résultats.

---

## 4. Ce qu'on a appris

<!-- À compléter au lot 8, une fois les résultats connus. -->
