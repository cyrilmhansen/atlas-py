# Cycle Bézier complet — recherche, approfondissement et harvest

## 1. État initial

L'expédition initiale avait déjà étudié Bézier, de Casteljau, Skia,
Anti-Grain Geometry et FreeType. Elle avait établi une différence entre :

* courbe paramétrique et points de contrôle ;
* évaluation ponctuelle ;
* subdivision exacte ;
* approximation par segments ;
* rasterisation et sortie consommée.

Elle n'avait pas encore discriminé ces distinctions par une expérience locale
et n'avait pas décidé si l'ontologie devait généraliser le segment
géométrique.

L'ontologie n'a pas été modifiée pendant ce cycle.

## 2. Trajectoire autonome suivie

### Branche 1 — contrat de chemin vectoriel

**OBSERVATION.** La source initiale traitait surtout l'objet mathématique et
les moteurs internes.

**QUESTION.** Une interface de chemin ajoute-t-elle une distinction qui ne
vient pas de l'algorithme de Bézier ?

**SOURCE CHOISIE.** [W3C SVG 2, Paths](https://www.w3.org/TR/SVG2/paths.html)
et [documentation SkPath::cubicTo](https://skia.googlesource.com/skia/%2B/2a8c48be4ff65d873d9d5ba65ecef989d82dd0be/site/user/api/SkPath_Reference.md).

**CONNAISSANCE.** Un chemin est une composition de sous-chemins et de
segments ; un segment cubique est défini par ses extrémités et ses points de
contrôle. La représentation de chemin peut donc porter un état de parcours et
une composition, sans être la courbe évaluée ni la sortie raster.

### Branche 2 — preuve locale de conservation

**OBSERVATION.** Skia et FreeType calculent des sous-courbes ; AGG produit
également une polyligne selon une tolérance.

**QUESTION.** Une subdivision exacte et une approximation par corde peuvent-
elles être distinguées par un cas analytique court ?

**SOURCE CHOISIE.** Une micro-expérience locale basée sur la construction de
de Casteljau, sans benchmark.

**CONNAISSANCE.** Oui : les sous-courbes reproduisent exactement les valeurs
de la courbe sur leurs sous-intervalles, tandis que la corde entre les
extrémités n'est qu'une approximation.

### Branche 3 — généralisation ontologique

**OBSERVATION.** Les termes Bézier importants ne sont pas tous des objets.

**QUESTION.** Quel ajout minimal éviterait de faire entrer une courbe dans le
modèle des segments sans créer une ontologie des courbes ?

**CONNAISSANCE.** Un concept candidat de courbe paramétrique est mieux
justifié qu'un concept nommé Bézier. Les points de contrôle, l'évaluation et
la subdivision restent respectivement des données, opérations et relations
possibles.

La recherche s'arrête ici : les sources supplémentaires devenaient
principalement redondantes pour la question de promotion minimale.

## 3. Sources supplémentaires et niveau de lecture

* [W3C SVG 2, Paths](https://www.w3.org/TR/SVG2/paths.html) : spécification
  technique primaire lue pour le contrat des chemins, des segments cubiques,
  des points de contrôle et des sous-chemins.
* [SkPath Reference](https://skia.googlesource.com/skia/%2B/2a8c48be4ff65d873d9d5ba65ecef989d82dd0be/site/user/api/SkPath_Reference.md) :
  documentation primaire lue pour la représentation d'un cubique dans un
  chemin.
* [SkPath cubicTo example](https://skia.googlesource.com/skia/%2B/refs/heads/main/docs/examples/SkPath_cubicTo_example.cpp) :
  exemple officiel lu ; il donne explicitement la forme paramétrique cubique
  et distingue les contrôles des extrémités.
* [SkGeometry.cpp](https://github.com/google/skia/blob/main/src/core/SkGeometry.cpp) :
  code réel lu pour SkEvalCubicAt, SkChopCubicAt et les coupes d'extrema ou
  d'inflexion.
* [AGG agg_curves.h](https://github.com/ghaerr/agg-2.6/blob/master/agg-src/include/agg_curves.h)
  et [agg_curves.cpp](https://github.com/ghaerr/agg-2.6/blob/master/agg-src/src/agg_curves.cpp) :
  code réel lu pour les familles incrémentale et récursive.
* [FreeType ftraster.c](https://github.com/freetype/freetype/blob/master/src/raster/ftraster.c) :
  code réel lu pour Split_Conic, Split_Cubic et Line_Up.

Les sources historiques de Bézier et de Casteljau restent celles indiquées
dans [l'expédition initiale](bezier-paper-to-code.md). Les rapports internes
de de Casteljau et le texte intégral ACM de Gordon–Riesenfeld n'ont toujours
pas été lus intégralement ; ils ne sont pas présentés comme des preuves
directes supplémentaires.

## 4. Micro-expérience discriminante

### Contrat

Comparer deux opérations sur le même cubique :

1. subdivision de de Casteljau au paramètre 0,5 ;
2. remplacement de la courbe par la corde reliant ses extrémités.

L'oracle attendu pour la première opération est l'identité de restriction :
le milieu de la sous-courbe gauche doit égaler la courbe originale à t=0,25,
et le milieu de la sous-courbe droite doit égaler la courbe originale à
t=0,75. Pour la corde, le point central est seulement le milieu des
extrémités.

### Cas

Points de contrôle cubiques :

    P0=(0,0), P1=(0,3), P2=(3,3), P3=(3,0)

Le script reproductible est
[bezier_subdivision_experiment.py](bezier_subdivision_experiment.py).
Il ne mesure pas le temps ; il calcule uniquement les points et les égalités
géométriques.

### Résultat observé

    left_midpoint_equals_original_quarter: true
    right_midpoint_equals_original_three_quarters: true
    curve_at_0.5: (1.5, 2.25)
    chord_midpoint: (1.5, 0.0)
    chord_midpoint_euclidean_error: 2.25

Le résultat complet est conservé dans
[bezier_subdivision_experiment.json](bezier_subdivision_experiment.json).

**SOURCE FACT EXPÉRIMENTAL.** La subdivision calculée par les combinaisons
affines conserve les deux restrictions ; la corde ne les conserve pas.

**DERIVED INTERPRETATION.** « Produire moins de points » ne décrit pas une
subdivision exacte. La sortie polyligne doit porter un contrat d'approximation
si elle remplace la courbe.

## 5. Test du modèle actuel

### Distinction : courbe géométrique / segment géométrique

- **EVIDENCE** : Bézier, SVG, Skia, AGG et FreeType utilisent une forme
  paramétrique avec données de contrôle, non seulement deux extrémités.
- **ERROR_IF_COLLAPSED** : degré, paramètre et contrôle seraient perdus ; une
  courbe ne pourrait plus être distinguée de sa corde.
- **SCOPE** : courbes paramétriques ; la généralisation à toutes les courbes
  2D n'est pas établie.
- **FORM** : concept candidat local, distinct de geometric_segment.
- **STATUT** : CONCEPT_CANDIDATE.

### Distinction : données de contrôle / objet courbe

- **EVIDENCE** : SVG définit les extrémités et contrôles comme paramètres du
  segment ; SkPath les stocke dans la commande de chemin ; Skia les consomme
  pour évaluer ou couper.
- **ERROR_IF_COLLAPSED** : un point de contrôle serait confondu avec un point
  de la courbe ou avec une occurrence de représentation.
- **SCOPE** : courbes paramétriques.
- **FORM** : information de définition et relation, pas concept promu.
- **STATUT** : KNOWLEDGE_ONLY.

### Distinction : évaluation / subdivision exacte

- **EVIDENCE** : SkEvalCubicAt et SkChopCubicAt ont des contrats différents ;
  la micro-expérience vérifie la conservation de restriction.
- **ERROR_IF_COLLAPSED** : une position à t serait confondue avec des
  sous-courbes.
- **SCOPE** : opérations sur courbes.
- **FORM** : opérations existantes à qualifier, pas nouveaux objets.
- **STATUT** : ALREADY_REPRESENTABLE comme opérations, avec connaissance
  spécifique de conservation.

### Distinction : subdivision exacte / approximation par segments

- **EVIDENCE** : Skia et FreeType produisent des sous-courbes ; AGG produit
  des line_to contrôlés par tolérance ; l'expérience donne une divergence
  numérique minimale.
- **ERROR_IF_COLLAPSED** : une approximation serait considérée comme une
  représentation exacte de l'objet.
- **SCOPE** : courbes et rendu vectoriel.
- **FORM** : relation/propriété de transformation et contrat d'erreur.
- **STATUT** : RELATION_CANDIDATE, mais trop tôt pour l'ontologie.

### Distinction : courbe / sortie consommée

- **EVIDENCE** : SVG décrit un path ; AGG fournit une polyligne ; FreeType
  fournit des profils raster.
- **ERROR_IF_COLLAPSED** : le consommateur et la géométrie seraient confondus.
- **SCOPE** : graphisme vectoriel et raster.
- **FORM** : contexte et relation de production ; la séparation objet /
  représentation existante suffit partiellement.
- **STATUT** : ALREADY_REPRESENTABLE / KNOWLEDGE_ONLY.

### Distinction : de Casteljau

- **EVIDENCE** : Skia et FreeType emploient les combinaisons qui réalisent
  l'évaluation ou la coupe ; le résumé scientifique de 1988 distingue sa
  propriété de subdivision.
- **ERROR_IF_COLLAPSED** : on ferait du nom historique un type d'objet, ou on
  attribuerait la subdivision exacte à toute récursion.
- **SCOPE** : mécanisme algorithmique de courbes de Bézier.
- **FORM** : connaissance de mécanisme.
- **STATUT** : KNOWLEDGE_ONLY.

## 6. Harvest

### Déjà représentable

* Une opération possède une entrée et produit un résultat : réutilisation de
  opère sur et produit.
* Un résultat peut avoir une représentation distincte : réutilisation de
  est représenté par et transforme en.
* Le segment géométrique et la ligne digitale restent valides pour leur cas
  Bresenham ; ils ne doivent pas être forcés sur Bézier.

### Patch conceptuel minimal proposé

Ajouter un seul concept local :

    ID : classic_2d_graphics.parametric_curve
    FR : courbe paramétrique
    en-GB : parametric curve

Définition proposée : objet géométrique défini par un paramètre et des données
de contrôle ou coefficients, dont la forme ne se réduit pas à ses points
d'extrémité.

Réutiliser les relations déjà présentes :

* opère sur : évaluation, subdivision ou approximation → courbe ;
* produit : évaluation → position ; subdivision → sous-courbes ;
  approximation → polyligne ;
* transforme en : subdivision ou approximation → sortie correspondante ;
* est représentée par : une commande de chemin ou une autre occurrence de
  représentation.

Aucune nouvelle relation générique n'est nécessaire dans ce patch conceptuel.
La conservation exacte d'une subdivision, la tolérance d'approximation et la
provenance des contrôles restent des propriétés de connaissance attachées aux
opérations.

### Éléments différés ou rejetés

* Ne pas ajouter Bezier ou BezierCurve : le concept proposé doit couvrir le
  mécanisme sans figer une famille historique.
* Ne pas ajouter ControlPoint : les preuves imposent une donnée de définition,
  pas une entité autonome.
* Ne pas ajouter DeCasteljau : c'est un mécanisme.
* Ne pas ajouter Evaluation ou Subdivision comme concepts : les relations
  opérationnelles existantes suffisent pour le besoin actuel.
* Ne pas généraliser digital_line : une polyligne et un profil raster ne sont
  pas une ligne digitale par simple analogie.
* Ne pas créer un concept universel de sortie raster ou de tolérance.

## 7. Retour sur Bresenham

### Distinctions qui survivent

* objet géométrique distinct de l'opération de discrétisation ;
* opération distincte de son résultat et de la représentation consommée ;
* importance du contrat de sortie ;
* conservation d'un état ou d'une information intermédiaire lorsqu'une
  transformation ultérieure prétend préserver le résultat.

### Distinctions trop spécifiques aux segments

* tie-breaking, réversibilité et translation-invariance ne sont pas des
  propriétés générales de toute courbe ;
* la ligne digitale n'est pas le résultat générique de toute rastérisation ;
* l'état d'erreur entier de Bresenham ne se transfère pas comme mécanisme
  Bézier.

### Structure candidate, non généralisée

Les deux corpus suggèrent un schéma local :

    objet géométrique
      → opération de transformation/évaluation
      → résultat sous contrat
      → représentation consommée

Cette structure reste une conclusion de recherche, pas une nouvelle
ontologie transversale.

## 8. Confirmed / Disproved / Unknown

### Confirmed

* Le modèle objet / opération / représentation reste utile pour Bézier.
* Une courbe paramétrique ne peut pas être représentée sans perte par le seul
  concept de segment géométrique.
* Subdivision exacte et approximation par segments ont des contrats distincts.
* Le cas analytique confirme qu'une corde peut différer de la courbe alors que
  la subdivision de de Casteljau conserve exactement ses restrictions.

### Disproved

* « Courbe = segment enrichi » est insuffisant.
* « Subdivision = approximation » est faux dans le cas exact étudié.
* « de Casteljau » ne suffit pas à identifier le contrat : le nom peut
  désigner évaluation, coupe ou mécanisme interne selon l'appelant.

### Unknown

* La frontière entre contrôle, définition et représentation n'est pas testée
  sur les courbes rationnelles ou les B-splines.
* Le concept courbe paramétrique doit-il subsumer ou seulement côtoyer
  geometric_segment ?
* Une sous-courbe exacte doit-elle recevoir une identité d'objet distincte ou
  être décrite comme un objet restreint de la courbe source ?
* Les contrats de clipping et d'extrémités de Bresenham se transfèrent-ils à
  une courbe aplatie ?
* L'approximation doit-elle porter une tolérance, une borne d'erreur ou une
  autre garantie selon le consommateur ?

## 9. Reproduction

    python3 -B expeditions/bezier-paper-to-code/bezier_subdivision_experiment.py

Cette commande régénère le résultat analytique local. Le cycle n'inclut aucun
benchmark de performance et n'a modifié aucune ontologie.
