# Contexte d'inférence — réutilisation d'un résultat de région QuickDraw

Type : contexte manuel, local à une décision QuickDraw. Il ne crée aucune
relation permanente entre les domaines et ne constitue pas un moteur
d'inférence.

## 1. Besoin

Après une opération booléenne sur deux régions, choisir entre :

1. conserver le résultat dans sa représentation bitmap B0 ;
2. convertir ce même résultat B0 vers la représentation B1 par segments
   horizontaux ;
3. appliquer ensuite la représentation choisie plusieurs fois à un `srcCopy`.

La question porte sur le cycle de vie complet :

```text
production B0 → conversion éventuelle → applications répétées
```

Le contexte ne cherche pas un gagnant universel. Il compare le coût fixe de
la conversion au gain par application, pour un spécimen logique, un workload,
une plateforme et un protocole donnés.

## 2. Concepts activés — `classic_2d_graphics`

Les concepts suivants sont activés depuis
`ontology/domains/classic-2d-graphics.md` :

- `classic_2d_graphics.region` : objet logique résultat de l'opération
  booléenne ;
- `classic_2d_graphics.region_boolean_operation` : production du résultat ;
- `classic_2d_graphics.region_intersection` : opération effectivement utilisée
  par les deux cas de mesure ;
- `classic_2d_graphics.bitmap_region_representation` : représentation B0 du
  résultat ;
- `classic_2d_graphics.horizontal_run_representation` : représentation B1
  cible ;
- `classic_2d_graphics.representation_conversion` : transformation B0 → B1 ;
- `classic_2d_graphics.region_application` : application répétée du clip ;
- `classic_2d_graphics.clipping` et `classic_2d_graphics.bitblt` : opération
  bitmap à laquelle la région est appliquée.

Le rectangle englobant, la densité, le nombre de segments et le stockage sont
utilisés comme propriétés du spécimen ou du résultat. Ils ne sont pas promus
ici en nouveaux concepts.

## 3. Concepts activés — `elementary_algorithms`

Seuls les concepts réellement utiles au rapprochement sont activés :

- `elementary_algorithms.sequence` : ordre des intervalles horizontaux dans
  une représentation B1 ;
- `elementary_algorithms.traversal` : parcours ordonné des intervalles ou du
  résultat lors de l'application ;
- `elementary_algorithms.ordered_merge` : mécanisme algorithmique utilisable
  pour combiner des séquences d'intervalles ordonnées.

Les concepts `collection`, `lookup`, `sorted_sequence`, `hash_table`,
`open_addressing` et `binary_search` ne sont pas activés : ils ne contribuent
pas à cette décision QuickDraw.

## 4. Propriétés et observations hors des deux ontologies

Ces informations sont nécessaires au raisonnement, mais ne sont rattachées à
aucun des deux domaines locaux :

### Besoin et cycle de vie

- scénario : `sparse_sparse/intersection` ou
  `fragmented_fragmented/intersection` ;
- nombre d'applications `N` ;
- régime de réutilisation, par exemple `build_once_apply_many` ;
- décision : conserver B0 ou convertir vers B1.

Le `reuse_count` est un compteur contextuel. Il compte ici les occurrences de
l'application du résultat, pas les constructions ni les conversions.

### Mesures et provenance

- durée de production B0 ;
- durée de conversion B0→B1 ;
- durée d'application B0 par usage ;
- durée d'application B1 par usage ;
- stockage B0 et B1 ;
- plateforme, compilateur, options, timer, CPU, échauffement, nombre
  d'échantillons et statistique ;
- expérience, exécutable, spécimen concret et artefact de résultat.

Ces éléments relèvent de la lignée expérimentale et du contexte de décision,
pas de l'ontologie algorithmique ou graphique.

### Identité du spécimen

Le résultat concret est noté localement `b0_C` : c'est le bitmap effectivement
produit par l'opération B0. `b1_C` est la représentation B1 obtenue en
convertissant `b0_C`. Les hash canoniques et les applications bit-identiques
servent à vérifier qu'il s'agit du même objet logique `C`.

