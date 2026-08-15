# Core V1 — C0 Conformance contract

## Statut

Ce répertoire définit la frontière black-box de la future suite de conformité
Core V1. Il ne contient pas encore d’implémentation, de backend SQLite ni de
tests exécutables.

La suite testera les comportements observables du profil
[`docs/core-v1-profile.md`](../docs/core-v1-profile.md), indépendamment des
classes internes, des dataclasses, du schéma SQLite, des indexes SQL et de la
forme du graphe mémoire.

Les identifiants d’opérations ci-dessous sont des noms de façade proposés pour
C0. Ils ne constituent pas encore une API Python ou une API Atlas définitive.

## 1. Trois couches

### Test fixture

Une fixture JSON versionnée fournit des données déclaratives : vocabulaire,
descriptions, assertions, règles, coûts, contexte, provenance et mutations de
snapshot. Elle ne contient ni requête SQL ni objet Python.

### Observable result

L’implémentation expose des résultats sémantiques sérialisables et inspectables.
Les tests ne déduisent pas ces résultats en regardant l’état interne.

### Test adapter

L’adapter traduit entre ce contrat et l’API concrète du core. Il peut ouvrir un
store Python, SQLite ou autre, mais ne contient aucune logique métier Atlas : il
ne calcule ni `covers`, ni le grounding, ni le coût optimal.

## 2. Façade black-box minimale

La façade proposée expose conceptuellement :

```text
open_store(config) -> StoreHandle
admit(batch) -> AdmissionResult
snapshot() -> SnapshotId
open_snapshot(snapshot_id) -> SnapshotHandle
find(pattern, snapshot, context) -> ObservationSet
ground(rule_id, bindings, snapshot, context) -> GroundingResult
build_decision_problem(intent, snapshot, context) -> GroundedDecisionProblem
solve(problem) -> DecisionResult
coverage_proof(problem_or_grounding) -> CoverageProof
explanation(decision_or_conclusion) -> Explanation
provenance(knowledge_id, snapshot) -> ProvenanceGraph
dependencies(knowledge_id, transitive=true) -> DependencyGraph
supersede(old_id, replacement) -> AdmissionResult
status(knowledge_id, snapshot) -> StatusResult
close_store() -> None
reopen_store(config) -> StoreHandle
```

`ground` doit exposer séparément :

1. la vérité locale `TRUE | FALSE | UNKNOWN` ;
2. une conclusion groundée éventuelle contenant terme relationnel, polarité,
   statut épistémique, scope, provenance et dépendances.

Une évaluation `FALSE` ne devient jamais une assertion négative. Une absence de
faits peut produire `UNKNOWN` avec un grounding complet ; elle n’est pas une
erreur structurelle.

Les catégories de statut ne sont pas fusionnées :

```text
truth: TRUE | FALSE | UNKNOWN
epistemic: exact | bound | estimate | unknown
record: active | superseded | stale | isolated
grounding: complete_for_declared_scope | incomplete | invalid
solver: solved | infeasible | invalid_problem | unknown
```

Les noms sont indicatifs, mais les distinctions sont contractuelles. Un input
malformé est rejeté ; une référence structurelle pendante est une erreur de
grounding ; une information absente dans un scope entièrement parcouru est
`UNKNOWN`.

## 3. Fixture JSON

JSON suffit pour C0. Le format est déclaratif et propre à cette fixture Core V1,
pas un format Atlas universel. La racine porte :

```text
schema: atlas.conformance.core-v1/1
fixture_id: m1-coverage
vocabulary: [...] 
descriptions: [...]
facts: [...]
relations: [...]
rules: [...]
contexts: [...]
snapshots: [...]
```

Chaque connaissance admise doit avoir une identité, une portée, un statut
épistémique et une provenance directe. Les assertions de propriété M1 sont
unaires et ciblent une `DescriptionId`, sans prétendre limiter le concept Atlas
général de `Fact`.

Les valeurs de la fixture utilisent seulement les formes Core V1 :
`symbol`, `integer`, `finite_set<symbol>` et `sequence<symbol>`. Une entrée
`finite_set<symbol>` contenant des doublons est invalide et doit être rejetée à
la frontière, non canonicalisée silencieusement.

La section `supersession` est une mutation déclarative utilisée par M1e. Elle
ne réécrit pas le snapshot antérieur. Dans la forme compacte de cette fixture,
`replaces` désigne le record source. Un nouveau Knowledge record est créé en
conservant à l’identique tous ses champs structurels — notamment `kind`,
`description`, `property`, `scope`, `epistemic_status` et `provenance` — tandis
que seuls `id` et `value` sont remplacés par `replacement_id` et
`replacement_value`. Le record remplacé n’est jamais muté : le nouveau record
possède une identité distincte et le supersède dans le snapshot ultérieur, alors
que le snapshot historique conserve l’ancien record actif relativement à son
état historique. Cette syntaxe compacte est un choix de la fixture C0/M1 ; elle
ne définit pas une sémantique générale Atlas de la supersession et ne constitue
pas un mécanisme de patch générique pour d’autres types de records.

## 4. Résultats observables

### Grounded relation

```text
{
  term: { predicate, participants: [...] },
  polarity: positive | negative,
  truth: TRUE | FALSE | UNKNOWN,
  epistemic_status: exact | bound | estimate | unknown,
  scope: ..., provenance: [...], dependencies: [...]
}
```

`term` est distinct de l’assertion persistable. `truth` est distinct de la
polarité et du statut épistémique.

