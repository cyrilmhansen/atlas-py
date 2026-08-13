# Proto-ontologie locale — Graphisme 2D classique

- Nom FR : **Graphisme 2D classique**
- Nom en-GB : **Classic 2D graphics**
- Identifiant : `classic_2d_graphics`

Cette proto-ontologie est issue des trois expéditions QuickDraw consacrées à
BitBlt, aux régions et aux opérations booléennes. Elle décrit les objets et
mécanismes graphiques nécessaires aux expériences réalisées, pas l'API
QuickDraw complète.

## Concepts retenus

### Région

- ID : `classic_2d_graphics.region`
- FR : **région**
- en-GB : **region**
- Définition : ensemble logique de pixels ou de coordonnées 2D appartenant à
  une forme, indépendant de la représentation utilisée pour le stocker.
- Alias : **Rgn** (terme historique QuickDraw, réservé à la recherche).
- Statut : **forcé**.
- Relations locales établies :
  - peut être représentée par un bitmap, des segments horizontaux ou des
    transitions différentielles ;
  - possède éventuellement un rectangle englobant ;
  - peut être l'entrée ou le résultat d'une opération booléenne ;
  - peut limiter l'application d'un blit.
- Justification Atlas : les expériences G0–G3 et B0–B2 comparent plusieurs
  représentations fonctionnellement équivalentes de la même région logique.

La distinction entre la région logique et l'instance concrète d'une
représentation est nécessaire dans ce domaine, mais l'instance n'est pas une
nouvelle espèce de région. Dans le cas v1.1, `b0_C` et `b1_C` sont deux
occurrences représentant le même `C`.

### Rectangle

- ID : `classic_2d_graphics.rectangle`
- FR : **rectangle**
- en-GB : **rectangle**
- Définition : zone 2D définie par quatre coordonnées ordonnées, utilisée
  comme étendue de bitmap, de région ou de blit.
- Alias : **Rect** (type historique QuickDraw).
- Statut : **forcé**.
- Relations locales établies :
  - possède un rectangle englobant lorsqu'il décrit une région ;
  - définit une étendue source ou destination pour BitBlt ;
  - peut être un cas spécialisé de région rectangulaire.
- Justification Atlas : les contrats BitBlt et régions utilisent explicitement
  des rectangles, leurs intersections et leurs bounding boxes.

### Rectangle englobant

- ID : `classic_2d_graphics.bounding_rectangle`
- FR : **rectangle englobant**
- en-GB : **bounding rectangle**
- Définition : plus petit rectangle expérimental contenant la région ou la
  zone de travail considérée.
- Alias : **bounding box**, **bbox** (termes des notes et des mesures).
- Statut : **forcé**.
- Relations locales établies :
  - borne l'univers de parcours ou de stockage ;
  - permet un rejet rapide d'une opération disjointe ;
  - contribue au coût bitmap mais ne suffit pas à décrire la complexité d'une
    région.
- Justification Atlas : QuickDraw utilise la bounding box pour limiter le
  travail ; les mesures montrent qu'une même bbox peut cacher des densités,
  nombres de runs et stabilités verticales très différents.

### Bitmap

- ID : `classic_2d_graphics.bitmap`
- FR : **bitmap**
- en-GB : **bitmap**
- Définition : tableau de bits organisé par scanlines, avec une largeur,
  hauteur et un stride, pouvant contenir des pixels ou un masque de région.
- Alias : **BitMap** (type historique QuickDraw).
- Statut : **forcé**.
- Relations locales établies :
  - peut représenter une région comme masque bitmap ;
  - est l'entrée ou la destination de BitBlt ;
  - conserve un stride distinct de la largeur logique.
- Justification Atlas : le sous-ensemble BitBlt est défini sur des bitmaps 1 bit
  et G0/B0 utilisent un masque bitmap.

### Représentation bitmap d'une région

- ID : `classic_2d_graphics.bitmap_region_representation`
- FR : **représentation bitmap d'une région**
- en-GB : **bitmap region representation**
- Définition : représentation d'une région par un bit de masque pour chaque
  position de l'univers bitmap considéré.
