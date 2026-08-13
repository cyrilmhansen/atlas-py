# Audit contrastif — Semantic Model v2

Auditeur : Laguna (indépendant).
Point de départ : commit `1250503` (HEAD de `semantic-core-v1`).
Statut : audit de conception uniquement. Aucun fichier de code ou de conception n'a été modifié.

## Artéfacts examinés

- `semantic-model-v2-design.md` (intégralité, 533 lignes)
- `semantic_core.py` (v1, 225 lignes)
- `semantic-core-v1-notes.md` (intégralité)
- `semantic-core-v1-1-conversion-results.md` (intégralité)
- `semantic-core-v1-audit-laguna.md` (intégralité)
- `semantic-core-v1-audit-review.md` (intégralité)
- `semantic_core_v1_demo.py` (v1 demo)
- `semantic_core_conversion.py` (v1 conversion measurement)
- `semantic_core_v1_native_conversion.c` + `semantic_core_v1_native_measurements.json` (v1.1 native harness)
- `knowledge.md` (POC 1–12, intégralité)
- `quickdraw-region-ops-results.md`, `quickdraw-regions-notes.md`, `quickdraw-bitblt-notes.md`
- `quickdraw_region_ops_experiment.c` (lignes pertinentes)
- `semantic_core_fixture.json`, `semantic_core_v1_measurements.json`

---

## Finding 1 — Universalité cachée : `counts_occurrences_of` promu **forcé** sans fondement dans le code

**Statut** : CONFIRMED — critical
**Section concernée** : `semantic-model-v2-design.md:163` (tableau C des relations), Section G (lignes 271-310).

### Preuve

La relation `compte les occurrences de / counts occurrences of` est marquée **forcé comme relation** dans le noyau transversal (ligne 163) :

> « Relier un compteur à l'événement précis qu'il compte. »

Pourtard :

1. **Le code v1 n'implémente aucune telle relation.** `semantic_core.py:171-176` définit `repeat()` qui ne vérifie que `count.kind is not REUSE_COUNT` et `count.unit is not COUNT` et `_is_duration(cost_per_use)`. Aucun lien entre le compteur et l'événement compté n'existe — le « sujet » est une simple chaîne (`semantic_core_v1_demo.py:41` : `subject="reuse of result"`).

2. **L'audit v1 l'appelle explicitement une distinction non résolue.** `semantic-core-v1-audit-review.md:14` :

> « The unresolved distinction is therefore not merely generalizing Repeat beyond ReuseCount; it is relating an occurrence count to its counted event. »

3. **Le concept dépendant est lui-même seulement candidat/local.** `événement compté` est **probable, local** (ligne 138) et `opération` est **candidat** (ligne 137). Une relation **forcée** exige des entités référençables, mais les entités qu'elle relie sont candidates ou locales — contradiction interne.

4. **La v2 design le contredit elle-même.** Ligne 310 : « app, build or convert can for the moment be simple identifiers of operations » — c'est-à-dire que les opérations n'ont pas besoin d'être des entités. Mais une relation **forcée** `counts_occurrences_of` exige précisément que l'opération soit une entité référençable.

### Conséquence architecturale minimale

Promouvoir `counts_occurrences_of` au noyau transversal **forcé** introduit une dépendance à une ontologie d'événements/operations — exactement ce que le document prétend éviter (ligne 310). Cette relation devrait rester **candidat/local** : le besoin de lier un compteur à son événement est spécifique au scénario de décision QuickDraw, pas transversal.

---

## Finding 2 — Universalité cachée : `protocole expérimental` et `exécution expérimentale` marqués **forcé** mais contradictoirement non forcés par la discipline

**Statut** : CONFIRMED — major
**Section concernée** : `semantic-model-v2-design.md:132-133` (tableau C), Section F (lignes 219-256), Discipline de modélisation (ligne 433).

### Preuve

