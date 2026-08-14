# Semantic Kernel — Knowledge

## Confirmed

- Step 1 can represent one stable intent, lookup(collection,key), and two
  distinct realizations that both realize that intent.
- A binary realization can depend on a separate representation fact:
  represents(S, collection) plus sorted_representation(S). The same intent
  remains unchanged when S is already present or must be built.
- The step-1 binary scenarios remain executable alongside step 2: an existing
  sorted representation gives binary lookup directly, while a known producer
  gives a one-time construction cost.
- The three resource situations are distinguishable without a closed-world
  impossibility fact: an auxiliary representation can be existing,
  constructible by a known producer, or have no known admissible producer in
  the current context. The last status is an evaluation result, not a claim
  that no producer can exist.
- The e-graph can record these descriptions, relations, availability facts,
  cardinality and workload-specific abstract costs without introducing
  fundamental Intent, Realization or Resource classes.
- With the fixed abstract equations, linear lookup is preferred for one lookup
  on n=16 when sorting must be built (cost 16 versus 68), while building the
  sorted representation is preferred for 20 lookups on n=64 (cost 1,280
  versus 504). An existing sorted representation makes binary lookup cost 120
  in the same workload.

## Refuted

- The absence of a sorted representation does not remove or change the
  lookup(collection,key) intention; it only removes immediate availability of
  the binary realization until construction is admitted.

## Uncertain

- Can Atlas represent intents and realizations using the same generic description model?
- Are Description, Fact and Relation sufficient as the initial semantic kernel?
- Does Resource need to be a fundamental concept?
- Does Atlas need distinct notions of equivalence, realization, refinement or construction?
- Is egglog a natural substrate for this model?

## Semantic kernel

Step 1 uses descriptions plus relations rather than a class hierarchy:

| Relation | Meaning in this POC |
|---|---|
| realizes(R, I) | realization R fulfils intention I |
| represents(S, C) | representation S denotes collection C |
| sorted_representation(S) | S has the ordering property required by binary lookup |
| available(R, S) | realization R is currently usable with S |
| builds(B, C, S) | operation B can produce representation S for C |
| cost(R, workload, value) | abstract cost fact for this concrete workload |

Description, Fact and Relation remain conceptual roles. The first experiment
does not justify separate technical types for Intent, Realization or Resource.

## Complexity smells

- Abstract costs are stored as workload-specific facts and also computed by a
  small Python function. This duplication is intentional for step 1 but warns
  that a later experiment must decide whether cost equations are semantic
  descriptions or evaluation code.
- At the end of step 1, available was still recorded manually; step 2 now
  derives resource-dependent availability through egglog rules.
- Treating absence of available/build facts as unobtainable would be a
  closed-world error. The prototype deliberately leaves that absence open and
  reports only no_known_admissible_producer for the tested context.
- Egglog currently demonstrates fact registration and checking. It has not yet
  demonstrated a useful rewrite or equivalence beyond recording relations.

## Step 2 — ressources construites, disponibles et partagées

### Confirmed

- lookup(collection,key) remains the same intention for linear, binary and
  hash realizations. Hash lookup requires a Description H with
  represents(H, collection) and hash_index(H).
- A hash index can be existing or constructible through
  build_hash_index(collection)->H. Its abstract build cost is paid once:
  with n=64 and 20 lookups, the existing-index case costs 60 and the
  constructible case costs 188, rather than charging the build 20 times.
- The same H is referenced by two lookup calls through uses; the prototype
  therefore does not duplicate the index or its construction cost merely
  because it is shared.
- A third state is represented without a closed-world fact: when no existing
  index and no known admissible producer are in the context, evaluation reports
  no_known_admissible_producer. It does not assert that no producer could
  exist. The lookup intention remains available and linear lookup remains a
  realization.
- The catalogue registers generic builds facts for all three producers in every
  scenario. Constructibility is derived only when local present(collection)
  and enabled(builder, scenario) facts satisfy the generic rule.
- scan(collection) is distinct from lookup(collection,key). It has both
  linear_scan(collection) and scan_dense(D) realizations. D is a Description
  with represents(D, collection) and dense_view(D), and may be existing or
  constructible.
- A memory constraint can reject a realization without changing the meaning of
  the intention. In the fixed scenario, a dense view with memory cost 200 and
  budget 100 is constructible but not admissible; linear scan remains usable.
- The cost and memory observations for the tested scenario are now registered
  as egglog facts as well as evaluated by the small Python layer. This keeps
  the distinction visible between semantic relations and the local numerical
  comparison.

### Refuted

- A Resource type is not required by these cases. Existing, constructible and
  contextually unavailable auxiliary structures can be expressed with
  Description plus relations and evaluation status.
- Treating missing available or builds facts as impossible(H) would be an
  invalid closed-world interpretation and is deliberately not part of the
  prototype.
- A memory cost is not a semantic precondition of scan; it is a constraint
  evaluated for a concrete scenario.

### Uncertain

- Whether the current one-step derivation of available is sufficient once
  producer chains become longer.
- Whether a future context needs a first-class producer/plan object to explain
  chains of construction, rather than the current builds relation.
- Whether egglog provides enough benefit once relations, sharing and
  construction chains grow. At this step it provides a common fact store and
  consistency checks, but no demonstrated rewrite, equivalence or search
  advantage over a small collection of Python records.

## Catalogue vs Scenario vs Search Result

The revised step 2 separates three layers:

### Catalogue

The catalogue is scenario-independent. It contains realizations, resource
properties, requirements and producer rules:

- linear, binary and hash lookup realize lookup;
- linear scan and dense scan realize scan;
- binary requires S, hash requires H, and dense scan requires D;
- the three build operations can produce S, H and D.

These facts are present even in a scenario where no corresponding resource can
currently be obtained.

### Scenario

A scenario contributes only local facts: collection presence and cardinality,
which resources are present, which known builders are enabled, lookup count,
and memory budget. It does not set hash_constructible, dense_constructible or
another universal property.

Egglog derives constructible(resource, scenario) from the catalogue builds rule
plus local facts. It derives available(realization, scenario) from a required
resource being present or constructible. Missing derivations remain open; they
are reported as no_known_admissible_producer, never as global impossibility.

Neither constructible nor admissible is an intrinsic catalogue property.
The catalogue says only that a producer can build a resource under its
declared structural preconditions. Constructible is derived for a scenario
from that rule and local facts. Admissible is evaluated afterwards from the
derived path availability and the simple local constraints currently modeled,
such as the memory budget. The tight dense-view assertion demonstrates that D
can be constructible while the dense path is not admissible.

### Search result

Search enumerates all catalogue realizations, removes paths that are not
available in the scenario, attaches the local abstract cost to each remaining
path, and selects the minimum. The linear path is always an ordinary candidate.
In the no-known-hash scenario it wins because it is the remaining admissible
minimum, not because a hash-specific fallback branch selected it.

The four architecture assertions in the runner check that the generic build
rule exists in a no-producer scenario, that constructibility is derived when
local facts enable it, that lookup remains a relation/intention without a
hash path, and that linear is selected by the same minimum operation.
They also check that constructible is absent without local enabling facts and
that admissibility is not stored in the catalogue: it is computed only during
path search under the scenario budget.

## Step 3 — composition, factorisation and specialization

### Confirmed

- The two intentions lookup(collection,key) and scan(collection) can be
  composed through one shared sorted representation S. The catalogue uses the
  existing builds, requires and realizes relations; binary lookup and
  scan_sorted both require the same S.
- In the large fixed scenario, the separate linear plan costs 1,344, while the
  shared sorted plan costs 568. The shared plan records one build of S and two
  consumers. In the small scenario, separate linear realizations cost 32 and
  win over the shared cost 84.
- This is a genuine factorisation cost-accounting test: the build work is
  attached once to the composite path, not once per consumer. The composite
  path itself is currently assembled by the explicit search layer; automatic
  discovery of such factorisations is not demonstrated yet.
- A specialization can use the same model. generic_operation_P and
  specialized_operation_P both realize operation(P,x), while the specialized
  path has preparation cost 100 and per-call cost 2 instead of 10. Generic
  wins for 5 repetitions (50 versus 110); specialization wins for 20 (200
  versus 140).
- No new fundamental Resource, Equivalence, Refinement or Factorisation type was
  required. Shared identity is carried by the same Description S and the
  existing relation structure; the search result contains the composite path.

### Validation intermédiaire

- Equivalence alone would not be sufficient: it can state that two
  realizations satisfy the same intention, but not that two consumers share one
  preparation or that a preparation cost must be paid once.
- The experiment still requires only one generic Description domain plus
  relations and facts. The current vocabulary includes realizes, requires,
  builds, present and enabled; relations such as constructible and available
  are derived from them in scenario context. Composite-path construction
  remains part of the search layer rather than the semantic ontology.
  Factorisation is a property of a composite candidate path, not a new
  ontological primitive.
- Egglog represents the shared resource and derives availability naturally.
  The enumeration and cost aggregation of composite paths remain a small
  explicit search layer; this is a limitation to retain rather than hide.
- No mechanism was added only to save the two examples. The same relations
  already used for sorted/hash/dense resources express the shared preparation
  and the specialization precondition.

### Refuted

- It is not necessary to duplicate the construction of S for lookup and scan.
- It is not necessary to encode specialization as a new kind of realization;
  it is an alternative path with a preparation cost and a lower repeated cost.

### Uncertain

- Whether a larger many-to-many composition still remains readable with only
  explicit composite paths.
- Whether a later experiment needs a first-class factorized plan to prevent
  accidental double counting across longer dependency graphs.
- Whether egglog should derive composite cost expressions, or whether keeping
  that calculation in the small search layer is the more transparent boundary.

### Audit ciblé de la factorisation

Le candidat `build_sorted + binary_lookup + scan_sorted` est actuellement
assemblé explicitement dans la fonction Python `composition_paths`. Il ne
résulte pas d'une découverte automatique par les dépendances du catalogue.
Les relations egglog existantes établissent seulement les préconditions :
`builds` décrit le producteur générique de S, `requires` relie les deux
réalisations à S, et les règles dérivent `constructible`/`available` à partir
des faits locaux du scénario. La composition elle-même, son coût et son
partage sont ensuite décrits par le chemin Python.

En conséquence, une troisième intention qui consommerait également S
nécessiterait aujourd'hui une extension manuelle de `composition_paths` : il
faudrait ajouter ce consommateur au chemin composite et inclure son coût. Le
système ne découvrirait pas automatiquement le nouveau plan factorisé. Cette
limite est classée `Uncertain` pour l'étape 4, et non corrigée ici.

Deux réalisations qui référencent la même description S peuvent partager son
identité dans le graphe : egglog peut donc établir qu'elles dépendent de la
même ressource et dériver leur disponibilité depuis cette ressource. En
revanche, egglog ne déduit pas actuellement la factorisation du coût du cycle
de vie et ne déduplique pas automatiquement la production de S. Le
`build_count: 1` et le coût de construction payé une seule fois sont codés
dans le chemin composite Python connu.

La frontière actuelle est donc la suivante : egglog garantit les faits
génériques du catalogue, l'identité des descriptions et les dérivations
locales de constructibilité/disponibilité. La couche de recherche Python
énumère les chemins composites connus, agrège leurs coûts, vérifie les
contraintes de scénario et sélectionne le minimum. Elle ne découvre pas les
factorisations à partir du seul graphe de dépendances.

Le prototype démontre ainsi l'évaluation d'une factorisation connue et
explicitement modélisée, pas la découverte d'une factorisation. La possibilité
d'une composition automatique pour plusieurs intentions, ainsi que la garantie
de déduplication dans des graphes plus longs, restent ouvertes.

## Step 4 — tentative de réfutation par surprise tests

### Variations exécutées

