# QuickDraw — régions et clipping de `RgnBlt`

## Provenance

Miroir historique read-only : <https://github.com/jrk/QuickDraw>, commit
`6377ec5d89735a11b3f6e1ae728f555936c7583f` (2010-07-20), publié comme le
source QuickDraw de Bill Atkinson provenant du Computer History Museum.
Notice `COPYRIGHT.TXT` : matériau copyright Apple Inc. (1984), disponible
uniquement pour usage non commercial.

SHA-256 des specimens étudiés :

- `Regions.a` : `e673b7a31f029541ccfbe0415d6cf52fd60dd17cd2f936c5e8605e24baae2748`
- `RgnOp.a` : `900364197e48f0445361d50839d844afc632b4942ac163cc55783a476f0abb6c`
- `SeekRgn.a` : `066b2e232133bebb8e6110479423f0d4f476924136ec9a0ea9e20d37685edf67`
- `RgnBlt.a` : `16c400510330c67c6db2b0e96601c3d9358e5ed2f13ee3c1319e7e765b06ea7f`
- `PackRgn.a` : `67a0efddbd84ef5beaeb2adddfe53f0dbe19b4ac6b21dd68820226e7605b0727`
- `GrafTypes.a` : `2d621b5233dd1f61c47e00514bf572c99b9338b66232b92aec04cbc4921e974e`
- `QuickDraw.p` : `c1d3590c448e4e0ed536cf701e0d1f23acaa39e054cb185dfbb91929fc96a63d`
- `COPYRIGHT.TXT` : `4d7a98ac9439bfb5ca9cd48928f62f9354de5073b1dfe8f14266015d57a19aaa`

Les sources historiques restent hors du dépôt et ne sont pas copiées dans les
réimplémentations.

## Représentation réellement observée

Une région est un handle vers un bloc commençant par un `rgnSize` 16 bits,
puis une bounding box `top,left,bottom,right`; les données commencent à
l'octet 10 (`GrafTypes.a:119-123`, `QuickDraw.p:120-129`). Une région vide ou
rectangulaire a exactement 10 octets : la bounding box suffit
(`Regions.a:232-250,390-423`). L'ensemble est demi-ouvert comme les rectangles :
`left <= x < right`, `top <= y < bottom` (`Regions.a:865-881`).

Pour une région non rectangulaire, `PackRgn.a:13-20,108-125` encode :

```text
vertical, horizontal-change..., 32767,
vertical, horizontal-change..., 32767,
32767
```

Les coordonnées sont des entiers 16 bits triés. Les horizontales sont des
points d'inversion : traverser une coordonnée bascule intérieur/extérieur. Le
point essentiel est que les listes verticales ne sont pas des runs complets de
chaque ligne. `SeekRgn` conserve un masque de scanline et XOR les changements
rencontrés ; l'état reste valable jusqu'au prochain événement vertical
(`SeekRgn.a:45-67,99-187`). Pour un rectangle développé temporairement, les
mêmes deux horizontales apparaissent au `top` puis au `bottom`, ce qui active
puis annule le run (`RgnOp.a:258-280`). La double sentinelle `32767` termine
d'abord la liste horizontale, puis la région.

`CloseRgn` trie les points d'inversion en ordre vertical/horizontal, annule les
paires dupliquées et les compacte (`Regions.a:289-329`). `RgnOp` développe les
rectangles si nécessaire, fait avancer les deux flux au prochain vertical,
fusionne les scans horizontaux triés pour intersection/différence/union/XOR,
puis n'émet que la différence avec le scan résultat précédent
(`RgnOp.a:65-75,144-253,296-349,413-441`).

## Application par `RgnBlt`

La primitive historique reçoit deux `BitMap`, deux rectangles, un mode, un
pattern et trois `RgnHandle` (`RgnBlt.a:13-24,69-79`). Un `BitMap` contient
`baseAddr`, `rowBytes` et `bounds` (`GrafTypes.a:91-96`) ; `rowBytes` est donc
le pas entre scanlines, distinct de leur largeur logique. Le présent
sous-ensemble retient uniquement le mode 0 `srcCopy` et ignore le pattern.