- `protocole expérimental` est **forcé comme contexte** (ligne 132).
- `exécution expérimentale` est **forcé comme contexte** (ligne 133).
- Mais la **Discipline de modélisation** (ligne 433) liste :

> « exécution expérimentale comme entité distincte de l'expérience déclarée » — **probablement utile mais non encore forcée**.

C'est une contradiction directe : le tableau C dit **forcé**, la discipline dit **non forcé**.

De plus :

- **Dans le code v1, tout cela est déjà capturé par `Provenance.context`.** `semantic_core.py:37-45` : `Provenance(status, source, context: tuple[tuple[str, str], ...])`. Les champs `platform`, `workload`, `statistic`, `phase` sont tous des entrées de contexte. Aucune de ces cinq entités n'existe comme classe dans le code.

- **Le JSON v1.1 combine protocole et exécution en un seul dict.** `semantic_core_v1_native_measurements.json:93-100` :

```json
"protocol": {
  "timer": "CLOCK_MONOTONIC_RAW",
  "samples": 31,
  "warmup": 1,
  "apply_batch": 100,
  "statistic": "median of 31 samples; application median divided by batch",
  "result_chain": "inputs -> B0 build/op -> exact B0 result -> B1 conversion -> apply"
}
```

Il n'y a pas de séparation `protocol` vs `run` — c'est une seule structure.

- **Le texte de la Section F mentionne `experiment` (ligne 235) mais il n'apparaît pas dans le tableau C.** La phrase « L'`experiment` décrit l'expérience ou le harness » introduit une troisième entité narrative sans entrée tableau. Triple redondance : `protocole` + `exécution` + `expérience`.

- **Le vrai problème audité (F5, Laguna) n'était pas l'absence d'entités, mais la granularité de provenance.** `semantic-core-v1-audit-laguna.md:187` : le JSON v1 avait `"source": "quickdraw_region_ops_measurements.json"` mais `conversion_*` venait de Python. Le problème est que `source` ne distinguait pas Python de C — résolu par un champ de provenance plus riche, pas par 5 nouvelles entités.

### Conséquence architecturale minimale

`protocole expérimental` et `exécution expérimentale` devraient rester **candidats**, pas **forcé**. Le v1 code capture déjà la provenance expérimentale via `Provenance.context`. La séparation en 5 entités est redondante avec un `context` dict enrichi. `experiment` ne devrait pas être une entité abstraite (`semantic-core-v1-1-conversion-results.md:64` : « La conclusion ne nécessite pas de modifier Semantic Core lui-même »).

---

## Finding 3 — Domaines vs contexte d'inférence : `reuse count` assigné à un domaine permanent sans justification

**Statut** : CONFIRMED — major
**Section concernée** : `semantic-model-v2-design.md:377` (Section I, « Concepts activés »).

### Preuve

La Section I assigne `reuse count` au domaine **Algorithmique et structures de données élémentaires** (ligne 377) :

```
- `sequence`, `merge`, `reuse count`, `ordered traversal` du domaine
  **Algorithmique et structures de données élémentaires**.
```

Or :

1. **`reuse count` n'appartient pas au domaine algorithmique dans le code.** Dans `semantic_core.py:30`, `REUSE_COUNT = QuantityKind("ReuseCount", "count")` est utilisé exclusivement dans le contexte du **cycle de vie QuickDraw** : `semantic_core_v1_demo.py:41` crée `quantity("N", REUSE_COUNT, COUNT, "reuse of result", ...)` pour compter les applications répétées d'un résultat de région. Dans le code des POC (`experiment.py`, `poc10.py`, etc.), les compteurs sont `comparisons`, `probes`, `visits`, `writes`, `allocations` — jamais `reuse_count`. Ce n'est pas un concept algorithmique général.

