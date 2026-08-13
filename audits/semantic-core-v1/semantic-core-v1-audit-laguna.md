# Semantic Core v1 — audit indépendant

Auditeur: Laguna (indépendant).  
Dépôt: `quickdraw_region_ops` + `semantic_core`.  
Date de l'audit: 2026-08-13. Aucun fichier n'a été modifié.

---

## État Git et artefacts examinés

```
7c227b0 (sematic-core-v1)  atlas: add semantic relations and conversion decision
81f91bc (semantic-core-v0) atlas: add minimal QuickDraw semantic core
1b27288 (quickdraw-region-ops-complete) quickdraw: explore boolean region operations
```

Tags pertinents: `semantic-core-v0`, `semantic-core-v1`, `quickdraw-region-ops-complete`.

Artefacts examinés:
- `semantic_core.py` (v1, commit `7c227b0`)
- `semantic_core_conversion.py` (v1, nouveau)
- `semantic_core_v1_demo.py` (v1, nouveau)
- `semantic_core_v1_measurements.json` (v1, nouveau)
- `semantic-core-v1-notes.md` (v1, nouveau)
- `semantic_core_demo.py` (modifié v0→v1: `*` → `repeat`)
- `semantic_core_fixture.json` (v0)
- `semantic-core-notes.md` (v0)
- `quickdraw_region_ops_experiment.c` (tag `quickdraw-region-ops-complete`)
- `quickdraw_region_ops.c`, `quickdraw_region_ops.h` (tag `quickdraw-region-ops-complete`)
- `run_quickdraw_region_ops.py` (tag `quickdraw-region-ops-complete`)
- `quickdraw_region_ops_measurements.json` (tag `quickdraw-region-ops-complete`)
- `quickdraw-region-ops-results.md`, `quickdraw-region-ops-notes.md` (tag `quickdraw-region-ops-complete`)
- `Makefile.region-ops`, `quickdraw_bitblt.h` (tag `quickdraw-region-ops-complete`)

---

## Conclusions revendiquées par v1

D'après `semantic-core-v1-notes.md` :

1. **Correctif du défaut v0** : v0 acceptait `count * duration` pour toute `QuantityKind` de famille `"count"`. v1 rejette `*` et introduit `repeat(reuse_count, duration)` qui n'accepte que `ReuseCount`. `run_count` est refusé.
2. **Conversion B0→B1 mesurée** : `semantic_core_conversion.py` mesure la conversion bitmap→runs après échauffement sur 31 échantillons. Les temps d'application viennent de QuickDraw 3 (C).
3. **Seuil N=66 (sparse)** : conversion ~5,11 ms, économie ~77,90 µs/application, premier N favorable = 66.
4. **Seuil N=119 (fragmented)** : conversion ~7,54 ms, économie ~63,41 µs/application, premier N favorable = 119.
5. **Contre-exemple** : le cas fragmenté est défavorable dans le régime court, ne justifie pas une règle universelle.
6. **Limites avouées** : conversion mesurée sur une seule fixture, non-reproductibilité garagaritique du code C, seuil dépend des observations.

D'après `semantic_core_v1_demo.py` (output observé) :

7. `logical_region_preserved: True` affiché pour les deux cas.
8. `break-even: 66` et `break-even: 119`.
9. `repeat(run_count, apply)` rejeté.
10. `conversion/storage + duration` rejeté.

---

## Audit indépendant initial

### 1. Conclusions précises annoncées

| # | Conclusion | Source |
|---|-----------|--------|
| C1 | `repeat` n'accepte que `ReuseCount`, refuse `RunCount` | notes +13 lignes 13-14 |
| C2 | `repeat(run_count, apply_time)` est rejeté | notes +13 lignes 14 |
| C3 | Conversion B0→B1 mesurée sur 31 échantillons après échauffement | notes +13 lignes 30-34 |
| C4 | Les temps d'application proviennent de QuickDraw 3 (C) | notes +13 lignes 32-33 |
| C5 | sparse: conversion ≈5,11 ms, économie ≈77,90 µs/use, N=66 | notes +13 lignes 37-38 |
| C6 | fragmented: conversion ≈7,54 ms, économie ≈63,41 µs/use, N=119 | notes +13 lignes 38-39 |
| C7 | `logical_region_preserved: true` pour les deux cas | demo output ligne 50 |
| C8 | fragmented est un contre-exemple (21 887 runs, 177 200 octets) | notes +13 ligne 27 |
| C9 | La conversion ne change pas l'objet logique, seulement la représentation | notes +13 ligne 68 |

### 2. Données expérimentales supportant chaque conclusion

- **C1-C2** : `semantic_core.py:171-176` — `repeat()` vérifie `count.kind is not REUSE_COUNT`. `_binary("*")` (ligne 200-201) rejette `*` universellement. Testé directement: `repeat(run_count, apply)` → `TypeError`; `repeat(reuse_count, apply)` → OK.
- **C3-C4** : `semantic_core_conversion.py:78-100` — 31 échantillons, échauffement ligne 83-84, médiane ligne 94.
- **C5-C6** : `semantic_core_v1_measurements.json:11,24` — `conversion_median_us`.
- **C7** : `semantic_core_conversion.py:96` — `"logical_region_preserved": True` (codé en dur).
- **C8** : `quickdraw_region_ops_measurements.json` — B1 fragmented result: `runs: 21887`, `storage_bytes: 177200`.