- Alias : **B0**, **bitmap mask**.
- Statut : **forcé**.
- Relations locales établies :
  - représente une région ;
  - combine des régions par opérations bit à bit ;
  - peut être transformée en représentation par segments horizontaux.
- Justification Atlas : B0 est mesuré comme représentation réelle des
  opérations booléennes et comme source de la conversion native B0→B1.

### Représentation par segments horizontaux

- ID : `classic_2d_graphics.horizontal_run_representation`
- FR : **représentation par segments horizontaux**
- en-GB : **horizontal-run representation**
- Définition : représentation d'une région par intervalles horizontaux actifs,
  ordonnés par scanline.
- Alias : **B1**, **runs**.
- Statut : **forcé**.
- Relations locales établies :
  - représente une région ;
  - peut être fusionnée avec une autre représentation de segments ;
  - peut être appliquée rapidement lorsque le résultat est sparse ;
  - peut être volumineuse lorsque la région est très fragmentée.
- Justification Atlas : G1/B1 est fonctionnellement validée, comparée en
  stockage, combinaison et application, puis produite par conversion native
  depuis un résultat B0 exact.

### Représentation différentielle par transitions

- ID : `classic_2d_graphics.differential_transition_representation`
- FR : **représentation différentielle par transitions**
- en-GB : **differential-transition representation**
- Définition : représentation compacte qui encode les changements verticaux et
  les inversions horizontales nécessaires pour reconstruire les scanlines.
- Alias : **B2**, **transitions**.
- Statut : **forcé**.
- Relations locales établies :
  - représente une région ;
  - conserve l'état d'une scanline jusqu'au prochain événement vertical ;
  - peut réduire fortement le stockage lorsque les scanlines se répètent ;
  - n'est pas nécessairement rapide à appliquer sur la plateforme moderne.
- Justification Atlas : G2/B2 est inspirée des mécanismes QuickDraw observés
  dans `PackRgn.a`, `SeekRgn.a` et `RgnOp.a`, puis comparée à B0/B1.

### BitBlt

- ID : `classic_2d_graphics.bitblt`
- FR : **BitBlt**
- en-GB : **BitBlt**
- Définition : opération de transfert rectangulaire de bits entre bitmaps,
  avec rectangles source et destination, stride et mode de copie.
- Alias : **BITBLT**, **bit block transfer** (forme documentaire).
- Statut : **forcé**.
- Relations locales établies :
  - opère sur des bitmaps et des rectangles ;
  - peut recevoir un masque de région par l'intermédiaire du clipping ;
  - `srcCopy` est le mode retenu dans les expériences ;
  - le sens de parcours protège les copies avec chevauchement.
- Justification Atlas : QuickDraw 1 a établi le contrat et comparé R0–R3 sur
  des copies 1 bit, alignées, désalignées et avec chevauchement.

### Rognage

- ID : `classic_2d_graphics.clipping`
- FR : **rognage**
- en-GB : **clipping**
- Définition : restriction d'une opération graphique aux pixels appartenant à
  une région ou à une étendue autorisée.
- Alias : **clip** (terme de code).
- Statut : **forcé**.
- Relations locales établies :
  - limite l'application d'un BitBlt ;
  - utilise une région et un rectangle destination ;
  - peut rejeter une opération à partir des bounding boxes.
- Justification Atlas : QuickDraw 2 étudie précisément l'application d'un
  `srcCopy` limité par une région.

### Opération booléenne sur régions

- ID : `classic_2d_graphics.region_boolean_operation`
- FR : **opération booléenne sur régions**
- en-GB : **region boolean operation**
- Définition : opération qui construit une région logique à partir de deux
  régions selon une combinaison d'appartenance.
- Alias : aucun.
- Statut : **forcé**.
- Relations locales établies :
  - produit une région résultat ;
  - peut être implémentée par bitmap, fusion de segments ou fusion de
    transitions ;
  - conserve la distinction entre coût de combinaison et coût d'application.