Le harnais séparé `experiments/semantic-kernel/surprise_tests.py` exerce sept
variations sans ajouter de nouvelle forme de candidat à `composition_paths` :

- un index hash déjà présent mais non rentable : avec `n=1`, un lookup hash
  coûte 3 contre 1 pour le chemin linéaire, qui est sélectionné ;
- un index hash constructible mais trop coûteux : avec `n=64` et un lookup,
  le hash coûte 131 contre 64 pour le linéaire ;
- deux représentations S et H présentes simultanément : les trois chemins sont
  admissibles et hash est sélectionné (60 contre 120 pour binary et 1 280 pour
  linear) ;
- deux consommateurs réutilisant S : la composition existante sélectionne le
  chemin partagé et compte zéro construction lorsque S est déjà présente ;
- une ressource sans producteur local connu : l'intention reste présente et
  linear est sélectionné parmi les chemins admissibles ;
- une spécialisation à 10 appels : le chemin générique reste meilleur (100
  contre 120) ;
- une spécialisation à 1 000 appels : le chemin préparé devient meilleur
  (2 100 contre 10 000).

Un défaut réel de comptabilisation a été découvert : le champ `build_count`
annonçait une construction pour S déjà présente alors que son coût de
production était nul. La correction est locale à ce résultat et ne modifie ni
les règles du catalogue ni la recherche de compositions.

### Instrumentation de la composition

Les surprise tests n'ont exigé aucune nouvelle forme de candidat composite :
le seul chemin partagé reste la forme explicitement codée
`shared_sorted_preparation`, face à `separate_linear_realizations`. Le résultat
confirme toutefois la limite précédente : cette absence d'extension est
observée parce que les tests restent dans les deux intentions prévues ; le
code ne sait pas découvrir automatiquement une composition pour une nouvelle
intention, un troisième consommateur de S, une collection mutable ou une
interaction où une ressource améliore une intention mais pénalise l'autre.
Ces cas restent des limites à tester avant toute généralisation.

### Validation intermédiaire des abstractions

| Concept | Cas qui l'utilisent | Fondamental ? | Peut être réduit à autre chose ? |
|---|---|---|---|
| Description | intentions, réalisations, S/H/D/P, scénarios | Oui pour le noyau observé | Pas sans perdre l'identité partagée et les objets du catalogue |
| Fact | présence, activation, cardinalité, coûts, budget | Rôle nécessaire, mais pas une classe technique démontrée | Peut rester une collection de relations/faits enregistrés |
| Relation | realizes, requires, builds, present, enabled et dérivations | Oui comme vocabulaire relationnel minimal | Pas proprement par de simples valeurs indépendantes |
| Resource | S, H, D et leur partage | Non comme type fondamental | Description + represents/requires/builds suffit |
| Cost | sélection selon cardinalité, fréquence et préparation | Nécessaire comme donnée de décision, pas comme type ontologique établi | Peut rester une observation/fonction locale contextualisée |
| Refinement | aucun surprise test ne l'exige | Non démontré | À laisser hors du noyau |

La sélection produit plusieurs résultats distincts sans planificateur : linear,
binary, hash, scan dense, composition partagée et spécialisation générique ou
préparée. Cela montre une extraction adaptée à ces cas, mais pas une découverte
générale de plans.

### Conclusion de l'étape

Les surprise tests réfutent l'idée qu'une représentation disponible ou
constructible est automatiquement préférable : la cardinalité, la fréquence,
le coût de construction, le budget mémoire et le partage changent la décision.
Ils ne réfutent pas encore le modèle Description + relations/faits + sélection
Python. En revanche, ils confirment que la factorisation et les compositions
restent explicitement énumérées dans cette couche.

La découverte automatique de factorisations, la gestion d'une troisième
intention, des graphes de dépendances plus longs et des ressources concurrentes
restent `Uncertain`. Aucune extension du noyau n'est justifiée par ces tests.

## Candidate discovery — étape 1

### Confirmed

Le nouvel espace `experiments/candidate-discovery/` remplace l'usage de
`composition_paths` pour les cas simples déjà connus. Son point d'entrée est
`discover_plans(goals, catalog, scenario)`. Le moteur reçoit les intentions,
les relations de catalogue portées par les données (`realizes`, `requires`,
`builds`) et les faits locaux du scénario.

Le moteur découvre génériquement :

- les réalisations correspondant à chaque intention ;
- les ressources requises par ces réalisations ;
- les ressources déjà présentes ;
- les producteurs activés du scénario ;
- les prérequis récursifs des producteurs ;
- le coût total des réalisations et des producteurs réellement inclus.

La résolution est indépendante des noms du domaine. Elle ne contient aucune
branche métier pour `hash`, `sorted`, `dense`, `lookup` ou `scan`. Une inspection
automatique de la source de découverte vérifie cette absence ; ces termes ne
figurent que dans la fixture et les assertions de régression.

Le plan candidat est une petite valeur canonique contenant les objectifs, les
réalisations, les producteurs, les ressources présentes utilisées, les
ressources produites et le coût. Une ressource requise deux fois est résolue
par son identité et son producteur n'est inclus qu'une fois. Dans le cas
lookup+scan, le plan `binary_lookup + scan_sorted + build_sorted` est découvert
avec un coût de 43, et non assemblé par une règle spéciale de partage.

La même résolution traite une ressource présente et une ressource produite :
la première ne génère aucun producteur, la seconde en sélectionne un si le
scénario l'active. Une réalisation dont la ressource n'est ni présente ni
productible n'apparaît simplement dans aucun plan. Les coûts sont additionnés
à partir des réalisations et producteurs du plan, pas via une formule propre à
une famille d'algorithmes.

La validation 1.5 couvre les régressions suivantes :

- lookup sans ressource : linear_lookup ;
- lookup avec producteur S : binary_lookup ;
- lookup avec H présent : hash_lookup ;
- scan sans ressource : linear_scan ;
- scan avec D productible : scan_dense est découvert ;
- scan avec S présente : scan_sorted ;
- lookup+scan avec S productible : le producteur partagé est unique.

Une chaîne artificielle `goal -> R -> Q` vérifie également la fermeture des
dépendances de producteurs sans cas métier.

Resource sharing currently relies on strict Description identity. Semantic
equivalence between distinct resource descriptions is not used for
deduplication. Whether e-class identity can safely serve as plan-level
canonical identity remains untested.

### Validation 1.5 — audit ciblé

| Question | Résultat |
|---|---|
| Une liste de candidats métier subsiste-t-elle dans le nouveau moteur ? | Non ; les alternatives sont des données du catalogue. |
| Les mots métier apparaissent-ils dans la logique de découverte ? | Non ; l’inspection source l’affirme automatiquement. |
| Une ressource partagée est-elle dédupliquée par identité ? | Oui ; les exigences sont regroupées par description et le producteur est compté une fois. |
| Présence et production utilisent-elles la même résolution ? | Oui ; la résolution court-circuite une ressource présente et construit une ressource absente avec les producteurs autorisés. |
| Les réalisations non admissibles disparaissent-elles naturellement ? | Oui ; sans ressource présente ou producteur activé, aucun plan correspondant n’est produit. |
| Le coût vient-il des éléments du plan ? | Oui ; il est la somme des coûts des réalisations et des producteurs sélectionnés. |

L'ancien `composition_paths` reste présent dans le Semantic Kernel committé
comme référence historique reproductible. Il n'est pas appelé par le nouveau
moteur et n'est pas une preuve de découverte générique. Aucun code des étapes
ultérieures — troisième consommateur, catalogue synthétique, croissance
combinatoire, canonicalisation expérimentale, mémoïsation ou pruning — n'est
inclus dans ce POC.

### Refuted

- Une forme composite spéciale n'est pas nécessaire pour découvrir le cas
  simple à deux intentions.
- Le partage de S n'est pas limité à un nom ou à une représentation triée dans
  le moteur ; il découle de l'identité de la ressource et des relations du
  catalogue.

### Uncertain

- La découverte reste démontrée seulement pour ce petit modèle statique et ces
  cas simples.
- Les plans de producteurs avec cycles, plusieurs chaînes concurrentes et
  contraintes globales n'ont pas encore été étudiés.
- La croissance de l'espace de plans, la mémoïsation et le pruning sont
  volontairement réservés à une étape ultérieure.

### Limites explicitement hors périmètre

Les premiers essais locaux contenaient une esquisse de résultats à trois
intentions et de catalogues synthétiques de croissance. Ils ont été retirés du
code de ce POC avant validation : ils appartiennent aux étapes futures et ne
doivent pas être interprétés comme des résultats expérimentaux actuels.

## Candidate discovery — étape 2

### Confirmed

Le moteur générique de l'étape 1 découvre maintenant sans modification de sa
logique le cas principal à trois intentions : `lookup`, `scan` et `summary`
peuvent tous sélectionner une réalisation qui requiert S, et le plan retenu
contient `build_shared` une seule fois.

Le même test paramétré avec 1, 2, 3, 5 et 10 consommateurs donne
respectivement 2, 4, 8, 32 et 1 024 candidats. Dans chaque cas, le plan retenu
utilise les réalisations partagées et une seule occurrence du producteur de S.
L'ajout d'un consommateur n'a exigé aucune modification de `discover_plans`.

Un catalogue joint H/D produit également automatiquement le plan :

    build_H + lookup_hash + build_D + scan_dense

Dans le scénario où S n'est pas activable et où H/D le sont, ce plan est le
meilleur des quatre plans produits, avec un coût de 55. Dans le scénario où
toutes les alternatives sont activées, neuf plans sont produits, dont les
combinaisons linear, hash, dense et shared sorted ; le plan partagé S est alors
sélectionné avec un coût de 43. Aucun candidat `hash+dense` ou `shared sorted`
n'est programmé dans la recherche.

### Validation 2.5

| Question | Résultat |
|---|---|
| Generic discovery : le troisième consommateur est-il découvert ? | Oui, sans modification du planner ; le plan contient un seul producteur de S. |
| Joint plans : H+D apparaît-il sans candidat spécifique ? | Oui ; quatre plans sont produits dans le scénario H/D et hash+dense est sélectionné. |
| Sharing : l'identité déduplique-t-elle les producteurs ? | Oui ; S est produite une fois pour 1 à 10 consommateurs. |
| Number of candidates | 2, 4, 8, 32, 1 024 pour 1, 2, 3, 5, 10 consommateurs ; 4 pour H/D ; 9 avec toutes les alternatives. |
| Duplicate plans avant canonicalisation éventuelle | 0 dans les scénarios mesurés. Le planner n'ajoute pas de canonicalisation ou mémoïsation expérimentale. |
| Search responsibility | La fermeture des dépendances, l'expansion des réalisations, le partage et la sélection sont assurés par Python dans ce harnais ; egglog n'est pas utilisé par cette étape. |
| New ontology | Aucun nouveau concept sémantique fondamental n'a été nécessaire. |

### Search-space observation

Le nombre de candidats croît déjà comme 2 puissance le nombre de
consommateurs dans le catalogue paramétré, avant d'introduire des producteurs
alternatifs ou des chaînes plus longues. Le partage réduit le coût du plan,
mais ne réduit pas automatiquement le nombre de choix de réalisations.
Cette observation est conservée comme signal de l'étape suivante, sans
introduire ici de pruning, de mémoïsation ou de solveur.

### Uncertain

- Les comptes de doublons sont nuls dans ces catalogues sans chemins
  structurellement redondants ; le comportement face à des descriptions
  équivalentes distinctes reste non testé.
- La croissance au-delà de ces petits cas et les stratégies de réduction de
  l'espace restent à étudier séparément.
- L'absence d'egglog dans ce harnais ne réfute pas son utilité comme stockage ou
  moteur de dérivation ; elle montre seulement que la découverte de plans est
  actuellement exécutée par Python.

## Candidate discovery — étape 3, explosion synthétique

### Générateur et stratégies