### 3. Éléments qui relèvent de la démonstration du mécanisme sémantique

- `repeat`/`Derived`/`leaves()` : mécanisme de contrainte et de traçabilité.
- Rejet de `run_count * apply_time` : contrainte de type.
- Rejet de `storage + duration` : contrainte de kind.
- `derived_duration` : identité de scénario.
- `leaves()` : extraction des feuilles de provenance.

### 4. Éléments présentés comme résultats physiques sur QuickDraw

- `production_initial_us` (5.281, 5.301) : de l'expérience C (`build_pair_median_ns + op_median_ns`).
- `apply_bitmap_us`, `apply_runs_us` : de l'expérience C (`apply_ns_per_use`).
- `storage_bitmap`, `storage_runs` : de l'expérience C (`result.storage_bytes`).
- `conversion_median_us` (5105.7, 7543.835) : de l'expérience Python (`semantic_core_conversion.py`).
- `logical_region_preserved: true` : affirmation non vérifiée contre QuickDraw 3.

### 5. Conclusions fragiles ou insuffisamment justifiées

- **G1** : `logical_region_preserved: true` pour sparse — la région Python `make_mask` n'est pas identique au résultat B0 du C (aire 1018 vs 990, bbox différent, sha256 différent). Affirmation fausse.
- **G2** : La conversion (Python) et les applis (C) proviennent de programmes, langages, chronomètres et tailles d'échantillon différents. La composition est conceptuelle, pas physique.
- **G3** : La conversion est instable : 4 902–12 259 µs pour sparse (2,5× de variance). Le seuil N=66 pourrait varier de 63 à 158.
- **G4** : Aucune mesure en bout de chaîne : il n'existe pas de course expérimentale unique mesurant « produire B0 → convertir → appliquer B1 N fois ».
- **G5** : L'addition de médianes de sources hétérogènes ne produit ni la médiane du cycle complet, ni une mesure physique directe.

---

## Audit du noyau sémantique

### A. Cohérence du mécanisme

**v0** (`semantic-core-v0:semantic_core.py` ligne 193-206) :
```python
if operator == "*":
    if _is_count(left) and _is_duration(right):
        return Binary(operator, left, right, DURATION, MICROSECONDS)
    if _is_duration(left) and _is_count(right):
        return Binary(operator, left, right, DURATION, MICROSECONDS)
    raise TypeError("multiplication is only count * duration in this prototype")
```

v0 accepte `count * duration` pour **toute** `QuantityKind` dont `family == "count"` : `RunCount`, `TransitionCount`, `ReuseCount`, `ActivePixels`, `BoundingBoxPixels` sont tous acceptés. Le défaut identifié : `run_count * apply_time` est accepté.

**v1** (`semantic_core.py:171-176, 199-201`) :
```python
def repeat(count: Quantity, cost_per_use: Expr) -> Repeat:
    if count.kind is not REUSE_COUNT or count.unit is not COUNT:
        raise TypeError("repeat requires a ReuseCount quantity")
    if not _is_duration(cost_per_use):
        raise TypeError("repeat requires a duration per use")
    return Repeat(count, cost_per_use)
```
Et `*` est universellement rejeté (`_binary`, ligne 200-201).

Tests exécutés (vérifiés):
- `repeat(reuse_count, apply_time)` → **accepté** ✓
- `repeat(run_count, apply_time)` → **rejeté** (`TypeError: repeat requires a ReuseCount quantity`) ✓
- `run_count * apply_time` → **rejeté** ✓
- `transition_count * apply_time` → **rejeté** ✓
- `reuse_count * apply_time` → **rejeté** (doit passer par `repeat`) ✓
- `repeat(reuse_count, storage)` → **rejeté** (le coût doit être une durée) ✓

**Le défaut v0 est correctement résolu** : `run_count * apply_time` est rejeté. Le mécanisme `Repeat` + `derived_duration` + `leaves()` fournit :
- Un `kind: QuantityKind = DURATION`, `unit: Unit = MICROSECONDS` correctement typé.
- Une identité de scénario via `Derived.scenario`.
- Une extraction de provenance via `leaves()` → `provenance`.

### B. Est-ce un « nombre d'occurrences » ou une règle codée spécialement pour ReuseCount ?

`repeat` vérifie `count.kind is not REUSE_COUNT` — c'est une règle codée spécialement pour `ReuseCount`. Ce n'est pas une relation sémantique générale de « nombre d'occurrences » :

> Contre-exemple sans étendre le modèle : un scénario où l'on applique un résultat `N` fois avec `N = run_count` du résultat. Sémantiquement, `N` représente bien « nombre d'occurrences de l'application », mais `repeat(run_count, apply_time)` est **rejeté** car `run_count.kind is RUN_COUNT`, pas `REUSE_COUNT`.