- Justification Atlas : QuickDraw 3 mesure B0, B1 et B2 sur intersection,
  union, différence et XOR avec un oracle indépendant.

### Intersection

- ID : `classic_2d_graphics.region_intersection`
- FR : **intersection de régions**
- en-GB : **region intersection**
- Définition : opération qui retient les positions appartenant aux deux
  régions d'entrée.
- Alias : **AND** (forme opérationnelle dans les implémentations bitmap).
- Statut : **forcé**.
- Relations locales établies :
  - est une opération booléenne sur régions ;
  - produit une région qui peut être représentée en B0, B1 ou B2.
- Justification Atlas : `sparse_sparse/intersection` et
  `fragmented_fragmented/intersection` sont les spécimens de la correction
  native B0→B1 ; l'intersection est aussi couverte dans QuickDraw 3.

### Union

- ID : `classic_2d_graphics.region_union`
- FR : **union de régions**
- en-GB : **region union**
- Définition : opération qui retient les positions appartenant à au moins une
  des deux régions d'entrée.
- Alias : **OR** (forme opérationnelle).
- Statut : **forcé**.
- Relations locales établies :
  - est une opération booléenne sur régions ;
  - peut modifier fortement la densité et le nombre de segments du résultat.
- Justification Atlas : les corpus QuickDraw 3 testent union sur des paires
  sparse/dense et dense/dense.

### Différence de régions

- ID : `classic_2d_graphics.region_difference`
- FR : **différence de régions**
- en-GB : **region difference**
- Définition : opération qui retient les positions de la première région qui
  n'appartiennent pas à la seconde.
- Alias : **difference**, **A-B**.
- Statut : **forcé**.
- Relations locales établies :
  - est une opération booléenne sur régions ;
  - peut produire une région vide ou très fragmentée.
- Justification Atlas : la différence fait partie des quatre opérations
  fonctionnelles QuickDraw 3 et de l'oracle indépendant.

### Différence symétrique

- ID : `classic_2d_graphics.region_symmetric_difference`
- FR : **différence symétrique de régions**
- en-GB : **region symmetric difference**
- Définition : opération qui retient les positions appartenant à une seule des
  deux régions d'entrée.
- Alias : **XOR**.
- Statut : **forcé**.
- Relations locales établies :
  - est une opération booléenne sur régions ;
  - peut produire le vide lorsque les entrées sont identiques.
- Justification Atlas : XOR est couvert par le corpus et l'oracle QuickDraw 3.

### Conversion de représentation

- ID : `classic_2d_graphics.representation_conversion`
- FR : **conversion de représentation**
- en-GB : **representation conversion**
- Définition : transformation qui matérialise une région existante dans un
  autre formalisme sans changer son identité logique.
- Alias : **B0-to-B1 conversion** pour le cas mesuré.
- Statut : **forcé**.
- Relations locales établies :
  - transforme une occurrence de représentation en une occurrence d'une autre
    représentation ;
  - préserve la région logique lorsque la comparaison canonique le vérifie ;
  - possède un coût de construction distinct du coût d'application.
- Justification Atlas : QuickDraw 1.1 exécute et vérifie `B0 result → B1
  converted` dans le même harness C. Les anciens seuils Python N=66/N=119
  restent historiques et non démontrés physiquement.

### Application d'une région

- ID : `classic_2d_graphics.region_application`
- FR : **application d'une région**
- en-GB : **region application**
- Définition : utilisation d'une représentation de région pour limiter une
  opération bitmap, notamment un `srcCopy`.
- Alias : **apply clip**.
- Statut : **forcé**.
- Relations locales établies :
  - opère sur une région représentée et un bitmap ;
  - est distincte de la construction et de la combinaison de régions ;
  - son coût dépend de la représentation et de la forme du résultat.
- Justification Atlas : QuickDraw 2 sépare construction, stockage et
  application ; QuickDraw 3 montre que le meilleur opérateur de combinaison
  n'est pas toujours le meilleur applicateur.