### Expression de cycle de vie

Le contexte utilise les expressions locales suivantes :

```text
without_conversion(N) = production_B0 + N × apply_B0
with_conversion(N)    = production_B0 + conversion_B0_to_B1
                           + N × apply_B1_converted
```

La production commune s'annule dans la comparaison algébrique, mais reste
conservée pour décrire le cycle de vie complet.

## 5. Rapprochements contextuels

### B1 et séquence ordonnée

Dans ce contexte seulement :

```text
horizontal_run_representation(C)
    expose une sequence ordonnée d'intervalles horizontaux
```

Cela ne signifie pas :

```text
Region is-a Sequence
horizontal_run_representation belongs_to elementary_algorithms
```

La représentation B1 reste un concept du graphisme 2D classique. La
`sequence` est une propriété de parcours rendue pertinente par la décision.

### Combinaison et fusion

Une opération booléenne B1 peut exploiter un parcours/fusion de séquences
d'intervalles ordonnées. Cette relation explique pourquoi
`ordered_merge` est activé ; elle ne crée pas une nouvelle relation
permanente entre les proto-ontologies.

Le bitmap B0, lui, peut combiner directement des masques sur l'univers bitmap.
Le contexte conserve donc deux mécanismes graphiques concurrents et leurs
propriétés observées ; il ne réduit pas leur différence à une catégorie
algorithmique commune.

### Conversion et identité logique

```text
C
├── b0_C : bitmap_region_representation
└── b1_C : horizontal_run_representation
       ^
       └── representation_conversion(b0_C, b1_C)
```

La conversion transforme une occurrence de représentation, pas l'objet
logique `C`. Le résultat est admissible dans ce contexte seulement si la
comparaison canonique établit l'identité logique.

## 6. Connaissances négatives et limites

- Il n'existe pas de représentation gagnante partout.
- B0 est généralement très efficace pour la combinaison bitmap sur l'univers
  testé ; B1 peut être nettement meilleur à l'application lorsque le résultat
  est sparse ; B2 peut être beaucoup plus compact sans être plus rapide.
- Le nombre de réutilisations change le classement : le coût de production ou
  conversion fixe ne peut pas être ignoré.
- La densité, le nombre de segments, la stabilité entre scanlines, la bounding
  box et le stockage sont des dimensions distinctes ; aucune ne suffit seule
  à prédire le choix.
- Sur `sparse_sparse/intersection`, le harness C natif donne un point-estimate
  de break-even à `N=7` et confirme le gain end-to-end près de cette frontière.
- Sur `fragmented_fragmented/intersection`, le point-estimate est `N=4`, mais
  la mesure end-to-end est pratiquement à égalité ; une frontière physique
  stable n'est pas établie.
- Les anciens `N=66` et `N=119` de Semantic Core v1 sont des artefacts
  historiques fondés sur une conversion Python et ne sont pas des break-even
  QuickDraw démontrés.
- La conversion B0→B1 mesurée ici est locale à ce harness, cette plateforme,
  ces spécimens et ce protocole. Elle ne définit pas une loi générale de
  performance.
- Un compteur de réutilisation doit être interprété comme comptant des
  applications dans ce contexte. La sémantique générale de la relation entre
  compteurs et événements n'est pas définie ici.

## 7. Décisions et expériences auxquelles le contexte aboutit

Le contexte permet de formuler et de vérifier, sans nouveau modèle général :

1. construire les entrées et produire le résultat B0 ;
2. conserver l'identité concrète `b0_C` ;
3. convertir `b0_C` en `b1_C` ;
4. vérifier l'identité logique par hash canonique et application ;
5. mesurer séparément production, conversion, application B0 et application B1 ;
6. calculer le premier entier strictement favorable par une boucle simple ;
7. comparer ce point-estimate à une mesure end-to-end ;
8. refuser une décision trop forte lorsque la frontière est dans le bruit.