Ceci est une **contrainte délibérative**, pas un défaut : v1 refuse volontairement toute `QuantityKind` autre que `ReuseCount` pour `repeat`, au nom de la précision sémantique. Le notes l'avouent : « Il n'y a toujours ni parser, ni solver, ni simplificateur, ni système de types générale » (notes L19-20).

**Verdict A** : Le noyau sémantique est **cohérent**. La correspondance `LogicalObject → Representation → Quantity → semantic relation → Derived → provenance` constitue une amélioration cohérente par rapport à v0.

---

## Traçabilité des mesures

### Provenance de chaque valeur dans `semantic_core_v1_measurements.json`

| Valeur | Provient de | Programme | Langage | Timer | Échantillons |
|--------|-------------|-----------|---------|-------|-------------|
| `production_initial_us` (5.281) | C JSON : `(b0.build_pair_median_ns + b0.op_median_ns)/1000` = (171+5110)/1000 | `quickdraw_region_ops_experiment.c` | C | `CLOCK_MONOTONIC_RAW` | 7 (médiane = index 3) |
| `apply_bitmap_us` (78.81905) | C JSON : `b0.apply_ns_per_use/1000` (= 78819.05/1000) | `quickdraw_region_ops_experiment.c` | C | `CLOCK_MONOTONIC_RAW` | 7 batchs de 100, median/reuse |
| `apply_runs_us` (0.91924) | C JSON : `b1.apply_ns_per_use/1000` (= 919.24/1000) | `quickdraw_region_ops_experiment.c` | C | `CLOCK_MONOTONIC_RAW` | 7 batchs de 100, median/reuse |
| `storage_bitmap` (16408) | C JSON : `b0.result.storage_bytes` | `quickdraw_region_ops_experiment.c` | C | — | statique |
| `storage_runs` (2392) | C JSON : `b1.result.storage_bytes` | `quickdraw_region_ops_experiment.c` | C | — | statique |
| `conversion_median_us` (5105.7) | **Python** : `statistics.median(31 samples) / 1000` | `semantic_core_conversion.py` | Python 3 | `time.perf_counter_ns` | 31 |
| `conversion_p95_us` (12420.414) | **Python** : `sorted(samples)[-2] / 1000` | `semantic_core_conversion.py` | Python 3 | `time.perf_counter_ns` | 31 |
| `logical_region_preserved` (true) | **Codé en dur** (`semantic_core_conversion.py:96`) | `semantic_core_conversion.py` | Python 3 | — | — |

### Écarts de provenance dans `semantic_core_v1_demo.py`

Le demo (`semantic_core_v1_demo.py:27-40`) enregistre pour **toutes** les feuilles :
```python
context = {
    "platform": "AMD Ryzen AI 9 HX 370 / x86-64 Linux / GCC 16.1.1 -O3",
    "workload": name,           # "sparse_sparse_intersection" — nom construit
    "source": SOURCE,           # "semantic_core_v1_measurements.json"
}
```

**Problèmes de provenance :**

1. **Source unique trompeur** : Le JSON v1 a `"source": "quickdraw_region_ops_measurements.json"` (`semantic_core_v1_measurements.json:3`), mais les valeurs `conversion_*` proviennent de `semantic_core_conversion.py`, pas du JSON C. Aucun champ ne distingue l'origine du code Python.

2. **`production` manque de `phase` et `statistic`** : Contrairement aux feuilles `conversion` (`phase=conversion, statistic=median`) et `apply` (`phase=apply, statistic=median`), la feuille `production` n'a ni `phase` ni `statistic` (`semantic_core_v1_demo.py:32-33`). Impossible de savoir qu'elle est la somme de deux médianes C de 7 échantillons.

3. **Nom de workload construit** : Le nom `sparse_sparse_intersection` n'existe pas dans le JSON C. Le cas C s'appelle `sparse_sparse` (opération `intersect`). Le suffixe `_intersection` est construit par `source_measurements()` (`semantic_core_conversion.py:68`) : `case["name"] + "_intersection"`.

4. **`apply_ns_per_use` n'est pas une médiane directe** : Le C calcule `apply_ns_per_use = apply_batch_median_ns / reuse` (`quickdraw_region_ops_experiment.c:65`), soit la médiane d'un batch de N applis divisée par N. Ce n'est pas la médiane d'applis individuelles. L'étiquette `statistic=median` est approximativement vraie mais trompeuse.

5. **`logical_region_preserved: true` est codé en dur** : `semantic_core_conversion.py:96` fixe `"logical_region_preserved": True` sans comparaison avec le résultat C. L'assertion (`semantic_core_conversion.py:91`) vérifie seulement `runs_mask(to_runs(rows)) == rows` — un auto-test du round-trip Python, **pas** une comparaison avec le bitmap B0 du C.

---

## Identité des objets expérimentaux

### Méthode

