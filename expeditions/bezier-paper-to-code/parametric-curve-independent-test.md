# Test indépendant du candidat parametric_curve

## 1. Question de promotion

Le cycle Bézier proposait de promouvoir :

    classic_2d_graphics.parametric_curve

La question n'est pas de savoir si un arc peut recevoir une paramétrisation
mathématique. Elle est de savoir si la paramétricité est la distinction
nécessaire pour comprendre les contrats et les choix des implémentations
réelles.

Conclusion de cette expédition : **QUESTION_REFINED**. Le corpus indépendant
confirme une famille de courbes géométriques distincte des segments, mais ne
confirme pas encore que parametric_curve soit la frontière ontologique la
plus utile. Dans les cas étudiés, la distinction décisionnelle est souvent
entre une géométrie d'arc/conique et un contrat de production ou de
rasterisation.

## 2. Corpus indépendant

### SVG 2 — arcs elliptiques

Source primaire : [SVG 2 Paths](https://www.w3.org/TR/SVG2/paths.html) et ses
[implementation notes](https://svgwg.org/svg2-draft/implnote.html).

**SOURCE FACT.** La commande A reçoit deux extrémités, deux rayons, une
rotation, un indicateur de grand arc et un indicateur de sens. Le centre est
calculé automatiquement. Les mêmes extrémités et rayons peuvent donc désigner
quatre arcs, départagés par les drapeaux. SVG définit aussi une conversion
entre cette paramétrisation par extrémités et une paramétrisation par centre,
rayons et angles.

**SOURCE FACT.** Des cas dégénérés modifient le contrat : rayon nul devient un
segment, extrémités identiques suppriment l'arc, et des rayons insuffisants
sont mis à l'échelle.

**INTERPRÉTATION.** La paramétrisation est ici une partie du format d'entrée
et du contrat de sélection, mais elle n'est pas nécessairement la
représentation interne conservée par le moteur.

### Skia — arc vers coniques

Source primaire de code : [SkPath::arcTo](https://api.skia.org/classSkPath.html)
et [SkGeometry.cpp](https://github.com/google/skia/blob/main/src/core/SkGeometry.cpp).

**SOURCE FACT.** Skia indique que arcTo implémente la fonctionnalité SVG
et ajoute jusqu'à quatre coniques. Le chemin interne n'est donc pas
nécessairement un objet « arc paramétré » conservant les drapeaux SVG :
l'opération produit une représentation conique intermédiaire.

**SOURCE FACT.** Les coniques et cubiques peuvent ensuite être coupées,
évaluées ou consommées par le pipeline de chemin.

**INTERPRÉTATION.** L'arc logique, sa paramétrisation d'entrée et sa
représentation interne par coniques sont trois rôles distincts.

### Pitteway — coniques et dispositif incrémental

Source primaire : [Pitteway, Algorithm for drawing ellipses or hyperbolae with
a digital plotter, The Computer Journal 10(3), 1967](https://academic.oup.com/comjnl/article-abstract/10/3/282/494116).

**SOURCE FACT.** Le résumé décrit un algorithme pour des segments de coniques
où chaque déplacement incrémental est choisi pour minimiser l'écart avec la
courbe visée. La boucle interne utilise additions, test et changements de
secteur ; le contrat vise un dispositif numérique.

**INTERPRÉTATION.** L'algorithme peut travailler à partir d'une équation
implicite et d'un état d'erreur sans exposer une variable paramétrique au
consommateur. Une paramétrisation mathématique possible n'est pas la
distinction opérationnelle dominante.

### Bresenham — arcs circulaires

Source primaire : [Bresenham, A linear algorithm for incremental digital
display of circular arcs, CACM 20(2), 1977](https://cir.nii.ac.jp/crid/1361137043978372608).

**SOURCE FACT.** L'article décrit une sélection incrémentale de points ou de
pas pour une vraie circonférence, avec seulement tests de signe et additions
ou soustractions. Il explicite des critères d'erreur, dont l'erreur au carré
et l'erreur radiale, et vise des écrans, plotters ou imprimantes matricielles.

**INTERPRÉTATION.** Deux rasteriseurs peuvent viser la même géométrie
circulaire mais produire des sorties différentes selon le critère d'erreur et
le contrat de déplacement. Cela réactive la distinction Bresenham entre
géométrie et résultat digital, sans imposer une représentation paramétrique
à l'algorithme.

### Van Aken — ellipse

Source primaire identifiée : [Van Aken, An Efficient Ellipse-Drawing
Algorithm, IEEE CG&A 4(9), 1984, DOI
10.1109/MCG.1984.275994](https://eurekamag.com/research/081/647/081647053.php).

La notice bibliographique et les métadonnées ont été consultées ; le texte
intégral n'a pas été accessible. Elle est donc une confirmation de variation
historique, pas une preuve détaillée supplémentaire.

## 3. Objets et opérations observés

| Cas | Objet géométrique | Données du contrat | Opération | Intermédiaire | Sortie |
|---|---|---|---|---|---|
| SVG | arc elliptique | extrémités, rayons, rotation, deux drapeaux | conversion/sélection puis rendu | centre, angles ou chemin interne | chemin consommable |
| Skia | arc de chemin | paramètres d'arc | arcTo puis conversion | jusqu'à quatre coniques | chemin |
| Pitteway | segment de conique | conique, secteur, critère d'écart | progression incrémentale | état d'erreur | pas/points du dispositif |
| Bresenham | arc circulaire | centre, rayon, extrémités, critère d'erreur | sélection incrémentale | résidu/erreur | points ou pas raster |

La paramétrisation est donc :

* **constitutive du format** dans SVG ;
* **transformée ou cachée** dans Skia ;
* **non exposée comme contrat principal** dans les algorithmes
  incrémentaux étudiés.

## 4. Confrontation au candidat

### geometric_segment

Le segment ne suffit pas : un arc possède une courbure et une règle de
sélection qui ne sont pas déterminées par deux extrémités.

- **EVIDENCE** : SVG distingue explicitement lineto et arc ; Pitteway et
  Bresenham traitent des coniques/circonférences.
- **ERROR_IF_COLLAPSED** : l'ellipse ou le cercle serait remplacé par une
  corde.
- **SCOPE** : courbes et primitives géométriques 2D.
- **FORM** : distinction déjà forcée comme connaissance ; elle ne justifie
  pas à elle seule un parent commun immédiat.

### parametric_curve

La notion couvre Bézier et peut couvrir un arc, mais elle mélange des
situations qui ont des contrats différents : paramétrisation d'entrée,
représentation interne et progression raster.

- **EVIDENCE** : SVG expose une paramétrisation endpoint ; les implementation
  notes donnent une autre forme center ; Skia convertit en coniques ; Pitteway
  et Bresenham pilotent des pas par erreur.
- **ERROR_IF_COLLAPSED** : on pourrait conclure qu'une implémentation doit
  conserver un paramètre ou que deux productions sont équivalentes parce
  qu'elles partagent une paramétrisation géométrique.
- **SCOPE** : courbes paramétriques, mais insuffisant comme seul vocabulaire
  pour les primitives coniques et raster.
- **FORM** : candidat de regroupement analytique, pas encore concept promu.
- **STATUT** : **QUESTION_REFINED**.

### Représentation/paramétrisation

Le corpus force une distinction entre :

1. les données qui spécifient une géométrie ;
2. une paramétrisation utilisée pour calculer ou encoder cette géométrie ;
3. une représentation interne, comme les coniques Skia ;
4. un état de production raster.

Cette distinction est plus précise que de déclarer toute paramétrisation
comme représentation de l'objet.

### Approximation et rasterisation

Les arcs incrémentaux de Pitteway et Bresenham ne sont pas seulement des
évaluations de points paramétriques. Ils choisissent des déplacements sous un
critère d'erreur. La sortie est donc le résultat d'une opération de
rasterisation, avec un contrat de proximité, et non une nouvelle
représentation exacte de l'arc.

## 5. Contre-exemple conceptuel

Un arc SVG peut être converti en coniques Skia puis rasterisé. Un arc
circulaire Bresenham peut viser la même géométrie sans calcul trigonométrique
ou paramètre exposé, en choisissant des pas par erreur.

Si parametric_curve est interprété comme « objet dont l'implémentation doit
être paramétrique », il exclut artificiellement les implémentations
incrémentales. Si on l'interprète seulement comme « objet mathématiquement
paramétrisable », il est trop faible pour expliquer les différences de
contrat observées.

## 6. Micro-expérience

Aucune nouvelle micro-expérience n'a été exécutée. Les sources fournissent
déjà le cas discriminant nécessaire :

* SVG convertit une forme endpoint en une autre paramétrisation ;
* Skia convertit l'arc en coniques ;
* Pitteway et Bresenham produisent directement des pas raster par critère
  d'erreur.

Une expérience numérique commune pourrait être utile plus tard pour comparer
les ensembles de pixels, mais elle ne déciderait pas à elle seule si la
paramétricité est la bonne frontière ontologique. Elle est donc différée.

## 7. Harvest

### geometric_segment

**Statut : ALREADY_REPRESENTABLE.** Le concept reste utile pour les segments
de Bresenham, mais le corpus des arcs ne justifie ni son remplacement ni un
parent commun immédiat.

### parametric_curve

**Statut : QUESTION_REFINED.**

**EVIDENCE** : Bézier, SVG, Skia et les descriptions de coniques utilisent
des paramètres ou des données équivalentes ; Pitteway et Bresenham montrent
qu'un mécanisme réel peut masquer ce paramètre derrière une équation et un
état d'erreur.

**ERROR_IF_COLLAPSED** : confusion entre géométrie, encodage, représentation
interne et contrat de rasterisation.

**SCOPE** : courbes paramétriques et certaines primitives de graphisme 2D.

**FORM** : notion analytique candidate ; ne pas la promouvoir encore comme
concept sans distinguer les rôles de spécification, représentation et
production.

### Alternative candidate : aucune promotion immédiate

Le corpus suggère une frontière de recherche plus fidèle :

    géométrie de courbe/conique
      → contrat de construction ou de paramétrisation
      → opération de production
      → représentation ou sortie consommée

Ce n'est pas proposé comme nouveau concept. Les termes « courbe
géométrique », « représentation paramétrique » et « contrat de production »
restent des vocabulaires contextuels jusqu'à une expérience montrant qu'ils
doivent être distingués dans plusieurs décisions.

## 8. Recommandation finale

Classer parametric_curve comme **QUESTION_REFINED**, et non comme
CONFIRMED_BY_INDEPENDENT_CORPUS.

Le corpus indépendant confirme une distinction plus générale que le segment :
une primitive courbe/conique possède une géométrie qui ne se réduit pas à ses
extrémités. Mais il ne confirme pas que « paramétrique » soit le meilleur
nom ou le meilleur critère de décision. Cette paramétricité peut être :

* la syntaxe d'entrée ;
* une forme interne ;
* une construction intermédiaire ;
* ou un formalisme absent de l'interface raster.

Ne pas modifier classic-2d-graphics.md.

## 9. Confirmed / Disproved / Unknown

### Confirmed

* geometric_segment ne suffit pas pour les arcs et ellipses.
* Une même géométrie d'arc peut être décrite par des paramétrisations
  endpoint ou centre.
* Une implémentation peut convertir un arc en coniques avant consommation.
* Des rasteriseurs d'arcs peuvent fonctionner par état d'erreur et pas
  incrémentaux sans exposer de paramètre.
* La séparation géométrie / opération / sortie consommée issue de Bresenham
  reste utile.

### Disproved

* « Toute implémentation pertinente d'une courbe doit exposer ou conserver un
  paramètre » est réfuté par le corpus incrémental.
* « Paramétrisable » suffit à expliquer le contrat d'une primitive graphique
  est réfuté : les critères d'erreur, les drapeaux, la représentation interne
  et la sortie changent indépendamment.

### Unknown

* Une future ontologie doit-elle distinguer curve_geometry et
  parametric_representation ?
* Les arcs et les Bézier peuvent-ils partager une notion de contrat de
  production sans perdre les différences utiles ?
* Les sorties pixel de deux productions censées viser le même arc sont-elles
  suffisamment différentes pour justifier une propriété dédiée ?
* Faut-il un concept de courbe géométrique plus général, ou seulement des
  connaissances locales et des relations d'opération ?

## Inventaire

* parametric-curve-independent-test.md — test du candidat, corpus, harvest
  et recommandation.

Commande de reproduction documentaire : consulter les liens cités dans cette
note. Aucun code, benchmark ou ontologie n'a été modifié.
