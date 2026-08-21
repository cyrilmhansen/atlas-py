# Atlas Core V1 — profil d’implémentation

## Statut et hiérarchie

Ce document définit un profil d’implémentation nommé **Core V1** pour
`atlas-specification-v0.3.2.1.md`. Il ne redéfinit pas Atlas et ne transforme
pas les choix de cette première implémentation en exigences générales.

Les niveaux suivants sont utilisés explicitement :

- **NORMATIVE** : exigence héritée de la spécification Atlas ou nécessaire pour
  respecter son modèle sémantique ;
- **CORE_V1_CHOICE** : décision locale de cette tranche, réversible et non
  normative pour Atlas ;
- **OPEN** : question volontairement non résolue ou hors périmètre.

Core V1 est une tranche verticale minimale couvrant cinq responsabilités :

1. un modèle sémantique d’identités, valeurs, descriptions, faits, relations et
   vocabulaire versionné ;
2. un Knowledge Store persistant et validé, avec snapshots ;
3. l’évaluation d’une famille limitée de règles structurées paramétriques ;
4. la compilation d’un problème de décision fini et sa sélection exacte
   monoobjectif ;
5. une explication reconstruite à partir des dépendances effectivement
   utilisées.

Les notions `Intent`, `Realization`, `Resource`, `Query`, `Index` et `Array`
restent des rôles de `Description`, déterminés par les relations et faits ; ce
ne sont pas des types fondamentaux Core V1.

## 1. Décisions classées

### 1.1 Exigences normatives Atlas

Core V1 respecte les exigences suivantes sans les étendre :

- les descriptions possèdent une identité nominale persistante et stable ; le
  contenu d’une description ne constitue pas son identité ;
- identité, équivalence sémantique et partage d’instance restent distincts ;
  aucune fusion implicite n’est effectuée ;
- égalité, ordre, unicité, hash et coercions qui ont une signification Atlas
  sont définis explicitement et ne sont pas hérités du langage hôte ;
- le monde est ouvert : `TRUE`, `FALSE` et `UNKNOWN` sont distincts, et
  l’absence d’un fait ne produit pas une négation globale ;
- les prédicats et propriétés ont une sémantique stable ;
- les propriétés sont résolues relativement au participant groundé demandé ;
  une propriété homonyme d’un autre participant ne constitue pas un fallback ;
- les relations sont multivaluées par défaut ; aucun premier résultat n’est
  choisi implicitement ;
- structure et ordre sont conservés lorsqu’ils sont sémantiques ; une séquence
  et un ensemble fini ne sont pas interchangeables ;
- une conclusion dérivée conserve au minimum son prédicat, participants,
  statut épistémique lorsque pertinent et dépendances ; un booléen d’évaluation n’est pas la conclusion ;
- les dépendances des dérivations sont structurées et auditables ; une
  justification narrative seule est insuffisante ;
- les mêmes invariants sont appliqués à l’écriture, à la lecture et au décodage
  des connaissances ;
- toute décision finie est qualifiée par un snapshot, un scope et une
  politique de grounding explicites ;
- une explication doit être reconstructible à partir des dépendances effectives,
  et non ajoutée comme texte indépendant du calcul.

### 1.2 Choix propres à Core V1

Les décisions suivantes sont locales à Core V1 :

- SQLite local est utilisé comme backend du Knowledge Store ;
- les payloads persistés sont des enveloppes JSON versionnées ;
- le store est append-only et les corrections utilisent la supersession ;
- les snapshots sont des vues immuables et reproductibles ;
- les identifiants opaques sont séparés par domaine (`DescriptionId`,
  `KnowledgeId`, `RuleId`, `ContextId`, `SnapshotId`, etc.) ;
- l’arité, les rôles ordonnés et les versions sémantiques sont stockés dans le
  vocabulaire persistant afin de garantir la stabilité des prédicats ;
- la syntaxe des identifiants est ASCII, non vide et comparée exactement. ASCII
  simplifie la canonicalisation et le stockage ; ce n’est pas une propriété
  intrinsèque d’Atlas ;
- les valeurs supportées sont limitées à `symbol`, `integer` exact,
  `finite_set<symbol>` et `sequence<symbol>` ;