`RgnBlt` reçoit en réalité trois régions et limite d'abord le travail à
l'intersection du rectangle destination, des bounds destination et de leurs
trois bounding boxes (`RgnBlt.a:15-24,130-145`). Si elles sont rectangulaires,
il ajuste l'origine source et délègue directement à `BitBlt`
(`RgnBlt.a:155-208`).

Sinon, il alloue un masque d'une scanline, aligné sur 16 bits et traité par
longs de 32 bits (`RgnBlt.a:211-232`). Chaque région non rectangulaire reçoit
un état `SeekRgn`; s'il n'y en a qu'une, elle joue directement dans le masque
composite. Pour deux ou trois, les masques sont intersectés par AND de longs
(`RgnBlt.a:249-302,535-661`). La boucle `srcCopy` reconstruit les longs source,
les AND avec le masque, puis préserve les bits destination hors masque
(`RgnBlt.a:679-719`).

Le chevauchement choisit le sens vertical puis horizontal comme `BitBlt`
(`RgnBlt.a:369-416`). Pour remonter, `SeekRgn` ne possède pas d'index inverse :
il efface son scan, revient au début du flux et rejoue vers le bas
(`SeekRgn.a:69-91`).

## Contrat expérimental minimal

- bitmaps monochromes MSB-first, source et destination distinctes ;
- rectangles source/destination de même étendue, mode `srcCopy`, aucun scaling ;
- le résultat copie un bit seulement si sa coordonnée destination appartient à
  la région et à `dstRect`; les autres bits destination sont préservés ;
- régions valides dérivées d'un masque de référence déterministe, incluant vide,
  rectangle et formes arbitraires ;
- pour G2, coordonnées non négatives strictement inférieures à la sentinelle
  historique `32767` ;
- un seul clip est étudié : ni combinaison de régions, ni API de construction
  géométrique, ni autre mode booléen.

Le backend stable pour copier un run est R3 de QuickDraw 1, inchangé. G0 et G2
fusionnent cependant leur masque avec une copie portable par octets : conserver
cette interaction est nécessaire pour représenter le mécanisme central de
`RgnBlt`, plutôt que de mesurer une conversion artificielle du masque en runs.
Le choix source/destination distinctes écarte l'interaction chevauchement afin
que la variable principale reste la représentation et le parcours du clip.

## Mécanismes confirmés et hypothèses de coût

| Mécanisme | Problème | Coût/mémoire attendus | Provenance |
|---|---|---|---|
| Bounding box | rejeter ou réduire vite le travail | constant avant parcours ; peut être peu discriminant pour formes creuses | `Regions.a:865-881`, `RgnBlt.a:130-145` |
| Rectangle de 10 octets | éviter toute donnée de contour | construction et application spécialisables | `Regions.a:390-423`, `PackRgn.a:47-59` |
| Changements verticaux + inversions horizontales | compacter les scanlines répétées | stockage proportionnel aux changements de contour, état d'une scanline | `PackRgn.a:13-20`, `SeekRgn.a:99-187` |
| Flux triés d'inversions | combiner des régions sans masque 2D | fusion linéaire dans les transitions | `RgnOp.a:296-349` |
| Masque de scanline rejoué | transformer le flux compact en travail bitmap | mémoire proportionnelle à largeur bbox, XOR aux seuls changements | `RgnBlt.a:211-232`, `SeekRgn.a` |
| Masque fusionné à la copie | éviter de produire une liste intermédiaire de pixels | parcourt les longs de bbox même vides | `RgnBlt.a:689-719` |

L'intérêt moderne de ce dernier parcours dense, face aux runs explicites ou à
un masque 2D, doit être mesuré. La compacité de la forme historique dépend des
changements entre scanlines, pas seulement de l'aire ou du nombre de runs.
