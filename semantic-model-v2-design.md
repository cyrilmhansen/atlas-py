# Semantic Model v2 — conception des proto-ontologies locales

Statut : document de conception uniquement. Aucun modèle machine, code ou
schéma définitif n'est introduit par cette étape.

## A. Principes architecturaux

Atlas ne cherche pas une ontologie universelle des algorithmes. Il conserve
des proto-ontologies locales, chacune liée à un domaine de connaissance.
Un domaine peut être étroit, large, redondant avec un autre ou partiellement
recouvrant ; les domaines ne forment pas nécessairement un arbre.

Une même notion peut appartenir à plusieurs domaines, mais cette
multi-appartenance reste facultative. Elle ne doit pas être ajoutée seulement
pour rendre possible une inférence. Les frontières de domaine servent à
organiser et retrouver la connaissance, pas à interdire une combinaison
contextuelle.

Le recollage appartient au contexte d'inférence : un besoin active des
concepts et des relations issus de plusieurs domaines, puis un raisonnement
local peut les considérer ensemble. Il n'existe pas encore de moteur de ce
raisonnement, de score de proximité, de distance entre domaines ou de
politique de filtrage.

Le vocabulaire canonique est français, avec pour chaque domaine et concept un
nom technique anglais britannique (`en-GB`) désignant exactement le même
concept. Les identifiants techniques sont stables et dérivent de préférence
du terme anglais ; un changement de label ne les change pas. Les alias restent
exceptionnels et motivés par un terme historique ou de recherche.

La conclusion de POC12 est conservée : deux représentations non isomorphes
peuvent préserver les mêmes conséquences décisionnelles. Le modèle ne doit
donc pas rechercher une forme normale. Il doit préserver l'information dont la
perte pourrait modifier une propriété, une contrainte ou une décision, et
permettre une précision ultérieure si une nouvelle question la rend
nécessaire.

### Statuts utilisés dans ce document

- **forcé** : la distinction est nécessaire pour exprimer un résultat ou une
  erreur déjà observé ;
- **probable** : plusieurs expériences la rendent plausible, sans la rendre
  encore indispensable ;
- **candidat** : utile pour organiser la conception, mais non justifié par un
  cas actuel ;
- **repoussé** : volontairement hors périmètre.

Ces statuts portent sur la nécessité de conception, pas sur la vérité
universelle des concepts.

## B. Carte initiale des domaines

### Domaine A — Algorithmique et structures de données élémentaires

- nom FR : **Eléments d'algorithmique et de structures de données**
- nom en-GB : **Elementary algorithms and data structures**
- identifiant proposé : `elementary_algorithms`
- rôle : vocabulaire des POC 1–12 et des mécanismes de recherche, parcours,
  stockage et composition.

Concepts effectivement rencontrés ou directement nécessaires :

- `collection` — collection ;
- `sequence` — séquence ;
- `lookup` — recherche ;
- `traversal` — parcours ;
- `sorted_sequence` — séquence triée ;
- `hash_table` — table de hachage ;
- `open_addressing` — adressage ouvert ;
- `binary_search` — recherche dichotomique ;
- `merge` — fusion ;
- `workload` — charge de travail ;
- `memory_constraint` — contrainte mémoire.

Cette liste n'est pas une taxonomie complète. Par exemple, `hash_table` et
`sorted_sequence` sont des mécanismes observés dans les POC, tandis que leur
relation avec une région graphique n'est pas une relation `is-a`.

### Domaine B — Graphisme 2D classique

- nom FR : **Graphisme 2D classique**
- nom en-GB : **Classic 2D graphics**
- identifiant proposé : `classic_2d_graphics`
- rôle : vocabulaire de BitBlt, des régions QuickDraw et de leur cycle de vie.

Concepts effectivement rencontrés :

- `region` — région ;
- `rectangle` — rectangle ;
- `bitmap` — bitmap ;
- `horizontal_runs` — segments horizontaux ;
- `differential_transitions` — transitions différentielles ;
- `bitblt` — BitBlt ;
- `clipping` — rognage ;
- `region_boolean_operation` — opération booléenne sur régions ;
- `intersection` — intersection ;
- `union` — union ;
- `difference` — différence ;
- `symmetric_difference` — différence symétrique ;
- `representation_conversion` — conversion de représentation ;
- `region_application` — application d'une région.

