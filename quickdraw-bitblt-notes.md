# QuickDraw `BITBLT` — notes de lecture

## Specimen et provenance

- Miroir public : <https://github.com/jrk/QuickDraw>, annoncé comme le source
  QuickDraw de Bill Atkinson publié par le Computer History Museum.
- Révision étudiée : `6377ec5d89735a11b3f6e1ae728f555936c7583f`
  (`master`, 2010-07-20). Le clone de travail est extérieur à ce dépôt et les
  fichiers historiques n'ont pas été modifiés.
- SHA-256 :
  - `BitBlt.a` : `331e8a5299c646fc5bde0dc7a6facff514230bbb061678b2e02514f9702aa0e8`
  - `QuickDraw.p` : `c1d3590c448e4e0ed536cf701e0d1f23acaa39e054cb185dfbb91929fc96a63d`
  - `RgnBlt.a` : `16c400510330c67c6db2b0e96601c3d9358e5ed2f13ee3c1319e7e765b06ea7f`
  - `Bitmaps.a` : `745f6e7fd58de49e41e5644df319363959cb9b5689dee9a3193329678a53647e`
  - `COPYRIGHT.TXT` : `4d7a98ac9439bfb5ca9cd48928f62f9354de5073b1dfe8f14266015d57a19aaa`
- Notice du miroir : matériau copyright Apple Inc. (1984), disponible
  uniquement pour usage non commercial. `BitBlt.a` porte aussi la mention
  Apple et attribue le code à Bill Atkinson. Aucun bloc substantiel du source
  n'est repris dans les réimplémentations.

## Contrat retenu

`BITBLT` reçoit deux `BitMap`, deux `Rect`, un mode et un motif (`BitBlt.a:14-20`).
Un `BitMap` est `baseAddr + rowBytes + bounds`; un `Rect` contient
`top,left,bottom,right` (`QuickDraw.p:78-94`). Les coordonnées sont converties
par rapport à `bounds`; les lignes sont séparées par `rowBytes`
(`BitBlt.a:113-123,200-237`).

Le sous-ensemble expérimental est : bitmap monochrome 1 bit, source bitmap,
mode 0 `srcCopy`, aucune région ni clipping, origine source et rectangle
destination valides, même largeur et même hauteur logiques. La copie préserve
les bits de destination hors rectangle.

Correction d'une hypothèse initiale : la primitive ne vérifie pas deux tailles
égales. Elle calcule largeur et hauteur depuis `dstRect` (`BitBlt.a:100-105,
255-270`) et ne consulte que `top/left` de `srcRect`. `RgnBlt` lui fournit une
origine source ajustée et un rectangle destination déjà limité
(`RgnBlt.a:177-207`). La précondition expérimentale est donc que la zone source
de l'étendue destination soit valide. Une dimension destination non positive
produit un no-op.

Le commentaire « no clipping » est confirmé : aucune intersection avec les
bounds n'est calculée dans `BITBLT`; le clipping rectangulaire a lieu chez
l'appelant. Les `rowBytes` peuvent différer entre bitmaps. Pour un chevauchement
testé ici, source et destination sont le même descripteur bitmap. L'aliasing de
deux descripteurs différents n'est pas promis : le code historique ne recherche
le chevauchement que lorsque les `baseAddr` sont égaux (`BitBlt.a:167-180`).

Le résultat attendu en cas de chevauchement est celui d'une copie depuis l'état
source antérieur. Le code choisit bas-vers-haut si la destination est plus
basse, et droite-vers-gauche si les lignes commencent au même niveau et que la
destination est à droite (`BitBlt.a:162-193`).

## Mécanismes observés

| Mécanisme | Où | Problème résolu | Nature |
|---|---|---|---|
| Masques gauche/droite, combinés pour un rectangle dans un mot | `242-270`, table étroite `380-387`, `END0 449-464` | préserver les bits hors rectangle et traiter les bords | structurel |
| Décalage relatif modulo 16 | `198-220` | aligner des origines source/destination différentes | structurel, largeur 16 liée au 68000 |
| Reconstruction par lecture longue chevauchante puis shift | `MAIN0 449-464` | fabriquer un mot destination depuis deux mots source adjacents | structurel ; forme exacte 32→16 liée aux registres/instructions 68000 |
| Sens vertical puis horizontal | `162-193`, ajustement `280-297` | éviter d'écraser une source encore non lue | structurel |
| Chemin `srcCopy` aligné | dispatch `300-314`, boucles `390-443` | retirer shift et dispatch de mode de la boucle chaude | structurel |
| Dispatch de mode avant les lignes | `316-337`, `MODETAB 371-387` | spécialiser les boucles internes par opération | structurel, forme assembleur spécifique |
| Copie par mots longs et boucle déroulée jusqu'à 32 mots | `467-507` | réduire contrôle de boucle et doubler la largeur des transferts | probablement 68000-spécifique dans cette forme |
| Cas étroit tenant dans un mot | deuxième moitié de `MODETAB`, masques combinés | éviter une boucle générale et fusionner les deux bords | structurel |

Le commentaire du fast path est conforme à ses gardes : mode 0, décalage nul,
plus d'un mot destination, puis choix d'une boucle avant/arrière
(`BitBlt.a:300-314`). En revanche « same bitmap » est plus précisément testé
comme égalité de `baseAddr`; l'équivalence de descripteur n'est pas vérifiée.

## Hypothèses et inconnues

- Le format 1 bit et l'ordre exact des bits sont implicites dans les masques et
  conventions QuickDraw ; les réimplémentations fixent explicitement MSB-first
  dans chaque octet, cohérent avec les mots big-endian du 68000.
- Le source suppose des accès word/long valides autour des mots reconstruits.
  Le contrat portable ne l'imite pas : il ne lit jamais hors des lignes.
- L'intérêt moderne du déroulage, des mots 16/32 bits et du dispatch indirect
  ne peut pas être déduit du source ; il sera jugé seulement par mesure.
- Aucun toolchain 68000 n'est requis pour cette expédition.
