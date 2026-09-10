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

---

## 4. Ce qu'on a appris

<!-- À compléter au lot 8, une fois les résultats connus. -->