2. **`reuse count` n'est pas dans la liste des concepts du Domaine A (Section B, lignes 63-73).** `collection`, `sequence`, `lookup`, `traversal`, `sorted_sequence`, `hash_table`, `open_addressing`, `binary_search`, `merge`, `workload`, `memory_constraint` — `reuse count` n'apparaît nulle part dans cette liste. Il est introduit *ad hoc* dans l'exemple de la Section I comme appartenant à l'algorithmique, sans justification.

3. **Le besoin qui active `reuse count` est un contexte d'inférence temporaire.** Le recours à `repeat(reuse_count, apply_time)` n'existe que dans le contexte de la décision QuickDraw B0→B1 (choisir si convertir le résultat). C'est un **rapprochement contextuel**, pas une appartenance de domaine permanente. La Section H (lignes 327-331) reconnaît bien : « Une relation souvent réutilisée peut être conservée comme connaissance locale ou pont, mais elle reste justifiée par des observations. »

### Conséquence architecturale minimale

`reuse count` ne devrait pas être assigné à un domaine permanent. C'est un concept qui émerge du **besoin de décision** (combien de fois réutiliser le résultat), pas d'une organisation de connaissance permanente. Il devrait rester **candidat** ou **local au scénario**, sans appartenance de domaine imposée.

---

## Finding 4 — Objet logique / représentation / instance : l'identité logique n'est pas mécanisée dans le noyau

**Statut** : CONFIRMED — critical
**Section concernée** : `semantic-model-v2-design.md:174-217` (Section E), `semantic_core.py:48-60`.

### Contre-exemple (cas QuickDraw sparse B0→B1)

La Section E (lignes 178-185) propose la distinction :

```
objet logique :       C
représentation :      B0 bitmap, B1 runs
spécimens :           b0_C, b1_C
transformation :      b0_C --convertit--> b1_C
```

Et (lignes 199) : « Une occurrence doit pouvoir conserver au minimum : … un identifiant ou hash du contenu concret … les propriétés observées qui servent à vérifier l'identité logique. »

Mais :

1. **Le noyau v1 n'a aucun mécanisme d'identité.** `semantic_core.py:48-51` : `LogicalObject` est `(name: str, kind: str)` — un nom et un type. `Representation` (lignes 54-60) lie à un `LogicalObject` par référence Python. Deux `LogicalObject("R", "Region")` créés séparément sont **égaux par valeur** (frozen dataclass) mais **pas liés par hash ou canonical form**. L'identité logique repose sur la **référence Python** (`semantic_core_demo.py:20` : `assert bitmap.object is runs.object is transitions.object`), pas sur une vérification de contenu.

2. **L'assertion d'identité est un booléen codé en dur.** `semantic_core_conversion.py:96` : `"logical_region_preserved": True`. L'audit v1 (Laguna, F1) a prouvé cela **faux pour sparse** : `make_mask("sparse_sparse_intersection")` produit une aire de 1018, bbox (3,5,251,512), sha256 `504138ee…` — alors que le résultat B0 du C a une aire de 990, bbox (3,5,226,508), sha256 `fe3483f6…` (`semantic-core-v1-audit-laguna.md:209`). Le booléen `True` n'établit pas l'identité — il l'affirme sans preuve.

3. **Le correctif v1.1 déplace l'hash hors du noyau sémantique.** `semantic_core_v1_native_measurements.json:19-21` calcule `b0_canonical_hash` et `b1_canonical_hash` **dans le harness C**, pas dans `semantic_core.py`. Le noyau sémantique n'a toujours aucun champ de hash. La Section E dit (ligne 203-204) : « L'affirmation « même région logique » est une relation vérifiable par une observation canonique, pas une conséquence du seul fait que les deux objets portent le même nom. » Mais le code n'a pas cette « observation canonique » — `LogicalObject` est juste `(name, kind)`.

### Conséquence architecturale minimale