Les opérations booléennes, les représentations B0/B1/B2 et l'application au
blit appartiennent à ce domaine. Le fait que B1 soit parcourue par des
intervalles ordonnés ne transforme pas une `Region` en `Sequence` du domaine
A.

### Appartenance principale et secondaire

Un concept peut être indexé avec un domaine principal et zéro ou plusieurs
domaines secondaires, mais cette structure est d'abord une aide de navigation
et de vocabulaire par défaut. Elle n'impose ni héritage ni priorité
sémantique.

La notion de domaine principal n'est pas encore forcée par une décision
expérimentale. Elle est **candidate** : utile pour présenter une fiche de
concept, mais remplaçable par une simple liste de domaines si aucun besoin de
navigation ne l'exige.

## C. Candidats au vocabulaire transversal

| Concept FR | Concept en-GB | ID proposé | Statut | Pourquoi nécessaire |
|---|---|---|---|---|
| objet logique | logical object | `core.logical_object` | **forcé** | Distinguer la région logique de ses formes B0/B1 et des structures physiques. |
| représentation | representation | `core.representation` | **forcé** | B0, B1 et B2 décrivent le même objet sous des formes différentes. |
| instance de représentation | representation instance | `core.representation` | **forcé** | L'audit distingue le résultat B0 réel du masque Python reconstruit. |
| transformation | transformation | `core.transformation` | **forcé** | La conversion native B0→B1 relie des occurrences sans créer un nouvel objet logique. |
| propriété | property | `core.property` | **forcé comme rôle** | Les coûts, contraintes et propriétés structurelles ne sont pas tous des mesures. |
| quantité | quantity | `core.quantity` | **forcé** | v0/v1 distinguent kind, unité, sujet et statut de la valeur. |
| observation | observation | `core.observation` | **forcé comme rôle** | Une mesure physique est un résultat contextualisé, pas une propriété universelle. |
| mesure | measurement | `core.measurement` | **probable** | Une observation numérique avec unité, statistique et protocole doit être distinguée d'une observation qualitative. |
| protocole expérimental | experimental protocol | `core.exp.protocol` | **forcé comme contexte** | Le fichier JSON ne suffit pas à identifier le programme et le protocole producteurs. |
| exécution expérimentale | experimental run | `core.exp.run` | **forcé comme contexte** | Le fichier JSON ne suffit pas à identifier le programme et le protocole producteurs. |
| artefact de résultat | result artefact | `core.exp.result_artifact` | **forcé** | Un fichier qui contient une valeur n'est pas sa lignée expérimentale. |
| contexte d'inférence | inference context | `core.inference_context` | **probable** | Le recollage temporaire de concepts de domaines différents doit avoir un lieu conceptuel. |
| scénario | scenario | `core.scenario` | **candidat** | v1 conserve un libellé de scénario ; aucun besoin actuel ne force une identité autonome. |
| opération | operation | `core.operation` | **candidat** | Très utile dans les deux domaines, mais peut encore être portée par une transformation ou un concept local. |
| événement compté | counted event | `core.counted_event` | **probable, local** | Il manque une relation entre `ReuseCount` et l'application qu'il compte. Ce n'est pas encore un système d'événements universel. |

`Property` et `Measurement` ne doivent pas nécessairement devenir deux classes
du noyau. La distinction sémantique est forcée ; une première représentation
peut garder une quantité comme propriété ou observation selon son statut et sa
provenance.

## D. Relations candidates

Les relations ci-dessous sont des rôles sémantiques, non une spécification
d'API. Leur nom français est normatif dans la conception et le nom anglais
sert d'identifiant de recherche.

