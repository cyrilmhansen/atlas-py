# Bresenham : de la publication scientifique au code réel

Étude documentaire et lecture de code réalisée le 13 août 2026. Cette
expédition ne modifie ni les ontologies, ni les benchmarks QuickDraw, ni les
implémentations étudiées. Elle ne constitue pas un benchmark : les mesures
mentionnées ci-dessous sont celles publiées par les sources ou les contrats
observables dans le code.

## 1. Corpus scientifique et éditions lues

### Publication fondatrice

**SOURCE FACT** — Jack E. Bresenham, *Algorithm for Computer Control of a
Digital Plotter*, IBM Systems Journal 4(1), pp. 25–30, 1965, DOI
[10.1147/SJ.41.0025](https://doi.org/10.1147/SJ.41.0025). La lecture intégrale
a été faite sur le scan lisible
[ibm-1401.info/Pics3/bresenham1965.pdf](https://ibm-1401.info/Pics3/bresenham1965.pdf),
qui reproduit les pages originales 25–30. La réédition ACM
[10.1145/280811.280913](https://doi.org/10.1145/280811.280913) a été vérifiée
comme réédition de cette publication, et non comme un article ultérieur.

Le papier est explicitement motivé par le contrôle d'un plotter numérique à
huit mouvements vers les points voisins d'une maille. Les coordonnées des
points de données sont entières et les segments de courbe sont approximés par
une suite de mouvements de maille (p. 25). Il ne s'agit pas d'une spécification
moderne de pixels, d'anti-aliasing ou de couverture de surface.

### Publications ultérieures lues

1. Jack E. Bresenham, *A Linear Algorithm for Incremental Digital Display of
   Circular Arcs*, Communications of the ACM 20(2), pp. 100–106, 1977, DOI
   [10.1145/359423.359432](https://doi.org/10.1145/359423.359432). Lecture du
   texte intégral sur une copie institutionnelle lisible
   [public.callutheran.edu/~reinhart/CSC505/Week1/BresenhamCircles.pdf](https://public.callutheran.edu/~reinhart/CSC505/Week1/BresenhamCircles.pdf),
   en conservant l'identité ACM de l'article.
2. Jack E. Bresenham, *Incremental Line Compaction*, The Computer Journal
   25(1), pp. 116–120, 1982, DOI
   [10.1093/comjnl/25.1.116](https://doi.org/10.1093/comjnl/25.1.116). La
   métadonnée et l'abstract ont été vérifiés chez
   [Oxford Academic](https://academic.oup.com/comjnl/article/25/1/116/527278);
   le texte intégral lisible a été étudié dans la reproduction
   [paperzz.com/doc/7786058/incremental-line-compaction](https://paperzz.com/doc/7786058/incremental-line-compaction).
   Cette provenance de lecture est moins forte que l'éditeur et est signalée
   comme telle.

L'article *Ambiguities in Incremental Line Rastering* (IEEE Computer Graphics
and Applications 7(5), pp. 31–43, 1987, DOI
[10.1109/MCG.1987.276986](https://doi.org/10.1109/MCG.1987.276986)) a été
identifié et utilisé comme publication de retour, notamment parce que le code
Xorg le cite explicitement. Il n'est pas compté parmi les articles lus
intégralement ici : l'accès disponible était fermé. Les conclusions portant
sur les ambiguïtés sont donc comparées à sa notice et à la citation du code,
pas présentées comme une lecture intégrale de 1987.

## 2. Lecture serrée de 1965

### Ce que le papier affirme

**SOURCE FACT — pp. 25–26, Fig. 3–4, équations (1)–(4).** Dans le premier
octant, le plotter n'utilise que deux mouvements voisins. À l'étape `i`, il
compare les deux points candidats et choisit l'un lorsque `r_i < q_i`, l'autre
lorsque `r_i >= q_i`. Le signe de la quantité `V_i` est construit pour avoir
le même signe que cette différence géométrique. Le papier donne une
récurrence incrémentale par additions :

* si `V_i >= 0`, le nouvel état ajoute `2 Δb - 2 Δa` ;
* si `V_i < 0`, il ajoute `2 Δb` ;
* l'initialisation est `V_1 = 2 Δb - Δa` ;
* `V_i < 0` sélectionne `M1`, et `V_i >= 0` sélectionne `M2`.

**SOURCE FACT — pp. 27–28, Fig. 5 et Table 1.** Les autres octants sont
traités en orientant différemment le système de coordonnées et en modifiant
les membres droits des équations et l'affectation des mouvements. Le papier
ne propose donc pas une unique boucle indépendante de la direction : il
décrit une normalisation conceptuelle par octant puis une sélection de la
forme appropriée.

**SOURCE FACT — p. 29.** Les signes des différences de coordonnées et de la
différence entre leurs valeurs absolues sont condensés dans des variables
booléennes servant à choisir les mouvements. La conclusion revendique
l'absence de multiplications et divisions dans le programme de contrôle, ainsi
qu'un usage mémoire et un temps d'exécution favorables sur la configuration
IBM étudiée : 333 positions mémoire et environ 1,5 ms entre incrémentations,
contre 513 positions et 2,4 ms pour une comparaison citée.

### Interprétations et limites

**DERIVED INTERPRETATION.** Le noyau observable est un état entier incrémental
qui transforme une décision géométrique locale en un mouvement axial ou
diagonal, avec une normalisation par octant. « Erreur accumulée » est une
reformulation moderne utile, mais ce n'est pas le vocabulaire principal du
papier.

**HYPOTHESIS.** La règle `>=` constitue une convention de départage pour les
cas d'égalité. Le papier la fixe dans le cas présenté, mais ne démontre pas
que cette convention est la seule possible, qu'elle est réversible, ou qu'elle
est la convention de tous les dispositifs ultérieurs.

**NON-CLAIMS.** Le texte ne démontre pas une norme universelle de
rasterisation moderne. Il ne traite ni sous-pixel, ni anti-aliasing, ni
épaisseur de trait, ni clipping de fenêtre, ni contrat d'inclusion des
extrémités dans une API graphique. Ses coûts sont ceux du plotter et de la
machine décrits, pas une loi indépendante de plateforme.

## 3. Ce que les publications ultérieures ajoutent

### Arcs circulaires, 1977

**SOURCE FACT — pp. 100–102 et 105–106.** L'article reprend le cadre des
dispositifs à huit mouvements mais change l'objet géométrique : il sélectionne
des points de maille pour un arc circulaire. Dans le premier quadrant, trois
mouvements sont candidats : axial horizontal, diagonal, axial vertical. La
quantité `A_i` et deux différences auxiliaires réduisent la comparaison des
trois erreurs à des tests de signe et à trois récurrences d'addition.

**SOURCE FACT — pp. 100–102.** Pour centre et rayon entiers, le papier affirme
que minimiser la différence quadratique de rayon et minimiser la différence
radiale donnent le même choix ; il traite aussi des centres/rayons non entiers,
où l'initialisation doit chercher les points de maille voisins du point
géométrique de départ et d'arrivée. Les passages de quadrant réinitialisent
ou transforment les mouvements.

**DERIVED INTERPRETATION.** Le mécanisme incrémental n'est pas une identité
entre toutes les courbes discrétisées : la fonction objectif, le nombre de
mouvements candidats et l'initialisation font partie du contrat. La
continuité de forme « Bresenham » ne suffit pas à prédire les points produits.

### Compaction de lignes, 1982

**SOURCE FACT — pp. 116–119.** L'article traite une séquence de pas de ligne
comme une donnée pouvant être stockée ou transmise sous forme de pas
explicites, de longueurs de runs, de séquence complète ou de période répétée.
Il décrit un même type de boucle itérative, mais avec des paramètres
d'initialisation et de terminaison différents selon la forme de compaction.
Les longueurs de runs sont calculées sans devoir calculer séparément le PGCD,
qui peut être obtenu comme sous-produit de l'itération.

**SOURCE FACT — p. 117.** L'égalité du terme d'erreur apparaît explicitement
dans la boucle de compaction ; l'article indique que le traitement retenu
produit un chemin exactement réversible dans les cas concernés, tout en le
distinguant de la méthode de Boothroyd et Hamilton.

**SOURCE FACT — p. 118.** Le papier avertit que les paramètres de stockage
peuvent coûter plus cher que les pas directs pour de très courtes lignes. Il
laisse explicitement hors étude plusieurs coûts d'exécution et de
reconstruction, notamment les problèmes de frontières de mots et le partage
de fonction.

**DERIVED INTERPRETATION.** La même progression arithmétique peut produire
une représentation de sortie différente. Le mécanisme de génération et le
contrat de consommation de la ligne ne doivent donc pas être confondus.

## 4. Implémentations réelles étudiées

Les quatre sources ci-dessous sont des codebases distinctes, avec des commits
précis. Les lectures ont porté sur le code, les structures associées et les
appels nécessaires, pas seulement sur les noms « Bresenham ».

### 4.1 Xorg — `miZeroLine`

**Source.** X.Org Server, commit
`989e42c1d46a241bd54475d2e062dceed314a97a`,
[`mi/mizerline.c`](https://gitlab.freedesktop.org/xorg/xserver/-/blob/989e42c1d46a241bd54475d2e062dceed314a97a/mi/mizerline.c),
avec [`mi/miline.h`](https://gitlab.freedesktop.org/xorg/xserver/-/blob/989e42c1d46a241bd54475d2e062dceed314a97a/mi/miline.h)
et [`mi/mizerclip.c`](https://gitlab.freedesktop.org/xorg/xserver/-/blob/989e42c1d46a241bd54475d2e062dceed314a97a/mi/mizerclip.c).

**SOURCE FACT.** `miZeroLine` (lignes 99–347) reçoit un drawable, un GC, un
mode de polyline et une suite de points. Son résultat réel est envoyé à
`FillSpans`; ce n'est pas seulement une fonction qui retourne une liste de
coordonnées. Le code normalise les signes via `CalcLineDeltas`, choisit une
branche X-major ou Y-major, puis entretient `e`, `e1`, `e2` et `e3`. Dans la
boucle X-major, un `e >= 0` provoque le pas mineur en Y ; dans la branche
Y-major, il provoque le pas mineur en X (lignes 201–327 du fichier).

**SOURCE FACT.** Le code traite d'abord les codes de sortie du drawable. Si
un segment est partiellement hors cadre, `miZeroClipLine` est appelée ; après
clipping, le terme d'erreur est avancé de `clipdx` et `clipdy` avant de
reprendre la boucle (lignes 226–248 et 286–308). La longueur et la dernière
extrémité dépendent aussi du clipping et du `capStyle` (lignes 331–343).

**SOURCE FACT.** `mi/miline.h` permet à l'écran de configurer un `bias` par
octant. `FIXUP_ERROR` soustrait le bit de biais à l'état initial, ce qui
change le résultat lorsque le terme serait exactement nul. Le commentaire
relie explicitement ce choix à *Ambiguities in Incremental Line Rastering*
(1987).

**DERIVED INTERPRETATION.** Dans Xorg, la « ligne Bresenham » est un
composant d'un contrat X plus large : clipping, spans, cap style et politique
de tie font partie du résultat observable. La récurrence incrémentale n'est
pas suffisante pour reproduire le même tracé.

**HYPOTHESIS.** Le biais par écran semble destiné à choisir une convention
cohérente dans les cas d'égalité entre octants, mais le code étudié ne suffit
pas à établir le motif historique complet de chaque valeur de biais.

### 4.2 SDL_gfx — `lineColor`

**Source.** SDL_gfx, commit
`4cc9485e8b36fab6126ee390c5746bbe16dcd3e6`,
[`SDL_gfxPrimitives.c`](https://github.com/ferzkopp/SDL_gfx/blob/4cc9485e8b36fab6126ee390c5746bbe16dcd3e6/SDL_gfxPrimitives.c),
fonction `lineColor` (lignes 2347–2539), avec `_clipLine` et les primitives
`hlineColor`/`vlineColor`.

**SOURCE FACT.** `lineColor` clippe les extrémités avant de dessiner, puis
spécialise les lignes verticales, horizontales et le point unique (lignes
2358–2383). Le contrat est l'écriture dans une `SDL_Surface`, avec retour
d'erreur, et non la production abstraite d'une séquence de points.

**SOURCE FACT.** Pour une couleur opaque, le code calcule `dx` et `dy` avec
les signes, ajoute 1 aux longueurs, choisit l'axe majeur par échange de
variables, puis écrit les pixels avec un accumulateur `y += dy; if (y >= dx)`
(lignes 2400–2492). Ce chemin est commenté comme une adaptation d'une routine
de Pete Shinners/Pygame, pas comme une transcription de l'article de 1965.

**SOURCE FACT.** Pour une couleur alpha, la même fonction utilise un autre
chemin : elle pose `d = ay - (ax >> 1)` ou son analogue, et choisit le pas
mineur lorsque `d > 0`, ou lorsque `d == 0` et que le signe de l'axe majeur
vaut `+1` (lignes 2494–2529). L'extrémité finale est écrite explicitement.

**DERIVED INTERPRETATION.** Deux appels ayant les mêmes extrémités peuvent
emprunter des mécanismes différents selon l'alpha. Le format du pixel et la
nécessité du blending déterminent donc la boucle, et la convention de tie
n'est pas une propriété indépendante du chemin d'exécution.

**HYPOTHESIS.** Le chemin opaque cherche surtout à réduire le coût des
écritures et des adresses selon `BytesPerPixel`; le code le montre, mais ne
permet pas de séparer sans mesure le gain de l'accumulateur de celui des
primitives mémoire.

### 4.3 libtcod — état C et itérateur C++

**Source.** libtcod, commit
`c54823ee3e4859fa33da3db7d47827b73d131a82`,
[`src/libtcod/bresenham_c.c`](https://github.com/libtcod/libtcod/blob/c54823ee3e4859fa33da3db7d47827b73d131a82/src/libtcod/bresenham_c.c),
[`bresenham.h`](https://github.com/libtcod/libtcod/blob/c54823ee3e4859fa33da3db7d47827b73d131a82/src/libtcod/bresenham.h),
et l'itérateur C++ dans
[`bresenham.hpp`](https://github.com/libtcod/libtcod/blob/c54823ee3e4859fa33da3db7d47827b73d131a82/src/libtcod/bresenham.hpp).

**SOURCE FACT.** `TCOD_line_init_mt` conserve les extrémités, les signes,
les deltas doublés et un terme `e`. Il choisit l'axe majeur avec la
comparaison `stepx * deltax > stepy * deltay` (lignes 36–64). `TCOD_line_step_mt`
avance d'abord sur l'axe majeur puis avance sur l'autre seulement si `e < 0`
(lignes 65–85). L'égalité n'entraîne donc pas le pas mineur dans ce chemin.

**SOURCE FACT.** L'API C accepte une structure d'état externe, ce qui rend
les lignes réentrantes avec `*_mt`; l'ancienne API utilise au contraire un
état statique global (lignes 34, 94–102). Le module expose aussi un callback
qui peut interrompre le parcours.

**SOURCE FACT.** Il existe une différence de contrat à vérifier entre les
surfaces publiques : l'en-tête décrit `TCOD_line` comme appelant le listener
sur les deux extrémités, tandis que `TCOD_line_mt` appelle le listener avant
chaque `TCOD_line_step_mt` et ne consomme pas les coordonnées lorsque
`TCOD_line_step_mt` retourne vrai après avoir atteint l'extrémité (lignes
87–92). Le code FOV appelle intentionnellement `TCOD_line_step_mt` dans une
boucle `while (!step)` et traite ainsi les positions intermédiaires
([`fov_circular_raycasting.c`](https://github.com/libtcod/libtcod/blob/c54823ee3e4859fa33da3db7d47827b73d131a82/src/libtcod/fov_circular_raycasting.c),
lignes 48–81). L'itérateur C++ moderne, lui, fixe `index_end_` à
`delta_major + 1` et documente l'inclusion des deux extrémités.

**SOURCE FACT.** `BresenhamLine` normalise l'octant par une petite matrice,
permet l'accès aléatoire et fournit `adjust_range`, `without_start` et
`without_end`. Sa progression utilise `y_error > 0` pour le pas mineur
(lignes 353–383), formulation qui doit être comparée à l'état C plutôt que
assimilée sans preuve.

**DERIVED INTERPRETATION.** Dans ce projet, le même nom de mécanisme recouvre
au moins trois contrats : état C manuel, callback C et plage C++ avec
extrémités manipulables. Le choix entre eux peut modifier la ligne livrée au
client, même si la récurrence de base est apparentée.

**HYPOTHESIS.** La différence apparente entre le callback C et l'itérateur C++
peut être intentionnelle pour les usages de ray-casting, ou être une
incohérence documentaire/API. Les tests et les appels devront être suivis
plus loin avant de la qualifier définitivement.

### 4.4 Pilote X.Org Geode — `gfx_bresenham_line`

**Source.** `xserver-xorg-video-geode`, commit Git Debian
`92486c972a8e9b47394888b5c995ea9b3306e913`,
[`src/gfx/gfx_rndr.c`](https://salsa.debian.org/debian/xserver-xorg-video-geode/-/blob/92486c972a8e9b47394888b5c995ea9b3306e913/src/gfx/gfx_rndr.c),
[`src/gfx/rndr_gu1.c`](https://salsa.debian.org/debian/xserver-xorg-video-geode/-/blob/92486c972a8e9b47394888b5c995ea9b3306e913/src/gfx/rndr_gu1.c),
et la variante GP3 dans `src/cim/cim_gp.c`.

**SOURCE FACT.** Le pilote ne reçoit pas nécessairement deux extrémités. Son
API `gfx_bresenham_line(x, y, length, initerr, axialerr, diagerr, flags)`
reçoit un état déjà calculé. Le commentaire de `rndr_gu1.c` précise qu'il
n'existe pas ici de routine qui calcule les paramètres depuis les extrémités
et que cette primitive reste nécessaire après clipping (lignes 1417–1434).

**SOURCE FACT.** Le wrapper choisit GU1 ou GU2 selon `gfx_2daccel_type`
(lignes 402–420 de `gfx_rndr.c`). GU1 ajoute éventuellement le mode de
lecture du framebuffer, ignore une longueur nulle et écrit longueur, erreur
initiale, incrément axial, incrément diagonal et drapeaux dans les registres
du moteur graphique (lignes 1436–1470 de `rndr_gu1.c`). Le pas par pas n'est
donc pas exécuté par cette routine C.

**SOURCE FACT.** Dans la routine GP3 `gp_bresenham_line`, le pilote traite
séparément les directions négatives : il approxime l'offset minimal nécessaire
pour éviter un sous-débordement lorsque la base framebuffer est alignée sur
des régions de 4 MiB, puis programme le moteur (lignes 3027–3084 de
`cim_gp.c`). Cette branche dépend du format d'adresse et non de la géométrie
seule.

**DERIVED INTERPRETATION.** Dans ce cas, « implémentation Bresenham » désigne
une frontière de contrat entre calcul d'état, clipping/offset côté pilote et
boucle de rasterisation dans le matériel. Comparer seulement le nombre de
tests de signe dans le code C serait une comparaison de mauvais niveau.

**HYPOTHESIS.** Le choix de fournir des paramètres pré-calculés est motivé à
la fois par le clipping préalable et par l'interface du moteur. Le code
l'établit comme contrat, mais ne permet pas d'attribuer séparément le choix à
l'un ou à l'autre sans remonter aux appelants matériels.

## 5. Première comparaison puis retour aux sources

La première comparaison a retenu deux différences susceptibles de changer la
ligne produite ou le contrat de substitution.

### Différence A — égalité, tie et extrémités

Xorg expose un biais configurable par octant ; SDL_gfx a deux boucles dont le
tie alpha dépend du signe ; libtcod C utilise `e < 0`, tandis que l'itérateur
C++ utilise une autre écriture (`y_error > 0`) et un contrat de plage explicite.
Le nombre de points et le choix sur une égalité peuvent donc différer sans
que la formule incrémentale générale cesse d'être reconnaissable.

**RETOUR AUX SOURCES — confirmation.** La seconde lecture de `mi/miline.h`,
`mizerline.c`, `SDL_gfxPrimitives.c`, `bresenham_c.c` et `bresenham.hpp` a
confirmé les conditions exactes : `FIXUP_ERROR` modifie l'état avant la
boucle Xorg ; SDL alpha teste `d == 0` avec un signe ; libtcod C teste
strictement `e < 0`, alors que sa plage C++ utilise `y_error > 0`. La
seconde lecture des tests libtcod a aussi confirmé que les tests distinguent
le parcours C et la plage C++ et revendiquent l'inclusion des extrémités pour
la plage C++.

**CORRECTION D'INTERPRÉTATION.** Il serait incorrect de résumer libtcod à
« une seule implémentation avec un seul contrat ». Les tests, l'API C, le
ray-casting et l'itérateur C++ imposent des consommations différentes de
l'état. Le code ne suffit pas encore à conclure si la discordance callback/
documentation est un bug ou une convention oubliée ; elle reste une
inconnue locale vérifiable.

### Différence B — où se trouve la boucle de décision

Xorg, SDL_gfx et libtcod exécutent la progression dans le logiciel, mais
leurs sorties diffèrent : spans Xorg, writes dans une surface SDL, callback ou
range libtcod. Geode transmet un état à un moteur matériel et déplace même
une partie de la gestion d'adresses dans un chemin spécifique au framebuffer.

**RETOUR AUX SOURCES — confirmation.** La lecture de `gfx_rndr.c` a montré
que le wrapper ne calcule ni delta ni erreur : il ne fait que dispatcher vers
GU1/GU2. La lecture conjointe de `rndr_gu1.c` et `cim_gp.c` a confirmé que la
longueur nulle, les drapeaux de direction et l'offset négatif sont traités
avant l'écriture des registres. La variation est donc bien une séparation de
mécanismes et non une simple différence de noms.

### Distinction issue des publications recherchée dans le code

La distinction 1987 entre égalités de métrique, biais et effets au niveau du
pixel a été recherchée explicitement. Elle apparaît directement dans le
commentaire de `mi/miline.h` et dans `miSetZeroLineBias`; elle apparaît sous
forme de conditions de signe dans SDL_gfx et libtcod. Cela ne prouve pas que
ces projets implémentent tous la politique décrite par l'article 1987, mais
montre que la question publiée — que faire de l'égalité — est devenue une
partie concrète du code.

Le papier de 1982 sur la compaction a également orienté la recherche d'une
sortie en runs ou en période dans les sources étudiées. Aucune des quatre
routines retenues ne réalise cette compaction de ligne comme contrat de
sortie ; leur sortie est un flux de pixels, spans ou commandes matérielles.
L'absence est importante : le vocabulaire « incrémental » ne suffit pas à
conclure à une représentation compacte.

## 6. Variations effectivement observées

### Contrat de sortie

* Xorg produit des spans et applique cap/clipping/GC.
* SDL_gfx écrit une surface et choisit la boucle selon alpha et format de
  pixel.
* libtcod fournit un état de parcours, un callback ou une plage d'itération.
* Geode programme un accélérateur qui produira la ligne hors de la routine C.

La propriété « produit une ligne » est trop grossière pour expliquer une
substitution sûre.

### Tie et réversibilité

* Xorg rend le tie configurable par octant.
* SDL_gfx rend le tie dépendant du chemin opaque/alpha et de la direction.
* libtcod encode une condition stricte et fournit une autre surface de
  consommation en C++.
* 1965 fixe une inégalité dans son premier cas ; 1982 discute explicitement
  un traitement particulier des égalités pour obtenir un effet de
  réversibilité dans la compaction.

La réversibilité n'est donc pas une conséquence automatique de l'incrément,
mais une propriété du contrat et de la convention de tie.

### Clipping et état initial

Xorg reconstruit le terme d'erreur après déplacement de l'extrémité clipée.
Geode demande que l'appelant fournisse déjà les paramètres, précisément dans
un contexte où le clipping peut avoir déplacé le début du segment. SDL_gfx
clippe d'abord mais recommence ensuite avec des extrémités modifiées. Ces
formes sont structurellement comparables, mais leurs frontières de
responsabilité sont différentes.

### Spécialisation de plateforme

SDL_gfx spécialise les écritures par `BytesPerPixel`; Xorg spécialise le
résultat par spans et par écran; Geode spécialise le protocole par génération
de moteur et alignement d'adresse. La machine cible ne change pas seulement
le coût : elle peut déplacer la décision algorithmique hors du code de
parcours.

## 7. Ce que signifie aujourd'hui « Bresenham »

Les sources permettent de distinguer, sans en faire une taxonomie définitive :

1. **Le problème** : sélectionner une suite de points ou de mouvements de
   maille représentant une géométrie.
2. **Le noyau 1965** : la boucle de décision incrémentale à deux mouvements,
   organisée par octants pour le plotter décrit.
3. **Une propriété structurelle** : maintenir un état entier et choisir le
   prochain pas par une mise à jour et un test de signe.
4. **Des extensions publiées** : arcs à trois mouvements et métriques
   explicitement discutées en 1977 ; sorties compactées et périodiques en
   1982.
5. **Des implémentations dérivées** : clipping, biais, callbacks, spans,
   alpha, formats de pixels ou registres matériels.

Le nom est donc ambigu lorsqu'il désigne à la fois une récurrence, une
politique de pixel, une API de parcours et un protocole d'accélérateur. Il
faut conserver le contrat local avant d'utiliser le nom historique.

## 8. Comparaison avec QuickDraw B1×B1

Le cas QuickDraw B1×B1 et ces quatre lignes partagent une idée structurelle
faible : deux progressions ordonnées peuvent être consommées par un état
incrémental, et des conventions de frontière déterminent le résultat. Mais
les sources étudiées ici ne valident aucun transfert vers les régions.

* **REDUNDANT_WITH_QUICKDRAW** — la nécessité de documenter la représentation
  de sortie et le contrat de consommation était déjà visible dans QuickDraw
  3 ; Bresenham fournit un autre exemple, pas une connaissance nouvelle
  démontrée pour B1.
* **TRANSFER_CANDIDATE** — séparer explicitement progression géométrique,
  politique de frontière et contrat de sortie pourrait aider à analyser une
  implémentation B1, mais cela n'a pas été testé sur l'intersection de régions.
* **QUICKDRAW_TEST_CANDIDATE** — vérifier si les bornes inclusives/exclusives
  des runs, comme le tie des pixels, doivent être attachées au contrat de
  l'opération B1 plutôt qu'à la seule représentation. Les sources QuickDraw
  déjà étudiées ne suffisent pas à attribuer cette conséquence aux
  implémentations de lignes.

## 9. Connaissances candidates pour Atlas, sans modification d'ontologie

* **Connaissance locale acquise.** Une implémentation incrémentale doit être
  décrite avec son objet géométrique, sa représentation de sortie, sa
  convention de frontière et son site d'exécution.
* **Distinction candidate.** `error_state` ne décrit pas à lui seul une ligne
  substituable ; il faut aussi un contrat d'extrémité/tie et une politique de
  clipping.
* **Question expérimentale.** La compatibilité de deux traceurs devrait être
  vérifiée sur les propriétés de sortie demandées par l'appelant, pas sur la
  présence d'une récurrence nommée Bresenham.
* **Trop tôt pour conclure.** Le transfert de ces distinctions vers les
  régions QuickDraw, la compaction 1982 ou une autre famille graphique n'est
  pas établi.

## 10. Prochaine question expérimentale unique

**Pour un même contrat d'appel (extrémités incluses ou non, clipping donné,
direction et égalités spécifiés), quelles paires de ces implémentations
produisent exactement la même suite de points, et quelles différences restent
visibles lorsque le segment est inversé ou commence après clipping ?**

Cette question découle directement des conditions observées dans Xorg,
SDL_gfx et libtcod. Elle doit précéder toute conclusion de substituabilité ou
toute mesure de performance ; elle ne justifie pas encore de modifier une
ontologie.

## 11. Confirmed / Disproved / Unknown

### Confirmed

* Le papier de 1965 décrit un plotter à huit mouvements, des coordonnées de
  maille entières, une décision incrémentale par octant et une réduction des
  opérations arithmétiques ; il ne décrit pas une norme moderne de pixels.
* Les publications de 1977 et 1982 ajoutent respectivement un autre objet
  géométrique et des représentations compactées ; elles ne sont pas de simples
  répétitions du papier de 1965.
* Quatre codebases réelles exécutent ou programment des mécanismes apparentés,
  mais leurs contrats de sortie, leurs tie-breaks et le lieu d'exécution
  diffèrent.
* Xorg possède un biais de tie configurable par octant et le relie
  explicitement aux ambiguïtés de rasterisation ; SDL_gfx possède des chemins
  de calcul distincts selon alpha ; libtcod distingue état C et plage C++ ;
  Geode reçoit des paramètres pré-calculés pour le moteur matériel.

### Disproved

* « Bresenham » ne désigne pas une boucle et une sortie uniques dans le code
  réel.
* La présence d'un état incrémental ne suffit pas à établir l'inclusion des
  extrémités, la réversibilité ou l'identité pixel à pixel.
* Une publication sur la compaction de lignes ne permet pas d'attribuer une
  sortie compacte aux quatre routines étudiées : aucune ne l'implémente comme
  contrat de sortie observé.

### Unknown

* La discordance apparente entre la documentation/certains tests libtcod et le
  chemin callback C quant à l'extrémité finale est-elle une convention
  d'appel, une évolution partielle ou un bug ?
* Quelles conventions de tie sont réellement nécessaires aux appelants Xorg,
  SDL_gfx et libtcod, et lesquelles sont seulement des choix historiques ?
* Quelle est la relation expérimentale entre ces conventions de ligne et les
  bornes de l'intersection B1×B1 de QuickDraw ?
* La séparation hôte/matériel de Geode modifie-t-elle le choix de pixels ou
  seulement le lieu où la même décision est exécutée ?
* Les gains de compaction 1982 restent-ils utiles lorsque la sortie est
  consommée par une API moderne plutôt que stockée/transmise ?

## Inventaire et reproduction documentaire

Fichier créé :

* `expeditions/bresenham-paper-to-code/bresenham-paper-to-code.md`

Code externe seulement cloné ou consulté sous `/tmp` pour lecture ; aucun de
ces dépôts n'est ajouté au dépôt Atlas. Aucune dépendance et aucun benchmark
n'ont été ajoutés. La vérification peut être reproduite en relisant les URLs
et commits indiqués dans les sections 1 et 4 ; aucune commande de benchmark
n'est requise pour cette étape.