`experiments/candidate-discovery/step3_explosion.py` introduit un générateur
paramétrique sans vocabulaire QuickDraw ni clé-valeur. Ses paramètres sont :

- G : nombre d'intentions ;
- A : alternatives par intention ;
- D : profondeur de la chaîne de producteurs ;
- P : producteurs concurrents par ressource ;
- S : nombre d'intentions partageant un groupe de ressources.

Les cycles sont exclus. Chaque intention possède une alternative directe et des
alternatives qui requièrent une ressource ; les producteurs peuvent eux-mêmes
requérir la ressource du niveau précédent.

Trois traitements sont comparés :

- `naive_search`, combinaison et expansion indépendantes servant de témoin ;
- `canonicalize`, qui retire les expansions invalides ou structurellement
  identiques et recompte les producteurs par identité ;
- `memoized_search`, qui résout chaque ressource distincte une fois avant de
  combiner les choix d'intentions.

Un pruning générique supplémentaire conserve le producteur de moindre coût
pour une même sélection de réalisations et de ressources produites. Aucun nom
de domaine ni cas métier n'intervient dans ces stratégies.

### Table de croissance observée

Les temps sont en secondes sur l'environnement Python local ; les limites sont
50 000 états pour le témoin naïf et 200 000 plans pour la recherche mémoïsée.
Un résultat marqué interrompu est donc une borne observée, pas un décompte
complet.

| G | A | D | P | S | descriptions | relations | naïf | canonique | mémo | pruning | naïf s | mémo s |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 2 | 0 | 1 | 1 | 10 | 8 | 4 | 4 | 4 | 4 | 0.00007 | 0.00005 |
| 3 | 2 | 1 | 2 | 3 | 15 | 15 | 125 | 29 | 29 | 8 | 0.00044 | 0.00012 |
| 4 | 2 | 2 | 2 | 1 | 48 | 52 | 6 561 | 6 561 | 6 561 | 16 | 0.0356 | 0.0307 |
| 5 | 2 | 2 | 2 | 5 | 24 | 25 | 26 281* | 241* | 249 | 32 | 0.1278 | 0.00064 |
| 6 | 3 | 2 | 2 | 1 | 78 | 90 | 40 121* | 40 121* | 200 000* | 123 | 0.1401 | 0.5517 |
| 6 | 2 | 3 | 3 | 6 | 34 | 39 | 19 927* | 487* | 5 104 | 64 | 0.0651 | 0.0074 |

`*` indique qu'une limite a été atteinte ou que la canonisation porte sur une
entrée naïve incomplète. Les colonnes `descriptions`, `relations`, `states`,
`max_frontier`, `duplicates_eliminated` et `aborted` sont également émises par
le JSON du runner, afin de ne pas réduire l'observation au seul nombre final.

Les tests de sensibilité mémoïsés donnent, à paramètres constants sauf celui
indiqué :

| dimension | valeurs de plans terminaux observées |
|---|---|
| G = 1..5 | 5, 25, 125, 625, 3 125 |
| A = 1..4 | 1, 29, 105, 253 |
| D = 0..3 | 15, 29, 57, 113 |
| P = 1..3 | 8, 29, 64 |
| S = 1,2,3 | 125, 65, 29 |

Dans cette famille, G est la croissance exponentielle la plus immédiate ; A,
D et P augmentent aussi fortement la base ou la profondeur de l'espace. Le
partage S réduit le nombre de ressources distinctes et donc le nombre de plans
mémoïsés, sans supprimer les alternatives de réalisation.

### Confirmed

- Un générateur paramétrique peut produire des graphes indépendants, partagés,
  profonds et dotés de producteurs concurrents sans branches de domaine.
- La recherche naïve devient mauvaise dès les petits cas combinés : le cas
  G=6, A=3, D=2, P=2 atteint sa limite de 50 000 états.
- Le partage structurel réduit fortement les résolutions répétées : pour
  G=6, A=2, D=3, P=3, S=6, la recherche mémoïsée termine avec 5 104 plans,
  tandis que le témoin naïf est borné à 19 927 expansions observées et reste
  incomplet.
- La réduction observée dans les catalogues générés vient surtout du filtrage
  d'expansions invalides issues du témoin naïf : 19 440 dans le dernier cas et
  26 040 dans le cas G=5. Les compteurs de doublons canoniques et stricts sont
  séparés et nuls dans ces cas.
- Le pruning par coût réduit par exemple 29 plans à 8 dans le cas G=3 et 487
  à 64 dans le dernier cas, parce que plusieurs producteurs sont
  interchangeables pour les mêmes ressources dans ce générateur.

### Validation conceptuelle des réductions

Les compteurs sont séparés :

- `invalid_expansions_filtered` : une expansion contient plusieurs producteurs
  pour une même ressource et ne constitue donc pas un plan valide ;
- `canonical_equivalents_merged` : plusieurs ordres ou représentations valides
  ont la même signature canonique ;
- `exact_duplicates_removed` : la même représentation brute apparaît plusieurs
  fois à l'identique.

Le micro-test de classification donne respectivement `1`, `1` et `1`. Dans les
catalogues générés, les doublons stricts et les équivalents canoniques restent
nuls ; les réductions observées dans les cas partagés sont principalement des
expansions invalides. Il serait incorrect de les attribuer à la seule
canonicalisation.

### Validité du pruning

Le pruning actuel peut éliminer un producteur plus cher uniquement si les plans
comparés ont :

- la même sélection de réalisations ;
- les mêmes identités de ressources produites ;
- les mêmes propriétés de producteurs pertinentes pour les consommateurs et
  les contraintes du plan ;
- les mêmes préconditions et effets utiles au modèle courant.

Dans ce cas seulement, le coût plus élevé est le seul critère qui distingue les
plans et le producteur moins cher domine l'autre. Le code encode désormais les
propriétés dans la signature de dominance minimale du générateur.

Le contre-test fournit deux producteurs de R : `cheap_R` et `rich_R` ont le
même résultat principal, mais `rich_R` expose en plus la propriété `also_Q`.
Les deux sont conservés. Lorsque les propriétés sont identiques et que seul le
coût diffère, `cheap_R` est conservé seul.

Cette expérience ne démontre donc pas une dominance générale. Elle démontre
seulement un pruning local conditionné par l'identité du résultat et par
l'égalité des propriétés pertinentes modélisées. Une propriété non représentée
dans le catalogue pourrait encore rendre ce pruning trop agressif.

### Refuted

- Un espace de descriptions compact n'implique pas un espace de plans compact :
  le cas à 48 descriptions produit 6 561 plans.
- Le partage ne rend pas automatiquement le nombre de choix constant : il
  réduit les sous-problèmes de ressources mais laisse les alternatives des
  intentions.
- Trouver rapidement les petits cas ne permet pas de conclure à la
  scalabilité : les mesures bornées montrent déjà des recherches incomplètes.

### Uncertain

- Les décomptes naïfs interrompus ne donnent pas encore une loi générale de
  croissance.
- Le pruning testé repose sur l'équivalence structurelle explicitement définie
  par le générateur ; sa validité pour des descriptions sémantiquement
  équivalentes reste inconnue.
- Egglog n'a pas été utilisé dans cette expérience synthétique : son aide
  éventuelle pour compacter les descriptions ne mesure pas automatiquement la
  réduction de l'espace des plans.
- Les interactions entre profondeur, producteurs concurrents et partage plus
  grands n'ont pas été explorées au-delà des bornes retenues.

## Candidate discovery — étape 4, formulation CP-SAT

### Configuration

Une contre-expérience séparée est implémentée dans
`experiments/candidate-discovery/step4_solver.py` avec OR-Tools CP-SAT. La
dépendance est isolée dans `requirements-step4.txt`; le catalogue et les
topologies sont ceux du générateur synthétique de l'étape 3.

Le modèle ne connaît aucun nom de domaine. Il crée :

- une variable booléenne par réalisation ;
- une variable booléenne par producteur ;
- une variable booléenne par ressource satisfaite.

Les contraintes imposent une réalisation par intention, activent les ressources
requises, sélectionnent au moins un producteur pour une ressource produite et
activent récursivement les dépendances des producteurs. Le coût est la somme
des réalisations et des producteurs sélectionnés ; une ressource partagée n'a
donc qu'une variable de producteur dans le plan.

### Oracle croisé

Sur les cas où l'énumérateur mémoïsé termine, CP-SAT retrouve le même coût et
la même signature sémantique (réalisations, ressources produites, dépendances
et propriétés des producteurs), même si deux producteurs de même profil ont
des identifiants différents. Les cas complets suivants ont concordé :

| G | A | D | P | S | plans énumérés | coût | variables CP-SAT | contraintes | temps CP-SAT |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 2 | 0 | 1 | 1 | 4 | 20 | 8 | 10 | 0.0016 s |
| 3 | 2 | 1 | 2 | 3 | 29 | 30 | 12 | 15 | 0.0008 s |
| 4 | 3 | 1 | 2 | 2 | 1 089 | 40 | 24 | 30 | 0.0011 s |
| 4 | 2 | 2 | 2 | 1 | 6 561 | 40 | 44 | 64 | 0.0018 s |
| 6 | 2 | 3 | 3 | 6 | 5 104 | 60 | 28 | 38 | 0.0014 s |

Les cas G=6/A=3/D=2 et G=8/A=3/D=3 ont atteint la borne de 200 000 plans
de l'énumérateur. CP-SAT les a néanmoins résolus à l'optimum, respectivement
avec 72 variables/102 contraintes en 0.0025 s et 40 variables/50 contraintes
en 0.0017 s. Ils sont classés `enumerator_bounded`, pas comme une preuve que
le solveur est toujours scalable.

### Partage obligatoire

Trois cas dérivés de la même topologie, avec les alternatives partagées
rendues préférables, valident explicitement :

- trois consommateurs d'une même chaîne de ressource : coût 13 ;
- deux intentions sur deux ressources distinctes : coût 12 ;
- quatre intentions sur deux ressources partagées : coût 24.

Dans chaque cas l'énumérateur et CP-SAT concordent, les producteurs sont
sélectionnés une seule fois par ressource, et aucun candidat spécial S, H+D ou
multi-partage n'existe dans la formulation.

### Confirmed

- Le catalogue relationnel suffit à produire une formulation booléenne qui
  sélectionne directement un plan sans matérialiser tous les plans candidats.
- Le partage par identité est exprimable par les variables de ressource et de
  producteur, sans contrainte métier spécifique.
- CP-SAT traite les premiers cas où l'énumérateur atteint sa borne avec un
  modèle encore petit ; cela montre une différence de représentation entre
  espace des plans et espace des contraintes.

### Refuted

- Il n'est pas nécessaire de programmer des contraintes séparées pour trois
  consommateurs, H+D ou plusieurs ressources partagées.
- Le solveur ne remplace pas l'oracle : l'accord observé est limité aux
  catalogues et coûts exacts de cette expérience.

### Uncertain

- Les résultats ne disent pas encore si la formulation reste fidèle avec des
  cycles, des durées de vie, de la mutation, des contraintes globales ou des
  coûts incertains.
- Le coût de construction du modèle et la qualité de la formulation n'ont pas
  été comparés à une implémentation egglog.
- La recherche CP-SAT utilise ici une fermeture acyclique et des contraintes
  statiques ; elle ne constitue pas encore un moteur de planification Atlas.

## Tests de clôture — troisième consommateur et ressources coexistantes

### Test A — troisième consommateur de S

Un troisième consommateur `summary_sorted(sorted_representation)` a été ajouté
uniquement au graphe du test. Il requiert la même description S et egglog
établit correctement sa disponibilité lorsque S est constructible.

Le résultat de `composition_paths` reste toutefois limité à ses deux
consommateurs codés : binary lookup et scan_sorted. Le troisième consommateur
n'est pas découvert dans le chemin partagé. Pour le prendre en compte dans une
composition à trois consommateurs, il faudrait ajouter manuellement une
nouvelle forme de candidat composite et son agrégation de coût.