Le noyau sémantique **ne peut pas distinguer** deux instances de représentation qui représentent le même objet logique (fragmented : même sha256) d'instances qui n'en représentent pas (sparse : sha256 différent). La structure actuelle (`LogicalObject(name, kind)` + référence Python) **suppose** l'identité par nom. Sans ajouter un champ de hash ou de forme canonique — ce que le document refuse (`semantic-core-v1-1-conversion-results.md:64` : « La conclusion ne nécessite pas de modifier Semantic Core lui-même ») — la distinction objet logique / spécimen ne peut pas être mécanisée dans le noyau.

---

## Finding 5 — Quantité et sujet sémantique : `repeat` n'aligne pas les sujets, et le design réintroduit l'ontologie des événements

**Statut** : CONFIRMED — major
**Section concernée** : `semantic_core.py:171-176`, `semantic-model-v2-design.md:275-310`, `semantic-core-v1-audit-review.md:14`.

### Contre-exemple concret

La règle visée (Section G, lignes 282-304) exige que `count` et `unit_cost` portent sur la **même opération** :

```
reuse_count    counts occurrences of    apply_result
apply_time     cost of                  apply_result
→ repeat(reuse_count, apply_time) valide
```

Mais dans le code v1 :

```python
# semantic_core.py:171-176
def repeat(count: Quantity, cost_per_use: Expr) -> Repeat:
    if count.kind is not REUSE_COUNT or count.unit is not COUNT:
        raise TypeError("repeat requires a ReuseCount quantity")
    if not _is_duration(cost_per_use):
        raise TypeError("repeat requires a duration per use")
    return Repeat(count, cost_per_use)
```

**`repeat` ne vérifie jamais l'alignement des sujets.** Les valeurs, unités et QuantityKind sont compatibles (`REUSE_COUNT/count` + `DURATION/microseconds`), mais le sujet n'est qu'une chaîne :

- `semantic_core_v1_demo.py:41` : `n = quantity("N", REUSE_COUNT, COUNT, "reuse of result", ...)` — sujet = `"reuse of result"`
- `semantic_core_v1_demo.py:37-38` : `apply_before = measured(DURATION, MICROSECONDS, ..., str(initial))` — sujet = `"bitmap_mask(R_sparse)"`

Ces deux sujets sont **différents** mais la composition `repeat(n, apply_before)` est **acceptée**. La même structure accepterait `repeat(n, production)` où `production` a pour sujet `"produce(bitmap_mask(R_sparse))"` — valeurs et unités compatibles, QuantityKind compatibles (REUSE_COUNT + DURATION), mais le sujet est **faux** : `reuse_count` compte les *applications*, pas les *constructions*. La Section G le reconnaît (lignes 275-280) :

> « Ainsi, le noyau peut encore accepter conceptuellement : repeat(reuse_count, apply_time) / repeat(reuse_count, build_time) »

Et l'audit review (ligne 14) :

> « repeat(reuse_count, build_time) appears semantically admissible although the scenario's reuse count denotes repeated application, not rebuilding. »

### Ontologie des événements réintroduite

Le design dit (ligne 310) : « Atlas n'a pas besoin d'introduire une ontologie universelle des événements ou des opérations. » Mais :

- `counts_occurrences_of` est **forcé** (ligne 163) → exige des événements référençables.
- `produit` est **probable** (ligne 157) → exige des producteurs = événements.
- `événement compté` est **probable, local** (ligne 138) → concept d'événement.
- `opération` est **candidat** (ligne 137) → concept d'opération.

Ces quatre concepts sont dans le noyau transversal. Leur statut cumulé **réintroduit silencieusement** une ontologie d'événements, malgré l'assertion explicite du contraire.

### Conséquence architecturale minimale

Le noyau ne peut pas distinguer `repeat(reuse_count, apply_time)` (correct) de `repeat(reuse_count, build_time)` (faux) sans un lien `counts_occurrences_of` entre le compteur et l'événement. Mais ce lien est **forcé** dans le noyau transversal, ce qui nécessite des entités d'événements — ce que le design prétend éviter. La relation et les entités associées devraient rester **locales au scénario** jusqu'à ce qu'une expérience force la distinction.

