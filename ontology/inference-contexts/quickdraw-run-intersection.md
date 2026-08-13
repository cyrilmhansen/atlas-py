# Contexte d'inférence — intersection directe de runs QuickDraw

Type : contexte manuel, local à une opération graphique. Il ne modifie aucune
proto-ontologie et ne crée aucune relation permanente entre domaines.

## 1. Besoin

Deux régions logiques `R1` et `R2` sont déjà disponibles sous forme de
segments horizontaux ordonnés, représentation locale
`classic_2d_graphics.horizontal_run_representation`.

Le résultat recherché est la région logique :

```text
R = R1 ∩ R2
```

La contrainte est de construire `R` directement dans la même famille de
représentation, sans matérialiser un masque bitmap intermédiaire. Le résultat
doit donc être une nouvelle représentation par segments horizontaux de `R`,
et non un bitmap ensuite converti.

Les propriétés à préserver sont :

- chaque segment émis appartient à l'intersection de `R1` et `R2` ;
- aucun segment non vide de l'intersection n'est perdu ;
- les segments d'une même scanline restent ordonnés ;
- les segments internes d'une représentation restent valides et non
  chevauchants selon les conventions de runs ;
- l'identité logique du résultat est celle de `R1 ∩ R2` ;
- aucune dépendance à une représentation bitmap n'est introduite.

Le contexte ne traite ni la construction des régions depuis une géométrie, ni
les autres opérations booléennes, ni le choix général de représentation.

## 2. Concepts activés — Graphisme 2D classique

Les concepts suivants sont suffisants et activés depuis
`ontology/domains/classic-2d-graphics.md`.

### `classic_2d_graphics.region`

Les deux entrées et le résultat sont des régions logiques distinctes : `R1`,
`R2` et `R`. Une représentation de runs n'est pas une nouvelle région
logique.

### `classic_2d_graphics.horizontal_run_representation`

Chaque région est déjà représentée par des intervalles horizontaux groupés par
scanline. L'ordre des intervalles et leur validité interne sont des
préconditions locales de cette représentation.

### `classic_2d_graphics.region_boolean_operation`

L'intersection construit une région résultat à partir de deux régions
existantes. Le contexte retient ici son exécution directe sur les runs, et non
une implémentation bitmap.

### `classic_2d_graphics.region_intersection`

Cette opération détermine la sémantique du résultat : une position est active
si elle appartient aux deux entrées. Elle fournit le critère fonctionnel de
validation.

### Relations graphiques locales utilisées

- `is represented by` : `R1`, `R2` et `R` sont représentées par des runs ;
- `operates on` : l'intersection opère sur les deux régions représentées ;
- `produces` : l'opération produit `R` ;
- `merges` : les flux de segments sont fusionnés scanline par scanline dans la
  réalisation directe.

Ces relations restent locales au domaine graphique. Elles ne sont pas
réinterprétées comme des relations d'appartenance au domaine algorithmique.

## 3. Concepts examinés — Algorithmique et structures de données

Les concepts suivants ont été examinés, mais aucun n'est activé dans ce
contexte.

### `elementary_algorithms.sequence`

Les runs d'une scanline sont effectivement ordonnés. Cependant,
`horizontal_run_representation` et la relation locale `merges` suffisent à
exprimer cette précondition et cette opération dans le domaine graphique.

Retrait : aucune information nécessaire ne disparaît. Le contexte peut dire
que chaque scanline contient une suite ordonnée d'intervalles sans importer le
concept général de séquence.

### `elementary_algorithms.traversal`

Le mécanisme parcourt les scanlines et les segments. Mais « parcourir les
scanlines dans l'ordre et avancer les segments actifs » est une étape du
mécanisme graphique décrit ici, pas une connaissance supplémentaire fournie
par le concept générique de parcours.

Retrait : aucune opération ou propriété n'est perdue ; l'ordre de parcours
reste une précondition contextuelle.

### `elementary_algorithms.sorted_sequence`

Ce concept n'est pas adapté : les runs sont ordonnés horizontalement dans
chaque scanline, mais le besoin n'est pas une séquence triée de clés soumise à
une recherche dichotomique.

Retrait : aucune information pertinente ne disparaît.

### `elementary_algorithms.ordered_merge`