| Relation FR | Relation en-GB | Statut | Usage minimal |
|---|---|---|---|
| appartient à | belongs to | **forcé** | Associer un concept à un ou plusieurs domaines. |
| représente | represents | **forcé** | Relier une représentation ou son occurrence à l'objet logique représenté. |
| est une occurrence de | is an occurrence of | **forcé** | Relier un spécimen à une représentation abstraite. |
| transforme | transforms | **forcé** | Relier une occurrence source à une occurrence cible. |
| produit | produces | **probable** | Nommer explicitement la sortie d'une transformation ou d'une exécution. Peut être dérivé de `transforms`. |
| porte sur | concerns | **forcé** | Attacher propriété, observation ou mesure à son sujet concret. |
| dérive de | derives from | **forcé** | Conserver les dépendances d'une quantité calculée ou d'une décision. |
| est produite par | is produced by | **forcé** | Relier une observation à l'exécution expérimentale qui l'a produite. |
| est sérialisée dans | is serialised in | **forcé** | Relier une observation à l'artefact qui la contient. |
| respecte le protocole | follows protocol | **probable** | Attacher une exécution à son protocole, timer, warm-up, répétitions et statistiques. |
| compte les occurrences de | counts occurrences of | **forcé comme relation** | Relier un compteur à l'événement précis qu'il compte. |
| active | activates | **probable** | Relier un besoin à des concepts ou domaines placés dans un contexte d'inférence. |
| rapproche contextuellement | contextually relates | **probable** | Exprimer une correspondance utilisée dans un raisonnement sans créer d'appartenance permanente. |
| expose | exposes | **candidat** | Décrire qu'une représentation rend disponible une propriété d'un autre domaine, par exemple une séquence d'intervalles. |

`produit` peut rester une formulation lisible de `transforms` tant qu'aucun
cas ne demande de distinguer plusieurs sorties. De même, un « pont
inter-domaines » n'est pas une relation primitive obligatoire : un
`contextually relates` portant une justification et une provenance suffit à
ce stade.

## E. Identité objet / représentation / spécimen

### Distinction minimale

Le cas QuickDraw exige trois niveaux :

```text
objet logique :       C
représentation :      B0 bitmap, B1 runs
spécimens :           b0_C, b1_C
transformation :      b0_C --convertit--> b1_C
```

`C` est l'identité logique de la région résultat. `B0 bitmap` et `B1 runs`
sont des formalismes ou types de représentation ; ils ne sont pas deux
régions logiques. `b0_C` est l'occurrence concrète du résultat B0 produit par
l'intersection QuickDraw 3, avec ses dimensions, octets et hash. `b1_C` est
l'occurrence B1 obtenue en convertissant ce même résultat.

Une occurrence doit pouvoir conserver au minimum :

- l'objet logique représenté ;
- la représentation abstraite réalisée ;
- un identifiant ou hash du contenu concret ;
- la transformation ou exécution qui l'a produite ;
- les propriétés observées qui servent à vérifier l'identité logique.

La transformation ne crée donc pas `C2`. Elle crée ou matérialise une autre
occurrence de représentation de `C`. L'affirmation « même région logique »
est une relation vérifiable par une observation canonique, pas une conséquence
du seul fait que les deux objets portent le même nom.

### Ce que v1.1 établit

Le harness C suit réellement :

```text
inputs → B0 operation → b0_C → B0-to-B1 conversion → b1_C → application
```

Les hash canoniques et les applications concordent pour `sparse_sparse` et
`fragmented_fragmented`. Cette preuve justifie la distinction de spécimen et
la relation de transformation ; elle ne justifie pas une ontologie plus fine
des octets, buffers ou allocations.

## F. Lignée expérimentale

### Distinction minimale

Une chaîne `source = fichier.json` est insuffisante. La lignée doit relier au
moins :

```text
Observation/Measurement
  → porte sur : specimen ou opération concrète
  → est produite par : experiment run
  → respecte : protocole et environnement
  → est sérialisée dans : result artefact
```

Le `result_artifact` est le fichier contenant le résultat ; il n'est pas la
source expérimentale. L'`experiment` décrit l'expérience ou le harness, tandis
qu'une exécution concrète peut préciser la date, le binaire, les sources, le
workload, la plateforme et le protocole effectivement utilisés. La distinction
entre expérience et exécution est **forcée comme relation**, même si une
première implémentation peut conserver l'exécution comme un enregistrement de
contexte plutôt que comme une entité autonome.

Pour une mesure physique, la lignée minimale doit rendre lisibles :