---

## Finding 6 — Vocabulaire expérimental : redondance entre protocol/run et observation/measurement

**Statut** : CONFIRMED — major
**Section concernée** : `semantic-model-v2-design.md:122-138` (tableau C), Section F (lignes 219-269), v1 audit (F5, F6).

### Preuve

Le vrai problème auditif (v1, Laguna F5-F6) : la provenance ne distinguait pas l'origine Python de l'origine C, et la feuille `production` manquait de `phase` et `statistic`.

Mais le v2 design propose **5 entités** pour résoudre un problème qui, dans le code, est déjà partiellement adressé par `Provenance.context` :

```python
# semantic_core.py:37-45
@dataclass(frozen=True)
class Provenance:
    status: str
    source: str
    context: tuple[tuple[str, str], ...] = ()
```

Les champs `platform`, `workload`, `statistic`, `phase`, `source` sont **déjà** des entrées de contexte. Le v2 design n'a pas besoin de `protocole`, `exécution`, `observation`, `mesure`, `artefact` comme entités distinctes — un `context` dict enrichi suffit.

**Redondances constatées :**

1. **`protocole expérimental` + `exécution expérimentale`** : les deux marqués **forcé comme contexte**, mais la discipline de modélisation (ligne 433) dit **non forcé** pour l'exécution. Le JSON v1.1 les fusionne en un seul dict `protocol` (lignes 93-100).

2. **`observation` + `mesure`** : `observation` est **forcé comme rôle** (ligne 130), `mesure` est **probable** (ligne 131). Mais dans le code v1, les deux sont des `Quantity` avec `status="measured"` — aucune distinction qualitative/quantitative n'existe. Aucun artefact v1 ne force une observation qualitative. La distinction est **anticipée**, pas **forcée**.

3. **`experiment`** (ligne 235) : mentionné dans le texte mais absent du tableau C. Triple entité narrative (`experiment` + `protocol` + `run`) pour ce qu'une provenance enrichie fait déjà.

### Conséquence architecturale minimale

Conserver un modèle minimal où `Provenance` porte un `context` dict suffisant (programme, timer, samples, plateforme, phase, statistique, artefact). `protocole`, `exécution`, `observation`, `mesure` devraient rester **candidats** jusqu'à une expérience qui force une distinction spécifique. `experiment` ne devrait **pas** être une entité abstraite — le v1.1 l'a résolu par un enrichissement de contexte, pas par une nouvelle entité (`semantic-core-v1-1-conversion-results.md:64`).

---

## Finding 7 — Domaines initiaux : `workload` et `memory_constraint` ne sont pas des concepts algorithmiques

**Statut** : CONFIRMED — major
**Section concernée** : `semantic-model-v2-design.md:63-73` (Section B, Domaine A).

### Preuve

Le Domaine A « Algorithmique et structures de données élémentaires » liste (lignes 72-73) :

- `workload` — charge de travail ;
- `memory_constraint` — contrainte mémoire.

Mais :

1. **`workload` n'est pas un algorithme ni une structure de données.** Dans `experiment.py`, `SCENARIOS` définit des charges comme `lookup_heavy` (950 lookups, 30 walks, 10 updates) ou `memory_tight` (POC 10). Un `workload` décrit **quoi tester**, pas **comment** algorithmer. Le knowledge.md (ligne 5) : « Un besoin (10 000 éléments, charge de lecture majorité) peut produire des choix différents. » — c'est un **besoin/exigence**, pas un concept algorithmique.

2. **`memory_constraint` n'appartient pas à l'algorithmique.** C'est une **contrainte d'exécution** (ex. `memory_tight` dans POC 10, ligne 541). Elle limite la mémoire admissible dans un scénario de test, pas une structure de données. Dans `semantic_core.py`, il n'existe même **pas** de `MEMORY_CONSTRAINT` — le concept est absent du code.

