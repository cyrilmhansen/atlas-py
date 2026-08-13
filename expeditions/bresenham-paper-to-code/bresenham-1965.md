# Bresenham 1965 — lecture primaire

Cette note est limitée à la publication originale. Elle ne décrit pas encore
des implémentations concurrentes et ne constitue pas un benchmark.

## 1. Référence bibliographique

Jack E. Bresenham, “Algorithm for Computer Control of a Digital Plotter”,
*IBM Systems Journal*, vol. 4, no 1, 1965, pp. 25–30,
DOI [10.1147/SJ.41.0025](https://doi.org/10.1147/SJ.41.0025).

La publication a été lue intégralement dans le scan de six pages disponible à
[ibm-1401.info/Pics3/bresenham1965.pdf](https://ibm-1401.info/Pics3/bresenham1965.pdf),
qui reproduit les pages originales 25 à 30. La version ACM Seminal Graphics,
DOI [10.1145/280811.280913](https://doi.org/10.1145/280811.280913), est une
réédition du même article, pas une publication scientifique ultérieure.

La lecture couvre le résumé, les figures 1 à 5, les équations (1) à (4), la
table 1, les remarques finales, les remerciements, les notes et les références.

## 2. Contexte et problème formulé

### SOURCE FACT — p. 25

Le dispositif est un plotter numérique qui peut effectuer, après une impulsion,
l'un des huit mouvements linéaires vers un point voisin de la maille. La maille
typique indiquée est de 1/100 de pouce.

Les données sont exprimées dans un système rectangulaire `(x, y)` mis à
l'échelle par rapport à cette maille. Les points de données sont donc situés
sur des points de maille et ont des coordonnées entières.

La courbe est supposée être décrite par un nombre suffisant de points de données
reliés par des segments. Pour chaque segment, le chemin du plotter doit choisir
des points de maille ; le papier illustre le choix du point de maille le plus
proche du segment désiré (p. 25, Fig. 2–3).

### DERIVED INTERPRETATION

Le problème traité n'est pas une API moderne de dessin de pixels. C'est le
contrôle discret d'un appareil dont les sorties élémentaires sont des
mouvements de maille. La sortie immédiate est une suite de mouvements et de
points de maille atteints.

### MODERN REFORMULATION

On peut parler de discrétisation incrémentale d'un segment entier sur une
grille, à condition de conserver les restrictions du dispositif et de ne pas
ajouter les conventions modernes de couverture ou d'anti-aliasing.

## 3. Lecture structurée du mécanisme

### 3.1 Cas développé : premier octant

### SOURCE FACT — pp. 25–26, Fig. 3–4

Le premier cas suppose que `D2` est dans le premier octant relativement à
`D1`. Après translation de l'origine en `D1`, le second point a pour
coordonnées :

```text
Δa = x2 - x1
Δb = y2 - y1
```

Le chemin n'emploie alors que deux mouvements, `M1` et `M2`. Depuis le point
`P(i-1)`, les deux candidats sont notés `R(i)` et `Q(i)`. Le texte indique
que `M1` est choisi si `r(i) < q(i)` et `M2` si `r(i) >= q(i)` (p. 26).

Le papier introduit `V(i)`, proportionnel à la différence entre les deux
distances candidates. Son signe est donc celui qui suffit pour choisir le
mouvement, sans recalculer les distances géométriques.

### SOURCE FACT — pp. 26–27, équations (1)–(4)

La récurrence donnée est :

```text
V(i+1) = V(i) + 2Δb - 2Δa, si V(i) >= 0
V(i+1) = V(i) + 2Δb,        si V(i) < 0
```

avec l'initialisation :

```text
V(1) = 2Δb - Δa
```

La règle de mouvement est :

```text
V(i) < 0  → M1
V(i) >= 0 → M2
```

Elle est appliquée pour `i = 1, ..., Δa`. Les équations (1) à (4) constituent
explicitement l'algorithme pour ce cas particulier (p. 27).

### SOURCE FACT — pp. 26–27, preuve de la récurrence

La preuve emploie les coordonnées de `P(i-1)`, les opérateurs plancher et
plafond, ainsi que la position de la ligne entre les deux points candidats.
Elle montre que le nouvel état s'obtient par l'une des deux additions selon le
mouvement choisi. Le document ne se contente donc pas de donner une boucle :
il justifie la relation de récurrence dans la géométrie du premier octant.

### 3.2 Autres octants

### SOURCE FACT — pp. 27–28, Fig. 5 et Table 1

Pour les autres octants, Bresenham translate encore l'origine au premier point
mais oriente les axes selon l'octant. Les mouvements `m1` et `m2` sont affectés
aux mouvements matériels appropriés. La table 1 donne les formes modifiées
des équations et les affectations pour les huit octants.

Le texte demande aussi de déterminer l'octant à partir du signe de `Δx`, du
signe de `Δy` et de la comparaison entre `|Δx|` et `|Δy|` (p. 28).

### SOURCE FACT — p. 29

Les variables booléennes `X`, `Y` et `Z` codent ces décisions. Le papier
présente des fonctions booléennes `F(X,Y,Z)` et `G(X,Y)` pour obtenir les
affectations des mouvements à partir de la table 1. Il précise que cette
formulation peut être programmée sans instructions de multiplication ou de
division.

### 3.3 État, transformations et invariants observables

### SOURCE FACT

L'état conservé entre deux décisions est principalement `V(i)` dans le cas
développé, avec les coordonnées courantes et les paramètres de déplacement.
La transition est une addition choisie par le signe de `V(i)`, suivie du
mouvement correspondant. Les autres octants changent les paramètres et les
directions, pas le principe de la décision incrémentale.

La preuve des pages 26–27 établit que le signe de `V(i)` conserve le même rôle
de décision que la comparaison géométrique entre les deux candidats.

### DERIVED INTERPRETATION

Le mécanisme minimal peut être décrit comme :

```text
paramètres entiers + état signé
    → test de signe
    → choix d'un mouvement voisin
    → mise à jour additive de l'état
```

Cette formulation est une lecture moderne du mécanisme, pas un nom employé
tel quel par l'article.

### 3.4 Motivations matérielles

### SOURCE FACT — résumé et p. 29

Le résumé annonce une programmation sans multiplication ni division et une
bonne efficacité en vitesse et en mémoire. La conclusion indique qu'un
programme IBM 1401 contrôlant un IBM 1627 utilisait 333 positions mémoire,
avec environ 1,5 ms entre incrémentations. Une solution fonctionnellement
similaire citée dans la littérature est donnée à 513 positions et 2,4 ms.

### DERIVED INTERPRETATION

La simplicité arithmétique et la taille du programme sont des propriétés
revendiquées dans le contexte IBM décrit. Elles ne sont pas une mesure
universelle du coût sur une machine actuelle.

## 4. Assertions traçables, reformulations et limites

| Sujet | SOURCE FACT | DERIVED INTERPRETATION | MODERN REFORMULATION |
|---|---|---|---|
| Entrées | Points de données à coordonnées entières sur une maille, p. 25 | Le calcul part de déplacements entiers | Segment entre deux points entiers |
| Sortie | Mouvements vers des points voisins, pp. 25–26 | La sortie est une trajectoire discrète | Suite de points de grille |
| Décision | Comparaison des candidats puis signe de `V`, p. 26 | Le signe remplace une comparaison géométrique répétée | Variable de décision incrémentale |
| Mise à jour | Deux additions conditionnelles, équation (2) | L'état est maintenu sans recalcul global | Récurrence entière |
| Directions | Table des huit octants, pp. 27–28 | La généralité passe par une normalisation et des cas directionnels | Gestion des huit octants |
| Arithmétique | Pas de multiplication/division dans le programme, p. 29 | La formulation cible le matériel et le langage de la machine | Boucle entière sans division |
| Efficacité | 333 positions et 1,5 ms pour la configuration indiquée, p. 29 | Le résultat est dépendant de cette plateforme | Coût historique contextualisé |

### Non-claims et anachronismes

Les points suivants ne peuvent pas être attribués à ce document sans source
supplémentaire :

* **Tous les octants au même niveau de détail.** La table 1 les couvre dans
  la formulation de l'article, mais le papier développe et prouve surtout le
  premier cas. Il ne fournit pas une implémentation moderne testée de chaque
  convention.
* **Une politique universelle de tie-breaking.** Le cas développé emploie
  `V >= 0` pour `M2`. Le texte ne démontre pas que cette règle est une norme
  universelle, ni que toutes les variantes directionnelles possèdent une
  symétrie ou une réversibilité identique.
* **Le mot “pixel”.** Le papier parle de plotter, de maille, de points de
  maille et de mouvements ; il ne formule pas le contrat moderne d'un pixel
  de framebuffer.
* **Une notion moderne d'error accumulator.** `V(i)` est une quantité de
  décision géométrique incrémentale ; le terme moderne peut être employé en
  reformulation, mais il ne doit pas effacer sa définition et sa preuve
  propres à l'article.
* **Un rasteriseur général.** L'objet est le contrôle d'un plotter à huit
  mouvements, pour des segments entre points entiers et dans le cadre de
  courbes approximées par segments.
* **Anti-aliasing, sous-pixels, épaisseur, clipping ou modes de composition.**
  Ces problèmes ne sont pas traités dans le papier.
* **Identité avec toutes les algorithmes ultérieurs appelés Bresenham.** Les
  références finales mentionnent Stockton et l'origine présentée à la
  conférence ACM de 1963, mais ce document n'établit pas l'histoire complète
  des variantes et usages ultérieurs.

## 5. Mécanisme minimal observé

Les objets effectivement manipulés sont :

* deux points de données `D1` et `D2` sur la maille ;
* un segment géométrique désiré entre eux ;
* deux mouvements candidats dans le cas du premier octant ;
* un point courant du chemin ;
* un état signé `V` ;
* des paramètres entiers `Δa`, `Δb` et une sélection d'octant.

La transition est :

1. choisir la forme directionnelle à partir des déplacements ;
2. initialiser `V` ;
3. tester son signe ;
4. émettre le mouvement correspondant ;
5. ajouter l'incrément associé ;
6. répéter jusqu'à la longueur du déplacement majeur.

### Dépendances et variantes conservées

Le choix de la forme de la récurrence dépend de l'octant. La règle de
départage dépend du signe nul dans le cas exposé. Le document ne permet pas de
réduire honnêtement ces deux dépendances à une seule abstraction canonique.

### HYPOTHESIS

Une implémentation peut appeler `V` une erreur accumulée et réécrire les
octants par échanges de coordonnées, mais il faut vérifier séparément que ces
transformations conservent la ligne et la convention d'égalité du papier.

## 6. Questions produites par cette lecture

### Question 1 — conventions d'égalité et réversibilité

**OBSERVATION SOURCE.** Le premier cas choisit `M2` lorsque `V >= 0` (p. 27),
alors que les autres octants sont décrits par des affectations distinctes dans
la table 1.

**QUESTION.** La convention de choix sur égalité est-elle réversible et
cohérente lorsqu'un segment est parcouru dans l'autre sens ou dans un autre
octant ?

**EVIDENCE NEEDED.** Une publication ultérieure consacrée aux ambiguïtés ou
à la réversibilité, puis des implémentations historiques qui exposent ce
choix.

### Question 2 — ce que conserve exactement la généralisation par octants

**OBSERVATION SOURCE.** L'article développe la preuve pour le premier octant
et fournit une table de modifications pour les sept autres (pp. 27–28).

**QUESTION.** Les formulations ultérieures conservent-elles exactement le
même contrat de points et de ties, ou changent-elles l'objet discret visé ?

**EVIDENCE NEEDED.** Publications ultérieures primaires de Bresenham ou
d'autres auteurs, avec leurs définitions et exemples, plutôt qu'un tutoriel.

### Question 3 — frontière entre génération et représentation de sortie

**OBSERVATION SOURCE.** La sortie décrite est une suite de mouvements, tandis
que le programme est optimisé pour le contrôle d'un plotter et sa mémoire
(pp. 25, 29).

**QUESTION.** Le même état incrémental peut-il produire ou être consommé sous
des représentations compactées sans changer le contrat géométrique ?

**EVIDENCE NEEDED.** Publication primaire sur la compaction de lignes ou
publication/code historique décrivant une sortie en runs ou motifs périodiques.

## 7. Prochaines investigations possibles

### A — Recommandée : ambiguïtés de rasterisation

**Question exacte.** Quelles égalités, conventions d'extrémités et exigences
de réversibilité le travail ultérieur distingue-t-il explicitement du cas
1965 ?

**Pourquoi elle découle du papier.** La règle `V >= 0` et la table par octant
fixent une décision mais laissent ouverte sa portée hors du cas développé.

**Source recherchée.** Publication primaire ultérieure, en priorité Jack E.
Bresenham, sur les ambiguïtés de rasterisation.

**Valeur discriminante.** Elle permettrait de séparer une propriété du papier
de 1965 d'une convention ajoutée par l'histoire ultérieure.

### B — Compaction incrémentale

**Question exacte.** Une séquence de mouvements issue de la boucle de 1965
peut-elle être encodée en runs ou en périodes avec le même contrat de ligne ?

**Pourquoi elle découle du papier.** Le papier décrit explicitement une
sortie de mouvements et une contrainte de mémoire, mais ne traite pas une
représentation compacte de cette séquence.

**Source recherchée.** Publication primaire sur la compaction de lignes.

**Valeur discriminante.** Elle teste si “mécanisme incrémental” et
“représentation de sortie” doivent être distingués.

### C — Code historique du plotter

**Question exacte.** Comment une implémentation réelle du contrôle IBM traduit-
elle la table des octants, l'état `V` et le tie dans les mouvements matériels ?

**Pourquoi elle découle du papier.** Les motivations de temps et de mémoire
sont données pour un programme IBM 1401 contrôlant un IBM 1627, mais le papier
ne fournit pas le programme complet.

**Source recherchée.** Code historique, listing d'archive ou documentation
technique primaire du dispositif.

**Valeur discriminante.** Elle permettrait de vérifier quelles parties de la
description mathématique étaient réellement des choix de programme et
lesquelles restaient une formulation papier.

La prochaine étape recommandée est **A**, car la politique d'égalité peut
changer directement les points produits et conditionne toute comparaison
ultérieure entre implémentations.

## 8. État de connaissance à la clôture de cette étape

### Confirmed

* La publication traite le contrôle discret d'un plotter à huit mouvements,
  avec coordonnées de maille entières et segments reliant des points de
  données (p. 25).
* Dans le premier octant, elle donne une règle de décision par signe et une
  récurrence additive explicitement prouvée (pp. 26–27, équations 1–4).
* Elle fournit une adaptation par octants et une sélection booléenne de la
  forme des équations (pp. 27–29, table 1).
* Elle revendique l'absence de multiplication/division dans le programme et
  rapporte des coûts contextualisés à IBM 1401/1627 (p. 29).

### Disproved

* Il est faux, sur la seule base de 1965, de présenter Bresenham comme une
  spécification universelle de pixels modernes.
* Il est faux d'attribuer au papier une démonstration de l'anti-aliasing,
  des sous-pixels, du clipping ou d'un contrat moderne d'extrémités.

### Unknown

* La portée exacte de la règle d'égalité pour tous les octants et le parcours
  inverse.
* La relation entre la sortie de mouvements de 1965 et d'éventuelles formes
  compactées.
* La traduction concrète de la description dans le programme historique du
  plotter.

## Inventaire

Fichier créé :

* `expeditions/bresenham-paper-to-code/bresenham-1965.md`

Aucun code, benchmark, JSON historique ou ontologie n'a été modifié.