- programme ou binaire et version/empreinte si disponible ;
- implémentation et sources pertinentes ;
- spécimen, workload et opération ;
- plateforme, compilateur et options ;
- timer, affinité CPU, warm-up et nombre d'échantillons ;
- statistique utilisée, par exemple médiane d'un lot ;
- artefact contenant le relevé ;
- provenance des valeurs dérivées si une somme ou une conversion de données
  intervient.

Cette liste est issue de la fracture auditée entre conversion Python et
application C, puis corrigée par v1.1 grâce au harness C homogène. Elle ne
constitue pas une base de provenance générale.

### Observation, mesure et artefact

Une **observation** est un résultat attaché à un sujet et à une exécution. Une
**mesure** est une observation quantitative : elle porte une quantité, une
unité, une statistique et un protocole. Une observation qualitative ou une
assertion d'identité peut ne pas être une mesure.

Un résultat dérivé comme un break-even n'est pas une mesure physique nouvelle :
il est une expression dérivée dépendant de mesures contextualisées. Les
anciens `N=66/N=119` restent des sorties historiques de v1 et non des
propriétés QuickDraw ; les nouveaux point-estimates `N=7/N=4` viennent du
harness C, avec une frontière fragmented explicitement bruitée.

## G. Compteur ↔ opération comptée

v1 a corrigé le défaut count * duration en distinguant ReuseCount de RunCount. Cette distinction reste toutefois insuffisante : ReuseCount indique qu'une quantité représente un nombre de réutilisations, mais ne précise pas quelle opération est répétée.

Ainsi, le noyau peut encore accepter conceptuellement :

repeat(reuse_count, apply_time)
repeat(reuse_count, build_time)

alors que, dans le scénario actuel, reuse_count compte les applications du résultat et non ses reconstructions.

La distinction manquante est relationnelle. Un compteur d'occurrences doit référencer l'opération dont il compte les répétitions, et un coût unitaire doit référencer l'opération dont il mesure le coût :

reuse_count
    compte les occurrences de / counts occurrences of
apply_result

apply_time
    coût de / cost of
apply_result

repeat(reuse_count, apply_time) est alors valide parce que le compteur et le coût unitaire portent sur la même opération.

À l'inverse :

reuse_count
    counts occurrences of
apply_result

build_time
    cost of
build_result

rend repeat(reuse_count, build_time) incohérent.

La règle recherchée n'est donc pas « ReuseCount peut répéter une durée d'application », mais :

un compteur d'occurrences peut composer avec le coût unitaire de l'opération dont il compte les occurrences.

Cette relation peut rester locale au domaine ou au scénario. apply, build ou convert peuvent pour l'instant être de simples identifiants d'opérations ; Atlas n'a pas besoin d'introduire une ontologie universelle des événements ou des opérations.

## H. Composition inter-domaines

### Règle

Une ontologie locale répond à « où ce concept est-il organisé ? ». Elle ne
répond pas seule à « quels concepts dois-je mettre en relation pour ce besoin
? ». Le contexte d'inférence actif est donc une sélection temporaire :

```text
besoin
  → concepts/domaines pertinents
  → contexte d'inférence
  → relations et contraintes considérées
```

Le contexte peut relier deux concepts sans les fusionner, sans ancêtre commun
et sans relation permanente d'héritage. Une relation souvent réutilisée peut
être conservée comme connaissance locale ou pont, mais elle reste justifiée
par des observations et ne devient pas une condition universelle de toute
inférence.

### Exemple de correspondance

Le cas QuickDraw fournit une correspondance concrète :

```text
graphisme 2D classique : représentation par segments horizontaux
algorithmique élémentaire : séquence ordonnée d'intervalles, fusion ordonnée
```

La relation utile n'est pas `Region is-a Sequence`. C'est plutôt :

```text
runs(R) expose une séquence ordonnée d'intervalles par scanline
intersection(R1, R2) peut exploiter une fusion ordonnée
```

Cette relation peut être active uniquement dans un contexte traitant une
intersection et son cycle de vie. Si elle est conservée, elle doit garder sa
provenance : observation du parcours B1/RgnOp, mesure des coûts et scénario
concerné. Elle ne fusionne pas les deux vocabulaires.