Ce test sépare donc clairement :

- la représentation sémantique du partage, qui fonctionne pour une nouvelle
  dépendance vers S ;
- la découverte générique des compositions, qui n'est pas démontrée.

### Test B — H et D coexistants

Un scénario avec H et D simultanément présents conserve bien deux identités
distinctes. Avec n=64 et 20 lookups, hash est sélectionné à coût 60 ; le scan
dense est sélectionné à coût 32 avec une mémoire de 128 sous budget 128.

Un second scénario rend les deux ressources constructibles par deux producteurs
distincts. Les coûts restent séparés : hash coûte 188 pour le lookup et dense
coûte 96 pour le scan, mais les sélections indépendantes choisissent
respectivement hash et linear_scan. Aucun nouveau concept sémantique
fondamental n'est nécessaire : les descriptions H et D, leurs relations
`builds`, `requires`, `constructible` et les contraintes locales suffisent.

Pour ces deux intentions indépendantes, aucun nouveau candidat composite n'est
nécessaire. En revanche, si l'on demandait un plan joint comptant explicitement
les deux constructions H et D dans un même cycle de vie, ce candidat devrait
encore être assemblé manuellement par la couche Python.

### Verdict final par axe

#### Semantic representation

La représentation générique `Description` avec des relations de catalogue et
des faits locaux représente correctement les intentions, les réalisations et
les ressources partagées. Elle exprime également que trois consommateurs
peuvent référencer la même S, sans faire de la ressource un nouveau type
fondamental.

#### Resource identity/sharing

L'identité partagée fonctionne au niveau des descriptions : les consommateurs
référençant S partagent bien la même ressource, tandis que H et D restent
distinctes. Le comptage d'une production unique est correct pour le chemin
composite connu et pour S déjà présente après la correction de `build_count`.

#### Candidate discovery

La découverte n'est pas acquise. Le troisième consommateur est dérivable comme
disponible, mais il n'est pas injecté automatiquement dans la composition.
Une composition jointe H+D serait également une extension explicite. Le
prototype évalue des formes de candidats connues ; il ne découvre pas
généralement les factorisations ou plans multi-intentions.

#### Egglog suitability

Egglog est adapté au stockage des relations génériques et à la dérivation
contextuelle de `constructible`/`available`, y compris pour des ressources
coexistantes et un consommateur ajouté au test. La sélection, l'agrégation des
coûts et la découverte des candidats restent dans Python. Ces tests ne
justifient pas encore de déplacer cette responsabilité vers egglog ni de
construire un moteur de recherche plus général.

### Conclusion de clôture

Le POC démontre une représentation sémantique ouverte et un partage d'identité
des ressources, mais seulement une évaluation de compositions explicitement
énumérées. La limite de découverte de candidats reste `Uncertain` et doit être
conservée pour une étape ultérieure plutôt que masquée par une généralisation
prématurée de `composition_paths`.
## Temporal Planning POC — étape 1

Cette étape teste uniquement si une sélection statique peut devenir impossible
après planification, dans un modèle synthétique CP-SAT minimal. Le harnais est
dans `experiments/temporal-planning/run.py` et utilise OR-Tools `9.15.6755`.

### Modèle démontré

- chaque intention possède des réalisations avec `duration` et `scratch` ;
- `select_then_schedule` choisit la durée minimale sans utiliser la capacité
  ni la deadline, puis fixe ce choix et optimise son planning ;
- `joint_select_and_schedule` sélectionne les réalisations et les intervalles
  optionnels dans le même modèle ;
- la capacité globale est une contrainte cumulative de scratch ;
- la deadline borne le makespan ;
- l'ordre partiel est représenté par des précédences `end(A) <= start(B)` dans
  le modèle, mais aucun cas de dépendance n'est nécessaire au contre-exemple.

### Confirmed

- Il existe un contre-exemple reproductible où la sélection statique choisit
  `Fast` pour A et B (`duration=2`, `scratch=5`), mais ce choix est
  infaisable sous `scratch_capacity=5` et `deadline=3` : les deux opérations
  doivent être séquentielles et dépassent la fenêtre.
- La sélection jointe choisit `Compact` pour A et B (`duration=3`,
  `scratch=1`) et les exécute en chevauchement ; le makespan est 3 et respecte
  la capacité.
- La différence est provoquée par la combinaison capacité + chevauchement +
  deadline. La capacité interdit le chevauchement des deux `Fast`; la deadline
  interdit leur séquencement. La dépendance temporelle n'est pas utilisée dans
  ce cas discriminant.
- Le couplage observé est réel pour la faisabilité sous ces contraintes, mais
  l'échec de la méthode A vient aussi de sa faiblesse définie dans le protocole :
  elle ignore délibérément capacité, chevauchement et deadline et n'autorise
  aucun retour arrière.
- Un témoin reproductible (`scratch_capacity=10`, `deadline=2`) donne `Fast`
  aux deux stratégies : le chevauchement est alors autorisé et le makespan 2
  respecte la deadline.
- Les deux stratégies sont comparées par assertions reproductibles ; le
  modèle joint n'est donc pas seulement illustré par une sortie de benchmark.

### Refuted

- Il est réfuté, même dans ce petit univers, qu'une sélection indépendante du
  planning soit toujours sûre : elle peut produire une sélection impossible
  sans retour arrière.
- Il n'est pas démontré que toute séparation est mauvaise : le cas témoin
  montre un régime où la sélection statique et le scheduling produisent le
  même choix.

### Uncertain

- Le contre-exemple montre un couplage réel entre choix et planning pour le
  critère testé, mais ne mesure pas encore dans quelle mesure ce couplage reste
  nécessaire avec des coûts statiques différents, des précédences actives ou
  plusieurs ressources.
- Il reste à déterminer quelles classes de contraintes permettent de séparer
  les deux phases sans perte ; aucun critère général n'est proposé ici.
- Les résultats ne couvrent ni mutation, ni incertitude, ni concurrence
  système, ni modèle de plateforme.

### Temporal kernel

Les seules primitives temporelles nécessaires et démontrées par le code sont :

- durée et relation début/fin ;
- intervalles optionnels liés à une sélection ;
- capacité cumulative d'une ressource `scratch` ;
- makespan borné par une deadline ;
- précédence simple disponible dans le modèle, sans rôle causal dans le
  contre-exemple actuel.

### Complexity smells

- Le choix statique de cette étape minimise uniquement la durée locale ; cette
  politique est volontairement aveugle au planning et ne doit pas être
  confondue avec un optimiseur statique complet.
- Le contre-exemple ne justifie pas encore un planificateur général ni une
  théorie de séparation des phases.
- La prochaine étape devra éviter de transformer les propriétés observées ici
  en règles procédurales spécifiques à `Fast` ou `Compact`.

## Temporal Planning POC — étape 2 : lifetimes et peak live memory

Cette étape étend le modèle minimal avec des ressources produites, consommées
et dimensionnées. La reproduction reste dans
`experiments/temporal-planning/run.py`, avec CP-SAT `9.15.6755`.

### Convention minimale

Une ressource est live sur l'intervalle semi-ouvert :

```text
[fin du producteur, fin du dernier consommateur)
```

La production doit donc précéder le début de chaque consommation. Le modèle
crée l'intervalle de vie à partir des intervalles d'opérations sélectionnés ;
aucune relation manuelle « A partage avec B » n'est déclarée.

### Confirmed

- `lifetimes_sequential_reuse` produit A puis la consomme, puis produit B et
  la consomme. Avec `size(A)=5`, `size(B)=7` et une capacité mémoire de 7,
  le planning est faisable et le peak vaut 7, pas 12. Les vies observées sont
  respectivement `(1,2)` et `(3,4)`.
- `lifetimes_concurrent_required` impose indirectement le chevauchement par
  une deadline de 2 alors que chaque chaîne producteur-consommateur dure 2.
  Les deux ressources sont vivantes sur `(1,2)` et le peak vaut 12, soit
  `size(A)+size(B)`.
- La mémoire totale construite et le peak live memory sont donc distincts :
  les deux ressources sont toujours produites, mais leur stockage peut être
  réutilisé lorsque leurs lifetimes ne se chevauchent pas.
- Pour les mêmes réalisations et ressources de taille 6, une capacité mémoire
  de 12 autorise le planning rapide avec chevauchement (makespan 2, peak 12),
  tandis qu'une capacité de 6 impose un planning compact séquentiel (makespan
  3, peak 6). Le choix de planning et le peak changent effectivement avec la
  contrainte mémoire ; une deadline de 2 rend le régime rapide nécessaire.
- La réutilisation est une conséquence de la non-coïncidence des intervalles
  de vie et de la contrainte cumulative, non une propriété déclarée entre les
  noms A et B.

### Refuted

- Il est réfuté que le stockage temporaire peak soit nécessairement la somme
  des tailles de toutes les ressources construites.
- Il est réfuté qu'un même ensemble de réalisations ait un peak unique
  indépendant de son planning.

### Uncertain

- Cette étape ne démontre pas encore qu'une réalisation différente devient
  optimale uniquement parce qu'elle permet un meilleur arrangement des
  lifetimes. Les cas construits gardent les mêmes réalisations et font varier
  l'ordonnancement ; l'interaction choix-de-réalisation/lifetime reste à tester.
- La convention d'intervalle est suffisante pour ces cas, mais les lifetimes
  avec plusieurs producteurs, consommateurs conditionnels ou ressources
  réutilisables explicitement nommées ne sont pas étudiés.
- Le modèle ne couvre toujours ni mutation, ni invalidation, ni cache, ni
  incertitude, ni plateforme physique.

### Validation intermédiaire

#### Lifetime

La définition minimale `[production terminée, dernier usage terminé)` suffit
à exprimer les cas séquentiels et concurrents testés.

#### Peak memory

Oui, le calcul dépend du planning : les mêmes ressources ont un peak 12 en
chevauchement et 6 en séquence dans les scénarios de planning.

#### Reuse

Oui. CP-SAT impose seulement la capacité cumulative sur les intervalles de vie;
la possibilité de réutiliser la capacité découle automatiquement de l'absence
de chevauchement.

#### Choice interaction

Non tranché. La variation observée porte sur le planning, pas encore sur une
réalisation alternative sélectionnée pour sa durée de vie.

#### Ontology

Aucun type fondamental `Lifetime` n'a été nécessaire. Une ressource possède une
taille et un intervalle dérivé de ses relations producteur/consommateurs ; le
peak est une propriété du planning résultant.

#### CP-SAT boundary

CP-SAT exprime naturellement les débuts/fins, précédences, intervalles
optionnels et contraintes cumulatives de scratch et de mémoire. Le harnais
calcule extérieurement les lifetimes sélectionnés, le peak rapporté et les
comparaisons entre scénarios. Il ne s'agit pas encore d'un moteur général de
gestion de mémoire.
## Temporal Planning POC — étape 3 : choix de réalisation et lifetimes

Cette étape teste l'interaction entre une intention unique `compute_result`,
deux graphes internes de réalisation et les contraintes temporelles/mémoire.
Elle ajoute uniquement des structures de code locales au harnais :
`CompositeRealization` et `CompositeOperation` ne sont pas promues comme
concepts Atlas.

### Modèle expérimental

- `wide` produit A et B en parallèle puis exécute `wide.combine`, qui consomme
  les deux ressources ;
- `streamed` produit A, exécute une opération qui consomme A et produit B,
  puis consomme B ;
- A et B ont chacune une taille de 6 ;
- le solver CP-SAT contient simultanément `wide` et `streamed`, avec une
  variable de sélection exactement-un ;
- les lifetimes restent `[fin du producteur, fin du dernier consommateur)` et
  sont dérivés des opérations effectivement sélectionnées.