- toute connaissance admise en Core V1 doit porter une provenance ;
- les propriétés fonctionnelles ne le sont que si leur contrat le déclare et
  qu’une multiplicité contradictoire n’est pas silencieusement écrasée ;
- les dépendances cycliques sont rejetées dans cette tranche ;
- toute explication Core V1 est reconstruite à partir des dépendances effectives
  réellement utilisées par la décision ; cette exigence renforce localement le
  `DEVRAIT` de la spécification et n’est pas une obligation Atlas universelle ;
- l’obsolescence est traitée paresseusement : une dérivation devenue stale est
  recalculée avant réutilisation ;
- la décision M1 est monoobjectif, avec un coût entier exact et une réalisation
  choisie par problème ; toutes les solutions co-optimales sont retournées ;
- aucun artefact de `experiments/` n’est importé comme code, donnée ou API.

Ces décisions peuvent être remplacées dans une implémentation ultérieure sans
modifier les exigences normatives auxquelles elles répondent.

## 2. Modèle sémantique minimal

### 2.1 Description, Fact et Relation

`Description` est une entité à identité nominale stable. Ses labels et rôles
documentaires ne deviennent pas automatiquement des prédicats de raisonnement.

Un `Fact` est conceptuellement une connaissance pouvant associer une propriété
à une ou plusieurs descriptions, avec une valeur, une portée, un statut
épistémique et une provenance. **Core V1 ne redéfinit pas ce concept général.**
Pour M1, il ne supporte initialement qu’une forme restreinte de *property
assertion* unaire attachée à une seule `Description`. Cette restriction est un
`CORE_V1_CHOICE`, pas une définition générale de `Fact`.

Une `Relation` est un prédicat appliqué à une liste ordonnée de descriptions.
Une assertion relationnelle persistable ajoute au terme relationnel :

- une polarité `positive` ou `negative` ;
- un statut épistémique ;
- un scope ;
- une provenance ;
- éventuellement une dérivation et ses dépendances.

La vérité locale de l’évaluation d’une règle est une troisième notion distincte
et vaut `TRUE`, `FALSE` ou `UNKNOWN`.

L’invariant est le suivant :

```text
evaluation FALSE != assertion negative
```

Une condition `FALSE` rend la règle non applicable. Elle ne produit une
assertion négative que si une autre règle possède explicitement une tête
négative et que ses propres conditions valent `TRUE`. L’absence d’assertion
positive et l’absence d’assertion négative signifient `UNKNOWN`, non `FALSE`.

### 2.2 Valeurs

Core V1 valide explicitement les quatre formes suivantes :

- `symbol` : texte comparé selon sa séquence exacte de scalaires, sans
  normalisation implicite ;
- `integer` : entier signé exact, distinct de `bool` ;
- `finite_set<symbol>` : ensemble non ordonné sans doublons ;
- `sequence<symbol>` : séquence ordonnée avec égalité positionnelle.

Une collection Python n’est jamais directement une valeur Atlas. Elle passe par
une validation et une conversion qui rejettent les coercions, égalités, hashes
ou pertes d’ordre introduits par le langage hôte.

### 2.3 Vocabulaire

Le vocabulaire du store conserve au minimum, pour chaque prédicat ou propriété :

- son identifiant et sa version sémantique ;
- son arité et les rôles ordonnés des participants lorsqu’il s’agit d’un
  prédicat ;
- la forme de valeur attendue lorsqu’il s’agit d’une propriété ;
- sa cardinalité éventuelle ;
- une référence vers son contrat sémantique.

Une propriété peut être valide dans le vocabulaire sans être lue par la règle
courante. Les relations restent multivaluées par défaut.

## 3. Représentation structurée Core V1

Le pivot conceptuel minimal est :

```text
property(participant, property_id)
set_union(left, right)
set_subset(left, right)
relation head(predicate, ordered participants, polarity)
```

Il permet la règle `covers(candidate, request)` : l’union des propriétés de la
request doit être incluse dans la propriété disponible du candidate.

Ce pivot n’est pas un AST universel Atlas. Les expressions inconnues peuvent
être persistées comme opérateurs isolés et non évaluables, mais elles ne sont
pas interprétées silencieusement par Core V1.