Reproduction exacte de `shape()` (SPARSE, FRAGMENTED) et de l'intersection `A AND B` depuis `quickdraw_region_ops_experiment.c:17,33-34`, puis comparaison octet-à-octet avec `make_mask()` de `semantic_core_conversion.py:14-28`. Le C construit `shape(A)=shape(B)` (SPARSE/FRAGMENTED n'utilise pas `rng`), donc l'intersection = la forme elle-même.

### Résultats (checksum FNV-1a et comparaison octet-à-octet)

| Cas | make_mask sha256 | C B0 result sha256 | Octets identiques | Aire | Bbox | Runs |
|-----|-------------------|---------------------|-------------------|------|------|------|
| sparse_sparse | `504138ee...` | `fe3483f6...` | **Non** | 1018 | 125 736 | 36 |
| fragmented | `1a140da9...` | `1a140da9...` | **Oui** | 65 534 | 131 072 | 21 887 |

**Sparse** (`semantic_core_conversion.py:17-22` vs `quickdraw_region_ops_experiment.c:17` SPARSE case) :
- C SPARSE : 18 rectangles de **2 lignes** de haut (`rect(m, y, x, y+2, ...)`), 18 itérations (`i in 0..17`).
- Python make_mask : 36 rectangles de **1 ligne** de haut, 36 itérations (`i in 0..35`).
- Même formule `y = 3 + (i*13)%251`, `x = 5 + (i*47)%492`, largeur `15 + (i%4)*9`, mais 36 vs 18 itérations et 1 vs 2 lignes.
- → **Objets différents.** Aire 1018 ≠ 990. Bbox (3,5,251,512) ≠ (3,5,226,508).

**Fragmented** (`semantic_core_conversion.py:23-27` vs `quickdraw_region_ops_experiment.c:17` FRAGMENTED case) :
- Même formule `((x//3)+(y//3))&1`.
- → **Identité démontrée.** Octets identiques, aire 65 534 = 65 534, 21 887 runs = 21 887 runs.

### Classification

| Cas | Classification |
|-----|----------------|
| `sparse_sparse_intersection` | **Objets différents** |
| `fragmented_fragmented_intersection` | **Identité démontrée** (sha256 identique) |

Le champ JSON `logical_region_preserved: true` (`semantic_core_conversion.py:96`) est **faux pour le cas sparse**.

---

## Compatibilité des mesures

### Composition conceptuelle ≠ mesure physique

**La chaîne revendiquée** (`semantic-core-v1-notes.md` ligne 48-51) :
```
production_initiale + conversion + repeat(N, apply_runs) → with_conversion(N)
production_initiale + repeat(N, apply_bitmap) → without_conversion(N)
```

**États de la chaîne :**

| Étape | Programme | Langage | Timer | Pin CPU | Warmup | Samples |
|-------|-----------|---------|-------|---------|--------|---------|
| production (build_pair + op) | `quickdraw_region_ops_experiment.c` | C | `CLOCK_MONOTONIC_RAW` | Oui (affinité 0) | Oui | 7 |
| conversion (bitmap→runs) | `semantic_core_conversion.py` | Python 3 | `perf_counter_ns` | **Non** | Oui | 31 |
| apply_bitmap | `quickdraw_region_ops_experiment.c` | C | `CLOCK_MONOTONIC_RAW` | Oui | Oui | 7 batchs de 100 |
| apply_runs | `quickdraw_region_ops_experiment.c` | C | `CLOCK_MONOTONIC_RAW` | Oui | Oui | 7 batchs de 100 |

**Problèmes :**

1. **Langage mixte** : la conversion est en Python, le reste en C. Un `to_runs` Python est ~1000× plus lent qu'une implémentation C équivalente. La conversion Python (5 ms) surestime probablement le coût d'une conversion C.

2. **Timer différent** : `perf_counter_ns` (Python) vs `CLOCK_MONOTONIC_RAW` (C). Résolutions et sources d'horloge différentes.

3. **Pin CPU absent pour la conversion** : `run_quickdraw_region_ops.py:38-40` pince le CPU pour le benchmark C, mais `semantic_core_conversion.py` n'effectue aucun pin. La conversion Python peut être dégradée par la migration de processus.

4. **Tailles d'échantillon incompatibles** : 7 (C) vs 31 (Python). Les incertitudes statistiques ne sont pas comparables.

5. **Aucune mesure en bout de chaîne** : le C construit B1 directement (`qro_b1_build` + `qro_b1_op`) sans passer par B0→B1. La conversion Python est une observation isolée, pas une mesure dans la chaîne d'exécution C.

---

## Cohérence statistique

### Addition de médianes

Le seuil est calculé par :
```
T_without(N) = median(prod_C) + N × median(apply_C)
T_with(N) = median(prod_C) + median(conv_Python) + N × median(apply_C)
```

**Médiane de la somme ≠ somme des médianes** (`semantic-core-v1-notes.md` ligne 55 : « Une boucle entière cherche le premier N strictement favorable »).