### Confirmed

- Avec `memory=12` et `deadline=2`, CP-SAT sélectionne `wide`, obtient
  `makespan=2`, `peak=12`, et observe A/B vivantes simultanément sur `(1,2)`.
- Avec `memory=6` et une deadline de 10, CP-SAT sélectionne `streamed`, obtient
  `makespan=3`, `peak=6`, avec A sur `(1,2)` puis B sur `(2,3)`.
- Avec `memory=6` et `deadline=2`, le modèle joint est infaisable : `wide`
  dépasse la capacité par ses lifetimes simultanés et `streamed` dépasse la
  deadline.
- Le changement de réalisation est donc provoqué par la structure de
  production/consommation et d'ordonnancement, pas par une taille mémoire
  arbitrairement attachée à `streamed`.
- Le bénéfice mémoire émerge des intervalles de vie dérivés ; aucune relation
  `shares_storage_with`, `reuses` ou préférence mémoire n'est déclarée.
- `wide` et `streamed` sont contextuellement non dominées dans les scénarios
  testés : `wide` gagne sur le makespan quand la mémoire le permet, tandis que
  `streamed` est le seul choix faisable sous la mémoire contrainte.

### Refuted

- `Refuted: realization selection cannot in general be decomposed into
  independent per-intention decisions followed by scheduling.` Le contre-
  exemple `wide`/`streamed` montre qu'une sélection locale peut choisir une
  réalisation dont les lifetimes rendent le plan global infaisable, alors
  qu'une autre réalisation de la même intention est faisable après
  composition temporelle.
- Il est réfuté que la réalisation la plus rapide soit toujours le choix
  global : `wide` devient infaisable sous la capacité mémoire 6.
- Il est réfuté que le modèle doive choisir localement une « stratégie de
  réutilisation » : la réutilisation observée découle du graphe de la
  réalisation sélectionnée et des contraintes cumulatives.
- Il n'est pas démontré qu'une réalisation domine l'autre sur tous les axes :
  les scénarios montrent au contraire un compromis temps/mémoire.

### Uncertain

- Ce cas ne suffit pas à établir une notion générale de dominance ou de front
  de Pareto pour Atlas.
- Les réalisations composites restent décrites manuellement dans le harnais ;
  la découverte automatique de leurs sous-opérations et dépendances n'est pas
  étudiée.
- Les ressources alternatives multiples, les producteurs concurrents, la
  mutation et les lifetimes conditionnels restent hors périmètre.

### Validation intermédiaire

#### Choice interaction

Oui. Une contrainte de mémoire change effectivement la réalisation choisie :
`wide` sous capacité 12, `streamed` sous capacité 6.

#### Emergence

Oui. Le peak inférieur de `streamed` vient de A puis B dans son graphe interne,
et non d'une relation de reuse déclarée.

#### Trade-off

Oui, dans le domaine testé les réalisations ne sont pas globalement ordonnées :
`wide` est plus rapide mais demande 12 de peak ; `streamed` est plus lent mais
reste faisable avec 6.

#### Ontology

Le modèle conceptuel minimal suffit encore. Aucun concept fondamental
`MemoryStrategy`, `LifetimeStrategy`, `ReusePlan` ou `StreamingImplementation`
n'a été nécessaire.

#### CP-SAT boundary

CP-SAT exprime la sélection exactement-un, les opérations optionnelles, les
précédences internes, les intervalles de ressources, le makespan, les
capacités cumulatives et l'infaisabilité. Le harnais calcule extérieurement la
présentation des lifetimes, le peak observé et l'interprétation de dominance ;
ces rapports ne sont pas des contraintes supplémentaires du vocabulaire Atlas.

## Temporal Planning POC — étape 5 : frontière de séparabilité

Cette étape ne construit pas un nouveau graphe. Elle réutilise exactement les
deux intentions X/Y et leurs réalisations `fast`/`compact` de l'étape 4, puis
balaye les capacités mémoire 6 à 12 et les deadlines `None`, 3, 4 et 5.
Chaque ligne compare une baseline qui résout X et Y isolément puis fixe
`fast+fast`, au modèle joint CP-SAT.

`deadline=None` signifie l'absence de contrainte de deadline effective ; le
harnais conserve seulement une borne de domaine CP-SAT égale à 20, supérieure
à tous les plannings de ce modèle.

### Cartographie observée

| mémoire | deadline | baseline locale | modèle joint | classe |
|---:|---:|---|---|---|
| 12 | None | FF, faisable, makespan 3, peak 12 | FF, faisable, makespan 3, peak 12 | Equivalent |
| 8 | None | FF, faisable, makespan 5, peak 6 | CF/FC, faisable, makespan 4, peak 6 | Local feasible but globally suboptimal |
| 12 | 3 | FF, faisable, makespan 3, peak 12 | FF, faisable, makespan 3, peak 12 | Equivalent |
| 8 | 4 | FF, infaisable | CF/FC, faisable, makespan 4, peak 6 | Local infeasible, joint feasible |
| 8 | 3 | infaisable | infaisable | Both infeasible |

Les autres capacités 6–11 reproduisent les mêmes régimes dans cette
structure : sans deadline restrictive, `fast+fast` peut être sérialisé mais
le joint préfère une combinaison mixte plus rapide ; avec deadline 4, la
baseline est infaisable et le joint mixte reste faisable ; avec deadline 3,
les deux sont infaisables. À capacité 12, les deux méthodes convergent sur
`fast+fast` pour toutes les deadlines testées 3–5 et sans deadline.

Chaque ligne est produite sous forme structurée par le harnais avec les champs
`memory`, `deadline`, sélections, statuts, makespans, peaks,
`same_selection` et `same_feasibility`.

### Confirmed

- Il existe une région de convergence où la sélection indépendante et la
  sélection jointe donnent les mêmes réalisations, planning et métriques :
  mémoire 12 dans la grille.
- Une contrainte mémoire seule ne force pas toujours un changement de
  réalisation : sans deadline, la baseline `fast+fast` reste faisable par
  sérialisation pour les capacités 6–11. Elle devient toutefois plus lente que
  le modèle joint, qui choisit une combinaison mixte.
- Une contrainte mémoire peut donc rendre la sélection locale sous-optimale
  même lorsqu'elle ne la rend pas infaisable.
- La combinaison mémoire 8 + deadline 4 produit la divergence forte : la
  baseline `fast+fast` est infaisable, tandis que le joint choisit `compact+fast`
  ou `fast+compact` avec makespan 4 et peak 6.
- La deadline seule, avec mémoire 12, ne change pas le choix dans la grille :
  `fast+fast` reste le meilleur planning pour les deadlines 3–5 ; une deadline
  plus courte que 3 rendrait ce catalogue infaisable plutôt que de favoriser
  `compact`.
- La combinaison mémoire contrainte + deadline serrée crée un troisième
  régime `Both infeasible` : à mémoire 8 et deadline 3, ni la baseline ni le
  modèle joint ne trouve de plan.

### Refuted

- Il est réfuté que toute contrainte mémoire impose nécessairement de rouvrir
  la sélection : la sérialisation suffit dans plusieurs points sans deadline.
- Il est réfuté que la sélection indépendante soit toujours correcte dès lors
  qu'un planning global existe : elle est faisable mais globalement sous-
  optimale sans deadline aux capacités 6–11.
- Il est réfuté qu'une deadline seule change nécessairement la réalisation :
  elle ne le fait pas dans le régime mémoire abondante observé.

### Uncertain

- La frontière est établie uniquement pour deux intentions, deux réalisations,
  une capacité mémoire dure et l'objectif makespan.
- Aucun critère général de séparabilité n'est démontré, et aucune stratégie
  automatique de décomposition n'est implémentée.
- La grille ne couvre pas les graphes conditionnels, les coûts multiples, la
  mutation, les ressources persistantes plus complexes ou la scalabilité du
  solveur.

### Validation intermédiaire

#### Memory only

Sans deadline restrictive, la mémoire peut être absorbée par la sérialisation
de `fast+fast`, mais cette solution est plus lente que la combinaison jointe
mixte pour les capacités 6–11.

#### Deadline only

Avec mémoire 12, les deadlines 3–5 ne changent ni la sélection ni le makespan.
La contrainte temporelle ne crée pas ici de réalisation alternative meilleure.

#### Combined constraints

Mémoire 8 + deadline 4 rend la baseline infaisable mais conserve une solution
jointe mixte ; mémoire 8 + deadline 3 rend les deux méthodes infaisables.

#### Convergence domain

Oui : mémoire 12 fournit un domaine de convergence explicite.

#### Divergence domain

La divergence apparaît lorsque la capacité empêche le chevauchement optimal
de `fast+fast` et que la fenêtre temporelle rend sa sérialisation trop lente,
ou lorsque cette sérialisation dépasse directement la deadline.

#### Minimal explanation

Dans ce modèle, la décomposition est sûre seulement lorsque le planning de la
combinaison localement optimale reste faisable et optimal face aux alternatives.
La mémoire seule peut parfois être absorbée par le scheduling, mais elle peut
aussi révéler une combinaison globale plus rapide ; mémoire et deadline
ensemble peuvent supprimer cette possibilité.

#### Ontology

Aucun nouveau concept Atlas ni aucune relation inter-réalisations n'a été
nécessaire. La décomposabilité est une propriété du problème composé et de ses
contraintes, non un attribut stocké sur une intention ou une réalisation.

#### Solver strategy

Les résultats suggèrent qu'une future implémentation pourrait exploiter les
régions de convergence, mais cette étape n'implémente ni détection de sûreté,
ni décomposition automatique.

#### CP-SAT boundary

CP-SAT décide les sélections, les intervalles, les lifetimes contraints, la
capacité et le makespan. Le harnais produit la grille, calcule les peaks à
partir des lifetimes, compare les deux méthodes et attribue les classes ; ces
classifications restent une analyse expérimentale extérieure au modèle.

## Temporal Planning POC — étape 4 : connaissance disponible dans le temps

Cette étape teste une spécialisation temporelle minimale sans générer de code.
Un fait `P` est représenté par la fenêtre de validité semi-ouverte
`[known_from, valid_until)`. Une préparation optionnelle possède une durée et
une vraie présence dans le planning ; elle doit être placée après
`known_from`, finir avant `valid_until` et précéder tous les appels
spécialisés.

### Modèle

- chaque appel choisit exactement une variante `generic` ou `specialized` ;
- `generic` est utilisable partout et dure 2 unités ;
- `specialized` dure 1 unité mais nécessite la préparation de 3 unités et la
  fenêtre de connaissance ;
- tous les appels et la préparation partagent un worker de capacité 1 ;
- l'objectif est uniquement le makespan ; aucune fonction de gain ou de score
  multi-critères n'est ajoutée.

### Confirmed

- Cas A : six appels doivent être terminés avant la disponibilité de P et deux
  appels seulement sont dans `[14,20)`. CP-SAT choisit zéro spécialisation,
  aucune préparation, et un makespan de 18. La préparation suivie de deux
  appels spécialisés finirait à 19 : elle n'est pas amortie dans ce planning.
- Cas B : six appels sont disponibles dans `[10,30)`. CP-SAT place la
  préparation sur `(10,13)`, spécialise les six appels et obtient un makespan
  de 19, contre 22 pour des appels génériques séquentiels.
- Cas C : quatre appels pouvant se dérouler dans `[10,20)` sont spécialisés,
  avec préparation `(10,13)` et makespan 17. En déplaçant les mêmes appels à
  `[21,30)`, après la fenêtre, aucun n'est spécialisé et le makespan devient
  29.
- La préparation est donc une opération temporelle placée par le modèle, non
  une constante statique détachée des usages concernés.
- La fenêtre temporelle change à la fois la faisabilité de la spécialisation
  et son amortissement. La même décision ne se transfère pas automatiquement
  à des appels déplacés hors de la fenêtre.

