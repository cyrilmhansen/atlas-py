# Semantic Core v0 — notes

Cette expérience ne représente aucun programme, CFG, AST ou instruction. Elle
représente seulement quelques faits déjà nécessaires dans QuickDraw 1–3.

## Ce qui est représenté

- `LogicalObject("R_sparse", "Region")` est l'objet logique.
- `Representation(R, "bitmap_mask"/"runs"/"transitions")` porte trois vues
  expérimentales du même objet.
- `Quantity` transporte une valeur ou un symbole, un `QuantityKind`, une
  `Unit`, un sujet et une `Provenance`.
- `Binary` conserve `+`, `-`, `*` et `/` sans parser ni simplificateur.

`active_pixels / bbox_pixels` produit `RegionDensity`. Les durées peuvent être
additionnées ; `reuse_count * apply_time` produit une durée ; une addition
entre `RunCount` et `Duration`, ou entre `PersistentStorage` et `Duration`, est
rejetée. Les unités seules ne décident donc pas de la compatibilité.

Les valeurs de la fixture viennent de `quickdraw_region_ops_measurements.json`.
Elles restent des mesures contextualisées par plateforme, workload, opération
et statistique ; elles ne deviennent pas des propriétés universelles de B0,
B1 ou B2.

## Ce qui paraît naturel

La séparation objet logique/représentation, la distinction kind/unité, la
provenance et l'expression symbolique du cycle de vie correspondent directement
aux expériences. La densité et `build + op + N * apply` sont exprimables avec
très peu de mécanisme.

## Ce qui paraît artificiel ou limité

Les règles d'arithmétique sont locales et incomplètes. Elles ne représentent
pas toutes les opérations QuickDraw, ne modélisent pas les intervalles ou
l'incertitude, et ne calculent aucun seuil de conversion. `QuantityKind` est un
vocabulaire local QuickDraw, pas une ontologie générale.

Restent explicitement hors périmètre : vocabulaire inter-domaines, découverte
depuis le code, choix de représentation, relations approximatives,
multi-plateforme, entiers machine, overflow, persistance et optimisation
d'expressions.

Reproduction :

```sh
python3 -B semantic_core_demo.py
```