Ce concept décrit une famille algorithmique ressemblante : deux séquences
ordonnées peuvent être parcourues conjointement. Il n'est cependant pas
nécessaire pour décrire précisément la solution graphique. La proto-ontologie
graphique possède déjà la relation locale `merges`, et les invariants et
étapes spécifiques peuvent être conservés comme connaissances contextuelles.

Retrait : le contexte sait toujours exprimer la fusion de deux flux de runs,
scanline par scanline, avec deux positions courantes et émission des
intersections. Seul un raccourci de vocabulaire transférable disparaît.

## 4. Rapprochement inter-domaines

### Test de retrait

Le rapprochement hypothétique aurait été :

```text
horizontal_run_representation(R)
    expose une suite ordonnée d'intervalles

region_intersection(R1, R2)
    peut utiliser une fusion ordonnée
```

Après retrait de `sequence`, `traversal` et `ordered_merge`, le contexte
graphique peut encore décrire :

- les deux flux de runs par scanline ;
- leur ordre horizontal ;
- deux positions courantes dans ces flux ;
- la comparaison des bornes gauche et droite ;
- l'émission d'un intervalle commun non vide ;
- l'avancée de la position dont la borne droite arrive en premier ;
- la conservation de l'ordre dans le résultat.

La description reste complète et spécifique au besoin graphique. Aucun concept
du second domaine ne passe donc le test de nécessité.

### Ce qui n'est pas déclaré

Le contexte ne déclare pas :

```text
Region is-a Sequence
horizontal_run_representation belongs_to elementary_algorithms
region_intersection is-a ordered_merge
```

La représentation B1, l'intersection et la fusion locale restent des concepts
graphiques. Le mécanisme algorithmique est décrit par des propriétés et des
étapes contextuelles, sans relation permanente inter-domaines.

## 5. Mécanisme concret

La construction directe s'organise par scanline.

1. Prendre la prochaine scanline pertinente de `R1` et de `R2` ; une
   scanline absente d'une région est considérée comme ne contenant aucun
   intervalle actif.
2. Maintenir une position dans les segments ordonnés de chacune des deux
   scanlines.
3. Comparer les bornes des segments courants. Leur zone commune est délimitée
   par le maximum des bornes gauches et le minimum des bornes droites.
4. Émettre cette zone uniquement si elle est non vide.
5. Avancer le segment dont la borne droite est la plus petite. En cas de même
   borne droite, avancer les deux segments concernés.
6. Continuer jusqu'à épuisement des segments de la scanline, puis produire la
   prochaine scanline du résultat.

La progression est linéaire dans les flux de segments parcourus pour chaque
scanline. Elle ne demande pas de reconstruire les pixels de la bounding box.
La description n'est pas un pseudocode d'implémentation : elle fixe seulement
les opérations et invariants nécessaires au mécanisme graphique.

## 6. Test explicite de nécessité

### A. Description avec le seul domaine Graphisme 2D classique

La solution est entièrement exprimable avec :

- deux `region` représentées par des `horizontal_run_representation` ;
- `region_intersection` comme opération ;
- `merges` comme relation locale entre les flux de segments ;
- les préconditions d'ordre horizontal et de non-chevauchement interne ;
- les règles contextuelles de comparaison, émission et progression ;
- la validation par appartenance pixel ou représentation canonique.

Cette description distingue déjà le mécanisme direct B1×B1→B1 de l'opération
bitmap B0. Elle ne confond pas la représentation avec l'objet logique.

### B. Description avec les concepts algorithmiques candidats

Ajouter `sequence`, `traversal` ou `ordered_merge` donne des noms généraux aux
propriétés et à la stratégie déjà décrites. Cela peut faciliter une recherche
documentaire ou un transfert futur vers un autre domaine, mais ne permet pas
d'exprimer une étape qui manquait dans A.

La comparaison A/B montre donc :

- aucune perte fonctionnelle dans A ;
- aucun invariant nouveau dans B ;
- aucun mécanisme supplémentaire rendu disponible par B ;
- seulement un vocabulaire algorithmique plus générique, non nécessaire ici.

## 7. Connaissances contextuelles hors ontologies

Ces éléments sont nécessaires à l'exécution correcte mais restent dans le
contexte :