### Refuted

- Il est réfuté qu'une connaissance pertinente rende automatiquement tous les
  appels spécialisés : le cas A conserve les appels génériques.
- Il est réfuté que le seul nombre total d'appels suffise à décider : le cas C
  conserve le même nombre d'appels mais change de choix lorsque leur position
  temporelle change.
- Il est réfuté que le coût de préparation puisse être traité uniquement comme
  un coût statique par appel : son placement et son chevauchement avec les
  appels déterminent la rentabilité observée.

### Uncertain

- Le modèle ne couvre qu'un fait, une préparation, un worker et une fenêtre ;
  les connaissances multiples, invalidations, mises à jour et préparations
  concurrentes restent inconnues.
- Le critère de sélection est le makespan, pas une mesure générale de gain
  amorti ou de coût énergétique.
- Aucune génération de code spécialisé ni décision de plateforme n'est
  étudiée.

### Validation intermédiaire

#### Knowledge window

La relation minimale `known_from`/`valid_until` suffit à empêcher l'usage
spécialisé avant disponibilité ou après expiration.

#### Preparation

La préparation est un intervalle réel de durée 3, placé après la disponibilité
de P et avant les appels spécialisés. Son coût est compté une seule fois.

#### Amortization

Deux appels dans la fenêtre ne compensent pas la préparation dans le cas A,
tandis que six appels la compensent dans le cas B.

#### Temporal placement

Le cas C confirme que déplacer les appels hors de la fenêtre supprime la
spécialisation ; déplacer la préparation au début de la fenêtre permet au
contraire l'utilisation spécialisée.

#### Ontology

Aucun nouveau concept fondamental de connaissance temporelle n'a été
nécessaire. La fenêtre, la préparation et les appels restent des propriétés et
opérations locales du modèle temporel.

#### CP-SAT boundary

CP-SAT décide les variantes d'appel, la présence et le placement de la
préparation, les intervalles, l'ordre implicite du worker et le makespan. Le
harnais interprète extérieurement la rentabilité, le nombre d'appels
spécialisés et la signification de la fenêtre ; il ne génère aucun code.

## Temporal Planning POC — étape suivante : recherche bornée de contre-exemples

Cette étape cherche automatiquement des divergences dans une famille
synthétique très petite. Le générateur varie le nombre d'intentions, les deux
alternatives par intention, une profondeur de précédence simple, la capacité et
la deadline. Les alternatives sont des opérations temporaires portant
`duration` et `scratch` ; aucune spécialisation métier n'est ajoutée.

### Oracle et comparaison

Pour chaque sélection, l'oracle énumère les heures de début entières, vérifie
les deadlines, précédences et la capacité, puis conserve le makespan minimal.
Les résultats du modèle CP-SAT joint sont comparés à cet oracle indépendant,
et non seulement à la sortie du même solveur. La baseline choisit localement
la durée minimale puis soumet cette sélection fixe au même scheduler exact.

### Confirmed

- Dans la famille bornée explorée, le premier contre-exemple non trivial
  apparaît à `G=2`, `A=2`, `D=0`, capacité 3, deadline 2.
- Chaque choix local est individuellement faisable, mais la sélection locale
  `fast/fast` est globalement infaisable ; le modèle joint choisit `compact/fast`
  avec makespan 2. L'oracle exact confirme cette faisabilité et ce makespan.
- La divergence apparaît immédiatement au premier nombre non trivial de deux
  intentions après 264 instances valides examinées ; aucune divergence de ce
  type n'est nécessaire avec une seule intention dans la famille filtrée par
  faisabilité individuelle.
- Sur le même motif, capacité 3 sans deadline restrictive rend `fast/fast`
  faisable mais sous-optimal : le local obtient makespan 4 par sérialisation,
  tandis que le joint trouve `fast/compact` en 3.
- Capacité 4 suffit ici à faire converger les méthodes sur `fast/fast` et
  makespan 2. La famille contient donc une région sûre observée.
- Pour le plus petit contre-exemple, le modèle CP-SAT fixé utilise 5 variables
  et 4 contraintes, contre 13 variables et 19 contraintes pour le modèle
  joint : le temps ajoute 8 variables et 15 contraintes dans cette formulation.

### Classification des causes

| structure | séparation sûre observée ? | contre-exemple ? | cause |
|---|---|---|---|
| une intention, alternatives individuelles faisables | oui dans les bornes testées | aucun trouvé | aucune interaction inter-intentions |
| deux intentions, capacité suffisante | oui | non | chevauchement `fast/fast` admissible |
| deux intentions, capacité seule restrictive | parfois | oui, sous-optimalité | sérialisation des lifetimes et makespan global |
| capacité restrictive + deadline | non dans certains points | oui | capacité empêche le chevauchement, deadline empêche la sérialisation |
| précédence simple `D=1` | non généralisé | non requis pour le premier cas | hors cause du contre-exemple minimal |

### Refuted

- Il est réfuté que les divergences exigent une profondeur de dépendance : le
  premier cas utilise `D=0`.
- Il est réfuté que la baseline soit seulement en danger lorsque le problème
  devient grand : une instance à deux intentions et deux alternatives suffit.
- Il est réfuté qu'une contrainte mémoire seule soit toujours absorbée sans
  perte par le scheduler : sans deadline elle peut laisser la baseline
  faisable mais sous-optimale.

### Uncertain

- Le « plus petit » est relatif à la famille, aux valeurs et à l'ordre de
  génération testés ; ce n'est pas une minimalité mathématique universelle.
- La fréquence observée est celle de cette petite famille filtrée, pas une
  probabilité sur des catalogues réels.
- La zone sûre n'est pas un théorème : elle est observée ici lorsque la
  capacité permet le chevauchement de la sélection locale et qu'aucune
  alternative ne réduit davantage le makespan.
- Les dépendances, lifetimes persistants, partages de préparation et la
  croissance au-delà de trois intentions restent à caractériser.

### Validation intermédiaire

#### Minimal counterexample

Le premier cas est `G=2, A=2, D=0, capacity=3, deadline=2` : local `F/F`
infaisable, joint/oracle `C/F`, makespan 2.

#### Frequency

La divergence apparaît dès la première structure à deux intentions capable de
la produire dans la recherche, après 264 instances valides ; elle n'est donc
pas rare dans cette exploration, sans que cela constitue une fréquence
statistique générale.

#### Safe region

Dans les bornes testées, une intention seule est sûre, et deux intentions avec
capacité suffisante pour exécuter simultanément les choix rapides convergent.
Avec capacité restrictive mais sans deadline, le scheduler peut rester
faisable mais la sélection locale n'est plus nécessairement optimale.

#### Model growth

Pour le contre-exemple minimal, la formulation fixée compte 5 variables et 4
contraintes contre 13 variables et 19 contraintes pour le modèle joint. Cette
mesure est locale à la formulation CP-SAT et ne prétend pas décrire la
scalabilité générale.

#### Risk conclusion

`R3` est conditionnel : la décomposition est sûre dans certaines structures
bornées, mais elle est réfutée dès que plusieurs intentions et contraintes
globales font interagir les calendriers. Le résultat n'appelle pas encore une
stratégie automatique de décomposition.

## Temporal Planning POC — étape 4 : composition de plusieurs intentions

Cette étape teste si le choix local de chaque intention peut être figé avant
la composition globale. Deux intentions indépendantes `compute_x` et
`compute_y` possèdent chacune les réalisations `fast` et `compact`, avec des
graphes d'opérations distincts mais des ressources intermédiaires de taille 6.

### Modèle expérimental

- `fast` produit une ressource en 1 unité puis la consomme pendant 2 unités :
  son lifetime local est `(1,3)` et son makespan local est 3 ;
- `compact` ajoute une préparation de 2 unités, puis produit et consomme la
  ressource : son lifetime est `(3,4)` et son makespan local est 4 ;
- les quatre alternatives sont présentes dans un seul modèle CP-SAT, avec
  exactement une réalisation sélectionnée pour chaque intention ;
- les ressources X et Y sont indépendantes et aucune relation de conflit ou de
  partage n'est déclarée entre elles.

### Confirmed

- Résolues isolément avec mémoire abondante, X et Y sélectionnent toutes deux
  `fast` : makespan local 3 contre 4 pour `compact`.
- Avec `memory=8` et `deadline=4`, la baseline qui fixe les deux choix locaux
  à `fast+fast` est infaisable : leurs lifetimes `(1,3)` se chevaucheraient
  avec un peak de 12 ; les séparer rendrait le makespan supérieur à 4.