### Coverage proof

```text
{
  snapshot, context, manifest_version,
  rule_version, vocabulary_versions,
  categories: [{
    category, query, parameters,
    searched: true,
    found_ids: [...], included_ids: [...], excluded: [{id, reason}]
  }],
  derived_dependencies: [{id, transitive_ids: [...], traversal: ...}],
  grounding_status: complete_for_declared_scope | incomplete | invalid
}
```

Chaque catégorie prescrite doit apparaître, y compris une recherche sans
résultat. Une exclusion par contexte est visible et cite le fait ou la règle
qui la justifie. Une catégorie absente, un parcours interrompu, une borne ou un
pruning heuristique rendent la preuve incomplète.

### Decision result

```text
{
  problem: {intent, snapshot, context, scope, manifest_version},
  selected: [...],
  co_optimal: [...],
  objective: {name: exact_cost, optimum: integer},
  solver_status: solved | infeasible | ...,
  grounding_status: complete_for_declared_scope | incomplete | invalid,
  explanation_id: ...
}
```

`optimal + complete_for_declared_scope` qualifie uniquement le problème M1
effectivement construit, jamais le Knowledge Store mondial.

## 5. Groupes de conformité

### IDENTITY / VALUES

- identité nominale malgré des contenus identiques ;
- absence de fusion structurelle ;
- rejet de `bool`/`int` et des coercions hôte ;
- ordre des séquences ;
- rejet des doublons d’un ensemble fini ;
- relations multivaluées.

### STORE / VOCABULARY

- rejet atomique d’un batch invalide ;
- record persistant invalide isolé à la lecture ;
- référence structurelle non résolue rejetée ;
- propriété valide mais inutilisée acceptée ;
- provenance récupérable ;
- dépendances dérivées récupérables.

### RULE / GROUNDING

- mismatch de participant ;
- absence de fallback inter-participants ;
- information absente donnant `UNKNOWN` ;
- `FALSE` ne créant pas d’assertion négative ;
- assertion négative explicite distincte ;
- conclusion groundée conservant prédicat et participants ;
- dépendances effectives de la dérivation ;
- faits valides non liés absents de l’explication décisive.

### COVERAGE

- chaque catégorie du manifeste est effectivement parcourue ;
- une recherche sans résultat reste enregistrée ;
- catégorie omise => pas de `complete_for_declared_scope` ;
- interruption ou pruning => pas de `complete_for_declared_scope` ;
- référence pendante => pas de `complete_for_declared_scope` ;
- `UNKNOWN` compatible avec un grounding complet ;
- exclusion contextuelle observable et justifiée.

### DECISION

- candidat moins cher mais inadmissible non sélectionné ;
- candidats admissibles de coût égal tous retournés ;
- statut du solveur distinct du statut de grounding ;
- optimum explicitement local au Grounded Decision Problem.

### PERSISTENCE

- restart conservant IDs, scopes et `ContextId` ;
- snapshot historique reproductible ;
- supersession créant un état ultérieur sans réécrire l’ancien ;
- ancienne dérivation stale uniquement dans le snapshot ultérieur.

### EXPLANATION

- résultat sélectionné relié à sa dérivation et sa provenance ;
- rejet accompagné d’une raison structurée ;
- fait inutilisé absent de l’explication décisive.

## 6. Fixture canonique M1

`fixtures/m1-coverage.json` est la fixture unique utilisée progressivement par
M1a à M1e. Elle contient :

- une intention ;
- une request ;
- deux réalisations candidates ;
- `realizes` pour les deux candidats ;
- un candidat moins cher mais non couvrant ;
- un candidat plus cher et couvrant ;
- `coverage:v1` ;
- les propriétés participant-scoped nécessaires et un fait valide inutilisé ;
- des coûts entiers exacts ;
- une provenance directe pour chaque connaissance admise.

M1e ajoute la supersession d’un fait dans un snapshot ultérieur afin de vérifier
la reproduction historique et le statut stale.

## 7. Exécution progressive

Les tests suivants attendent les sous-checkpoints d’implémentation :

- **M1a** : fixtures, valeurs, identité, vocabulaire, admission atomique,
  snapshots et persistence ;
- **M1b** : grounding, règle `coverage:v1`, distinctions vérité/assertion,
  provenance et dépendances ;
- **M1c** : DecisionScope fermé, manifeste, preuve de couverture, problème
  groundé, coût et sélection ;
- **M1d** : explication structurée basée sur les dépendances effectives ;
- **M1e** : fermeture/réouverture, supersession, stale et reproduction du
  snapshot historique.

Peuvent exister avant le core : validation JSON de la fixture, vérification des
IDs, formes de valeurs, doublons d’ensemble, références déclaratives et
présence des champs requis. Les tests sémantiques et de persistence attendent
la façade correspondante ; aucun faux backend ne sera introduit pour les faire
passer.

## 8. Choix encore OPEN

- noms définitifs et transport de la façade black-box ;
- encodage exact des erreurs et des raisons d’exclusion ;
- format final des graphes de provenance, dépendances et explication ;
- format de configuration pour ouvrir un store de test ;
- stratégie de fixture pour les records invalides isolés ;
- versionnement détaillé du manifeste et compatibilité future ;
- mapping d’un backend non Python vers la façade ;
- séparation finale entre statut de record, statut de grounding et statut du
  solveur.

Ces points ne justifient pas encore la création de `src/atlas/` ni de
`conformance/` exécutable.
