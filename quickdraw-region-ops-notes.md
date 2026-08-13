# QuickDraw — opérations booléennes de régions

## Provenance

Specimen historique read-only : <https://github.com/jrk/QuickDraw>, commit
`6377ec5d89735a11b3f6e1ae728f555936c7583f`.
Les fichiers étudiés sont `RgnOp.a` (`900364197e48f0445361d50839d844afc632b4942ac163cc55783a476f0abb6c`),
`Regions.a` (`e673b7a31f029541ccfbe0415d6cf52fd60dd17cd2f936c5e8605e24baae2748`),
`SeekRgn.a` (`066b2e232133bebb8e6110479423f0d4f476924136ec9a0ea9e20d37685edf67`),
`PackRgn.a` (`67a0efddbd84ef5beaeb2adddfe53f0dbe19b4ac6b21dd68820226e7605b0727`),
`RgnBlt.a` (`16c400510330c67c6db2b0e96601c3d9358e5ed2f13ee3c1319e7e765b06ea7f`),
`GrafTypes.a` (`2d621b5233dd1f61c47e00514bf572c99b9338b66232b92aec04cbc4921e974e`),
`QuickDraw.p` (`c1d3590c448e4e0ed536cf701e0d1f23acaa39e054cb185dfbb91929fc96a63d`).
`COPYRIGHT.TXT` est `4d7a98ac9439bfb5ca9cd48928f62f9354de5073b1dfe8f14266015d57a19aaa`.

## Algorithme réellement observé

`RgnOp.a:3-22` définit `RgnOp(rgnA,rgnB,buf,maxBytes,op,dh,okGrow)` ; les
codes sont intersection 0, différence A-B 2, union 4 et XOR 6. Les wrappers
publics sont dans `Regions.a:649-704`. L'opération produit directement un
flux de points d'inversion ordonnés, que `Regions.a` fait ensuite empaqueter.

À l'entrée, `RgnOp.a:260-291` développe une région rectangulaire de taille 10
en deux événements verticaux et deux inversions horizontales. Les deux régions
non rectangulaires sont donc parcourues comme des flux verticaux/horizontaux,
sans bitmap 2D intermédiaire.

Le cœur (`RgnOp.a:127-232`) maintient plusieurs scans temporaires. Il avance
au prochain événement vertical de A ou B, applique `XorScan` à la scanline
concernée, puis appelle le scan choisi. `SectScan`, `DiffScan` et `UnionScan`
(`RgnOp.a:296-349`) fusionnent deux listes d'inversions ordonnées en faisant
évoluer deux états intérieur/extérieur. `XorScan` (`RgnOp.a:415-441`) fusionne
les coordonnées et annule les doublons. Enfin, `RgnOp.a:185-232` compare le
scan résultat au scan résultat précédent et n'émet que ses changements.

La capacité de sortie peut être augmentée par blocs de 256 octets si
`okGrow` est vrai (`RgnOp.a:213-249`). Si elle ne l'est pas, l'opération peut
s'arrêter avec un résultat partiel (`RgnOp.a:233-258`). Cette expérience
utilise une sortie extensible locale et ne mesure pas l'échec de capacité.

## Contrat expérimental

Deux masques monochromes de même univers `512x256`, quatre opérations
(`AND`, `OR`, `A-B`, `XOR`) et un oracle pixel par pixel. B0 combine les bits
du masque directement ; B1 fusionne les runs horizontaux de chaque ligne ; B2
rejoue les événements différentiels, combine les états de scanline et encode
le résultat sous forme d'événements. Le résultat est ensuite appliqué comme
clip `srcCopy` avec le backend R3 figé de QuickDraw 1.

L'application utilise des runs horizontaux pour éviter une comparaison
artificielle avec une copie pixel par pixel. B0 et B2 reconstruisent ces runs
au moment de l'application ; B1 les possède déjà. Le coût de cette
reconstruction reste donc dans la mesure d'application.