## Distinctions locales à préserver

### Région, représentation et occurrence

Une région logique `C` n'est pas confondue avec `B0(C)` ou `B1(C)`. Une
occurrence concrète, par exemple `b0_C`, porte le résultat effectivement
produit, tandis que `b1_C` peut être l'occurrence obtenue par conversion de ce
même résultat. Cette distinction explique pourquoi un masque Python
reconstruit ne pouvait pas être substitué au résultat B0 QuickDraw dans l'audit
v1.

Il s'agit d'une discipline locale de description des expériences ; elle ne
crée pas trois sortes universelles de régions.

### Opération, mécanisme et propriété

- une **opération** produit ou applique un résultat : intersection, BitBlt,
  conversion ;
- un **mécanisme** est la manière concrète de réaliser l'opération : masque
  bitmap, fusion de runs, transitions différentielles, masques de bords et
  parcours directionnel ;
- une **propriété** décrit le résultat ou le coût : aire, bbox, densité, runs,
  transitions, stockage, durée.

Ces catégories servent ici à éviter de confondre B1 avec l'opération qu'elle
réalise. Elles ne sont pas proposées comme classes transversales obligatoires.

## Concepts candidats ou volontairement écartés

### Candidats

- **motif / pattern** (`pattern`) : présent dans le contrat historique de
  BitBlt, mais exclu du sous-ensemble expérimental `srcCopy` ;
- **mode de transfert** (`transfer_mode`) : `srcCopy` est mesuré, mais aucun
  catalogue des modes booléens BitBlt n'a été étudié ;
- **région vide et région rectangulaire** (`empty_region`,
  `rectangular_region`) : cas spécialisés réellement observés, mais encore
  traités comme propriétés ou variantes de `region`, pas comme concepts
  autonomes ;
- **spécimen de représentation** (`representation_specimen`) : distinction
  nécessaire pour la preuve B0→B1, mais conservée pour l'instant comme rôle
  d'occurrence plutôt que comme entrée lexicale séparée.

### Écartés de cette proto-ontologie

Patterns complets, scaling, régions géométriques complexes, polygones,
lignes, ovales, texte, autres opérations QuickDraw et GPU ne sont pas des
concepts retenus : aucune expérience présente ne les rend nécessaires.

Les concepts `workload`, `scenario`, `reuse_count`, `memory constraint`,
`measurement`, `platform` et `protocol` qualifient les expériences et les
décisions. Ils ne sont pas ajoutés comme concepts graphiques locaux.

## Relations locales établies

Ces relations restent propres au domaine `classic_2d_graphics` :

| Relation FR | Relation en-GB | Usage établi |
|---|---|---|
| est représentée par | is represented by | Région → bitmap, runs ou transitions. |
| possède pour rectangle englobant | has bounding rectangle | Région → rectangle englobant. |
| opère sur | operates on | BitBlt → bitmaps/rectangles ; opération booléenne → régions. |
| produit | produces | Intersection/union/différence/XOR → région résultat. |
| limite | clips | Rognage → opération bitmap ; région → zone d'application. |
| transforme en | transforms into | Conversion → nouvelle occurrence de représentation de la même région. |
| applique | applies | Application de région → BitBlt ou copie `srcCopy`. |
| spécialise | specialises | Représentation rectangulaire ou fast path aligné → cas général local. |
| fusionne | merges | Opération B1/B2 → flux de segments ou transitions ordonnées. |

Ces relations ne disent rien des relations avec le domaine algorithmique.
Une future inférence pourra rapprocher `fusionne` de `ordered merge` sans
faire de cette relation une appartenance permanente.

## Limites locales

La proto-ontologie ne comprend pas de modèle de coût, de plateforme, de
provenance, de scénario ou de contexte inter-domaines. Elle conserve seulement
les concepts graphiques nécessaires pour interpréter les résultats existants.
Les performances QuickDraw historiques du 68000 original restent distinctes
des mesures des réimplémentations C modernes.
