# Expédition QuickDraw 3 — résultats

## Validation

Le corpus contient 12 800 paires déterministes × opérations, couvrant
`rect_rect`, `sparse_sparse`, `sparse_dense`, `dense_dense`,
`fragmented_fragmented`, `vertically_stable`, `vertically_unstable`,
`empty/full`, plus 3 000 paires pseudo-aléatoires reproductibles. B0, B1 et
B2 produisent exactement le masque oracle pour les quatre opérations.
ASan/UBSan passent. Le benchmark compare aussi le checksum du bitmap après
application entre les trois variantes.

Plateforme : AMD Ryzen AI 9 HX 370, Linux x86-64, GCC 16.1.1, `-O3`, glibc
2.44, un CPU logique fixé. Un passage complet d'échauffement précède le
passage enregistré. Les working sets sont cache-hot.

## Résultats représentatifs

Les temps ci-dessous sont des médianes en microsecondes ; `build` est la
construction des deux entrées, `op` la combinaison, `apply` une application
du résultat déjà construit. Les valeurs complètes sont dans
`quickdraw_region_ops_measurements.json`.

| workload/opération | B0 combinaison | B1 combinaison | B2 combinaison | application B0/B1/B2 |
|---|---:|---:|---:|---:|
| sparse_sparse / intersection | 5,2 µs | 1,6 µs | 92,8 µs | 81,2 / 0,95 / 74,2 µs |
| sparse_dense / union | 5,6 µs | 5,3 µs | 151,5 µs | 75,8 / 22,1 / 100,2 µs |
| dense_dense / union | 5,5 µs | 5,0 µs | 154,7 µs | 76,3 / 20,7 / 100,5 µs |
| fragmented / intersection | 5,5 µs | 108,1 µs | 150,2 µs | 346,1 / 277,2 / 372,4 µs |
| vertically_stable / union | 5,3 µs | 3,9 µs | 105,8 µs | 53,9 / 2,4 / 74,5 µs |

Les valeurs varient légèrement entre exécutions ; les JSON sont la source
exacte. B0 a un coût d'opération presque constant sur l'univers de 512×256.
B1 est très rapide lorsque la fusion de runs reste petite, mais son résultat
fragmenté atteint 177 200 octets et son opération devient comparable à
l'application. B2 reste compact : le résultat fragmented/intersection ne
demande que 1 416 octets, mais sa fusion d'événements est plus coûteuse dans
cette réimplémentation portable.

Les opérations ne sont pas équivalentes selon leur résultat : sur les paires
identiques, `A-B` et XOR peuvent produire le vide, rendant l'application
quasi nulle pour B1 ; une union sparse/dense produit au contraire 344 runs et
fait monter l'application B1 à environ 22 µs.

## Cycle de vie

Les profils sont conservés dans chaque cas par le champ `reuse`. `reuse=1`
correspond au régime build-once/apply-once ; les valeurs 20, 50 et 100
représentent build-once/apply-many. Le régime `dynamic_clip` est décrit par la
même opération avec peu de réutilisations : son coût pertinent est alors
`build(A)+build(B)+op+apply`, et non le seul temps d'application.

Sur `sparse_sparse/intersection`, B0 combine en environ 5 µs mais applique en
81 µs, B1 combine en 1,6 µs et applique en 0,95 µs, tandis que B2 combine en
93 µs et applique en 74 µs. B0 n'est donc pas le meilleur choix du cycle de
vie même s'il est le meilleur mécanisme de combinaison brute dans ce cas.
Sur `fragmented/intersection`, B0 combine et applique rapidement, B1 paie
son immense résultat de runs et B2 paie la fusion mais conserve un stockage
compact. Le choix dépend donc de l'opération et du nombre d'applications,
pas seulement de la forme d'entrée.

## Substitution

Aucun B3 adaptatif n'a été ajouté. Les mesures B0–B2 suffisent à établir la
substitution concrète suivante : une stratégie appropriée pour combiner une
région n'est pas nécessairement appropriée pour l'appliquer ensuite. Une
conversion B0→B1 ou B2→B1 pourrait être intéressante pour un résultat sparse
réutilisé, mais elle n'a pas été implémentée ici ; son point d'amortissement
reste donc inconnu. Cette limite est préférable à un seuil ajusté sur les
seuls workloads présents.

## Perspective historique

- Structurellement pertinent : bounding boxes, spécialisation des régions
  vides/rectangulaires, fusion de flux ordonnés, états intérieur/extérieur,
  émission différentielle du résultat et croissance explicite du tampon.
- Adapté au contexte historique : cinq scans temporaires sur la pile, points
  16 bits, `32767`, longues et mots 68000, gestion manuelle de la mémoire.
- Battu sur la plateforme moderne dans cette réimplémentation : la combinaison
  bitmap B0 est beaucoup plus régulière et rapide que B2 sur l'univers testé.
- Indéterminé : performance du code 68000 original, coût réel de la croissance
  du handle QuickDraw et combinaison de plusieurs régions dans les chemins
  historiques complets.

## Limites et reproduction

Une seule région résultat, quatre opérations, univers monochrome fixe, pas de
chaînes de composition ni de conversion mesurée. La représentation B2 est
sémantiquement inspirée de `RgnOp.a`, mais n'est pas son assembleur exécuté.
Les métriques sont physiques et locales à la plateforme documentée.

```sh
make -f Makefile.region-ops test
python3 -B run_quickdraw_region_ops.py
python3 -m json.tool quickdraw_region_ops_pre_b3.json >/dev/null
python3 -m json.tool quickdraw_region_ops_measurements.json >/dev/null
```
