# Expédition — combinaisons ordonnées dans du logiciel réel

## Objet et périmètre

Cette note compare cinq implémentations existantes qui combinent ou
confrontent des flux ordonnés. Elle ne cherche ni une ontologie commune, ni
une hiérarchie de solutions. Chaque fiche conserve le contrat du logiciel
étudié et distingue :

- **fait source** : comportement lisible dans le code étudié ;
- **interprétation** : rapprochement analytique construit ici ;
- **hypothèse** : conséquence plausible qui demanderait une expérience.

Les sources ont été consultées le 13 août 2026. Aucun code source étranger
n'est incorporé au dépôt et aucun benchmark nouveau n'est réalisé dans cette
expédition.

Dans les fiches, **SOURCE FACT** correspond à un comportement lu directement
dans le code ou ses interfaces, **DERIVED INTERPRETATION** à une conséquence
raisonnable de cette lecture, et **HYPOTHESIS** à une explication ou un
transfert qui demanderait une expérience. Les titres français utilisés dans
les fiches sont des raccourcis de ces trois niveaux.

## Corpus et traçabilité

| Projet | Révision et fichier étudié | Contrat observé |
|---|---|---|
| QuickDraw | [jrk/QuickDraw](https://github.com/jrk/QuickDraw), commit `6377ec5d89735a11b3f6e1ae728f555936c7583f`; principalement `RgnOp.a`, avec `Regions.a`, `SeekRgn.a`, `PackRgn.a` | Combiner des régions raster compactes, dont l'intersection, en produisant une région logique résultat. |
| Apache Lucene | [ConjunctionDISI.java](https://github.com/apache/lucene/blob/a759a950f7b15e32a4b6b9cbc86b10de01726dad/lucene/core/src/java/org/apache/lucene/search/ConjunctionDISI.java), commit `a759a950f7b15e32a4b6b9cbc86b10de01726dad` | Parcourir les identifiants de documents présents dans tous les itérateurs. |
| PostgreSQL | [nodeMergejoin.c](https://github.com/postgres/postgres/blob/fba4233c832870c8363438419743c48fdcb2151c/src/backend/executor/nodeMergejoin.c), commit `fba4233c832870c8363438419743c48fdcb2151c` | Exécuter une jointure d'égalité sur deux entrées triées, en conservant la sémantique des doublons et des jointures externes. |
| RocksDB | [merging_iterator.cc](https://github.com/facebook/rocksdb/blob/e18d41e08c96a465a9ecdd96b375d54a543045c6/table/merging_iterator.cc), commit `e18d41e08c96a465a9ecdd96b375d54a543045c6` | Fusionner plusieurs itérateurs ordonnés, avec visibilité et tombstones d'intervalle. |
| GNU coreutils | [comm.c](https://github.com/coreutils/coreutils/blob/c5ddd417aa8d8e1cf070445760e1747410fb42be/src/comm.c), commit `c5ddd417aa8d8e1cf070445760e1747410fb42be` | Comparer deux fichiers triés et produire les lignes propres à chaque fichier ou communes. |

Les licences restent celles des projets sources : Apache 2.0 pour Lucene,
GPLv2/Apache 2.0 pour RocksDB, PostgreSQL License pour PostgreSQL et GPLv3+
pour coreutils. QuickDraw est le specimen historique déjà documenté dans
`quickdraw-regions-notes.md` ; ses notices et ses empreintes ne sont pas
recopiées ici.

## Fiches individuelles

### 1. QuickDraw — fusion de scans différentiels

**Question étudiée.** `RgnOp.a` construit les opérations booléennes sur des
régions QuickDraw, notamment l'intersection. La représentation historique
n'est pas une liste de runs indépendants par ligne : elle encode des
événements verticaux et des points d'inversion horizontaux. `SeekRgn` maintient
l'état intérieur/extérieur d'une scanline.

**Fait source.** `RgnOp` développe les rectangles si nécessaire, avance les
deux flux jusqu'au prochain événement vertical, fusionne les changements
horizontaux triés selon l'opération, puis n'émet que la différence entre le
scan courant et le scan précédent. Les listes sont terminées par les
sentinelles historiques et les points d'inversion sont ordonnés.

**Mécanisme observé.** Synchronisation de deux flux verticaux, puis fusion de
deux états horizontaux sur chaque bande. La sortie est différentielle par
rapport à l'état précédent, ce qui lie la combinaison au stockage choisi.

**Préconditions.** Régions valides, coordonnées ordonnées, interprétation
cohérente des points d'inversion et des bornes demi-ouvertes.

**Interprétation.** Ce n'est pas seulement une « fusion de listes » : le
résultat dépend d'un état géométrique par bande et d'une représentation
différentielle. La forme de sortie fait partie du mécanisme.

**Hypothèse.** Une version moderne pourrait bénéficier d'un saut ou d'un
parcours piloté par la structure la plus courte d'une bande, mais rien dans
les mesures QuickDraw existantes ne démontre que cette spécialisation est
rentable.

### 2. Apache Lucene — conjonction pilotée par le coût

**Question étudiée.** `ConjunctionDISI` doit ne produire que les doc IDs
présents dans tous ses sous-itérateurs.

**Fait source.** La construction vérifie que les sous-itérateurs sont
positionnés sur le même document, calcule le coût minimal, trie les itérateurs
pour laisser le plus sparse mener la recherche, et sépare certains bitsets.
La boucle `doNext` avance le second itérateur vers le document courant du
leader ; si elle le dépasse, le leader est avancé à son tour. Les autres
itérateurs sont ensuite amenés au candidat et un dépassement relance le
leader. Le résultat est accepté lorsque tous sont au même document.

Le code traite aussi les itérateurs en deux phases et ordonne les vérifications
par coût de match. Pour les bitsets, Lucene distingue un chemin candidat-par-
document d'un masquage par fenêtres, selon le coût du leader et la longueur du
bitset. Les contrats associés sont dans
[`DocIdSetIterator.java`](https://github.com/apache/lucene/blob/a759a950f7b15e32a4b6b9cbc86b10de01726dad/lucene/core/src/java/org/apache/lucene/search/DocIdSetIterator.java)
et [`TwoPhaseIterator.java`](https://github.com/apache/lucene/blob/a759a950f7b15e32a4b6b9cbc86b10de01726dad/lucene/core/src/java/org/apache/lucene/search/TwoPhaseIterator.java).

**Mécanisme observé.** Intersection par candidat, avec un leader choisi par
une estimation de coût et des opérations `advance` capables de sauter des
éléments.

**Préconditions.** Itérateurs compatibles sur le même espace de doc IDs,
contrat d'avancement monotone, estimation de coût disponible pour le tri.

**Interprétation.** La structure de l'intersection est ici asymétrique : le
choix du flux candidat est une décision algorithmique distincte de la règle
logique « présent dans tous ».

**Hypothèse.** Cette idée pourrait être testée dans une intersection de runs
QuickDraw si la représentation expose un coût de saut ou une asymétrie de
densité. Il ne s'ensuit pas que le leader Lucene soit directement applicable
aux bandes QuickDraw.

### 3. PostgreSQL — jointure par fusion avec doublons

**Question étudiée.** `ExecMergeJoin` traite des clauses d'égalité sur deux
relations triées.

**Fait source.** Le code compare les tuples courants et avance l'entrée dont
la clé est la plus petite jusqu'à rejoindre l'autre. Lorsqu'une égalité est
trouvée, il produit les tuples correspondants. Il marque la première position
de l'entrée interne et la restaure pour traiter plusieurs tuples externes de
même clé ; le code est organisé comme une machine à états persistante entre
appels.

**Mécanisme observé.** Synchronisation monotone jusqu'à l'égalité, puis
réutilisation d'un groupe égal par `mark/restore`. La combinaison ne cherche
pas seulement un ensemble de clés commun : elle doit produire les paires
issues des doublons, avec des variantes pour les jointures externes et
anti-jointures.

**Préconditions.** Entrées ordonnées selon les familles de comparaison
annoncées au planificateur, comparateur compatible, contrat de restauration de
l'entrée interne lorsque les doublons l'exigent.

**Interprétation.** Le traitement des doublons transforme le problème : un
algorithme d'intersection d'ensembles ne suffit plus. L'état de groupe et la
possibilité de revenir à un point marqué deviennent des propriétés du
contrat.

**Hypothèse.** Une stratégie QuickDraw pourrait avoir besoin d'un état
analogue seulement si elle devait réémettre ou réutiliser des groupes de runs;
ce n'est pas le contrat de l'intersection actuelle.

### 4. RocksDB — fusion multi-voie avec état de visibilité

**Question étudiée.** `MergingIterator` combine plusieurs itérateurs de
points, dans les deux directions, tout en masquant les clés couvertes par des
tombstones d'intervalle.

**Fait source.** Le code utilise un min-heap ou un max-heap pour maintenir le
prochain élément selon la direction. Les bornes de tombstones sont également
placées dans le heap ; un ensemble `active_` représente les niveaux dont un
tombstone est actif. Des invariants documentent que le sommet du heap est un
itérateur valide et non couvert. `Next` avance uniquement l'itérateur courant
puis restaure la propriété du heap.

**Mécanisme observé.** Fusion multi-flux par frontière globale, enrichie d'un
état d'intervalles actifs et de règles de visibilité. Ce n'est ni une
intersection binaire, ni une simple concaténation.

**Préconditions.** Comparateur d'InternalKey cohérent, itérateurs valides,
correspondance entre niveaux et tombstones, invariants de heap et de
visibilité conservés après `Seek`, `Next` et `Prev`.

**Interprétation.** L'extension à plusieurs flux ne consiste pas seulement à
répéter une fusion binaire : le choix du prochain élément et l'état des
intervalles sont couplés.

**Hypothèse.** La partie heap pourrait être pertinente pour une composition
QuickDraw de plus de deux régions, mais les tombstones et la visibilité ne
sont pas présents dans le contrat QuickDraw étudié.

### 5. GNU coreutils — comparaison séquentielle de deux flux

**Question étudiée.** `comm` compare deux fichiers supposés triés et produit
trois classes : seulement dans le fichier 1, seulement dans le fichier 2,
présent dans les deux.

**Fait source.** `compare_files` conserve une ligne courante par fichier,
compare les deux valeurs, émet la plus petite ou la valeur commune, puis
avance le fichier correspondant ; en cas d'égalité les deux avancent. Le code
peut vérifier l'ordre d'entrée et respecte les règles de collation de la
locale.

**Mécanisme observé.** Fusion binaire séquentielle avec classification du
résultat et progression monotone des flux.

**Préconditions.** Ordre des entrées selon la collation utilisée, comparateur
stable, buffers permettant de conserver les lignes courantes. Les doublons
restent des occurrences : ils ne sont pas dédupliqués comme dans un ensemble.

**Interprétation.** C'est le cas de référence le plus simple : la progression
est symétrique selon le résultat de la comparaison et il n'existe pas de
`advance` spécialisé, de heap multi-voie ni de restauration de groupe.

**Hypothèse.** Ce mécanisme décrit une base utile pour isoler le bénéfice
d'une primitive de saut dans une future expérience, mais pas pour expliquer à
lui seul les autres contrats.

## Retour adaptatif aux sources après la première comparaison

La première comparaison faisait apparaître quatre contrastes : choix d'un
leader, restauration de groupes, frontière multi-voie et état géométrique par
bande. Une seconde lecture des fonctions et structures associées a conduit
aux précisions suivantes.

### QuickDraw : la fusion est couplée à la mémoire temporaire

**Source fact.** Dans `RgnOp`, l'espace de pile disponible est divisé pour
allouer cinq buffers de scan (`SCAN1` à `SCAN5`). `UPDATEA` et `UPDATEB`
mettent à jour l'état de chaque région avec `XORSCAN`; `CALC` applique
`SECTSCAN`, `DIFFSCAN`, `UNIONSCAN` ou `XORSCAN`; `CHANGES` fait ensuite un
nouveau `XORSCAN` entre le scan calculé et le scan précédent avant d'émettre
les points. `EXPAND` remplace temporairement une région rectangulaire par un
flux artificiel de transitions.

**Correction de l'interprétation.** La combinaison n'est donc pas seulement
une progression de deux curseurs horizontaux : elle alterne états courants,
état de résultat précédent et buffers de travail. Le choix de représentation
et la mémoire de travail sont dans le même mécanisme concret.

**Hypothèse maintenue.** Une sélection de flux sparse inspirée de Lucene ne
pourrait être introduite qu'en conservant ce cycle d'états et la sortie
différentielle ; aucune mesure actuelle ne montre qu'elle l'améliore.

### Lucene : `cost()` est une information disponible, pas une vérité physique

**Source fact.** `DocIdSetIterator.cost()` est documenté comme une estimation
qui peut être une borne supérieure, une heuristique approximative ou même une
valeur inexacte. `ConjunctionDISI.createConjunction` trie les itérateurs sur
ce coût, mais sépare aussi les `BitSetIterator` dont le coût est supérieur au
minimum. `DocIdSetIterator.advance(target)` autorise un saut monotone et sa
documentation précise que certaines implémentations sont plus efficaces que
la boucle linéaire par `nextDoc`. Les `TwoPhaseIterator` exposent séparément
une approximation, `matches()` et `matchCost()`.

**Correction de l'interprétation.** La spécialisation observée n'est pas une
loi « le plus sparse est toujours meilleur ». C'est une décision conditionnée
par une estimation déclarée, par la disponibilité d'une primitive de saut,
par des bitsets et par un éventuel coût de vérification en deux phases.

**Conséquence.** Le candidat de transfert vers QuickDraw porte sur la chaîne
`coût estimé → flux leader → primitive de saut`, non sur le simple vocabulaire
de sparsité. QuickDraw ne possède pas encore l'équivalent démontré de
`cost()`, `advance()` ou `matchCost()`.

### PostgreSQL : la restauration est une branche de contrat, pas une propriété
universelle du merge join

**Source fact.** La structure [`MergeJoinState`](https://github.com/postgres/postgres/blob/fba4233c832870c8363438419743c48fdcb2151c/src/include/nodes/execnodes.h)
contient `mj_SkipMarkRestore`,
`mj_MarkedTupleSlot` et l'état persistant de la machine. Dans
`EXEC_MJ_SKIP_TEST`, PostgreSQL marque la position interne lorsqu'une égalité
est trouvée et que `mj_SkipMarkRestore` est faux. Dans
`EXEC_MJ_TESTOUTER`, il restaure cette position seulement dans le même cas.
Le code peut donc prendre un chemin où la restauration n'est pas nécessaire
si l'état courant est déjà la première correspondance possible.

**Correction de l'interprétation.** `mark/restore` n'est pas le mécanisme
constitutif de toute progression ordonnée : c'est une spécialisation rendue
nécessaire par la production de plusieurs paires pour des clés égales, et
écartée lorsque le plan ou la position courante permet de l'éviter.

### RocksDB : la sémantique de l'union et les petits cas sont explicites

**Source fact.** [`merging_iterator.h`](https://github.com/facebook/rocksdb/blob/e18d41e08c96a465a9ecdd96b375d54a543045c6/table/merging_iterator.h)
définit le résultat comme l'union des
enfants et dit explicitement qu'il n'y a pas de suppression des doublons : une
clé présente dans `K` enfants est produite `K` fois. `NewMergingIterator`
retourne un itérateur vide pour zéro enfant et peut retourner directement
l'unique enfant pour un enfant. Pour plusieurs enfants,
`MergingIterator::Next` avance le sommet du min-heap puis restaure la propriété
du heap. `SwitchToBackward` reconstruit le max-heap et repositionne les
enfants ; `FindNextVisibleKey` combine `active_`, les bornes de tombstones et
`SkipNextDeleted` avant d'exposer le sommet.

**Correction de l'interprétation.** La « fusion multi-voie » observée a au
moins trois spécialisations concrètes : arité 0/1, direction avant/arrière,
et visibilité avec tombstones. Elle ne doit pas être comparée à une
intersection binaire comme si son résultat supprimait les doublons.

### coreutils : la collation et la vérification d'ordre font partie du contrat

**Source fact.** `compare_files` compare les lignes courantes avec `xmemcoll`
si la locale est complexe, sinon avec `memcmp` et la longueur. Il avance les
deux flux en cas d'égalité, un seul sinon. Le tableau `fill_up` détermine les
flux à recharger. `check_order` n'est pas un simple invariant interne : il
peut avertir ou échouer selon l'option, et sa mise en œuvre dépend de
`seen_unpairable` et de `hard_LC_COLLATE`.

**Correction de l'interprétation.** Le mécanisme séquentiel dépend aussi du
coût et de la sémantique du comparateur de lignes, pas seulement d'un ordre
abstrait sur des entiers. La conservation des occurrences est distincte
d'une intersection d'ensemble.

Cette seconde lecture retourne effectivement aux sources et réduit les
interprétations initiales : les différences utiles ne sont pas les noms des
algorithmes, mais les contrats de saut, d'estimation, de restauration,
d'arité, de visibilité et de comparaison.

## Comparaison des mécanismes sans canonisation

Les cinq cas ne sont pas cinq variantes d'un même algorithme. Ils partagent
certains invariants, mais diffèrent par le contrat de sortie et par les
opérations autorisées sur les entrées.

| Dimension | QuickDraw | Lucene | PostgreSQL | RocksDB | coreutils |
|---|---|---|---|---|---|
| Nombre de flux | 2 bandes/états | plusieurs itérateurs | 2 relations | plusieurs itérateurs | 2 fichiers |
| Résultat | région booléenne | doc IDs communs | paires de tuples, parfois remplissage | clés visibles fusionnées | trois classes de lignes |
| Progression | événements verticaux puis horizontaux | leader et `advance` | avance de la clé plus petite | sommet de heap | avance du ou des flux comparés |
| Doublons | représentation géométrique, pas de multiplicité de tuples | doc ID logique | multiplicité et `mark/restore` | versions/visibilité, pas jointure de paires | occurrences conservées |
| État supplémentaire | scan précédent, intérieur/extérieur | coûts, bitsets, deux phases | marque et position restaurable | heap, direction, tombstones actifs | buffers et contrôle d'ordre |
| Spécialisation confirmée | rectangles, transitions différentielles | leader sparse, bitsets, coût de match | groupes égaux, jointures externes | heap min/max et états actifs | collation et vérification d'ordre |

### Propriétés réellement nécessaires pour expliquer les différences

Les propriétés suivantes ne sont pas toutes propres à chaque source, mais
elles expliquent pourquoi le même nom « merge » ne suffit pas :

1. **Sémantique du résultat** : intersection d'ensemble, fusion avec
   classification, paires de jointure, ou flux visible après masquage.
2. **Ordre et monotonie** : ordre total ou ordre géométrique par bandes,
   direction de parcours, et comportement autorisé de `advance`/`seek`.
3. **Densité et coût d'un flux** : Lucene rend cette propriété décisionnelle
   en choisissant le leader le moins coûteux ; ce rôle n'est pas présent dans
   `comm`.
4. **Doublons et groupes égaux** : la présence de doublons peut exiger
   `mark/restore` ou, au contraire, rester une simple occurrence à émettre.
5. **Arity** : deux flux permettent une progression symétrique ; plusieurs
   flux nécessitent une frontière globale, ici un heap dans RocksDB.
6. **État de visibilité ou d'intervalle** : un flux peut être filtré par un
   état actif qui modifie l'admissibilité du prochain élément.
7. **Forme de sortie et mémoire intermédiaire** : QuickDraw doit préserver
   une représentation différentielle ; Lucene peut garder des bitsets ; le
   choix ne se déduit pas du seul ordre des entrées.

## Ce qui constitue une connaissance nouvelle par rapport à QuickDraw

### Connaissances candidates transférables

| Connaissance candidate | Source | Statut pour QuickDraw |
|---|---|---|
| Choisir un flux candidat selon une estimation de coût/sparsité et avancer les autres vers lui | Lucene | **QUICKDRAW_TEST_CANDIDATE** : le mécanisme est réel et distinct, mais son bénéfice sur des runs géométriques n'est pas démontré. |
| Traiter explicitement les groupes de doublons avec une position restaurable | PostgreSQL | **NON TRANSFÉRABLE À CE STADE** : le contrat B1∩B1 ne produit pas de paires de tuples ni de multiplicité. |
| Remplacer une fusion multi-voie répétée par une frontière heap et un état actif d'intervalles | RocksDB | **HORS CONTRAT ACTUEL** : pourrait concerner une composition de plus de deux régions, mais aucune expérience QuickDraw ne le demande. |
| Séparer la fusion d'une classification des sorties et conserver les occurrences | coreutils | **CONNAISSANCE DE CONTRASTE** : utile pour éviter d'assimiler intersection logique et déduplication, sans mécanisme QuickDraw nouveau. |

La première entrée est le meilleur candidat de transfert concret, mais elle
reste une question expérimentale. Elle ne devient pas une règle de QuickDraw
par analogie.

### Familles observées, à titre descriptif seulement

Pour la suite immédiate, les mécanismes rencontrés peuvent être décrits par
cinq familles de travail :

1. fusion d'états géométriques différentiels ;
2. intersection pilotée par un candidat et des sauts ;
3. jointure par fusion avec groupes restaurables ;
4. fusion multi-voie avec frontière et état actif ;
5. fusion séquentielle avec classification.

Cette liste n'est pas une taxonomie et ne doit pas être ajoutée telle quelle
à une ontologie. Elle sert uniquement à ne pas masquer des différences
observées dans des sources concrètes.

### Classification explicite des connaissances externes

| Connaissance observée hors QuickDraw | Classification |
|---|---|
| Progression monotone par comparaison des prochains éléments, présente dans `comm` et dans l'intersection B1×B1 | `REDUNDANT_WITH_QUICKDRAW` |
| Choix d'un flux leader selon `cost()` puis progression de l'autre par `advance()` dans Lucene | `QUICKDRAW_TEST_CANDIDATE` |
| `mark/restore` des groupes égaux dans PostgreSQL | Aucun transfert vers le contrat B1×B1 : la connaissance concerne une sortie de paires et n'est pas activée dans le contexte QuickDraw |
| Heap multi-voie et tombstones actifs dans RocksDB | Aucun transfert vers le contrat B1×B1 : l'arité et la visibilité ne sont pas celles du cas étudié |

Il n'existe actuellement **aucun `TRANSFER_CANDIDATE` validé**. Le seul
rapprochement non redondant est explicitement marqué
`QUICKDRAW_TEST_CANDIDATE`; il ne constitue pas une connaissance transférée
tant qu'une expérience QuickDraw dédiée ne l'a pas vérifié.

## `ordered_merge` : trop large ou encore acceptable ?

Le concept `ordered_merge` de l'ontologie algorithmique est **trop large
comme explication suffisante** : il couvre au moins la fusion séquentielle de
`comm`, l'intersection pilotée de Lucene, le `merge join` de PostgreSQL et la
fusion heap de RocksDB, alors que leurs invariants et leurs sorties diffèrent.

Il reste néanmoins **acceptable comme concept local candidat** tant qu'il est
présenté comme une correspondance structurelle faible et non comme un
mécanisme exécutable unique. Les sources étudiées ne justifient pas encore de
modifier l'ontologie ni de lui substituer une décomposition canonique. Une
future question qui aurait besoin de distinguer le leader, les groupes
restaurables ou l'état actif pourrait alors demander un raffinement local.

## Conséquence pour QuickDraw

Le résultat le plus prometteur est une question ciblée, pas une substitution
déjà acquise :

> Pour une intersection B1×B1, lorsqu'une scanline présente beaucoup plus
> d'intervalles que l'autre, un parcours piloté par le flux le plus sparse ou
> une opération de saut peut-il réduire les comparaisons sans dégrader la
> production des intersections et l'état vertical QuickDraw ?

Cette question conserve les invariants QuickDraw : intervalles ordonnés,
absence de chevauchement interne, bornes demi-ouvertes, résultat logique et
représentation de sortie. Elle importe seulement le mécanisme de sélection du
flux candidat comme hypothèse à tester. Elle ne prétend pas que les coûts
Lucene, les bitsets ou `advance` existent déjà dans QuickDraw.

## Prochaine micro-expérience justifiée

Une expérience minimale pourrait comparer, sur les mêmes listes d'intervalles
ordonnées et avec le même résultat :

1. le parcours à deux curseurs QuickDraw actuel ;
2. un parcours où le flux le plus court sert de source de candidats et où
   l'autre est avancé par recherche monotone ;
3. éventuellement une variante avec saut explicite seulement si l'API de
   représentation le permet sans reconstruire la région.

Les facteurs à varier seraient le ratio de cardinalité des deux flux, la
densité des intersections, le nombre de bandes et la possibilité réelle de
sauter. Les mesures devraient compter les comparaisons, les avancées et le
temps, tout en vérifiant le même masque résultat. Cette expérience est
seulement formulée ici ; elle n'est pas lancée.

## Réponses finales

### 1. Nombre de familles réellement distinctes

Cinq familles de mécanismes sont observées dans le corpus, si l'on distingue
leurs contrats : fusion d'états différentiels, intersection pilotée par
candidat, jointure avec groupes restaurables, fusion multi-voie avec état
actif, et fusion séquentielle classifiante. Le chiffre n'est pas une
classification définitive : il indique seulement que le mot `merge` masque
plusieurs décisions algorithmiques réelles.

### 2. Propriétés qui expliquent leurs différences

La sémantique du résultat, les doublons, l'arité, le droit de sauter, les
estimations de coût, les besoins de restauration, l'état d'intervalles actifs,
la direction et la forme de sortie expliquent les différences observées. Le
seul fait que les entrées soient triées ne détermine pas le mécanisme.

### 3. Connaissance nouvelle potentiellement transférable à QuickDraw

La sélection d'un flux candidat selon sa sparsité ou son coût, observée dans
Lucene, est une **QUICKDRAW_TEST_CANDIDATE**. Elle est suffisamment concrète
pour motiver une expérience B1×B1, mais pas pour être classée comme transfert
validé. `mark/restore` et la fusion heap de RocksDB ne sont pas transférables
au contrat QuickDraw actuel sans changer la question.

### 4. Niveau d'action justifié par la connaissance nouvelle

La spécialisation Lucene justifie d'abord **une note** et **une question
expérimentale** : elle expose une chaîne concrète `cost() → leader → advance`,
mais son bénéfice pour les runs QuickDraw reste à établir. Elle ne justifie
pas encore une nouvelle distinction ontologique. `mark/restore` PostgreSQL et
la visibilité RocksDB restent des notes de contraste ou des pistes hors
contrat, pas des candidats d'ontologie QuickDraw.

### 5. Statut de `ordered_merge`

Il est trop large pour servir seul d'explication algorithmique, mais encore
acceptable comme étiquette locale de correspondance. Aucun raffinement
permanent n'est justifié par cette seule revue.

### 6. Prochaine question expérimentale la plus informative

Tester si un mécanisme de candidat sparse avec saut, inspiré de Lucene mais
réimplémenté pour les intervalles QuickDraw, bat réellement le parcours à deux
curseurs selon le ratio de cardinalité et la densité des intersections. La
question doit rester bit-à-bit contrôlée et mesurer les opérations de parcours,
pas seulement le temps.

### 7. Existe-t-il un vrai `TRANSFER_CANDIDATE` vers QuickDraw ?

Non, au sens strict d'une connaissance déjà transférable et suffisamment
justifiée. Il existe un **QUICKDRAW_TEST_CANDIDATE** : le choix d'un leader
selon un coût estimé, combiné à une primitive de saut, observé dans Lucene.
Il deviendrait un `TRANSFER_CANDIDATE` seulement après vérification que
QuickDraw possède une grandeur comparable et qu'une telle progression
préserve son contrat de régions différentielles. Cette vérification n'a pas
été faite ici.

### 8. Qualité des preuves et inconnues restantes

Les cinq fiches sont désormais appuyées par la lecture des routines
d'exécution et, lorsque le contrat l'exigeait, des interfaces ou structures
associées : `DocIdSetIterator`/`TwoPhaseIterator`, `MergeJoinState`,
`merging_iterator.h` et les fonctions de contrôle de `comm`. Les faits
retenus dans la comparaison sont donc traçables à des branches, champs ou
contrats de source précis.

Restent inconnus : les coûts relatifs de ces mécanismes sur des entrées
comparables, l'existence d'un avantage de leader pour les runs QuickDraw, et
la manière dont un coût de saut devrait être exposé sans importer le modèle
Lucene. Ces inconnues produisent une question expérimentale future ; elles
ne justifient ni benchmark dans cette étape ni modification ontologique.

## Vérification explicite des crans d'arrêt

### Cran 1 — routine d'implémentation précise

Le corpus satisfait ce cran : `RgnOp`/`SectScan` pour QuickDraw,
`ConjunctionDISI.createConjunction`/`doNext` pour Lucene,
`ExecMergeJoin`/`MJCompare` pour PostgreSQL, `MergingIterator::Next` et
`FindNextVisibleKey` pour RocksDB, et `compare_files` pour coreutils. Chaque
fiche donne le dépôt, le commit, le fichier et le rôle logiciel ; les
interfaces ou structures nécessaires sont ensuite référencées.

### Cran 2 — décision suivie jusqu'à sa condition et son effet

Les spécialisations ne sont pas seulement nommées :

| Source | Condition observée | Effet observé |
|---|---|---|
| QuickDraw | région rectangulaire (`RGNSIZE == 10`) ou prochain événement vertical | flux artificiel de transitions ou mise à jour d'un seul état avant le calcul de sortie |
| Lucene | `cost()` minimal, bitset plus coûteux que le leader, ou `lead.cost() < bitSet.length()` | tri du leader, séparation bitset, ou parcours candidat contre masquage par fenêtre |
| PostgreSQL | égalité de clés, doublons externes et `mj_SkipMarkRestore` | marquage/restauration de l'entrée interne, ou absence de restauration lorsque le plan le permet |
| RocksDB | arité 0/1, direction de parcours, tombstone actif | itérateur vide/direct, min/max heap, ou saut des clés non visibles |
| coreutils | égalité, ordre de locale, option de contrôle d'ordre | avancement d'un/deux flux, comparateur `xmemcoll`, avertissement ou échec |

### Cran 3 — différences revenues vérifier

Deux différences ont déclenché la seconde lecture :

1. **Progression symétrique contre leader avec saut.** La première lecture
   suggérait une simple opposition `comm`/QuickDraw versus Lucene. La seconde
   lecture de `DocIdSetIterator`, `TwoPhaseIterator` et `ConjunctionDISI` a
   confirmé que la différence porte réellement sur un contrat d'`advance`,
   une estimation `cost()` et une validation en deux phases.
2. **Doublons comme résultat contre doublons comme état à réutiliser.** La
   première lecture rapprochait PostgreSQL de toute intersection ordonnée. La
   seconde lecture de `MergeJoinState` et des états `EXEC_MJ_*` a corrigé cette
   interprétation : `mark/restore` est conditionnel et sert à produire les
   paires d'un groupe égal, contrairement au contrat d'ensemble de QuickDraw
   et aux occurrences de coreutils.

La seconde lecture de RocksDB et QuickDraw a également confirmé que l'arité,
la direction, la visibilité et la mémoire de travail sont des parties du
contrat, pas des détails de nommage.

## Confirmed

- Les structures ordonnées ne déterminent pas un mécanisme unique : le
  résultat attendu, les doublons, l'arité, la possibilité de saut et l'état
  auxiliaire changent effectivement le parcours observé dans le code.
- Les spécialisations importantes sont attachées à des conditions concrètes :
  `cost()`/bitsets, groupes égaux, tombstones actifs, arité et direction,
  transitions géométriques, ou collation et contrôle d'ordre.
- La seconde lecture a confirmé ou corrigé les interprétations initiales ; les
  différences retenues sont traçables à des fonctions, branches, champs ou
  contrats source précis.

## Disproved

- L'idée implicite qu'un même nom `ordered_merge` suffirait à expliquer les
  cinq implémentations est contredite par leurs contrats de sortie et leurs
  états auxiliaires.
- L'interprétation « Lucene choisit toujours le flux le plus sparse » est
  trop forte : le code choisit selon un `cost()` explicitement heuristique et
  prend en compte bitsets, saut et deux phases.
- L'interprétation « un merge join nécessite toujours mark/restore » est
  contredite par `mj_SkipMarkRestore` et les branches qui l'évitent.

## Unknown

- Les coûts comparés de ces mécanismes sur des entrées contrôlées ; aucune
  mesure nouvelle n'a été faite ici.
- L'existence d'un avantage réel d'un leader sparse pour l'intersection des
  runs QuickDraw.
- La grandeur qui pourrait jouer le rôle de `cost()` pour des runs
  géométriques et la possibilité d'un `advance` utile sans casser la sortie
  différentielle QuickDraw.
- La possibilité qu'une distinction supplémentaire apparaisse avec des
  contrats de sortie différents, sans qu'elle justifie encore un changement
  d'ontologie.

## Conclusion et arrêt

L'étude établit que le transfert utile ne vient pas d'un nom commun comme
`ordered_merge`, mais d'une propriété attachée à un contrat concret : ici,
la capacité à choisir un candidat et à avancer l'autre flux. Cette propriété
est une hypothèse de travail pour QuickDraw, non une connaissance validée.

La compréhension comparative est suffisante pour la question présente.
**STOP.**
