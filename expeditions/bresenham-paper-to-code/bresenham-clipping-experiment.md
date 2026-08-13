# Micro-expérience Bresenham — clipping et préservation de la ligne digitale

Cette expérience compare deux mécanismes de clipping sur une même convention
de rasterisation. Elle ne mesure pas la performance et ne prétend pas
reproduire exactement Xorg, libcaca ou Kuzmin.

## 1. Question

Pour un segment digital donné et un rectangle de clipping, compare-t-on
toujours les mêmes points avec :

* **FULL_THEN_MASK** : rasteriser le segment complet, puis garder les points
  dans le rectangle ;
* **PRECLIP_THEN_RASTER** : clipper le segment géométrique, arrondir les deux
  nouvelles extrémités, puis relancer le rasteriseur ?

La question est de savoir si le segment géométriquement clippé est
interchangeable avec le suffixe de la ligne digitale originale.

## 2. Contrat expérimental

Toutes les variantes utilisent exactement le même rasteriseur entier :

* tous les octants ;
* extrémités incluses ;
* erreur entière `error = abs(dx) - abs(dy)` sous la forme symétrique usuelle ;
* décision stricte : `2*error > dy` et `2*error < dx` ;
* le cas d'égalité ne prend donc pas la branche correspondante.

Le rectangle est fermé et défini par `xmin <= x <= xmax` et
`ymin <= y <= ymax`.

Pour **PRECLIP_THEN_RASTER** :

1. le segment réel est coupé par Liang–Barsky dans le rectangle fermé ;
2. chaque coordonnée fractionnaire est arrondie par `floor(v + 1/2)` ;
3. les coordonnées arrondies sont bornées au rectangle ;
4. le même rasteriseur entier est relancé entre ces deux points.

La règle d'arrondi est volontairement explicite. Elle fait partie du contrat
de cette expérience et n'est pas présentée comme une convention universelle.

L'oracle de référence est **FULL_THEN_MASK** :

```text
rasteriser(segment complet)
→ conserver exactement les points appartenant au rectangle
```

Une variante `STATE_PRESERVING` n'est pas ajoutée. Les sources montrent que
Xorg ajuste effectivement son terme d'erreur après clipping, mais ses formules
complètes (`miline.h`, biais et helpers) ne sont pas reproduites ici. Une
variante locale qui prétendrait être Xorg serait donc trompeuse.

## 3. Variantes

### FULL_THEN_MASK

La ligne digitale est d'abord produite sur toute la longueur du segment. Le
clipping ne peut supprimer que des points déjà produits.

### PRECLIP_THEN_RASTER

Le générateur ne voit que les extrémités entières obtenues après clipping et
arrondi. Son état initial est celui d'une nouvelle ligne entre ces extrémités,
pas nécessairement celui de la ligne originale au premier point visible.

Le code minimal reproductible est dans
[`bresenham_clipping_experiment.py`](bresenham_clipping_experiment.py).

## 4. Méthode de recherche des cas

Une recherche exhaustive locale parcourt :

* les extrémités entières dans `[-L,L]²` ;
* les rectangles dont les bornes appartiennent au même domaine ;
* `L = 1, 2, 3` ;
* puis une recherche non triviale imposant une largeur et une hauteur de
  rectangle strictement positives, des sorties non vides et une intersection
  fractionnaire de dénominateur supérieur à deux.

Ce n'est pas un benchmark : aucune durée ni aucun débit n'est mesuré. La
recherche sert seulement à trouver un contre-exemple court et reproductible.

Commande :

```sh
python3 -B expeditions/bresenham-paper-to-code/bresenham_clipping_experiment.py
```

Résultat observé :

```text
nontrivial=False search_limit=1 found=True
nontrivial=True search_limit=1 found=False
nontrivial=True search_limit=2 found=True
```

## 5. Cas discriminants minimaux

### 5.1 Cas dégénéré trouvé à `L=1`

```text
INPUT
  segment = (-1,-1) → (0,1)
  clip    = [-1,-1] × [-1,0]

FULL_THEN_MASK
  [(-1,-1), (-1,0)]

PRECLIP_THEN_RASTER
  [(-1,-1)]

DIFFERENCE
  le point (-1,0) disparaît
```

Ce cas utilise un rectangle de largeur nulle. Il établit déjà la
non-équivalence de la méthode générale, mais il n'est pas retenu comme preuve
principale car il mélange la question avec une frontière dégénérée.

### 5.2 Contre-exemple non trivial minimal trouvé à `L=2`

```text
INPUT
  segment = (-2,-2) → (-1,1)
  clip    = [-2,-1] × [-1,1]
```