- Dans le même modèle joint, CP-SAT sélectionne une combinaison mixte
  `compact+fast` (ou l'équivalent symétrique), avec makespan 4 et peak 6.
- Avec `memory=12` et `deadline=3`, CP-SAT sélectionne `fast+fast`, avec
  makespan 3 et peak 12. Le choix rapide n'est donc pas intrinsèquement
  mauvais ; il devient incompatible avec un contexte global contraint.
- Le peak est calculé après résolution depuis les lifetimes observés, en plus
  de la contrainte cumulative utilisée par CP-SAT.
- La différence entre les choix globaux provient uniquement des opérations,
  précédences, lifetimes et capacité mémoire sélectionnés ; aucune règle
  `fast+fast` interdite ou préférence de combinaison n'est codée.

### Refuted

- Il est réfuté qu'il suffise, en général, de sélectionner indépendamment la
  meilleure réalisation de chaque intention puis de scheduler le résultat.
- Il est réfuté qu'une réalisation possède un rang de préférence global
  indépendant des autres réalisations : `fast` est optimal localement pour X et
  Y, mais `fast+fast` est infaisable sous la contrainte globale testée.

### Uncertain

- La démonstration porte sur deux intentions, deux réalisations par intention,
  une mémoire dure et un objectif makespan ; elle ne mesure pas la scalabilité.
- Les interactions sont dérivées pour ce graphe, mais le harnais ne découvre
  pas automatiquement les sous-opérations ou les combinaisons de réalisations.
- Aucun graphe conditionnel complexe, aucune mutation, estimation,
  invalidation ou autre ressource de plateforme n'est couvert.
- Ce cas ne justifie ni une recherche Pareto générale ni une hiérarchie de
  sélection/scheduling.

### Validation intermédiaire

#### Local optimality

Oui. Chaque intention isolée sélectionne `fast` sur le critère makespan.

#### Global composition

Oui. Les deux choix locaux `fast+fast` deviennent incompatibles avec
`memory=8` et `deadline=4`.

#### Joint selection

Oui. Le modèle joint trouve une combinaison mixte faisable, sans que son
orientation X/Y soit imposée lorsque les deux sont symétriques.

#### Context dependence

Oui. Lorsque la mémoire est portée à 12 et la deadline à 3, `fast+fast` est de
nouveau sélectionné.

#### Emergence

Oui. L'interaction X/Y résulte uniquement du chevauchement des lifetimes et de
la capacité cumulative ; aucune relation inter-réalisations n'est introduite.

#### Ontology

Aucune relation explicite entre réalisations n'a été nécessaire. Les
interactions restent des propriétés émergentes de la composition.

#### CP-SAT boundary

CP-SAT décide les réalisations, les opérations optionnelles, les précédences,
les intervalles de vie, la capacité et le makespan. Le harnais calcule
extérieurement le peak observé, compare la baseline aux choix joints et
interprète la dépendance au contexte ; ces interprétations ne sont pas des
concepts supplémentaires du modèle Atlas.

## Temporal Planning POC — 4.5 : validation intermédiaire finale

Cette section consolide uniquement les expériences déjà exécutées dans les
étapes 1 à 4 et la recherche bornée de contre-exemples. Elle ne constitue pas
le verdict final du protocole et ne lance pas les surprise tests 4.6.

### Temporal representation

Dans le périmètre testé, le noyau minimal de descriptions et de
relations/faits a été suffisant pour porter les informations temporelles
nécessaires, sans introduire de nouvelle ontologie temporelle :

- les durées et les relations début/fin sont des données des opérations et des
  variables temporelles du modèle ;
- l'ordre producteur-consommateur est exprimé par des précédences ;
- la disponibilité des appels est représentée localement par leurs bornes de
  release/deadline dans `step4_specialization.py` ;
- les lifetimes sont dérivés des opérations sélectionnées, selon la convention
  `[fin du producteur, fin du dernier consommateur)` ;
- la validité temporelle de la spécialisation est représentée par la fenêtre
  locale `known_from`/`valid_until`.

Il faut distinguer ce résultat de l'existence d'une primitive Atlas générale :
`ResourceSpec`, `CompositeOperation`, `Call` et `KnowledgeWindow` sont des
structures du harnais Python. Le code démontre l'expressibilité opérationnelle
de ces cas, pas une représentation persistante de toute temporalité. Une
primitive Atlas de fait temporel ou d'intervalle reste seulement une
possibilité non démontrée.

### Joint optimization

Les résultats ne disent pas que le modèle joint est toujours meilleur. Ils
établissent trois régimes distincts :

- une région de convergence : avec mémoire 12, `fast+fast` est faisable et
  optimal dans la grille, et les deux méthodes produisent le même makespan ;
- une séparation faisable mais sous-optimale : avec mémoire 6 à 11 sans
  deadline restrictive, `fast+fast` peut être sérialisé, mais le modèle joint
  trouve une combinaison mixte plus rapide (`makespan=5` contre `4` à mémoire
  8) ;
- une séparation qui perd la faisabilité : avec mémoire 8 et deadline 4, la
  baseline fixée à `fast+fast` est infaisable alors que le joint trouve une
  combinaison mixte faisable ; avec mémoire 8 et deadline 3, les deux sont
  infaisables.

La recherche bornée fournit un contre-exemple indépendant du solveur : dans la
famille explorée, `G=2, A=2, D=0, capacity=3, deadline=2` donne une baseline
`fast/fast` infaisable et un optimum joint `compact/fast` de makespan 2,
confirmé par l'oracle exact. Elle confirme aussi un cas faisable mais
globalement sous-optimal sans deadline. À l'inverse, une intention seule et
une capacité suffisante dans la famille testée ne produisent pas cette
divergence.

La conclusion établie est donc conditionnelle : la sélection puis le
scheduling peuvent se séparer dans certaines régions, mais ne constituent pas
une décomposition sûre en général. Les limites sont la petite famille
synthétique, le temps entier discret, deux intentions dans les tests de
composition, une capacité principalement mémoire et l'objectif makespan.

### Peak resources

Oui, dans les scénarios exécutés, le peak dépend des lifetimes et du planning,
et non de la simple somme des ressources construites.

- Dans le cas séquentiel, A et B ont des tailles 5 et 7 : la mémoire totale
  construite vaut 12, mais leurs lifetimes `(1,2)` et `(3,4)` ne se chevauchent
  pas et le peak vaut 7.
- Dans le cas concurrent, les mêmes tailles sont vivantes ensemble et le peak
  vaut 12.
- Avec les mêmes réalisations et deux ressources de taille 6, le planning
  autorisé par une capacité 12 a un peak 12, alors que la capacité 6 impose un
  arrangement séquentiel de peak 6 et de makespan supérieur.

La capacité cumulative est la contrainte du modèle ; le peak est recalculé par
le harnais à partir des intervalles effectivement produits. La réutilisation de
capacité n'est pas une règle métier : elle résulte du non-chevauchement des
lives. Il faut donc distinguer mémoire totale construite, peak live memory,
capacité cumulative disponible et réutilisation issue du scheduling.

### Knowledge lifetime

Oui, dans le périmètre du cas spécialisé, une fenêtre équivalente à
`known_from(P, t1)` / `valid_until(P, t2)` suffit. La préparation ne peut
commencer avant `known_from`, doit finir avant `valid_until`, et les appels
spécialisés doivent être placés dans cette fenêtre après la préparation.
Le cas C montre qu'un déplacement des mêmes appels hors de la fenêtre supprime
la spécialisation.

Ce résultat ne couvre qu'un fait, une fenêtre et une préparation. Il ne valide
pas une sémantique d'invalidation, de mutation, de mise à jour ou de plusieurs
faits concurrents.

### Specialization economics

Le modèle arbitre effectivement entre préparation et travail évité, en tenant
compte des appels réellement situés dans la fenêtre :

- dans A, six appels sont antérieurs à la connaissance et deux seulement sont
  dans `[14,20)`. La préparation de durée 3 ne compense pas deux appels plus
  courts ; aucun appel n'est spécialisé et le makespan est 18 ;
- dans B, six appels sont disponibles dans `[10,30)`. La préparation `(10,13)`
  est exécutée une fois, les six appels sont spécialisés et le makespan est 19
  (contre 22 pour six appels génériques séquentiels dans ce modèle) ;
- dans C, les quatre mêmes appels placés dans `[10,20)` sont spécialisés
  (makespan 17), tandis que les quatre appels déplacés à `[21,30)` restent
  génériques (makespan 29).

Le cas C est important : le nombre d'appels ne change pas, seule leur position
temporelle change. La décision ne dépend donc pas seulement d'un compteur
d'usages, mais de leur admissibilité et de leur placement dans la fenêtre.

### Solver formulation

CP-SAT reste naturel pour les primitives effectivement expérimentées :
intervalles optionnels, choix exactement-un, précédences, bornes de début/fin,
contraintes cumulatives, présence conditionnelle de la préparation, fenêtre de
validité et objectif de makespan.

La mesure disponible suggère une croissance locale mais quantifie seulement
la formulation testée : pour le plus petit contre-exemple, le modèle fixé
compte 5 variables et 4 contraintes, contre 13 variables et 19 contraintes
pour le modèle joint. Cela montre ce que le choix simultané ajoute dans cette
instance ; ce n'est pas une conclusion de scalabilité générale.

Il faut aussi séparer les responsabilités : CP-SAT porte les décisions et
contraintes ; le harnais dérive les lifetimes, calcule les peaks, construit la
grille, énumère l'oracle exact et classe les écarts ; `knowledge.md` donne
l'interprétation conceptuelle. Le solver ne porte pas à lui seul la
signification Atlas de ces résultats.

### Boundary

Les limites suivantes restent non testées ou artificiellement simplifiées ;
elles ne sont pas des défauts démontrés :

- multiplicité et interaction de faits temporels, invalidation, mutation et
  mise à jour ;
- ressources persistantes complexes, plusieurs producteurs ou consommateurs
  conditionnels, et partage explicite entre plans ;
- coûts multiples, objectifs autres que le makespan et compromis
  temps/mémoire plus riches ;
- plateformes physiques, allocation réelle, cache, bande passante et
  concurrence système ;
- incertitude, acquisition d'information et décisions sur des observations ;
- temps continu, durées non entières et sémantiques d'arrondi ;
- croissance du modèle, heuristiques de décomposition, grandes instances et
  scalabilité CP-SAT ;
- génération réelle de code spécialisé et exécution de la spécialisation.

Le harnais reste en outre limité par ses dataclasses locales, son hypothèse
d'un worker unique dans l'expérience de spécialisation, son horizon entier
borné à 20 lorsque la deadline est absente dans la grille, et son oracle
exhaustif réservé à de très petites instances.

### Confirmed — consolidation

- Les durées, débuts/fins, contraintes de capacité, lifetimes dérivés et
  fenêtres temporelles testées peuvent être exprimés dans le modèle local sans
  prolifération de concepts métier.
- Le peak live memory dépend des lifetimes et du scheduling ; il n'est pas la
  somme obligatoire des ressources construites.
- La sélection indépendante peut converger, être faisable mais sous-optimale,
  ou perdre la faisabilité selon les contraintes globales.
- Une fenêtre `known_from`/`valid_until` et une préparation temporisée suffisent
  dans le cas testé pour situer économiquement une spécialisation.
- CP-SAT et un oracle discret indépendant concordent sur les petits cas
  vérifiés ; la formulation jointe reste lisible et compacte à cette échelle.

### Refuted — consolidation

- La sélection indépendante des réalisations suivie du scheduling est toujours
  sûre ou optimale.
- Le peak mémoire est nécessairement égal à la somme des tailles construites.
- Une connaissance disponible rend automatiquement tous les appels
  spécialisés.
- Le seul nombre total d'appels suffit à décider de la spécialisation.

### Uncertain — consolidation

- Un critère général permettant de reconnaître à l'avance les régions où la
  sélection et le scheduling sont séparables.
- La suffisance d'un noyau temporel analogue sur des faits multiples, des
  mutations, des plateformes physiques ou des temps continus.
- La scalabilité de la formulation jointe et la fréquence des divergences sur
  des catalogues réels.
- Une économie générale de spécialisation au-delà du makespan et d'une fenêtre
  unique.
- La génération et la validation de code spécialisé réel.

### Temporal kernel — inventaire consolidé

| Primitive | Rôle dans les expériences |
|---|---|
| durée | donnée conceptuelle locale et paramètre des intervalles |
| début / fin | variables de décision CP-SAT |
| précédence | contrainte temporelle CP-SAT entre opérations |
| intervalle optionnel lié à un choix | variable/structure de décision du solver |
| capacité cumulative | contrainte CP-SAT de ressource limitée |
| release / deadline / fenêtre de validité | faits locaux convertis en bornes de décision |
| lifetime d'une ressource | intervalle dérivé du planning et des producteurs/consommateurs |
| peak live memory | mesure dérivée du planning, également bornée par la capacité |
| présence de préparation | variable booléenne de décision CP-SAT |
| makespan | variable/objective CP-SAT et mesure dérivée du planning |

Cette liste ne constitue pas encore un schéma ontologique : en particulier,
le lifetime et le peak sont actuellement dérivés dans le harnais, tandis que
`known_from`/`valid_until` sont des faits de scénario locaux.

### Complexity smells

- les structures `LifecycleScenario`, `CompositeRealization`, `Call` et
  `KnowledgeWindow` sont des conventions ad hoc du harnais, non une API Atlas ;
- les temps sont entiers et le domaine sans deadline repose sur un horizon
  artificiel de 20 dans la grille ;
- la spécialisation suppose un seul worker et une capacité unitaire ;
- les scénarios limitent les producteurs/consommateurs et les formes de
  dépendances, sans mutation ni invalidation ;
- le peak est calculé hors solver selon la même convention d'intervalles, ce
  qui impose de maintenir cohérents modèle et instrumentation ;
- l'oracle par énumération est exact mais ne passe à l'échelle que sur les
  petites bornes ;
- l'objectif unique de makespan masque les coûts et préférences possibles ;
- les égalités et symétries du modèle peuvent laisser plusieurs plans
  équivalents, sans règle d'identification générale.

Ces points sont des risques de modélisation à surveiller, pas des résultats
réfutés par les expériences actuelles.

## Temporal Planning POC — 4.6 : surprise tests de clôture

Cette section ajoute uniquement les trois variations de clôture exécutées dans
`experiments/temporal-planning/step4_6_surprises.py`. Elle ne constitue pas
encore le verdict final du protocole.

### Tests et résultats

#### Préparation lente réutilisée longtemps

Le modèle existant est utilisé sans extension : une préparation de durée 25,
connue à 10 et valide jusqu'à 100, sert 12 appels spécialisés de durée 1.
Le solver place la préparation sur `(10,35)`, spécialise les 12 appels et
obtient `makespan=47`. La préparation lente devient donc rentable lorsque le
nombre d'utilisations situées dans une fenêtre suffisamment longue amortit son
coût.

#### Deux faits à fenêtres partiellement chevauchantes

Un appel nécessite simultanément `P` et `Q`. `P` est connu à 4 et valide
jusqu'à 18 ; `Q` est connu à 10 et valide jusqu'à 24. Le test produit deux
préparations distinctes, `P=(4,7)` et `Q=(10,13)`, puis spécialise l'appel et
termine à 14.

Le `SpecializationScenario` antérieur ne pouvait pas représenter cette
conjonction : il ne portait qu'une fenêtre et une préparation. Le nouveau
script emploie donc une structure locale générique `FactWindow`/`FactCall` et
des contraintes CP-SAT composées ; aucune branche ne connaît le nom du test.
Cette nécessité est expérimentale et locale, pas une promotion automatique de
ces classes en primitives Atlas.

#### Variante rapide à peak mémoire supérieur

Une variante spécialisée dure 1 et demande un peak de 6 ; la variante
générique dure 4 et demande 1. Sous capacité 6, la variante rapide est choisie.
Sous capacité 5, elle n'est plus admissible et la variante générique est
choisie. Le choix de spécialisation reste donc intégré à la faisabilité
temporelle et mémoire plutôt qu'à une préférence procédurale.

### Confirmed

- Une préparation beaucoup plus lente peut rester admissible et optimale
  lorsqu'elle est réutilisée assez longtemps dans sa fenêtre ; le modèle
  existant exprime ce cas naturellement.
- Plusieurs fenêtres peuvent être composées comme contraintes distinctes :
  l'appel spécialisé doit satisfaire chaque fenêtre et attendre chaque
  préparation requise. Le cas partiellement chevauchant est faisable sans
  fusionner les faits.
- Le choix entre variante rapide et variante plus économe en mémoire peut être
  effectué par le même principe de sélection sous capacité : sous capacité 6
  la variante rapide gagne, sous capacité 5 elle est éliminée.
- Les trois assertions de surprise et les régressions des étapes précédentes
  sont reproductibles avec CP-SAT `9.15.6755`.

### Refuted

- Il est réfuté qu'une préparation lente soit automatiquement exclue : sa
  rentabilité dépend du nombre et du placement des usages dans la fenêtre.
- Il est réfuté qu'une spécialisation plus rapide soit toujours admissible ou
  préférable indépendamment du peak mémoire.
- Il n'est pas réfuté que le noyau existant puisse exprimer directement deux
  faits : ce test montre au contraire que la classe de scénario précédente ne
  le permettait pas sans structure locale supplémentaire.

### Uncertain

- La combinaison de fenêtres multiples avec invalidation, renouvellement ou
  faits contradictoires n'est pas testée.
- La mémoire de la variante est ici une demande de capacité locale ; le test ne
  couvre pas des lifetimes persistants complexes ni le partage de ressources
  entre plusieurs intentions.
- Les tests ne déterminent pas si `FactWindow`, une relation temporelle plus
  générale ou une autre représentation serait la bonne primitive Atlas.

### Temporal kernel

Les primitives déjà présentes restent suffisantes pour le premier surprise
test. Les deux autres imposent seulement, dans le harnais de test, deux
extensions locales :

- une collection de fenêtres/faits et une relation « cet appel requiert ces
  faits » ;
- une demande mémoire attachée à une variante et une capacité cumulative.

La première extension est une information de scénario composée ; la seconde
est une contrainte de planification. Leur nécessité est démontrée pour
exprimer ces tests, mais aucune n'est encore promue au noyau Atlas.

### Complexity smells

- le modèle historique à une seule `KnowledgeWindow` masque la limite révélée
  par la conjonction de faits ;
- les deux faits du test sont préparés chacun une fois et partagent un worker
  unitaire, sans politique de réutilisation ou de concurrence plus riche ;
- le compromis mémoire de la surprise est une variante unique, non un graphe
  de lifetimes multi-ressources ;
- les temps restent entiers et les résultats optimisent uniquement le
  makespan ;
- les nouvelles structures sont locales au script et pourraient diverger du
  modèle précédent si elles étaient étendues sans validation croisée.

## Temporal Planning POC — verdict final

Ce verdict clôt le protocole sur les expériences déjà exécutées, y compris les
surprise tests 4.6. Aucun nouveau scénario ni modèle expérimental n'est ajouté
ici.

### `temporal_separation_safe_in_tested_scope` — `not_supported`

La sécurité de la séparation n'est pas établie dans le périmètre testé. Les
contre-exemples sont minimaux et indépendamment vérifiés :

- dans `wide`/`streamed`, le choix local rapide devient infaisable sous
  mémoire 6 et deadline 2 alors que l'alternative streamée reste représentable
  dans un autre régime ;
- dans le modèle X/Y, `fast+fast` est faisable mais sous-optimal sous mémoire
  restrictive sans deadline ;
- avec mémoire 8 et deadline 4, la sélection locale perd la faisabilité alors
  que le modèle joint trouve une combinaison mixte ;
- la recherche bornée et son oracle exact reproduisent ce phénomène dès deux
  intentions et deux alternatives.

Il existe toutefois des régions de convergence : mémoire abondante, une
intention dans la famille bornée, ou capacité suffisante pour le chevauchement
des choix rapides. Cela interdit la conclusion inverse « tout doit toujours
être joint » ; cela ne suffit pas à soutenir la sûreté générale de la
séparation.

### `joint_optimization_required` — `supported`

Le choix de réalisation et le planning doivent être optimisés ensemble dans
certains cas testés. La preuve minimale est la comparaison
`select_then_schedule` / `joint_select_and_schedule`, confirmée par l'oracle
discret indépendant : le joint récupère soit la faisabilité sous une deadline,
soit un meilleur makespan à capacité identique.

Ce verdict est existentiel et conditionnel, non universel : les mêmes
expériences montrent des régimes où les deux méthodes convergent.

### `lifetime_model_supported` — `supported`

Le modèle de lifetime est suffisant dans le périmètre étudié. Les ressources
sont live sur `[fin du producteur, fin du dernier consommateur)`, la capacité
cumulative porte sur ces intervalles et le peak est recalculé à partir du
planning. Les cas séquentiel et concurrent donnent respectivement peak 7 et
12 pour des ressources de tailles 5 et 7 ; les ressources non chevauchantes
réutilisent donc la capacité.

Le test de surprise mémoire ne change pas ce verdict : il attache une demande
de capacité à une variante pendant son exécution. Il ne constitue pas un
nouveau cas de lifetime persistant.

### `temporal_knowledge_supported` — `supported`

Une connaissance qui apparaît et reste valide pendant une fenêtre peut devenir
une ressource d'optimisation située dans le temps. La préparation est une
opération réelle du planning, placée après `known_from` et avant les appels
spécialisés, avec une fin avant `valid_until`.

Les cas A/B/C montrent séparément admissibilité, rentabilité et placement :
deux appels dans la fenêtre ne justifient pas la préparation, six appels la
justifient, et les mêmes quatre appels changent de décision lorsqu'ils sont
déplacés hors de la fenêtre. Le surprise test de préparation 25 réutilisée par
12 appels confirme que le coût initial peut être amorti sur une longue
réutilisation. Le test à deux faits montre qu'une spécialisation peut exiger
deux fenêtres et deux préparations distinctes ; cette généralisation est
représentée localement par `FactWindow`/`FactCall`.

Ce résultat ne couvre ni invalidation, ni mutation, ni plusieurs versions d'un
même fait.

### `temporal_kernel_incomplete` — `not_supported`

Aucune primitive Atlas temporelle manquante n'est démontrée par ces tests. La
classe historique `SpecializationScenario` ne représentait qu'une fenêtre,
mais cette limitation de dataclass a été contournée dans le surprise test par
une représentation locale de plusieurs faits et relations de dépendance. Le
noyau conceptuel `Description + relations/faits` peut donc exprimer ce besoin
sans imposer un type fondamental `KnowledgeWindow`, `FactWindow` ou `Lifetime`.

Cela ne prouve pas que le noyau est complet en général : les extensions
temporelles plus riches restent dans les limites et inconnues ci-dessous. Le
verdict signifie seulement qu'une insuffisance conceptuelle n'a pas été
établie dans le périmètre expérimental.

### `solver_model_mismatch` — `not_supported`

Le modèle CP-SAT reste cohérent avec les expériences : intervalles optionnels,
choix exactement-un, précédences, fenêtres, capacité cumulative et makespan
sont exprimés directement. Les résultats du petit modèle joint concordent
avec l'oracle exact ; les surprise tests réutilisent les mêmes primitives.

La comparaison 5 variables/4 contraintes contre 13 variables/19 contraintes
montre un accroissement local de la formulation, pas une erreur ou une
artificialité avérée. Elle ne permet en revanche aucune affirmation de
scalabilité.

### Réponses scientifiques

#### Le temps est-il ajouté après la sélection ?

Non, pas toujours. Dans les cas où capacité, chevauchement, lifetimes et
deadline interagissent, le temps fait partie des informations nécessaires pour
déterminer quelle réalisation doit exister : une sélection locale peut devenir
infaisable ou sous-optimale après planification. Mais le temps ne force pas
toujours une optimisation jointe : les régions de convergence montrent que la
séparation reste suffisante dans certains régimes. La formulation exacte est
donc : le planning est parfois une dimension constitutive du choix, pas une
phase universellement postérieure ni universellement inséparable.

#### Une connaissance temporairement stable est-elle une ressource ?

Oui, dans le modèle testé. Une connaissance valide est une condition
d'admissibilité pour une spécialisation et sa fenêtre fournit également la
zone où une préparation peut être amortie. La décision dépend de la durée de
préparation, du placement et du nombre d'usages réellement situés dans la
fenêtre ; elle ressemble donc, dans ce périmètre, à une ressource temporelle
conditionnant les choix au même titre qu'une capacité mémoire ou une
représentation disponible.

Cette analogie reste limitée : aucune invalidation, propagation de versions,
acquisition de connaissance ou plateforme réelle n'a été modélisée.

### Temporal kernel final

| Notion | Classe dans ce POC |
|---|---|
| durée d'une opération | information/fait local ; paramètre d'intervalle |
| release, deadline, `known_from`, `valid_until` | information/fait de scénario |
| dépendance producteur-consommateur / précédence | contrainte temporelle |
| début et fin | décision de planning |
| choix exactement-un d'une réalisation/variante | décision de planning |
| intervalle optionnel | décision de planning |
| capacité cumulative scratch/mémoire | contrainte de ressources |
| présence et placement d'une préparation | décision de planning |
| lifetime d'une ressource | propriété dérivée de la solution |
| peak live memory | propriété dérivée de la solution |
| makespan | propriété dérivée et objectif du planning |
| relation « appel requiert ces faits » | fait/relation de scénario, testée localement |

Cette classification ne promeut pas automatiquement les dataclasses du harnais
en types Atlas fondamentaux.

### Boundary finale

Restent hors démonstration :

- mutation, invalidation et renouvellement des connaissances ;
- plusieurs producteurs ou consommateurs conditionnels et lifetimes plus
  complexes ;
- temps non entier, temps continu et règles d'arrondi ;
- plateformes physiques, cache, bande passante et concurrence système ;
- coûts multiples, objectifs multiples et compromis autres que makespan,
  mémoire et durée ;
- scalabilité du modèle joint et de l'oracle ;
- génération puis exécution de code spécialisé réel.

Ces points sont des frontières du résultat, non des réfutations supplémentaires.

### Conclusion scientifique

Le POC démontre que les lifetimes, le peak et une connaissance temporellement
valide peuvent participer naturellement à une décision jointe de planning. Il
réfute la sûreté générale de « choisir indépendamment puis planifier », ainsi
que l'assimilation du peak à la somme des ressources construites. Il ne permet
pas encore d'affirmer une ontologie temporelle complète, une règle générale de
séparabilité, une scalabilité CP-SAT ou une génération de spécialisation
réelle.