Le contexte permet donc d'aboutir à une décision conditionnelle : convertir
est clairement avantageux pour le cas sparse dans le protocole mesuré ; le cas
fragmenté ne justifie pas une règle automatique à partir de la seule
expression arithmétique.

## Context pack agentique

### Objectif

Évaluer la décision « conserver B0 ou convertir le résultat B0 exact en B1
avant des applications répétées » sur le spécimen et le protocole QuickDraw
indiqués.

### Vocabulaire utile

`Region`, `region_intersection`, `B0 bitmap`, `B1 horizontal runs`,
`representation_conversion`, `region_application`, `sequence`, `traversal`,
`ordered_merge`, `b0_C`, `b1_C`, `reuse_count`.

### Faits acquis

- B0, B1 et B2 sont fonctionnellement équivalentes lorsqu'elles décrivent la
  même région.
- B0 combine généralement vite ; B1 peut appliquer très vite un résultat
  sparse ; B2 peut économiser du stockage.
- Le harness C natif convertit le résultat B0 réel, et les hash canoniques
  B0/B1 concordent.
- Sparse : point-estimate `N=7`, gain end-to-end confirmé près de la frontière.
- Fragmented : point-estimate `N=4`, frontière end-to-end non robuste.

### Propriétés importantes

Conserver la bounding box, densité, nombre de segments, transitions verticales,
stockage, coût de production, coût de conversion, coût d'application et nombre
d'applications. Conserver la provenance du programme, du spécimen, du
workload, de l'opération et du protocole.

### Mécanismes candidats

- conserver B0 et appliquer le masque bitmap ;
- convertir le même résultat B0 en B1 puis appliquer les segments ;
- conserver B2 uniquement comme comparaison historique déjà mesurée, sans
  ajouter une nouvelle stratégie à cette décision.

### Erreurs connues à ne pas reproduire

- ne pas reconstruire un masque à partir du nom du workload ;
- ne pas confondre représentation abstraite et spécimen concret ;
- ne pas mélanger une conversion Python avec des applications C ;
- ne pas prendre `N=66/N=119` pour des résultats physiques ;
- ne pas additionner des point-estimates hétérogènes sans vérifier
  end-to-end ;
- ne pas considérer `N=4` fragmented comme une frontière établie.

### Questions encore ouvertes

- stabilité de la frontière fragmented ;
- coût sur d'autres tailles, plateformes et formes ;
- coût de conversions B1/B2 ;
- relation générale entre un compteur et l'événement qu'il compte.

### Condition d'arrêt

S'arrêter lorsque l'identité logique, les quatre coûts composantes et la
comparaison end-to-end autour du point-estimate sont vérifiés pour les deux
cas. Ne pas construire de moteur d'inférence, de scoring ou de politique
adaptative.

## Réponses finales

### 1. Quelles informations utiles ont dû être prises en dehors des deux proto-ontologies ?

Le contexte a besoin du cycle de vie et du scénario, du nombre de réutilisations,
des mesures physiques, de la plateforme et du protocole, de la lignée
expérimentale, de l'identité des spécimens `b0_C`/`b1_C` et des expressions de
coût. Ces informations décrivent un besoin, une expérience ou une décision ;
elles ne sont pas des concepts des deux domaines.

### 2. Quel rapprochement inter-domaines a réellement été nécessaire ?

Un seul rapprochement est nécessaire : la représentation B1, qui reste une
représentation graphique, expose des intervalles horizontaux ordonnés que le
contexte peut traiter comme une séquence et combiner par fusion ordonnée. Ce
rapprochement est contextuel ; il ne crée ni `Region is-a Sequence`, ni
appartenance de B1 au domaine algorithmique.

### 3. Les deux ontologies ont-elles dû être modifiées pour réaliser ce raisonnement ?

Non. Les concepts déjà présents suffisent. Les informations supplémentaires
restent dans le contexte : scénario, spécimens, mesures, provenance, cycle de
vie et décision. Aucune relation permanente entre les domaines n'a été créée.