- `production_initial_us` = `median(build_pair_7) + median(op_7)` — somme de deux médianes.
- `apply_ns_per_use` = `median(batch_7) / reuse` — médiane de batch divisée par le nombre de réutilisations, **pas** médiane d'applis individuelles.
- `conversion_median_us` = `median(conv_31)` — médiane de 31 échantillons Python.

L'addition de ces point-estimates ne produit ni la médiane du cycle complet, ni une mesure physique directe de la stratégie « produire → convertir → appliquer N fois ».

**Classification statistique** : **estimation** basée sur des point-estimates médians, **pas** une mesure de la médiane du cycle.

---

## Vérification du break-even

### Calcul indépendant à partir de `semantic_core_v1_measurements.json`

**Sparse** (`semantic_core_v1_measurements.json:6-11`, `semantic_core_v1_demo.py:16-20`) :

```
T_without(N)  = 5.281 + N × 78.81905
T_with(N)     = 5.281 + 5105.7 + N × 0.91924

T_with < T_without  ⟺  5105.7 < N × (78.81905 - 0.91924) = N × 77.89981
                      ⟺  N > 5105.7 / 77.89981 = 65.542
                      ⟺  N = 66
```

Vérification : N=66 → `5105.7 < 66 × 77.89981 = 5141.39` ✓ ; N=65 → `5105.7 > 65 × 77.89981 = 5063.49` ✗. **Arithmétique correcte.**

**Fragmented** (`semantic_core_v1_measurements.json:19-24`) :

```
T_with(N) < T_without(N)  ⟺  7543.835 < N × (336.54155 - 273.13585) = N × 63.40570
                            ⟺  N > 7543.835 / 63.40570 = 118.977
                            ⟺  N = 119
```

Vérification : N=119 → `7543.835 < 119 × 63.4057 = 7545.28` ✓ ; N=118 → `7543.835 > 7537.87` ✗. **Arithmétique correcte.**

### Unités et signes

- Toutes les durées sont en **microsecondes** (µs). ✓
- `apply_runs < apply_bitmap` dans les deux cas → gain par application **positif**. ✓
- `conversion > 0` → coût fixe de conversion **positif**. ✓
- `production_initial_us` apparaît des deux côtés → **s'annule algébriquement**. ✓
- `break_even` (`semantic_core_v1_demo.py:16-20`) : recherche linéaire de 1 à 100 000. ✓

**Aucune divergence arithmétique.** Le défaut est ailleurs : la validité physique des termes, pas le calcul.

---

## Chaines de transformation réelle

### Sparse : sparse_sparse/intersection

```
production_initiale : C (B0 build_pair + op) → B0 bitmap (aire=990)
     ↓  conversion (Python to_runs)
conversion        : Python (sur make_mask, aire=1018) → runs (36 runs)
     ↓  apply
apply_after       : C (qro_b1_apply) sur B1 builds (aire=990, 36 runs)
```

**Problème** : le bitmap converti (aire=1018) ≠ le résultat B0 du C (aire=990). La conversion Python opère sur un **objet différent**. Les runs produits par `to_runs(make_mask)` partagent le même nombre de runs (36) mais pas le même contenu. L'application B1 du C n'est pas l'application des runs produits par la conversion Python.

### Fragmented : fragmented_fragmented/intersection

```
production_initiale : C (B0 build_pair + op) → B0 bitmap (aire=65 534)
     ↓  conversion (Python to_runs)
conversion        : Python (sur make_mask = B0 result) → runs (21 887 runs)
     ↓  apply
apply_after       : C (qro_b1_apply) sur B1 builds (aire=65 534, 21 887 runs)
```

**Identité démontrée** : make_mask = B0 result (octets identiques). Mais le **langage** de la conversion (Python) ≠ celui de l'application (C). La conversion n'est toujours pas mesurée dans la chaîne C.

---

## Findings

### F1 — CRITICAL : `logical_region_preserved: true` est faux pour le cas sparse

**Affirmation auditée** : `semantic_core_conversion.py:96` — `"logical_region_preserved": True` et la démo `semantic_core_v1_demo.py:50` — `Region identity preserved: True`.

**Preuve** :
- `semantic_core_conversion.py:14-28` — `make_mask("sparse_sparse_intersection")` crée 36 rectangles de 1 ligne (`for i in range(36)`, `y` seul, pas `y+1`).
- `quickdraw_region_ops_experiment.c:17` — le cas `SPARSE` crée 18 rectangles de 2 lignes (`rect(m,y,x,y+2,...)`, `for i in range(18)`).
- Comparaison octet-à-octet : les bitmaps diffèrent. Aire 1018 (Python) vs 990 (C). Bbox (3,5,251,512) vs (3,5,226,508). sha256 différent.
- L'assertion (`semantic_core_conversion.py:91`) vérifie seulement `runs_mask(to_runs(rows)) == rows` — un auto-test du round-trip Python. Elle **n'ignore pas** le résultat C.

**Conséquence** : la conversion pour sparse est mesurée sur un bitmap qui n'est **pas** le résultat B0 de QuickDraw 3. La provenance de la conversion ne peut pas être associée à l'objet logique revendiqué.

