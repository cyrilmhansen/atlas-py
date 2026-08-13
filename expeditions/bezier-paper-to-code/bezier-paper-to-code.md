# Expédition Bézier — de la publication au code réel

## Objet et périmètre

Cette expédition teste la proto-ontologie locale Graphisme 2D classique sur un
cas extérieur aux régions et aux segments digitaux. Elle ne modifie pas cette
ontologie, ne lance pas de benchmark et ne propose pas de nouveaux concepts
permanents.

La question suivie est : que désigne exactement « courbe de Bézier » lorsque
l'on passe de sa définition géométrique à son évaluation, sa subdivision, son
approximation et sa consommation par un rasteriseur ?

Les niveaux de preuve sont distingués ainsi :

- **SOURCE FACT** : information lue dans une publication, une interface ou du
  code ;
- **DERIVED INTERPRETATION** : conséquence construite à partir de ces faits ;
- **MODERN REFORMULATION** : vocabulaire actuel utilisé pour comparer des
  sources historiquement différentes ;
- **HYPOTHESIS** : conséquence non vérifiée expérimentalement ici.

## Sources scientifiques et historiques

### Pierre Bézier

* [Bézier, How Renault Uses Numerical Control for Car Body Design and
  Tooling, SAE 680010, 1968](https://saemobilus.sae.org/papers/renault-uses-numerical-control-car-body-design-tooling-680010).
  La notice et le résumé ont été consultés ; le texte intégral n'était pas
  accessible. La source établit le contexte industriel, pas chaque formule
  moderne.
* [Bézier, Numerical Control: Mathematics and Applications, Wiley,
  1972](https://books.google.com/books/about/Numerical_Control_Mathematics_and_Applic.html?id=wNZSAAAAMAAJ).
  Le catalogue, la table des matières et l'aperçu disponible ont été
  consultés. Toutes les pages n'étaient pas accessibles.

### Paul de Casteljau

Les notices bibliographiques consultées identifient les rapports internes
Améliorations Possibles Apportées aux Techniques de Cotation et de Calcul
Numérique (1959) et Courbes et Surfaces à Pôles (1963), associés à Citroën.
Les rapports eux-mêmes n'ont pas été lus intégralement : ils restent des
références historiques, pas une preuve textuelle directe ici.

Le [résumé de De Casteljau-type subdivision is peculiar to Bézier,
Computer-Aided Design 20(3), 1988](https://www.sciencedirect.com/science/article/pii/0010448588900188)
confirme que la propriété de subdivision n'est pas partagée par toute famille
d'algorithmes d'évaluation de type similaire.

### Source scientifique de synthèse

[Gordon et Riesenfeld, Bernstein-Bézier Methods for the Computer-Aided Design
of Free-Form Curves and Surfaces, JACM 21(2), 1974,
DOI 10.1145/321812.321824](https://doi.org/10.1145/321812.321824) a été
consulté au niveau notice/références ; l'accès ACM au texte intégral a été
refusé. Il s'agit d'une référence primaire importante, pas d'une lecture
intégrale revendiquée.

## Trajectoire du Semantic Spider

1. **Observation** : la proto-ontologie distingue segment géométrique,
   rastérisation et ligne digitale.
2. **Question** : une courbe est-elle simplement un segment avec davantage de
   paramètres ?
3. **Source choisie** : Bézier 1972, Gordon–Riesenfeld 1974 et les références
   historiques de de Casteljau.
4. **Connaissance** : une courbe est une définition paramétrique avec des
   données de contrôle ; le polygone de contrôle n'est pas une suite de points
   de la courbe.
5. **Question suivante** : évaluation, subdivision et approximation
   produisent-elles le même objet ?
6. **Source choisie** : Skia, Anti-Grain Geometry et FreeType.
7. **Connaissance** : les interfaces séparent évaluation ponctuelle, découpage
   exact en sous-courbes et émission d'une polyligne ou de profils raster.
8. **Arrêt** : ces différences suffisent à tester l'ontologie ; aucun
   benchmark n'est nécessaire ici.

## Objets et opérations rencontrés

### Courbe et données de contrôle

**SOURCE FACT.** Les sources Bézier décrivent une courbe paramétrique par des
points de contrôle et un paramètre. Les points de contrôle définissent le
polygone de contrôle ; ils ne sont pas, en général, des échantillons de la
courbe, sauf les extrémités dans le cas polynomial usuel.

**DERIVED INTERPRETATION.** Les points de contrôle sont des données de
définition, et non une représentation de points raster. Ils permettent
plusieurs représentations mathématiques de la même courbe.

### Évaluation

**SOURCE FACT.** Dans [SkGeometry.cpp](https://github.com/google/skia/blob/main/src/core/SkGeometry.cpp),
SkEvalCubicAt prend quatre points et un paramètre et peut produire position,
tangente et courbure. Le code traite séparément les tangentes dégénérées aux
extrémités.

**DERIVED INTERPRETATION.** L'évaluation est une opération qui produit une
valeur géométrique à un paramètre donné. Elle n'est pas la rastérisation.

### Subdivision exacte

**SOURCE FACT.** SkChopCubicAt calcule les combinaisons affines successives de
quatre points et produit les points de contrôle de deux cubiques jointives au
paramètre demandé. Il accepte aussi plusieurs paramètres de coupe.

**SOURCE FACT.** FreeType contient Split_Conic et Split_Cubic. Ces routines
mettent deux sous-arcs Bézier dans une pile de travail ; les commentaires les
placent au cœur de la rastérisation et le calcul emploie une arithmétique
entière adaptée au rasterizer.

**DERIVED INTERPRETATION.** La subdivision conserve la géométrie paramétrique
sur des sous-intervalles, mais la représente par plusieurs courbes de même
degré. Elle n'est ni une évaluation ponctuelle ni une approximation par
segments.

### Approximation par segments

**SOURCE FACT.** [Anti-Grain Geometry](https://github.com/ghaerr/agg-2.6/blob/master/agg-src/include/agg_curves.h)
expose les familles curve3/curve4_inc et curve3/curve4_div. La famille div
possède une échelle d'approximation et une tolérance angulaire ; vertex()
produit des commandes move_to et line_to. La famille inc conserve un état de
progression et un nombre d'étapes.

**DERIVED INTERPRETATION.** La sortie AGG est une polyligne consommable, pas
la courbe exacte. Le nombre de points dépend d'un contrat d'approximation.

### Rasterisation

**SOURCE FACT.** Dans [FreeType ftraster.c](https://github.com/freetype/freetype/blob/master/src/raster/ftraster.c),
Split_Conic et Split_Cubic alimentent une pile de Bézier, puis Line_Up
transforme des segments en coordonnées de profils avec clipping vertical et
arithmétique fixe.

**DERIVED INTERPRETATION.** Le chemin courbe → approximation ou profils →
pixels comporte une opération de consommation distincte de la définition de
la courbe. Une ligne digitale ne décrit donc pas tout le résultat
intermédiaire Bézier.

## Implémentations réelles étudiées

### Skia — géométrie cubique

Source : [SkGeometry.cpp](https://github.com/google/skia/blob/main/src/core/SkGeometry.cpp),
branche main.

SkEvalCubicAt sépare position, dérivée et dérivée seconde. SkChopCubicAt
applique les interpolations de de Casteljau pour une ou plusieurs valeurs de
paramètre. Les fonctions de recherche d'extrema et d'inflexions produisent
des paramètres de coupe ; elles ne sont pas la subdivision elle-même.
Certaines coupes doubles utilisent des chemins SIMD : c'est une spécialisation
d'implémentation.

### Anti-Grain Geometry — approximation de chemin

Sources : [agg_curves.h](https://github.com/ghaerr/agg-2.6/blob/master/agg-src/include/agg_curves.h)
et [agg_curves.cpp](https://github.com/ghaerr/agg-2.6/blob/master/agg-src/src/agg_curves.cpp),
branche master.

curve*_inc garde un état incrémental et un nombre d'étapes. curve*_div
construit une liste par subdivision récursive, contrôlée par l'échelle et les
tolérances. vertex expose une sortie de chemin composée de déplacements et de
segments.

**INTERPRÉTATION.** AGG offre deux mécanismes pour le même besoin de sortie,
mais avec des contrats numériques différents : progression incrémentale à
nombre d'étapes calculé, ou subdivision conditionnée par une tolérance.

### FreeType — contour vers profils raster

Source : [ftraster.c](https://github.com/freetype/freetype/blob/master/src/raster/ftraster.c),
branche master.

Split_Conic et Split_Cubic subdivisent dans une pile. Line_Up produit ensuite
des coordonnées de profils, avec bornes verticales et arithmétique fixe. Le
contrat est celui d'un rasterizer de contours, non celui d'une API
d'évaluation géométrique générale.

## Distinctions confirmées

### Courbe géométrique versus points de contrôle

- **EVIDENCE** : Bézier, Gordon–Riesenfeld, Skia et AGG.
- **ERROR_IF_COLLAPSED** : les points de contrôle seraient traités comme des
  points produits par la courbe, ce qui rendrait fausses évaluation et
  subdivision.
- **SCOPE** : courbes paramétriques ; généralisation hors Bézier non testée.
- **FORM** : distinction locale entre données de définition et objet
  géométrique, pas promotion ontologique.

### Évaluation versus subdivision

- **EVIDENCE** : Skia sépare SkEvalCubicAt et SkChopCubicAt ; le résumé de
  1988 distingue la propriété de subdivision.
- **ERROR_IF_COLLAPSED** : une valeur P(t) serait confondue avec une paire de
  sous-courbes.
- **SCOPE** : courbes paramétriques.
- **FORM** : opérations distinctes et relation de conservation.

### Subdivision exacte versus approximation par segments

- **EVIDENCE** : Skia produit des cubiques de même degré ; AGG produit des
  commandes line_to contrôlées par une tolérance.
- **ERROR_IF_COLLAPSED** : une polyligne approchée serait déclarée équivalente
  à la courbe sans contrat d'erreur.
- **SCOPE** : courbes et rendu vectoriel.
- **FORM** : propriété de transformation, pas nécessairement concept.

### Évaluation/rasterisation versus sortie consommée

- **EVIDENCE** : FreeType sépare pile de Bézier, profils et coordonnées ;
  AGG expose des commandes de chemin.
- **ERROR_IF_COLLAPSED** : points géométriques, segments de chemin et pixels
  deviendraient le même résultat.
- **SCOPE** : graphisme vectoriel et raster.
- **FORM** : relation entre opération et résultat consommé.

### État incrémental versus subdivision adaptative

- **EVIDENCE** : AGG conserve état et nombre d'étapes dans inc, alors que div
  conserve une liste et un compteur ; FreeType conserve une pile.
- **ERROR_IF_COLLAPSED** : progression, mémoire temporaire et arrêt seraient
  attribués à tort à la courbe.
- **SCOPE** : mécanismes d'implémentation.
- **FORM** : connaissance de mécanisme et contexte de consommation.

## Test de la proto-ontologie actuelle

### Ce qu'elle décrit correctement

La séparation objet géométrique / opération / représentation est utile.
L'idée qu'une opération doit conserver son contrat de sortie fonctionne pour
l'évaluation, la subdivision et les sorties AGG. La distinction Bresenham
entre objet discret et représentation consommée se transfère partiellement :
une courbe évaluée n'est pas sa polyligne, et une polyligne n'est pas le profil
raster.

### Ce qu'elle force artificiellement

Assimiler une courbe à un segment géométrique enrichi perd la fonction
paramétrique, le degré et les données de contrôle. Assimiler subdivision et
approximation par segments confond une famille de sous-courbes exactes avec
une sortie tolérée. Assimiler toute sortie discrète à digital_line est trop
étroit : AGG produit une polyligne et FreeType un profil raster.

## Candidats et éléments différés

* **Donnée de contrôle** : connaissance candidate ; elle a un rôle de
  définition, mais aucune expérience hors Bézier ne justifie encore un concept
  permanent.
* **Conservation lors d'une subdivision** : relation candidate entre une
  courbe et des sous-courbes exactes ; elle est distincte d'une approximation.
* **Contrat d'approximation** : propriété candidate portant sur tolérance,
  règle d'arrêt et sortie ; aucune valeur n'a été mesurée ici.
* **Sortie de rendu** : information contextuelle ; profil raster, commandes de
  chemin et points échantillonnés dépendent du consommateur.
* **BezierCurve, ControlPoint, Evaluation et Subdivision** : termes utiles
  pour l'analyse, trop précoces comme concepts permanents.
* **de Casteljau** : mécanisme d'évaluation/subdivision, pas type d'objet.
* **Bézier** : ne devient pas un parent taxonomique de digital_line.

## Confirmed / Disproved / Unknown

### Confirmed

* « Courbe de Bézier » recouvre au moins définition paramétrique, évaluation,
  subdivision exacte, approximation et consommation raster.
* Subdivision exacte et approximation par segments ne sont pas le même résultat.
* De Casteljau est un mécanisme de calcul dont la propriété de subdivision est
  plus spécifique que la simple récursivité.
* La proto-ontologie conserve utilement objet / opération / représentation,
  mais segment et ligne digitale ne suffisent pas à décrire les courbes sans
  perte.

### Disproved

* « Courbe = segment avec une sortie raster plus riche » est insuffisant.
* « Subdivision = approximation par segments » est réfuté par les sous-courbes
  cubiques exactes produites par Skia et FreeType.

### Unknown

* La frontière minimale entre données de contrôle, représentation et définition
  n'a pas été testée sur les courbes rationnelles ou les B-splines.
* Les conditions d'arrêt AGG et FreeType n'ont pas été comparées sur des cas
  numériques communs.
* L'équivalence entre polyligne et consommation raster reste dépendante du
  contrat du moteur.
* Il n'est pas établi que Graphisme 2D classique doive promouvoir les
  opérations de courbe.

## Questions expérimentales éventuelles

1. Sur un même cubique, quelle différence existe entre subdivision exacte,
   approximation AGG et rasterisation FreeType à tolérance fixée ?
2. Une subdivision conserve-t-elle assez de provenance pour distinguer une
   sous-courbe exacte d'une polyligne approximative ?
3. Les contrats de clipping et d'extrémités de Bresenham se transfèrent-ils à
   une courbe aplatie ?

Aucune question n'est exécutée ici.

## Inventaire

* bezier-paper-to-code.md — sources, trajectoire, code réel, distinctions et
  limites.

Cette expédition n'ajoute aucun code, aucune dépendance, aucun benchmark et
ne modifie aucune proto-ontologie.