3. **Leurs véritables cousins sont dans d'autres domaines.** `workload` relève du domaine des **scénarios/expérience** ; `memory_constraint` relève du domaine des **contraintes environnementales**. Les placer dans l'algorithmique est confondre le **besoin** (ce que l'on teste) avec la **mécanique** (comment on teste).

Dans le code v1, `workload` n'apparaît que comme un **contexte** (`"workload": name` dans `semantic_core_v1_demo.py:29`), jamais comme une entité du noyau sémantique. Dans `semantic_core.py`, il n'y a **aucune** classe `Workload`.

### Conséquence architecturale minimale

`workload` et `memory_constraint` devraient être **supprimés du Domaine A**. Ils sont du vocabulaire de **scénario/ besoin**, pas d'algorithmique élémentaire. Ils pourraient être des concepts locaux au domaine expérimental ou de décision, mais pas au noyau algorithmique.

---

## Finding 8 — Recollage inter-domaines : le champ `family` crée une compatibilité transversale fausse

**Statut** : LIKELY — major
**Section concernée** : `semantic_core.py:26-34,189-190`; `semantic-model-v2-design.md:120-138,312-363`.

### Exemple positif (recollage légitime)

La Section H (lignes 335-352) donne un example où `horizontal_runs` (Domaine B) et `sequence` (Domaine A) sont rapprochés via :

> « runs(R) expose une séquence ordonnée d'intervalles par scanline / intersection(R1, R2) peut exploiter une fusion ordonnée »

C'est un **rapprochement contextuel** justifié par un besoin (fusion efficace), sans fusion permanente. ✓

### Contre-exemple (ambiguïté produite par la liberté)

Le champ `family` sur `QuantityKind` (`semantic_core.py:23`) est une **catégorisation transversale** imposée sur tous les kinds, indépendamment des domaines :

```python
ACTIVE_PIXELS   = QuantityKind("ActivePixels", "count")     # QuickDraw
RUN_COUNT       = QuantityKind("RunCount", "count")         # QuickDraw
REUSE_COUNT     = QuantityKind("ReuseCount", "count")       # cycle de vie QuickDraw
TRANSITION_COUNT = QuantityKind("VerticalTransitionCount", "count")  # QuickDraw
```

Tous partagent `family="count"`. La fonction `_is_count` (`semantic_core.py:189-190`) :

```python
def _is_count(expr: Expr) -> bool:
    return expr.kind.family == "count" and expr.unit is COUNT
```

Cette famille est **universelle** — elle groupe des concepts de domaines différents sous une même catégorie. Quand le contexte d'inférence réunit :

- `REUSE_COUNT` (compte les **applications** d'une région — concept de cycle de vie)
- `RUN_COUNT` (compte les **runs** dans une région — concept graphique interne)

...les deux partagent `family="count"` et `unit=COUNT`. La structure **ne peut pas distinguer** qu'ils comptent des événements différents. Le seul mécanisme proposé pour les distinguer est `counts_occurrences_of` — mais il est **forcé** (Finding 1) et **non implémenté** (pas de champ d'event dans `semantic_core.py`).

**Ambiguïté concrète** : le code v1 a `_is_count` qui accepterait théoriquement une composition entre `REUSE_COUNT` et `RUN_COUNT` si une opération `*` existed dans v1 (elle n'existe plus — v1 rejette `*`). Mais la **vulnée structurelle** reste : le champ `family` crée une compatibilité structurelle transversale qui n'est pas ancrée dans un domaine ou un contexte d'inférence. La Section I (ligne 377) assigne `reuse count` à l'**Algorithmique** alors qu'il est un concept de cycle de vie QuickDraw — cette assignation permanente, combinée au `family="count"`, produit une ambiguïté sur ce que compte vraiment le compteur.

### Conséquence architecturale minimale

Sans un mécanisme pour ancrer un `QuantityKind` à un domaine spécifique et un contexte d'inférence (ce que le design refuse de proposer : « Aucun score, ranking, profondeur ou budget de traversée n'est défini », ligne 363), le champ `family` reste une **catégorisation transversale implicite** qui peut produire des compositions faussement compatibles. Ce problème est classifié **Unknown** : il exige un mécanisme (domain-scoped kind checking ou context-anchored relations) non encore conçu, dont l'architecture v2 ne traite pas la question. **Ne pas introduire** de tel mécanisme maintenant — attendre qu'une expérience force la distinction.

---

## Conclusion — Réponses aux 4 questions

### 1. L'architecture en îlots locaux + contexte d'inférence est-elle cohérente avec les connaissances Atlas actuelles ?

**Partiellement.** Les connaissances actuelles (v1 code, v1.1 native harness, POCs 1–12) montrent des îlots de connaissance bien distincts : QuickDraw graphique (B0/B1/B2), algorithmique élémentaire (POC 1–5), batch (POC 10). Le principe de « les domaines organisent la connaissance mais ne bornent pas l'inférence » est **cohérent** avec le code v1, où `Provenance.context` capture la provenance sans imposer d'ontologie. Mais le design v2 **dévie** de cette cohérence en promouvant 5+ concepts expérimentaux et `counts_occurrences_of` au noyau transversal forcé — exactement ce que le code v1 évite (pas de classe `Operation`, `Experiment`, `Run`, `Protocol`). La cohérence est rompue par **l'expansion du noyau**, pas par le principe d'îlots.

### 2. Quel est le risque principal d'universalité cachée ?

Le risque principal est **`counts_occurrences_of`** (Finding 1). Cette relation, marquée **forcé**, exige des entités d'événements/opérations référençables — une ontologie d'événements — ce que le design nie formellement (ligne 310). Une fois que les événements sont référençables, la pente glissante mène naturellement à un système d'événements universel, puis à une hiérarchie d'événements, exactement ce que le v0 a été évité et ce que le v2 tente de bloquer. Le risque : **transformer un besoin local de traçabilité (compter les applications d'une région) en une ontologie transversale d'événements**.

### 3. Quelle distinction du noyau paraît actuellement la plus solide ?

**objet logique / représentation / spécimen** (Section E). Même si le code v1 n'a pas de champ de hash (Finding 4), la **distinction conceptuelle** est clairement forcée : le v1.1 native harness calcule `b0_canonical_hash` et `b1_canonical_hash` dans le C, prouvant que deux spécimens de la même représentation peuvent exister pour un même objet logique, et que la transformation ne crée pas un nouvel objet. Cette distinction est **démontrée par les artefacts** (hash concordant pour fragmented, hash divergent pour sparse v1) et **n'importe quel implémentation future** la respectera ou la viole — c'est le point d'ancrage stable.

### 4. Quelle distinction devrait rester non implémentée tant qu'une nouvelle expérience ne la force pas ?

**`compteur ↔ événement compté`** (`counts_occurrences_of` comme entité). Aucune expérience actuelle n'oblige de lier `ReuseCount` à `apply_result` par une relation formelle. Le code v1 utilise des sujets chaîne, et la v2 design elle-même dit que `apply`/`build`/`convert` peuvent rester « simple identifiers » (ligne 310). Implémenter `counts_occurrences_of` comme relation **forcée** maintenant revient à **pré-anticiper** une ontologie d'événements. Rester sur le `subject: str` jusqu'à ce qu'une expérience réelle (pas l'exemple QuickDraw) force la liaison explicite.

---

**STOP.** Aucun fichier de code ou de conception n'a été modifié. Aucune implémentation n'est proposée. CET audit est une évaluation de conception uniquement.