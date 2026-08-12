# Expédition QuickDraw 1 — résultats BitBlt `srcCopy`

## Périmètre et validation

Le specimen est `BitBlt.a` du miroir `jrk/QuickDraw`, commit
`6377ec5d89735a11b3f6e1ae728f555936c7583f`, SHA-256
`331e8a5299c646fc5bde0dc7a6facff514230bbb061678b2e02514f9702aa0e8`.
Le contrat portable retient une copie monochrome 1 bit, sans clipping, entre
rectangles de même étendue, en mode `srcCopy`, avec strides arbitraires et
chevauchement lorsque le même bitmap est fourni.

R0 snapshotte puis copie bit par bit. R1 utilise des blocs destination de 32
bits et snapshotte l'aliasing. R2 reprend les idées structurelles observées dans
QuickDraw : mots et bords 16 bits, reconstruction désalignée, sens de parcours,
fast path aligné. R3, conçue après la mesure R0–R2 conservée, utilise `memmove`
pour les copies exactement alignées sur octets et des blocs directionnels de 64
bits sinon.

Les quatre variantes passent 6 298 cas déterministes bit à bit, dont 5 000
cas pseudo-aléatoires, et un passage ASan/UBSan. Les cas couvrent alignements,
strides, contenus, frontières de mots et chevauchements verticaux/horizontaux.

## Mesures physiques

Plateforme : AMD Ryzen AI 9 HX 370, x86-64 Linux 7.2.0-rc6, GCC 16.1.1,
glibc 2.44, `-O3`, affinité sur un CPU logique. Chaque mesure comporte un
échauffement, neuf répétitions et un ordre pseudo-aléatoire. Les compteurs sont
collectés hors des sections chronométrées. Les working sets sont réutilisés et
principalement cache-hot.

| Workload | R0 médiane | R1 médiane | R2 médiane | R3 médiane | Meilleur débit utile |
|---|---:|---:|---:|---:|---:|
| `small_ui` | 11,038 ms | 0,928 ms | 0,938 ms | 0,932 ms | R1, 0,201 GiB/s |
| `aligned_large` | 106,753 ms | 6,088 ms | 1,642 ms | 0,037 ms | R3, 49,880 GiB/s |
| `misaligned_large` | 107,245 ms | 6,737 ms | 7,649 ms | 6,906 ms | R1, 0,272 GiB/s |
| `scroll_overlap` | 61,686 ms | 12,988 ms | 7,924 ms | 7,027 ms | R3, 0,261 GiB/s |

Les valeurs exactes, neuf échantillons et percentiles empiriques élevés sont
dans `quickdraw_bitblt_measurements.json`. Les 49,880 GiB/s de
`aligned_large` décrivent une charge utile cache-hot répétée, pas la bande
passante DRAM.

## Interprétation

- `aligned_large` : R1 exécute 503 040 itérations de blocs, R2 990 720 mots de
  16 bits, alors que R3 confie 1 966 080 octets complets à `memmove`. Le fast
  path moderne est très nettement utile dans ce workload.
- `misaligned_large` : R1/R2/R3 reconstruisent respectivement 506 880 /
  994 080 / 261 120 blocs. R1 gagne néanmoins légèrement ; réduire les
  itérations ne suffit donc pas à établir le coût réel des blocs de 64 bits.
- `scroll_overlap` : R1 réserve 15 360 octets temporaires. R2 et R3 choisissent
  le sens des lignes et n'allouent rien ; ils sont respectivement environ 1,64×
  et 1,85× plus rapides que R1. C'est la confirmation moderne la plus claire
  d'un mécanisme structurel historique.
- `small_ui` : les trois variantes optimisées sont proches. Aucun gagnant
  universel n'apparaît.

Aucune attribution aux caches, branches ou unités CPU n'est avancée : les
compteurs algorithmiques suffisent à expliquer les contrastes nécessaires à
cette première expédition, mais pas tous les écarts fins.

## Perspective historique et limites

Restent structurels : masques de bord, reconstruction des mots désalignés,
parcours anti-écrasement, fast path aligné et spécialisation hors boucle. Les
mots 16 bits, la reconstruction 32→16 et le déroulage par table semblent
fortement liés au 68000 dans leur forme précise. Leur bénéfice sur une machine
68000 réelle reste indéterminé ; aucun toolchain historique n'a été restauré.

Ne sont pas traités : autres modes, patterns, scaling, régions, clipping,
SIMD, GPU et aliasing entre descripteurs distincts. La première comparaison
réelle et instructive est obtenue ; l'expédition s'arrête ici.

## Reproduction

```bash
make test
python3 -B run_quickdraw_bitblt.py
```

Pour rejouer seulement les trois familles qui précédaient R3 :

```bash
make
./quickdraw_bitblt_experiment --benchmark-r0-r2 > quickdraw_bitblt_pre_r3.json
make clean
```