### Appartenance et rapprochement

- appartenance permanente : `horizontal_runs` appartient au domaine de
  graphisme 2D classique ; `sequence` appartient au domaine algorithmique ;
- rapprochement contextuel : le besoin d'une fusion efficace met les deux
  concepts en présence et autorise une correspondance locale ;
- pont réutilisable : une relation documentée `exposes ordered interval
  sequence` peut être conservée, sans devenir `is-a`.

Aucun score, ranking, profondeur ou budget de traversée n'est défini.

## I. Exemple transversal complet

### Besoin

Après une intersection de deux régions QuickDraw, appliquer le résultat à de
nombreux blits `srcCopy`. Le besoin est de choisir si le résultat B0 doit rester
bitmap ou être converti en runs.

### Concepts activés

- `region`, `intersection`, `bitmap`, `horizontal_runs`, `region_application`
  du domaine **Graphisme 2D classique** ;
- `sequence`, `merge`, `reuse count`, `ordered traversal` du domaine
  **Algorithmique et structures de données élémentaires**.

Le contexte ne déclare pas que `Region` est une `Sequence`. Il active une
relation entre la représentation B1 et une propriété de séquence ordonnée qui
est utile pour expliquer son application et sa construction.

### Lignée et transformation

```text
inputs
  → intersection B0
  → b0_C : occurrence bitmap du même objet logique C
  → conversion native
  → b1_C : occurrence runs de C
  → application répétée
```

La comparaison canonique et les hash de v1.1 supportent l'identité logique de
`b0_C` et `b1_C`. Le programme, le timer, le protocole et les statistiques sont
ceux du même harness C ; ils ne sont pas remplacés par le fichier JSON seul.

### Décision observée

Sur `sparse_sparse/intersection`, la conversion native a une médiane d'environ
526,7 µs, l'application B0 environ 78,8 µs et l'application B1 environ
0,90 µs. Le point-estimate donne `N=7`, et les mesures end-to-end confirment le
gain à `N=6` et `N=7`.

Sur `fragmented_fragmented/intersection`, le point-estimate donne `N=4`, mais
la mesure end-to-end est pratiquement à égalité : aucune frontière physique
stable n'est revendiquée. Les valeurs historiques v1 `N=66/N=119` restent
visibles comme artefacts non démontrés.

L'exemple montre ce que le modèle doit conserver : objet logique, occurrence,
transformation, événement d'application compté, mesures contextualisées et
expression dérivée. Il ne démontre ni la généralité de la relation entre
domaines, ni la nécessité d'un pont permanent.

## Discipline de modélisation

### Distinctions déjà forcées

- objet logique / représentation abstraite / spécimen concret ;
- propriété structurelle / observation mesurée ;
- observation / artefact qui la sérialise ;
- expérience ou exécution / valeur produite ;
- quantité et `QuantityKind` / unité physique ;
- compteur / événement dont il compte les occurrences ;
- appartenance à un domaine / rapprochement contextuel.

### Distinctions probablement utiles mais non encore forcées

- scénario identifié séparément d'un contexte d'inférence ;
- opération transversale ;
- pont inter-domaines comme relation persistante ;
- exécution expérimentale comme entité distincte de l'expérience déclarée ;
- domaine principal et domaines secondaires.

### À ne pas transformer en abstraction maintenant

- filtres dynamiques, scores, distance entre domaines et ranking ;
- profondeur de traversée, budget d'exploration et politiques de pruning ;
- hiérarchie universelle ou racine commune ;
- moteur d'inférence complet ;
- système de types général ou logique formelle universelle ;
- ontologie de tous les programmes, événements ou plateformes ;
- parser, graphe de concepts, RDF/OWL, DSL ou schéma de stockage définitif.

## Réponses finales

### 1. Quelles distinctions sont déjà suffisamment forcées ?

Le petit noyau transversal est : objet logique, représentation, spécimen,
transformation, quantité/propriété, observation/mesure, lignée d'exécution et
artefact, ainsi que la relation `counts_occurrences_of`. Il faut également
distinguer appartenance de domaine et rapprochement contextuel. Ces
distinctions sont directement motivées par Semantic Core v1/v1.1, les audits,
POC12 et les expériences QuickDraw.

