# Expédition QuickDraw 2 — résultats régions et clipping

## Expérience

Le contrat exécuté est un `srcCopy` monochrome entre bitmaps distincts, limité
par une région destination. L'oracle examine chaque pixel indépendamment. G0
stocke un masque 1 bit complet, G1 des runs complets par scanline, et G2 les
changements verticaux/inversions horizontales observés dans QuickDraw. G2
rejoue une scanline et fusionne ce masque dans la copie ; le cas rectangle
délègue directement au backend R3 figé de QuickDraw 1.

G2 reprend la sémantique du flux historique, pas son layout binaire exact. Les
octets rapportés incluent les structures C natives et les payloads demandés,
mais pas l'overhead interne éventuel de l'allocateur.

Le corpus contient 3 227 cas déterministes : largeurs 1, 7, 8,
15/16/17, 31/32/33, 63/64/65, 127 et 255 ; régions vide, pleine,
rectangulaire, sparse, dense irrégulière, fragmentée, fine et pseudo-aléatoire ;
intersections complètes, partielles et disjointes ; strides et alignements
source/destination distincts ; trois grands cas dirigés ; puis 3 000 cas
pseudo-aléatoires. G0–G3 sont bit-identiques à l'oracle. ASan et UBSan ne
signalent aucune erreur.

Plateforme : AMD Ryzen AI 9 HX 370, Linux x86-64, GCC 16.1.1 `-O3`, glibc
2.44, processus fixé au CPU logique 0. Neuf batches sont mesurés après un tour
d'échauffement complet ; la table rapporte les médianes. Les working sets sont
réutilisés et majoritairement chauds.

## Mesures

Temps en microsecondes ; `apply` est le temps d'une application d'une région
déjà construite. `reuse100` additionne la médiane de construction à cent fois
la médiane d'application : c'est une combinaison descriptive, pas une mesure
atomique.

| workload | stratégie | build | apply | reuse100 | stockage |
|---|---:|---:|---:|---:|---:|
| rectangle | G0 bitmap | 356,2 | 111,55 | 11 511 | 65 576 o |
|  | G1 runs | 817,0 | 18,84 | 2 701 | 7 152 o |
|  | G2 transitions | 633,9 | 16,03 | 2 237 | 40 o |
|  | G3 hybride | 632,5 | 16,02 | 2 235 | 72 o |
| sparse_complex | G0 bitmap | 254,0 | 78,70 | 8 124 | 65 576 o |
|  | G1 runs | 715,9 | 1,41 | 857 | 4 440 o |
|  | G2 transitions | 951,6 | 77,30 | 8 682 | 234 o |
|  | G3 hybride | 1 280,5 | 1,41 | 1 422 | 4 464 o |
| dense_complex | G0 bitmap | 416,2 | 185,07 | 18 923 | 65 576 o |
|  | G1 runs | 887,6 | 43,66 | 5 254 | 9 568 o |
|  | G2 transitions | 1 125,6 | 193,93 | 20 519 | 7 486 o |
|  | G3 hybride | 1 610,2 | 43,06 | 5 916 | 9 592 o |
| checker_fragmented | G0 bitmap | 331,9 | 188,09 | 19 141 | 65 576 o |
|  | G1 runs | 868,0 | 772,15 | 78 083 | 528 440 o |
|  | G2 transitions | 1 053,7 | 190,82 | 20 136 | 2 090 o |
|  | G3 hybride | 983,4 | 189,96 | 19 979 | 65 608 o |
| thin | G0 bitmap | 259,5 | 102,35 | 10 495 | 65 576 o |
|  | G1 runs | 725,0 | 6,95 | 1 420 | 8 248 o |
|  | G2 transitions | 966,2 | 105,89 | 11 555 | 6 186 o |
|  | G3 hybride | 1 323,1 | 6,95 | 2 018 | 8 272 o |
| tiny_ui | G0 bitmap | 11,6 | 3,99 | 411 | 2 344 o |
|  | G1 runs | 28,9 | 2,76 | 305 | 2 112 o |
|  | G2 transitions | 38,0 | 4,20 | 458 | 342 o |
|  | G3 hybride | 51,9 | 2,76 | 328 | 2 136 o |

Les percentiles élevés, débits utiles, compteurs de runs/transitions,
allocations et checksums sont conservés dans
`quickdraw_regions_measurements.json`.

## Substitution guidée par les mesures

Le relevé préservé `quickdraw_regions_pre_g3.json` a été produit avec G0–G2
seuls. Il montre que G1 est très rapide pour 36 à 677 runs, mais que le damier
à 65 536 runs inverse temps et mémoire : 772,15 µs et 528 440 octets, contre
188,09 µs et 65 576 octets pour G0 dans le relevé final.

G3 a donc été ajouté après observation. Sa règle, définie sans seuil calibré,
est : rectangle direct ; sinon choisir entre runs et bitmap la représentation
dont le stockage calculé est le plus petit. Il choisit les runs pour sparse,
dense, thin et tiny, et le bitmap pour le damier. Il obtient ainsi la latence
d'application de la famille retenue. En contrepartie, son scan de décision
renchérit la construction : G3 perd face à G0 dans tous les cas `single_use`
mesurés. La substitution est utile pour une région réutilisée, pas universelle.

## Interprétation et perspective historique

- Toujours structurellement pertinent : bounding-box rejection, rectangle
  spécialisé, coordonnées ordonnées, encodage des changements entre
  scanlines, état d'une scanline et fusion du masque avec l'opération bitmap.
- Remplacé avantageusement ici : pour une région sparse déjà construite, des
  runs explicites appelant le backend moderne évitent le scan de la bounding
  box et battent largement notre parcours G2.
- Probablement lié au Macintosh/68000 : coordonnées et sentinelles 16 bits,
  alignement du masque sur mots 16 bits, opérations par longs 32 bits et
  déroulage de la boucle de copie.
- Indéterminé : performance d'une réimplémentation G2 reproduisant fidèlement
  la fusion par mots du source, coût de combinaison de plusieurs régions, et
  classement sur un 68000 réel. Le POC ne permet pas d'attribuer les écarts à
  une cause microarchitecturale précise.

Le résultat principal est un compromis à trois axes. G2 préserve très bien la
mémoire (2 090 octets sur le damier, contre 65 576 pour G0), G1 minimise le
travail d'application sur les formes à peu de runs, et G0 minimise souvent le
coût de construction. La densité seule n'explique pas ce classement : le
nombre de runs et la stabilité entre scanlines changent séparément les coûts.

## Limites et reproduction

Une seule région, `srcCopy`, bitmaps distincts, pas de scaling ni construction
géométrique. Les temps sont propres à la plateforme ci-dessus et aux working
sets chauds. G2 est une réimplémentation des mécanismes, pas l'assembleur
historique exécuté.

```sh
make -f Makefile.regions test
python3 -B run_quickdraw_regions.py
python3 -m json.tool quickdraw_regions_pre_g3.json >/dev/null
python3 -m json.tool quickdraw_regions_measurements.json >/dev/null
```