- les intervalles de chaque scanline sont ordonnés par borne gauche ;
- les intervalles internes d'une représentation ne se chevauchent pas ;
- les coordonnées suivent les conventions du format B1 ;
- les scanlines sont traitées dans un ordre déterminé ;
- une intersection vide n'est pas émise ;
- l'avancée par borne droite garantit de ne pas manquer d'intersection ;
- le résultat doit être comparé à un oracle logique indépendant ;
- la représentation bitmap n'est pas utilisée comme étape intermédiaire.

La propriété « parcours de deux flux ordonnés » est donc une précondition et
une règle locale de ce contexte, pas une nouvelle relation permanente.

## 8. Faits expérimentaux déjà acquis

Le contexte ne lance aucune mesure et n'ajoute aucun fait. Il réutilise
seulement les résultats QuickDraw existants :

- QuickDraw 3 a validé fonctionnellement les opérations B1 sur un corpus
  déterministe avec un oracle indépendant ;
- la fusion de runs est observée comme très rapide pour
  `sparse_sparse/intersection` et beaucoup plus coûteuse lorsque le résultat
  est fortement fragmenté ;
- le résultat peut contenir beaucoup plus de runs que les entrées ;
- B0, B1 et B2 ont des compromis distincts selon l'opération et la forme ;
- ces mesures concernent les réimplémentations portables et la plateforme
  moderne documentée, pas une exécution du QuickDraw 68000 original.

Ces faits motivent le mécanisme mais ne sont pas de nouvelles conclusions de
ce contexte.

## 9. Résultat du recollage

### PAS DE RECOLLAGE UTILE

Le domaine Graphisme 2D classique suffit pour décrire complètement la
construction directe B1×B1→B1. `ordered_merge` est une description générale
pertinente, mais son retrait ne fait disparaître aucune information, opération
ou étape nécessaire du raisonnement.

Le cas est donc un résultat négatif du test de composition : un domaine local
peut parfois contenir, avec son vocabulaire propre et quelques propriétés
contextuelles, toute la connaissance nécessaire à une opération qui ressemble
à un mécanisme d'un autre domaine.

## Context pack agentique

Non produit comme pack actif : aucun concept du second domaine n'a passé le
test de nécessité. Pour mémoire, une implémentation locale devrait seulement
respecter les éléments suivants :

- objectif : produire B1(R1 ∩ R2) directement depuis deux représentations B1 ;
- vocabulaire : région, runs horizontaux, intersection, fusion locale ;
- préconditions : runs ordonnés par scanline et non chevauchants ;
- mécanisme : positions courantes, comparaison des bornes, émission des
  intersections non vides, progression par borne droite ;
- invariants : ordre, absence de runs vides, appartenance exacte à R1 ∩ R2 ;
- erreurs : ne pas matérialiser B0, ne pas confondre union et intersection,
  ne pas perdre un recouvrement lorsque les bornes droites sont égales ;
- arrêt : validation contre un oracle indépendant sur le périmètre retenu.

Ce résumé reste un aide-mémoire local, pas une activation du domaine
`elementary_algorithms`.

## Questions finales

### Quel concept du second domaine passe réellement le test ?

Aucun. `ordered_merge` est le meilleur candidat, mais son retrait laisse une
description complète grâce à `horizontal_run_representation`,
`region_intersection`, `merges` et aux invariants contextuels.

### Quelle information précise est perdue lorsqu'on le retire ?

Aucune information nécessaire à ce raisonnement. On perd seulement un nom
générique et potentiellement réutilisable pour une stratégie déjà décrite
localement.

### Le rapprochement est-il une relation entre concepts, propriétés,
mécanismes ou vocabulaires ?

Dans ce cas, il n'est pas nécessaire comme relation sémantique. La comparaison
porte seulement sur un possible recouvrement de vocabulaires et de mécanismes :
la fusion ordonnée générale ressemble à la fusion locale de runs. Ce
recouvrement ne justifie pas un pont persistant.

### Une modification permanente des proto-ontologies est-elle nécessaire ?

Non. Ni `elementary-algorithms.md` ni `classic-2d-graphics.md` ne doit être
modifié.

### Cette expérience suggère-t-elle une règle générale de sélection
inter-domaines, ou seulement un cas local ?

Seulement un cas local. Elle suggère une règle méthodologique prudente : avant
d'activer un concept externe, le retirer et vérifier si une information ou une
étape nécessaire disparaît. Elle ne fournit ni filtre général, ni score, ni
politique universelle de rapprochement.