Les trois niveaux sont séparés :

| Niveau | Rôle |
|---|---|
| conceptuel | descriptions, faits, relations, règles et dépendances |
| mémoire | records immuables typés et indexes techniques sans sémantique implicite |
| persisté | enveloppes JSON versionnées dans une transaction SQLite |

## 4. Knowledge Store

Le store expose comportementalement la façade suivante ; les noms exacts ne
sont pas encore une API de conformance définitive :

- `admit(batch)` : valide puis admet atomiquement un lot ;
- `read(...)` : lit par identité dans un snapshot ;
- `snapshot()` : crée une vue immuable ;
- `find(...)` : interroge une collection de résultats, sans sélection implicite
  du premier ;
- `admit_derived(...)` : admet une conclusion et sa dérivation ;
- `dependencies(...)` : récupère les dépendances directes ou transitives ;
- `provenance(...)` : récupère les sources directes ou transitives ;
- `status(...)` : expose le statut relatif au snapshot demandé.

SQLite est un mécanisme de stockage Core V1, pas la définition du modèle. Les
contraintes d’unicité, l’ordre, l’égalité, l’upsert et la représentation de
`NULL` ne doivent pas être déduits implicitement du schéma ou du comportement
SQLite.

L’admission rejette notamment les références non résolues, les IDs ambigus, les
valeurs non validées, les arités incorrectes, les scopes absents, les
provenances absentes et les cycles de dérivation. Une relation ne doit pas être
écrasée par une clé unique si sa sémantique est multivaluée.

### Snapshots, supersession et stale

Les corrections sont append-only et portent une relation `supersedes`. Si `F1`
est actif dans `S1` et qu’une correction `F2` le supersède dans `S2`, une
dérivation `D1` qui dépend de `F1` reste valide et reproductible relativement à
`S1`. Dans `S2`, elle est `stale`, ne peut pas être réutilisée silencieusement
et doit être recalculée si nécessaire.

La supersession ne réécrit jamais l’histoire des snapshots antérieurs. Les
statuts `active`, `superseded`, `stale` et `isolated` sont toujours interprétés
relativement au snapshot lorsqu’un tel contexte est requis.

## 5. Règles, grounding et décision

Une règle reçoit un binding exact pour chaque participant déclaré. Chaque
lecture de propriété est effectuée sur la `DescriptionId` bindée ; une
propriété d’un autre participant ne peut pas satisfaire la lecture.

Une lecture absente ou ambiguë vaut `UNKNOWN`. Une règle ne produit sa tête
relationnelle que lorsque ses conditions valent TRUE. La conclusion groundée
conserve le prédicat, les participants ordonnés, la polarité, le statut
épistémique lorsque pertinent, la règle appliquée et les dépendances
effectivement lues.

### DecisionScope M1

Pour rendre ce scope falsifiable, M1 utilise un manifeste de grounding
versionné. C’est un `CORE_V1_CHOICE`, non un mécanisme universel Atlas. Le
manifeste déclare avant toute exécution :

- la catégorie de découverte `realizes(realization, intention)` en polarité
  positive ;
- la règle exacte d’admissibilité `coverage:v1` et sa version ;
- les lectures prescrites `candidate.available-capabilities`,
  `request.search-requirements` et `request.output-requirements` ;
- la propriété de coût `candidate.cost` ;
- les règles de visibilité du contexte `C` applicables à ces connaissances ;
- les versions de vocabulaire nécessaires ;
- l’obligation de parcourir transitivement les dépendances de toute
  connaissance dérivée incluse dans le problème.

Pour une intention `I`, un snapshot `S` et un contexte `C`, le `DecisionScope`
M1 est l’univers fermé décrit par ce manifeste :

1. toutes les assertions positives `realizes(R, I)` correspondant à `I` et au
   snapshot sont interrogées selon le manifeste ;
2. les assertions exclues par la visibilité de `C` sont enregistrées avec la
   règle ou le fait explicite de `C` qui motive l’exclusion ;
3. pour chaque candidat inclus, les trois lectures de propriétés prescrites et
   le coût exact sont recherchés ;
4. les versions de vocabulaire et de règle requises sont suivies ;
5. la fermeture transitive des dépendances de toute connaissance dérivée
   incluse dans le `Grounded Decision Problem` est parcourue.