### 2. Quelles notions restent spécifiques à un domaine ?

`Region`, `Bitmap`, `Runs`, `Transitions`, `BitBlt`, clipping et opérations
booléennes restent spécifiques au graphisme 2D. `Collection`, `Lookup`,
`HashTable`, adressage ouvert, recherche dichotomique, séquence triée et
parcours restent dans le domaine algorithmique élémentaire. Les unités et
quantités comme `RunCount`, `VerticalTransitionCount` ou `ApplyTime` peuvent
être transversales comme rôles, mais leur signification concrète reste locale.

### 3. `Scenario` mérite-t-il déjà une identité propre ?

Non, pas encore. v1 montre qu'un scénario doit être conservé dans une
expression dérivée et dans le contexte d'une mesure, mais aucun résultat ne
force une entité globale réutilisable. Un descripteur structuré suffit pour
l'instant ; son identité pourra être introduite si plusieurs expériences
doivent référencer exactement le même scénario.

### 4. Faut-il distinguer `Representation` de l'occurrence concrète ?

Oui. C'est une distinction forcée par l'audit et v1.1. `Representation` est
le formalisme B0/B1/B2 ; l'occurrence est le spécimen réellement produit,
avec hash, contenu, lignée et mesures. Sans elle, un masque reconstruit peut
être confondu avec le B0 effectivement produit.

### 5. Quelle est la représentation minimale d'une lignée expérimentale ?

Une observation quantitative doit référencer : le sujet concret, l'exécution
ou harness producteur, le protocole et l'environnement, l'artefact qui la
contient, et la statistique employée. L'exécution doit au moins identifier le
programme/implémentation, le workload/opération, le spécimen, le timer, le
warm-up, l'affinité, le nombre d'échantillons et la plateforme. C'est une
relation de provenance minimale, pas une base de provenance générale.

### 6. Quelle relation manque pour relier un compteur à l'événement qu'il compte ?

`counts_occurrences_of(count, event)` — en français
`compte_les_occurrences_de`. Pour `reuse_count`, l'événement doit être
l'application du résultat dans le scénario considéré. Cette relation permet
de refuser `repeat(reuse_count, build_time)` lorsque la durée porte sur un
événement différent.

### 7. Peut-on faire de l'inférence inter-domaines sans méta-ontologie ?

Oui. Un besoin active un contexte temporaire qui réunit des concepts locaux et
des relations justifiées par le scénario. Les concepts gardent leurs domaines
et leurs identifiants ; aucune hiérarchie globale, ancêtre commun ou pont
permanent n'est requis. Le cas `runs` / séquence ordonnée / fusion QuickDraw
illustre cette composition.

### 8. Quels concepts ne devraient pas être implémentés dans Semantic Core v2
à ce stade ?

Ne pas implémenter les filtres, scores, distances, rankings, budgets ou
politiques de pruning ; la hiérarchie universelle ; le moteur d'inférence ; le
système de types général ; une ontologie universelle des événements ; un
algorithme de rapprochement de domaines ; un modèle de scénario global ; un
graphe de provenance complet ; un parser, DSL, IR ou système de persistance.
Même les ponts inter-domaines doivent rester des relations narratives ou
locales jusqu'à ce qu'une expérience les rende nécessaires.

## Limites et inconnues

Cette conception ne tranche pas :

- comment découvrir les domaines ou concepts depuis du code ;
- comment comparer automatiquement deux représentations valides ;
- comment choisir la granularité minimale d'une inférence ;
- comment représenter plusieurs hypothèses ou observations corrélées ;
- comment calibrer les mesures sur plusieurs plateformes ;
- comment gérer les types numériques, arrondis et entiers machine ;
- comment persister et versionner des proto-ontologies ;
- comment automatiser ou optimiser le raisonnement.

Ces questions restent volontairement ouvertes. La conclusion de cette étape
est architecturale : des îles locales et un contexte de rapprochement suffisent
pour décrire les connaissances actuelles sans imposer une ontologie
universelle.