L'intersection géométrique d'entrée du rectangle est obtenue pour `y = -1` :

```text
t = 1/3
x = -5/3
```

Après arrondi `floor(v + 1/2)`, le point d'entrée devient `(-2,-1)`. Le
point de sortie est déjà `(-1,1)`.

```text
FULL_THEN_MASK
  [(-2,-1), (-1,0), (-1,1)]

PRECLIP_THEN_RASTER
  [(-2,-1), (-2,0), (-1,1)]

DIFFERENCE
  premier point différent après le point d'entrée :
  FULL_THEN_MASK       → (-1,0)
  PRECLIP_THEN_RASTER  → (-2,0)
```

Le résultat est non vide dans les deux cas et le rectangle n'est pas
dégénéré. La divergence n'est donc pas due à une convention de sortie vide.

## 6. Analyse de la divergence

### Observation

Pour le segment `(-2,-2) → (-1,1)`, le rasteriseur complet produit notamment
les points :

```text
(-2,-2), (-2,-1), (-1,0), (-1,1)
```

Le masque conserve les trois derniers points. Le pré-clipping géométrique
produit une entrée réelle en `(-5/3,-1)`, qui devient `(-2,-1)` après
arrondi ; le rasteriseur relancé sur `(-2,-1) → (-1,1)` produit :

```text
(-2,-1), (-2,0), (-1,1)
```

### Explication dérivée

Le point d'entrée arrondi est identique dans les deux sorties, mais l'état de
la récurrence au point `(-2,-1)` ne l'est pas. Dans la ligne complète, cet état
résulte des décisions prises depuis `(-2,-2)`. Dans la ligne relancée, il est
initialisé à partir du nouveau segment entier `(-2,-1) → (-1,1)`.

La perte n'est donc pas seulement une perte de précision de coordonnées. C'est
la perte du résidu incrémental et de l'historique de décisions qui a conduit
au premier point visible.

### Hypothèse contrôlée par la structure du cas

L'arrondi de `(-5/3,-1)` détermine le point d'entrée, mais ne suffit pas à
expliquer le point intérieur différent : les deux méthodes commencent bien à
`(-2,-1)` et terminent bien à `(-1,1)`. La différence restante est compatible
avec une réinitialisation de l'état incrémental.

Cette dernière phrase est une **DERIVED EXPLANATION**, pas une observation
directe du contenu d'un registre Xorg.

## 7. Retour aux sources

### Xorg

