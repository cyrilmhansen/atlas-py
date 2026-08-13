# Semantic Core v1.1 — conversion native B0 → B1

## Périmètre

Cette correction ne modifie ni Semantic Core v1 ni ses JSON historiques. Elle
réexécute uniquement la question physique dans un même harness C :

```text
inputs → qro_b0_build/op → résultat B0 exact → qro_b1_build → application
```

Le résultat B0 passé à `qro_b1_build` est celui produit par l'intersection
B0 mesurée ; aucune reconstruction depuis le nom du workload n'intervient.
Les hash canoniques B0/B1 sont identiques dans les deux cas et l'application
est également bit-identique.

## Protocole

`run_semantic_core_v1_native.py` compile et exécute le même programme C avec
`-O3 -DNDEBUG -std=c11 -Wall -Wextra -Wpedantic`, demande le CPU 0, utilise
`CLOCK_MONOTONIC_RAW`, un échauffement et 31 échantillons. Les applications
sont mesurées par lots de 100 puis rapportées par utilisation. ASan/UBSan
exécute le même harness séparément. Les détails et les SHA-256 des sources
sont dans `semantic_core_v1_native_measurements.json`.

## Confirmed

- La conversion native transforme bien le résultat B0 réel de l'opération en
  une représentation B1 de la même région logique.
- Les mesures composantes sont homogènes : production B0, conversion,
  application B0 et application B1 viennent du même exécutable et du même
  protocole.
- Pour `sparse_sparse/intersection`, les médianes sont environ 526,7 µs de
  conversion, 78,8 µs/application B0 et 0,90 µs/application B1. Le premier
  entier strictement favorable selon les point-estimates est `N=7`.
- Pour `fragmented_fragmented/intersection`, elles sont environ 246,4 µs,
  333,1 µs et 269,8 µs. Le premier entier calculé est `N=4`.
- Le cycle end-to-end confirme nettement le cas sparse à `N=6` et `N=7`.
  Pour fragmented, `N=3` reste défavorable et `N=4` est pratiquement à
  égalité (la mesure directe est légèrement défavorable) : la frontière est
  donc bruitée et ne valide pas un entier physique stable.

## Disproved / corrigé

- Les seuils v1 `N=66` et `N=119` ne sont pas des break-even physiques
  QuickDraw démontrés : la conversion v1 était Python et son fixture sparse
  ne correspondait pas au résultat C QuickDraw 3.
- La valeur `samples=9` signalée dans l'ancien JSON QuickDraw 3 n'est pas
  cohérente avec le protocole C observé, qui chronomètre 7 observations dans
  ce relevé historique. Le nouveau harness déclare et exécute explicitement
  31 échantillons ; il ne réécrit pas l'ancien artefact.

## Unknown

- La stabilité de la frontière fragmented demanderait davantage de répétitions
  ou un protocole de bruit plus ambitieux ; cette correction ne le construit
  pas.
- Le coût des allocations, d'autres tailles et d'autres conversions reste
  non mesuré.
- Semantic Core ne relie toujours pas un compteur d'occurrences à l'événement
  précis qu'il compte ; la validité de `repeat(reuse_count, build_time)` reste
  hors périmètre.

La conclusion ne nécessite pas de modifier Semantic Core lui-même : elle
corrige les preuves physiques qui alimentaient v1.