**Ce qu'on peut conclure malgré le problème** : pour le cas fragmented (où l'identité est démontrée), la conversion est sur le bon bitmap. Pour sparse, la conversion est sur un bitmap différent mais de propriétés statistiques similaires (36 runs, même univers 512×256).

**Preuve supplémentaire nécessaire** : comparer le checksum FNV-1a du C (`quickdraw_region_ops_experiment.c:26` `hash_bytes`) avec un hash du bitmap `make_mask`, ou faire produire le B0 par le code C et le comparer directement.

---

### F2 — MAJOR : La conversion est mesurée dans un langage/programme différent des applis

**Affirmation auditée** : `semantic-core-v1-notes.md` ligne 33 — « Les temps d'application viennent des mesures C de QuickDraw 3 » ; la conversion provient de `semantic_core_conversion.py` (Python).

**Preuve** :
- `semantic_core_conversion.py:87-89` — `time.perf_counter_ns()` en Python, 31 échantillons.
- `quickdraw_region_ops_experiment.c:65` — `CLOCK_MONOTONIC_RAW` en C, 7 échantillons (malgré `"samples": 9` dans le JSON, ligne 40 — `enum{S=9}` mais les arrays sont `bt[7]`, `ot[7]`, `at[7]`).
- `run_quickdraw_region_ops.py:38-40` — le benchmark C est piné sur un CPU logique (`os.sched_setaffinity`), mais `semantic_core_conversion.py` n'effectue **aucun pin**.

**Conséquence** : la conversion Python (5 ms) surestime probablement le coût d'une conversion C native. Un `to_runs` C serait probablement ~100× plus rapide (16 KB à scanner), ce qui rendrait le seuil N=66 invalide si la conversion étaient mesurée en C.

**Preuve supplémentaire nécessaire** : implémenter `to_runs` en C dans le benchmark QuickDraw 3 et mesurer la conversion dans la même chaîne d'exécution.

---

### F3 — CRITICAL : La conversion est instable, le seuil varie de 2,5×

**Affirmation auditée** : `semantic-core-v1-notes.md` ligne 40 — « Ces nombres peuvent varier entre exécutions ». Le seuil N=66 est présenté comme un résultat.

**Preuve** : exécution du script `semantic_core_conversion.py` 5 fois (restauration du JSON entre chaque) :

```
sparse trial 0: conversion_median_us=12259.040  → seuil ≈ 158
sparse trial 1: conversion_median_us=4895.204    → seuil ≈ 63
sparse trial 2: conversion_median_us=4904.872    → seuil ≈ 63
sparse trial 3: conversion_median_us=4973.801    → seuil ≈ 64
sparse trial 4: conversion_median_us=4902.799    → seuil ≈ 63
```

Le premier essai (12 259 µs) est 2,5× plus lent que les suivants (~4 900 µs). Le seuil varie donc de **N=63 à N=158**. Le seuil committé (N=66) correspond à une mesure de ~5 106 µs, mais une autre exécution peut facilement produire N=158.

**Conséquence** : le seuil N=66 pour sparse n'est pas reproductible sans qualification. Le `conversion_p95_us` (12 420 µs) suggère que la conversion a une forte variance, mais la médiane elle-même est instable d'une exécution à l'autre.

**Preuve supplémentaire nécessaire** : mesurer la conversion avec le même pin CPU, warmup et nombre d'échantillons que le benchmark C, sur plusieurs exécutions pour quantifier l'incertitude.

---

### F4 — MAJOR : Aucune mesure en bout de chaîne

**Affirmation auditée** : `semantic-core-v1-notes.md` ligne 32 — « La conversion Python est une observation distincte » ; la démo calcule un break-even à partir de ces observations.