Une preuve structurée de couverture doit être produite. Elle contient le
snapshot, le contexte, la version du manifeste, les versions de règle et de
vocabulaire, puis, pour chaque catégorie prescrite : la recherche effectuée,
ses paramètres exacts, les identités trouvées ou l’absence explicite de
résultat, les identités incluses, les identités exclues et la raison structurée
de chaque exclusion. Pour chaque connaissance dérivée incluse, elle contient
le parcours de la fermeture transitive de ses dépendances et son résultat.
Cette preuve est inspectable par la future façade de conformance.

Le statut `complete_for_declared_scope` est autorisé uniquement si chaque
recherche prescrite a été effectuée, aucune catégorie n’a été omise, aucune
borne n’a interrompu le parcours, aucun pruning heuristique n’a supprimé une
partie du scope et toutes les références structurelles requises sont résolues.
Une recherche complète qui retourne aucun fait, ou une connaissance
insuffisante ou ambiguë, reste compatible avec ce statut et peut conduire à
`UNKNOWN`. En revanche, une catégorie non parcourue, une référence pendante ou
un parcours interrompu l’interdit.

Ainsi, `UNKNOWN` de connaissance n’est pas un grounding incomplet. Les
dépendances « effectivement décisives » appartiennent à l’explication ; elles
ne remplacent pas la fermeture prescrite par la preuve de couverture.

Ce statut ne signifie pas que le Knowledge Store est complet au-delà du scope
déclaré.

Le problème M1 contient une intention, deux réalisations candidates, une
request, la règle `covers(candidate, request)`, un coût exact, une réalisation
moins chère mais non admissible et une réalisation plus chère admissible. Le
sélecteur retourne toutes les solutions de coût minimal ; aucun tie-break
lexical caché n’est appliqué.

Pour Core V1, cette sélection est une opération pure sur un `Grounded Decision
Problem` déjà persisté et identifié nominalement. Le résultat référence
l’identité du GDP source ; il ne crée ni ne modifie une `Decision`. La sélection
ne re-ground pas et ne reconstruit pas le GDP depuis un scope ou une vue
`current/latest`.

La persistance du résultat de sélection est une opération distincte et
explicite (`CORE_V1_CHOICE`). Elle crée un artefact nominal `Decision`, identifié
par un `DecisionId` distinct du `DecisionProblemId`, et conserve l’identité du
GDP source ainsi que le statut `RESOLVED`, `NEEDS_INFORMATION` ou
`NO_ADMISSIBLE_CANDIDATE`. Un `Decision` est validé directement contre ce GDP
historique lors de la restauration ; il n’est pas recalculé par `select_m1`.

Le choix suivant est explicitement un `CORE_V1_CHOICE` :

- `complete_for_declared_scope` décrit la complétude du parcours dans le scope,
  et non la complétude épistémique du corpus ;
- si au moins un candidat est `UNKNOWN`, le résultat est
  `NEEDS_INFORMATION`, sans candidat sélectionné ou co-optimal et sans
  optimum certifié ;
- `UNKNOWN` ne doit jamais être assimilé à `FALSE` ni supprimé implicitement
  pour établir une optimalité ;
- si tous les candidats sont `TRUE` ou `FALSE` et qu’aucun n’est `TRUE`, le
  résultat est `NO_ADMISSIBLE_CANDIDATE`, sans candidat sélectionné ou
  co-optimal ;
- sinon, le résultat est `RESOLVED` : l’optimum est le minimum entier exact des
  coûts des candidats `TRUE`, et les co-optimaux sont tous les candidats
  `TRUE` atteignant ce minimum.

L’ordre de la représentation des co-optimaux peut suivre celui du GDP, mais ne
constitue pas un tie-break : la sémantique du résultat est l’ensemble complet
des candidats au coût minimal.

La qualification `optimal + complete_for_declared_scope` signifie uniquement
que la solution est optimale dans le Grounded Decision Problem M1 effectivement
résolu et que son grounding est complet relativement au DecisionScope M1, au
manifeste, au snapshot et au contexte déclarés. Elle ne signifie ni optimum
mondial ni complétude du Knowledge Store.