Dans [`mi/mizerline.c`](https://sources.debian.org/src/xorg-server/2%3A1.20.11-1%2Bdeb11u13/mi/mizerline.c), Xorg commence avec les paramètres de la ligne complète.
Après `miZeroClipLine`, lorsqu'une extrémité initiale est déplacée, le code
met à jour le terme d'erreur avec `clipdx`, `clipdy`, `e1` et `e2` avant la
boucle visible. Le code traite également l'extrémité finale clippée pour la
longueur et le style de cap.

**SOURCE FACT.** Xorg ne fait donc pas simplement « arrondi des nouvelles
extrémités puis nouvel appel indépendant ». Il conserve/reconstruit un état
lié à la ligne originale.

**LIEN AVEC LE CAS.** Cette opération est précisément du type requis pour
éviter qu'un point intérieur soit déterminé par une nouvelle phase initiale.
L'expérience ne démontre pas que la formule Xorg est la seule correcte et ne
la reproduit pas.

### libcaca

Dans [`caca/line.c`](https://gitea.zoy.org/cacalabs/libcaca/blame/commit/fae3c1983518719eefd3813409ed7aac2b397372/caca/line.c), `clip_line` applique Cohen–Sutherland, calcule de nouvelles
coordonnées avec des divisions entières et peut inverser les extrémités avant
de recommencer. `draw_solid_line` initialise ensuite un nouvel état à partir
de ces coordonnées.

**SOURCE FACT.** Les conditions structurelles du contre-exemple sont donc
présentes : clipping séparé, coordonnées réécrites, puis nouvelle
rasterisation.

**LIEN AVEC LE CAS.** Cela ne prouve pas que libcaca produit exactement la
sortie du contre-exemple : son domaine de coordonnées, son arrondi C et sa
convention de division doivent être vérifiés séparément. Cela prouve seulement
que la famille de mécanisme comparée est réelle.

### Kuzmin

Le [résumé de l'article de 1995](https://diglib.eg.org/items/143e557c-3709-4e61-b171-924a3e48d85e) décrit une génération de ligne avec clipping
intégré, en arithmétique entière, et introduit une notion de correction de la
solution clippée.

**SOURCE FACT.** Le problème de préserver conjointement clipping et génération
est traité comme un problème algorithmique explicite, et non comme une simple
préparation des entrées.

**LIEN AVEC LE CAS.** La terminologie est compatible avec la distinction
« segment clippé » versus « suffixe de ligne digitale ». L'expérience ne
permet pas d'attribuer à Kuzmin la formule locale utilisée ici.

### X11

La [spécification X11](https://www.x.org/releases/X11R7.6/doc/xproto/x11protocol.pdf) exige que l'ensemble effectif d'une ligne fine soit
indépendant du clipping : le résultat visible doit être celui de la ligne
non clippée restreint à la zone. Elle laisse l'algorithme de ligne fine
dépendant du dispositif et ne rend pas la réversibilité obligatoire.

**CONSEQUENCE.** Dans le contrat X11, le résultat **FULL_THEN_MASK** est la
référence sémantique pour la propriété de clipping. Un pré-clipping n'est
acceptable que s'il reconstitue ce même ensemble.

## 8. Connaissance acquise

Le contre-exemple supporte les distinctions suivantes, sans les transformer
en concepts ontologiques :

```text
segment géométriquement clippé
    ≠ nécessairement
suffixe de la ligne digitale originale
```

et :

```text
nouvelles extrémités arrondies
    ≠ état suffisant pour reprendre la récurrence originale
```

Pour préserver le contrat de clipping de type X11, un mécanisme de clipping
doit soit :

* conserver la ligne complète puis masquer ;
* reconstruire correctement l'état incrémental au premier point visible ;
* ou démontrer une équivalence spécifique entre son pré-clipping et l'oracle.

Une nouvelle rasterisation indépendante après arrondi n'a pas cette propriété
par construction.

## 9. Confirmed

* `FULL_THEN_MASK` et `PRECLIP_THEN_RASTER` ne sont pas équivalents sur le
  domaine exhaustif borné testé.
* Le premier contre-exemple non trivial trouvé est
  `(-2,-2) → (-1,1)` avec le rectangle `[-2,-1] × [-1,1]`.
* Dans ce cas, les deux méthodes partagent le premier point visible et les
  mêmes extrémités arrondies, mais divergent au point intérieur.
* La distinction la plus informative est la conservation de l'état
  incrémental, pas seulement la conservation des nouvelles coordonnées.
* Le comportement observé correspond à la différence structurelle entre le
  clipping ajustant l'état de Xorg et le pré-clipping suivi d'une nouvelle
  boucle observé dans la famille libcaca.

## 10. Disproved

* Il est faux que clipper géométriquement puis relancer le même rasteriseur
  produise toujours le même résultat que rasteriser puis masquer.
* Il est faux que des extrémités arrondies identiques suffisent à garantir le
  même suffixe digital.
* Il est faux qu'un résultat de pré-clipping puisse être considéré équivalent
  sans préciser la règle d'arrondi et l'état initial de la récurrence.

## 11. Unknown

* La variante locale ne reproduit pas exactement les formules Xorg ou Kuzmin.
  Elle démontre la nécessité expérimentale d'un état préservé, pas la
  correction d'une implémentation réelle particulière.
* L'ensemble exact des cas où le pré-clipping arrondi reste équivalent n'est
  pas caractérisé.
* La convention X11 de clipping peut être satisfaite par plusieurs
  reconstructions d'état différentes.
* Les effets combinés avec les caps, les polylignes et EXOR n'ont pas été
  explorés ici.

## 12. Statut et prochaine question

Statuts supportés :

* **COUNTEREXAMPLE_FOUND** — démontré par recherche exhaustive bornée ;
* **STATE_INFORMATION_REQUIRED** — supporté par la divergence entre le même
  point d'entrée arrondi et deux états de continuation différents ;
* **QUESTION_REFINED** — la question utile n'est plus seulement « les
  extrémités sont-elles les mêmes ? », mais « l'état suffisant pour produire
  le suffixe original est-il préservé ? ».

La prochaine question la plus informative serait :

> Quelle reconstruction minimale du résidu incrémental, à partir du segment
> original et de la première frontière visible, suffit à rendre une méthode
> de clipping équivalente à `FULL_THEN_MASK` sur tous les cas d'un domaine
> borné ?

Cette question n'est pas exécutée dans cette étape.

## Inventaire

Fichiers créés :

* `expeditions/bresenham-paper-to-code/bresenham_clipping_experiment.py`
* `expeditions/bresenham-paper-to-code/bresenham-clipping-experiment.md`

Aucun benchmark de performance, aucune ontologie et aucun artefact historique
n'a été modifié.
