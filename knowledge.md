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