## 6. Milestone M1

**M1 — Persisted grounded coverage choice** est une seule tranche verticale,
construite par les sous-checkpoints suivants :

- **M1a — store + identité + valeurs + vocabulaire** ;
- **M1b — règle + grounding + dérivation** ;
- **M1c — Grounded Decision Problem + sélection** ;
- **M1d — explication** ;
- **M1e — supersession/stale + reproduction historique**.

Ces sous-checkpoints ne sont pas des POC indépendants. Ils construisent le
même fixture et doivent aboutir à une démonstration de persistence, grounding,
monde ouvert, provenance, décision correcte, explication, snapshot,
redémarrage et reproduction historique.

## 7. Conformance

Le profil devra à terme vérifier au minimum les comportements suivants :

- identité nominale distincte malgré des contenus identiques ;
- rejet des valeurs et coercions non supportées ;
- conservation de l’ordre des séquences et absence de doublons dans les
  ensembles ;
- résolution de propriétés par participant exact ;
- résultats multivalués sans premier élément implicite ;
- distinction `TRUE` / `FALSE` / `UNKNOWN` ;
- distinction évaluation `FALSE` / assertion négative ;
- provenance obligatoire et dépendances effectives des dérivations ;
- snapshots reproductibles et stale relatif au snapshot ;
- couverture du scope et décision correcte avec égalité de coûts ; le test doit
  inspecter la preuve structurée du manifeste M1, y compris les recherches
  prescrites sans résultat ;
- rejet à la frontière d’une entrée persistée `finite_set<symbol>` contenant
  des doublons. Une représentation canonique interne issue de membres déjà
  validés est permise, mais une entrée ambiguë ne doit pas être réparée
  silencieusement ;
- persistence/restart sans perte de l’identité ou du contexte M1 : après
  fermeture et réouverture du même store, un snapshot historique identifiable
  doit pouvoir être rouvert ou reconstruit, conserver ses connaissances actives
  logiques, ses `DescriptionId`, `KnowledgeId`, scopes et `ContextId`, et
  reproduire la même décision M1 à partir du snapshot et du contexte persistés.

Avant de créer `conformance/`, il faut définir une petite façade black-box
stable. Les tests ne devront dépendre ni de SQLite ni des classes internes de
l’implémentation.

## 8. Limites volontaires et points OPEN

Les éléments suivants restent explicitement hors de la première tranche :

- quantification et intervalles ;
- mutations générales et transitions d’état ;
- planning temporel, lifetimes, TMS réactif et cycles ;
- incertitude quantitative dans la décision ;
- CP-SAT, SMT et MILP ;
- décisions multiobjectifs ;
- acquisition d’information et Semantic Recovery ;
- matérialisation et validation de code ;
- équivalence ou canonicalisation générale de descriptions ;
- distribution, réplication et scalabilité du store ;
- plusieurs producteurs ou consommateurs conditionnels complexes ;
- invalidation générale et concurrence de mises à jour.

Ces absences sont des limites de Core V1, pas des impossibilités affirmées pour
Atlas.

Restent OPEN :

- la forme générale des `Fact` multi-descriptions et des assertions riches ;
- l’intégration de contrats structurés au-delà du pivot M1 ;
- la preuve automatique des préconditions et la quantification symbolique ;
- l’équivalence sémantique entre descriptions distinctes ;
- les politiques générales de stale et d’invalidation ;
- les backends de décision au-delà de la sélection exacte monoobjectif ;
- la couverture, la provenance et la distribution à grande échelle ;
- la future façade de conformance et la compatibilité de versions.

## 9. Décisions figées pour Core V1

La première tranche est donc figée autour d’un store local validé, de snapshots
immuables, de valeurs explicites, d’un grounding nominal participant-scoped,
d’un pivot `property`/`set_union`/`set_subset`, d’une dérivation persistée et
traçable, et d’une sélection finie monoobjectif à coût exact.

Elle ne prétend ni fournir une ontologie universelle, ni implémenter tous les
contrats Atlas, ni transformer les rôles métier de la fixture en types
fondamentaux. Toute extension devra d’abord être classée comme exigence
normative, choix Core V1 ou question OPEN, sans effacer cette séparation.