**Preuve** :
- Le C (`quickdraw_region_ops_experiment.c:24-62`) ne mesure **aucune** conversion B0→B1. B1 est construit indépendamment via `qro_b1_build` (depuis le masque d'entrée A), pas par conversion de B0.
- `semantic_core_conversion.py:82-91` mesure `to_runs(make_mask(...))` — une conversion Python sur un masque reconstruit.
- Aucune expérience ne mesure : « produire B0 (C) → convertir B0→B1 (Python) → appliquer B1 (C) » dans une seule chaîne d'exécution.

**Conséquence** : le break-even est une **composition conceptuelle** de mesures hétérogènes. Le nombre `5105.7 + N × 0.919` n'est pas une mesure physique du temps total de la stratégie « convertir puis appliquer ». C'est une estimation basée sur des point-estimates de programmes différents.

---

### F5 — MAJOR : La provenance ne distingue pas l'origine Python vs C

**Affirmation auditée** : Toutes les feuilles du demo (`semantic_core_v1_demo.py:27-40`) portent `source = "semantic_core_v1_measurements.json"`.

**Preuve** : `semantic_core_v1_measurements.json:3` — `"source": "quickdraw_region_ops_measurements.json"` (le fichier C). Mais `conversion_median_us` provient de `semantic_core_conversion.py` (Python), pas de ce fichier C. Le JSON ne contient aucun champ `conversion_source` ou équivalent. La fonction `source_measurements()` (`semantic_core_conversion.py:57-75`) lit les valeurs C mais ne trace pas leur origine.

**Conséquence** : un lecteur ne peut pas distinguer, à partir du JSON ou de la provenance du demo, que la conversion provient d'un programme Python différent. La chaîne de provenance est **partiellement correcte mais trompeuse**.

**Preuve supplémentaire nécessaire** : ajouter un champ `measurement_program` ou `conversion_source` dans le JSON pour chaque valeur.

---

### F6 — MAJOR : La feuille `production` manque de `phase` et `statistic`

**Affirmation auditée** : `semantic_core_v1_demo.py:32-33` — `production = measured(...)` sans `phase=` ni `statistic=`.

**Preuve** : La provenance affichée (`semantic_core_v1_demo.py:59`) montre pour production : `Duration@measured:semantic_core_v1_measurements.json (platform=..., workload=...)` — aucun `phase` ni `statistic`. Alors que `conversion` a `phase=conversion, statistic=median` et `apply` a `phase=apply, statistic=median`.

**Conséquence** : impossible de savoir que `production_initial_us` est la somme de deux médianes C (`build_pair_median_ns` + `op_median_ns`), chacune sur 7 échantillons. L'absence de `phase=build_pair` et `phase=boolean_op` rompt la traçabilité.

---

### F7 — MINOR : Le benchmark C rapporte `"samples": 9` mais mesure 7 échantillons

**Affirmation auditée** : `quickdraw_region_ops_measurements.json` — `"samples": 9`.

**Preuve** : `quickdraw_region_ops_experiment.c:39` — `enum{S=9}` et `printf("...\"samples\":%d...", S)`. Mais les arrays de timing sont `bt[7], ot[7], at[7]` (ligne 55) et la médiane est `bt[3]` (index 3 de 7, ligne 64). Le champ rapporte 9 mais 7 sont collectés.

**Conséquence** : discrétion mineure. La taille d'échantillon effective est 7, pas 9. N'affecte pas le résultat final mais rend la reproductibilité moins précise.

---

### F8 — MINOR : `apply_ns_per_use` n'est pas une médiane d'applis individuelles

**Affirmation auditée** : `quickdraw_region_ops_experiment.c:65` — `apply_ns_per_use = apply_batch_median_ns / reuse`.

**Preuve** : `apply_ns_per_use` = `median(7 batchs de 100 applis) / 100`. Ce n'est pas `median(700 applis individuelles)`. L'étiquette `statistic=median` du demo (`semantic_core_v1_demo.py:38-40`) est approximativement vraie mais ne capture pas cette nuance.

**Conséquence** : la valeur reportée comme "médiane de l'application" est techniquement une médiane de batch divisée par le nombre de réutilisations. L'incertitude statistique est donc différente d'une mesure directe par application.

---

### F9 — NOTE : `repeat` est une règle codée spécialement pour `ReuseCount`

**Affirmation auditée** : `semantic_core.py:172` — `count.kind is not REUSE_COUNT`.

**Preuve** : `repeat` n'accepte que `REUSE_COUNT`, rejetant `RUN_COUNT` (et toutes les autres kinds de la famille `"count"`). Ce n'est pas une relation sémantique générale de « nombre d'occurrences ».

> Contre-exemple sans étendre le modèle : `repeat(run_count_qty, apply_time)` où `run_count_qty` est une `Quantity(RUN_COUNT)`. Sémantiquement, cela représente « appliquer N fois » avec N = nombre de runs. Mais `repeat` le rejette. La relation est une règle spéciale à `ReuseCount`.

**Conséquence** : ce choix limite la généralité de `repeat` mais corrige correctement le défaut v0. C'est un choix de conception, admis dans les notes (L19-20).

---

### F10 — N/A (positive finding) : L'arithmétique du seuil est correcte

**Affirmation auditée** : N=66 (sparse) et N=119 (fragmented) sont les premiers entiers strictement favorables.

**Preuve** : calcul indépendant (section 12 ci-dessus) — les deux seuils sont arithmétiquement corrects à partir des valeurs du JSON. Aucun problème d'unités, de signes ou de termes communs.

---

## Verdict sur Semantic Core v1

**Verdict : Oui, amélioration cohérente.**

Le noyau sémantique v1 (`LogicalObject → Representation → Quantity → Repeat/Derived → provenance`) constitue une amélioration cohérente par rapport à v0 :

- Le défaut v0 (`count * duration` accepte n'importe quel kind de la famille `"count"`) est **correctement résolu** : `*` est universellement rejeté (`semantic_core.py:200-201`), et `repeat` n'accepte que `REUSE_COUNT` (`semantic_core.py:172`).
- `Derived` (`derived_duration`) donne une identité de scénario à chaque expression de cycle de vie.
- `leaves()` (`semantic_core.py:88,108,128,145,163`) expose la provenance de chaque feuille.
- Les contraintes de kind/unité (`storage + duration` rejeté) sont cohérentes.

**Limite admise** : `repeat` est une règle codée spécialement pour `ReuseCount` (F9), pas une relation sémantique générale. C'est un choix de conception, pas un défaut.

---

## Verdict sur l'expérience B0→B1

**Verdict : Composition conceptuelle, pas mesure physique directe.**

- La conversion B0→B1 **n'existe pas dans l'expérience C** (`quickdraw_region_ops_experiment.c`): B1 est construit indépendamment via `qro_b1_build`, pas par conversion de B0.
- `semantic_core_conversion.py` mesure une conversion Python (`to_runs`) sur un masque `make_mask` :
  - **Identique au B0 résultat pour fragmented** (F1 : identité démontrée, octets identiques).
  - **Différent du B0 résultat pour sparse** (F1 : aire 1018 vs 990, bbox différent, sha256 différent).
- La composition mélange Python (`perf_counter_ns`, 31 échantillons, pas de pin CPU) et C (`CLOCK_MONOTONIC_RAW`, 7 échantillons, pin CPU).
- Aucune course en bout de chaîne n'existe.

→ L'expérience fournit une **observation distincte** de la conversion, mais **pas** une mesure physique de la stratégie exécutable complète.

---

## Verdict sur N=66 / N=119

| Cas | Classification | Justification |
|-----|----------------|----------------|
| **N=66 (sparse)** | **Estimation plausible mais non démontré** | Arithmétique correcte, mais : (1) la conversion est sur un bitmap différent de B0 (F1), (2) la conversion est en Python pas C (F2), (3) la conversion est instable 2,5× (F3), (4) aucune mesure en bout de chaîne (F4). |
| **N=119 (fragmented)** | **Estimation plausible mais non démontré** | Plus solide : l'identité du bitmap est démontrée (F1). Mais : (1) conversion en Python pas C (F2), (2) instabilité de la conversion, (3) aucune mesure en bout de chaîne (F4), (4) addition de médianes (F4 notes §11). |

---

## Ce que le projet a réellement appris

Même si les seuils physiques s'avéraient invalides, Semantic Core v1 a apporté des connaissances réelles :

1. **Distinction sémantique ReuseCount vs RunCount** : v0 confondait "nombre de runs dans le résultat" et "nombre de fois qu'on réutilise le résultat." v1 sépare ces concepts par le kind `ReuseCount`, bloquant les compositions incorrectes comme `run_count * apply_time`. Cette distinction est **validée directement par le code**.

2. **Traçabilité de provenance** : `leaves()` expose que `production` (phase de build), `conversion` (phase de conversion), et `apply` (phase d'application) sont des observations distinctes. Cette visibilité est **elle-même la découverte** : l'audit révèle que la provenance ne distingue pas Python de C (F5), mais c'est précisément parce que le système **exige** une provenance que ce défaut est visible et auditable.

3. **Structure du problème de break-even** : le modèle `production + conversion + N × apply_after` vs `production + N × apply_before` isole correctement le coût fixe de conversion et le gain marginal par application. La production s'annule — une propriété structurelle non évidente dans un script de benchmark ad hoc.

4. **Nature du contre-exemple** : le cas fragmented (N=119, gain d'application modeste 63 µs vs 7,5 ms de conversion) montre que B0→B1 n'est **pas** universellement bénéfique. C'est une connaissance sémantique réelle : le choix de représentation dépend du résultat, pas seulement du format d'entrée.

5. **Diagnostic de la composition** : l'audit montre que le système de provenance révèle immédiatement le problème de la conversion Python vs C — l'origine du code n'est pas tracée. Un système de types plus général aurait pu exiger une annotation `runtime=Python` vs `runtime=C`, rendant la fracture visible dès la construction.

---

## Preuves supplémentaires nécessaires

1. **Pour établir l'identité du spécimen** (sparse) : comparer le checksum FNV-1a du C (`quickdraw_region_ops_experiment.c:26`, `hash_bytes`) avec un hash du bitmap `make_mask` de `semantic_core_conversion.py:14-22`, ou corriger `make_mask` pour reproduire exactement `shape(SPARSE)` du C (`quickdraw_region_ops_experiment.c:17`, 18 rectangles de 2 lignes).

2. **Pour établir un break-even physique** : implémenter la conversion B0→B1 en C dans le benchmark QuickDraw (`qro_b0_to_b1` ou par `qro_b1_build` depuis le masque B0), la mesurer sur **le même bitmap B0 résultat** avec le même timer, pin CPU et warmup, puis mesurer `production + conversion + N × apply` en une seule chaîne.

3. **Pour une provenance complète** : ajouter un champ `measurement_program` (et `timer`, `cpu_pinned`, `warmup_samples`) dans `semantic_core_v1_measurements.json` pour chaque valeur, distinguant clairement les mesures C de `quickdraw_region_ops_experiment.c` et les mesures Python de `semantic_core_conversion.py`.
