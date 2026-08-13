# Expédition Bresenham — contrats de ligne digitale

Cette note poursuit les lectures de 1965 et 1987. Elle cherche à distinguer
les propriétés réellement différentes derrière l'expression « même ligne
Bresenham ». Elle ne propose ni taxonomie générale, ni benchmark, ni
ontologie.

## 1. Question directrice

Une ligne digitale peut être considérée sous plusieurs angles :

* points produits par la discrétisation ;
* règle de départage lorsque deux candidats sont équidistants ;
* comportement lorsque les extrémités sont inversées ;
* invariance par translation ou réflexion ;
* effet du clipping ;
* inclusion des extrémités et jonctions de polylignes ;
* représentation et consommation des points par une primitive raster.

L'expédition cherche à savoir lesquels de ces aspects sont indépendants, et
lesquels ne sont que des reformulations d'un même choix.

## 2. Trajectoire de recherche réellement suivie

### 2.1 Point de départ : 1965

La note [bresenham-1965.md](bresenham-1965.md) établissait une récurrence
entière, une règle `V >= 0 → M2` dans le premier octant et une table de
transformations pour les huit octants. Elle laissait ouverte la portée de la
règle d'égalité lorsque le sens de parcours ou l'octant change.

### 2.2 Ambiguïtés explicitées : 1987 puis 1988

La lecture de [bresenham-ambiguities.md](bresenham-ambiguities.md) a montré
que l'égalité n'est pas le seul problème. Bresenham relie aussi la
rasterisation au clipping, aux intersections en espace raster, aux polylignes
EXOR, à la réversibilité et aux extrémités fractionnaires.

Le texte intégral IEEE de 1987 étant fermé, la note précédente distingue
l'article et l'exposé détaillé de 1988, *Anomalies in Incremental Line
Rastering*. Le chapitre de 1988 fournit les exemples concrets `(0,0) → (2,1)`,
la polyline EXOR et le cas du clipping avant/après rasterisation.

### 2.3 Contrat externe : X11

Le [protocole X11](https://www.x.org/releases/X11R7.6/doc/xproto/x11protocol.pdf),
section des lignes, apporte une distinction importante : une ligne fine est
laissée à un algorithme dépendant du dispositif, mais le contrat impose la
translation-invariance et l'indépendance du résultat effectif vis-à-vis du
clipping. La réversibilité des lignes fines est seulement recommandée, pas
obligatoire. La même spécification donne des règles distinctes pour les
extrémités, les caps et les jonctions des lignes larges.

Cette source a déplacé la question : « réversible » n'est pas nécessairement
une propriété fondamentale de toute API de ligne ; cela dépend du contrat
externe.

### 2.4 Implémentation réelle : Xorg `miZeroLine`

J'ai ensuite lu `mi/mizerline.c` de
[`xorg-server 2:1.20.11-1+deb11u13`](https://sources.debian.org/src/xorg-server/2%3A1.20.11-1%2Bdeb11u13/mi/mizerline.c),
fonction `miZeroLine`.

Cette implémentation annonce dans son commentaire qu'elle dessine les mêmes
pixels indépendamment des signes de `dx` et `dy`. Elle calcule un octant,
maintient des termes d'erreur entiers, applique un `bias`, et possède un
chemin de clipping qui ajuste le terme d'erreur après déplacement de
l'extrémité dans la zone visible. Elle n'est donc pas seulement une boucle
Bresenham suivie d'un masque.

### 2.5 Implémentation indépendante : libcaca

Enfin, j'ai lu `caca/line.c` au commit
[`fae3c1983518719eefd3813409ed7aac2b397372`](https://gitea.zoy.org/cacalabs/libcaca/blame/commit/fae3c1983518719eefd3813409ed7aac2b397372/caca/line.c).
La routine `draw_solid_line` utilise une forme incrémentale proche de
Bresenham, mais le clipping est réalisé séparément par Cohen–Sutherland avant
le tracé. Le départage est strict (`delta > 0`), et la boucle trace les deux
extrémités. La variante « thin » ne produit d'ailleurs pas la même sortie :
elle choisit des caractères ASCII représentant les formes locales, pas
seulement un ensemble de points binaires.

Cette source a confirmé qu'un même nom historique peut recouvrir des contrats
de sortie différents, y compris dans le même logiciel.

### 2.6 Retour à une publication de clipping

Pour vérifier que le choix « clipping séparé » contre « clipping intégré »
n'était pas seulement un détail de Xorg, j'ai consulté l'article de Yevgeny P.
Kuzmin, “Bresenham's Line Generation Algorithm with Built-in Clipping”,
*Computer Graphics Forum*, 1995, DOI
[`10.1111/1467-8659.1450275`](https://doi.org/10.1111/1467-8659.1450275).
Le résumé primaire décrit explicitement une approche qui unifie clipping et
génération de ligne dans une arithmétique entière et introduit une notion de
correction du clipping.

Après cette vérification, les sources supplémentaires accessibles devenaient
principalement redondantes : elles répétaient la famille « accumulateur
entier » sans apporter une nouvelle propriété de contrat. La recherche s'arrête
ici.

## 3. Sources principales et niveau de lecture

| Source | Type | Ce qui a été utilisé |
|---|---|---|
| Bresenham, 1965, *IBM Systems Journal* 4(1), pp. 25–30, DOI `10.1147/SJ.41.0025` | publication primaire | récurrence, premier octant, octants, égalité `V >= 0` |
| Bresenham, 1987, *IEEE CG&A* 7(5), pp. 31–43, DOI `10.1109/MCG.1987.276986` | publication primaire, texte intégral fermé | notice et résumé indexé ; thèmes : égalités, réversibilité, clipping, EXOR, extrémités |
| Bresenham, 1988, chapitre, pp. 329–358, DOI `10.1007/978-3-642-83539-1_12` | publication primaire de clarification, texte accessible par indexation | exemples nommés `RETRACEABILITY`, `FIDELITY`, `POLYLINE`, `SPECIFICATION` |
| X11 Protocol, X.Org X11R7.6, section lignes | spécification primaire de système | translation, clipping, réversibilité recommandée mais non requise, caps et joins |
| Xorg `mi/mizerline.c`, version Debian `2:1.20.11-1+deb11u13`, `miZeroLine` | implémentation réelle | octants, biais, clipping intégré, cap-not-last, sorties en spans |
| libcaca `caca/line.c`, commit `fae3c198...`, `draw_solid_line` et `clip_line` | implémentation réelle indépendante | Cohen–Sutherland séparé, tie strict, endpoints inclus, sortie ASCII distincte |
| Kuzmin, 1995, *Computer Graphics Forum*, DOI `10.1111/1467-8659.1450275` | publication primaire | clipping intégré à la génération, arithmétique entière, notion de correction |

Les sources X11, Xorg et libcaca ne sont pas utilisées comme preuves de ce que
Bresenham 1965 voulait dire. Elles sont des preuves séparées de contrats et de
choix d'implémentation ultérieurs.

## 4. Contrats distincts effectivement observés

### 4.1 Contrat géométrique local de 1965

**SOURCE FACT.** Le programme choisit à chaque étape l'un des deux mouvements
voisins en fonction d'un état entier issu d'une comparaison géométrique. Dans
le cas développé, l'égalité va vers `M2`.

**CONTRAT OBSERVABLE.** Pour deux extrémités entières et un octant donné, une
suite de mouvements est produite. La note de 1965 ne spécifie pas encore un
contrat moderne de pixel, de clipping ou de polyline.

### 4.2 Contrat de départage directionnel

**SOURCE FACT.** Une règle `>=` ou `>` peut choisir des candidats différents
sur une égalité.

**DERIVED INTERPRETATION.** Le départage change directement les points quand
la trajectoire rencontre une égalité. Il ne change pas nécessairement la
métrique de proximité ni la pente représentée.

### 4.3 Contrat de réversibilité

**SOURCE FACT.** 1987/1988 posent explicitement la question de l'identité des
points pour `A → B` et `B → A`. X11 recommande cette propriété pour les lignes
fines mais ne l'impose pas.

**CONTRAT OBSERVABLE.** La réversibilité est une relation entre deux appels,
pas une propriété locale d'un seul appel. Elle peut être vraie même si le
départage choisi n'est pas celui de 1965.

### 4.4 Contrat de translation

**SOURCE FACT.** X11 exige que la translation simultanée des deux extrémités
translate aussi l'ensemble des points touchés.

**CONSEQUENCE.** Cette propriété est différente de la réversibilité. Une
implémentation peut être translation-invariante sans être réversible, et
inversement une règle locale peut être réversible sur certains cas sans
garantir la translation-invariance générale.

### 4.5 Contrat de clipping

**SOURCE FACT.** X11 exige que le clipping ne modifie pas l'ensemble effectif
de la ligne : il doit être l'intersection entre la ligne non clippée et la
région de clipping.

**SOURCE FACT.** Xorg ajuste l'état d'erreur après le déplacement d'une
extrémité clippée. libcaca modifie d'abord les extrémités par Cohen–Sutherland,
puis relance sa boucle.

**DERIVED INTERPRETATION.** « Clipper puis tracer » et « tracer avec état
ajusté » sont deux mécanismes qui peuvent viser le même contrat X11, mais ils
ne sont pas équivalents par construction pour une arithmétique entière et des
ties.

### 4.6 Contrat d'extrémité

**SOURCE FACT.** X11 définit `CapNotLast`, tandis que Xorg n'émet le dernier
point qu'en fonction du cap-style et de la position dans la polyline. libcaca
trace toutes les positions de sa boucle solide, donc ses extrémités sont
incluses dans cette routine.

**CONSEQUENCE.** Deux routines qui produisent le même chemin intérieur peuvent
néanmoins différer d'un pixel aux extrémités et donc différer en mode EXOR ou
à une jonction.

### 4.7 Contrat de représentation/consommation

**SOURCE FACT.** Xorg accumule les points en spans avant de les remettre à
`FillSpans`; libcaca écrit directement dans une toile de caractères et sa
variante thin encode une forme visuelle par caractères.

**CONSEQUENCE.** Une même suite de décisions géométriques n'implique pas une
même représentation de sortie ni une même sémantique de consommation. Le
mot « ligne » peut donc désigner un chemin, un ensemble de pixels, des spans ou
une apparence ASCII selon le contrat.

## 5. Propriétés indépendantes ou en tension

| Propriété | Change les points ? | Peut changer seulement l'usage ? | Relation observée |
|---|---:|---:|---|
| métrique de proximité | oui, sur les égalités ou si la métrique change | non | distincte du mécanisme d'accumulation |
| règle d'égalité | oui | parfois | peut entrer en conflit avec une symétrie souhaitée |
| réversibilité | oui, par comparaison de deux appels | oui, si l'API ne l'expose qu'à l'utilisateur | recommandée par X11 pour thin, non obligatoire |
| translation-invariance | oui si violée | non | exigence de contrat X11 |
| choix de l'octant | souvent oui si transformation incorrecte | non | 1965 et Xorg normalisent les signes |
| clipping | oui si le contrat est mal préservé | oui si seul le parcours interne change | Xorg recalcule l'état ; libcaca pré-clipe |
| inclusion des extrémités | oui aux bords | oui pour un segment isolé, non en polyline/EXOR | Xorg et X11 lient ce choix au cap-style |
| représentation de sortie | non nécessairement | oui | spans et caractères ne sont pas des ensembles de points identiques |
| largeur/cap/join | oui | oui | surtout contrat de ligne large et de polyline |

### Propriétés qui semblent compatibles

La translation-invariance, une règle d'égalité fixe et une sortie en entier
peuvent coexister. X11 les demande pour les lignes fines, même s'il laisse la
méthode libre.

Le clipping indépendant du résultat non clippé peut également coexister avec
un parcours directionnel, à condition que l'état d'erreur soit ajusté ou que
la méthode de pré-clipping conserve exactement le contrat.

### Tensions réellement observées

* **Réversibilité contre autres objectifs de courbe.** Bresenham 1987/1988
  signale qu'une modification visant la réversibilité peut produire des
  effets indésirables dans une approximation polygonale de cercle.
* **Réversibilité contre liberté d'implémentation.** X11 recommande mais
  n'impose pas la réversibilité des lignes fines, précisément parce que des
  implémentations de dispositifs peuvent choisir des chemins différents.
* **Clipping séparé contre fidélité de la ligne complète.** Une division
  entière lors du déplacement des extrémités peut changer l'état initial si
  elle n'est pas accompagnée d'une correction du résidu. C'est la raison
  technique pour laquelle Xorg et Kuzmin traitent le clipping comme une
  question algorithmique, pas uniquement comme un test de boîte.
* **Chemin de points contre consommation.** Une représentation par spans ou
  caractères peut conserver ou perdre une information selon que le
  consommateur attend des points, des longueurs de runs ou une forme visuelle.

## 6. Cas discriminants utiles

### 6.1 `(0,0) → (2,1)` : égalité et réversibilité

Avec la règle du premier octant de 1965, `V(1)=2·1−2=0` et la branche nulle
choisit `M2`. La trajectoire dérivée est :

```text
1965, aller : (0,0), (1,1), (2,1)
```

Une forme avec départage strict, comme la routine solide de libcaca (`delta >
0`), donne :

```text
libcaca, aller : (0,0), (1,0), (2,1)
```

Pour le parcours inverse, la règle stricte de libcaca donne le même point
intermédiaire dans l'ordre inverse :

```text
libcaca, retour : (2,1), (1,0), (0,0)
```

La convention 1965 dérivée par octant opposé peut donner `(1,0)` au retour,
alors que l'aller avait `(1,1)`. Le cas montre séparément :

* un changement de règle d'égalité qui change les points ;
* une règle qui peut être réversible dans une implémentation ;
* le fait qu'« utiliser l'algorithme de Bresenham » ne fixe pas le contrat.

Il s'agit d'un calcul analytique, pas d'un benchmark.

### 6.2 Clipping d'un segment passant la frontière

**SOURCE FACT.** X11 exige que le résultat clippé soit l'ensemble non clippé
restreint par le clip. Xorg ajuste `e` avec `clipdx` et `clipdy` après
`miZeroClipLine`; libcaca appelle d'abord `clip_line`, qui peut inverser les
extrémités et recalculer les coordonnées par division entière.

**DISCRIMINATION.** Deux implémentations peuvent avoir le même résultat sur
un segment entièrement visible mais diverger sur un segment dont l'entrée se
trouve hors de la boîte, surtout lorsque l'intersection géométrique tombe
entre deux coordonnées entières. La différence attendue porte alors sur la
préservation du résidu, pas sur la boucle interne seule.

Ce cas reste une question analytique à vérifier, pas une divergence mesurée
ici.

### 6.3 Polyline et extrémité partagée

X11 distingue les caps et les joins, et Xorg ne traite pas l'extrémité finale
comme les extrémités internes. Une composition de deux segments partageant un
point peut donc avoir un contrat différent de deux appels indépendants, même
si chaque segment est produit par la même récurrence.

En EXOR, un point partagé traité deux fois peut s'annuler ; en mode solide il
peut ne produire aucun changement visible supplémentaire. Le résultat dépend
du mode de consommation et de l'inclusion d'extrémités, pas seulement de la
géométrie.

## 7. Connaissance émergente

### 7.1 Distinction : proximité versus départage

**Observations :** 1965 donne une comparaison géométrique et une branche nulle;
1987 insiste sur la métrique et les ties; libcaca choisit strictement `> 0`.

**Conséquence si ignorée :** deux chemins peuvent différer sur des segments
à égalité tout en ayant la même qualité selon la métrique principale.

**Statut :** observation confirmée par sources indépendantes.

### 7.2 Distinction : réversibilité versus translation-invariance

**Observations :** X11 impose la translation-invariance, recommande la
réversibilité sans l'imposer; 1987 présente la réversibilité comme une
préoccupation distincte.

**Contre-exemple :** une implémentation peut appliquer une règle stable sous
translation tout en dépendant de l'orientation du parcours.

**Statut :** distinction candidate fortement soutenue; la compatibilité exacte
de toutes les propriétés reste à tester analytiquement.

### 7.3 Distinction : clipping comme transformation de l'état

**Observations :** Xorg modifie le terme d'erreur après clipping; Kuzmin
propose d'intégrer les deux étapes; libcaca les sépare.

**Conséquence si ignorée :** pré-clipper les coordonnées et relancer la boucle
peut ne pas préserver le même chemin discret qu'une ligne complète ensuite
masquée.

**Statut :** observation d'implémentation; l'écart concret entre les deux
méthodes reste une question expérimentale.

### 7.4 Distinction : ligne logique versus représentation consommée

**Observations :** Xorg émet des spans; libcaca solide écrit des caractères;
libcaca thin choisit des caractères de forme; X11 spécifie des points touchés.

**Conséquence si ignorée :** une égalité de points ne garantit pas une égalité
de sortie ou d'apparence lorsque le consommateur applique une sémantique
différente.

**Statut :** observation confirmée dans les sources étudiées.

### 7.5 Distinction : segment isolé versus primitive composée

**Observations :** 1987/1988 traitent EXOR, clipping et polylignes; X11 donne
des règles spécifiques pour caps et joins; Xorg différencie la dernière
extrémité.

**Conséquence si ignorée :** une règle correcte pour un segment isolé peut
laisser des doublons, trous ou annulations dans une composition.

**Statut :** observation confirmée.

## 8. Semantic spider

```text
1965 : V >= 0 dans le premier octant
  → question : tie et sens inverse sont-ils invariants ?
1987 : égalité, réversibilité, clipping, EXOR, extrémités
  → question : la ligne doit-elle avoir un contrat système composé ?
1988 : cas (0,0)→(2,1), polyline EXOR, clipping avant/après
  → question : quelles propriétés une API impose-t-elle réellement ?
X11 : translation et clipping imposés; réversibilité thin seulement recommandée
  → question : comment une implémentation concrète réalise-t-elle ce contrat ?
Xorg : biais, octants, ajustement du résidu après clipping, caps
  → question : le clipping séparé donne-t-il les mêmes points ?
libcaca : tie strict, Cohen–Sutherland séparé, endpoints inclus, sortie ASCII
  → question : « Bresenham » désigne-t-il encore le même objet discret ?
Kuzmin 1995 : clipping intégré comme algorithme à part entière
  → connaissance : clipping et rasterisation peuvent être un seul mécanisme,
    mais le contrat visé doit être explicité.
```

## 9. Connaissances candidates pour Atlas

Ces formulations restent des connaissances candidates issues de cette branche,
pas des éléments à ajouter maintenant à une ontologie.

1. **Une ligne n'est pas entièrement définie par sa récurrence.** Il faut au
   moins connaître la métrique, le départage, les extrémités et le mode de
   consommation pertinent.
2. **La réversibilité est une relation de contrat entre appels.** Elle ne doit
   pas être confondue avec la symétrie d'un état ou avec la seule gestion des
   signes d'octant.
3. **Le clipping peut porter sur l'état incrémental.** Un pré-clipping
   géométrique n'est pas automatiquement équivalent à un clipping intégré.
4. **Les transformations d'octant et les changements de représentation sont
   différents.** Les premières doivent préserver une convention de points;
   les seconds peuvent conserver un chemin mais changer sa consommation.
5. **Une API peut délibérément laisser une propriété indéterminée.** X11
   impose translation et clipping pour les lignes fines mais laisse la
   réversibilité non obligatoire.
6. **Le nom historique ne fixe pas le contrat.** Les routines 1965, Xorg et
   libcaca partagent une famille de mise à jour entière mais diffèrent sur
   tie, clipping, caps et sortie.

## 10. Inconnues restantes

* L'article IEEE 1987 complet n'est pas accessible dans cette recherche; les
  détails attribuables uniquement à ses figures restent à séparer du chapitre
  de 1988.
* L'équivalence exacte entre le pré-clipping Cohen–Sutherland de libcaca et le
  contrat de clipping X11 n'a pas été calculée sur une table de cas.
* La signification précise du `bias` Xorg et sa relation avec la convention
  de tie n'a pas été reconstruite jusqu'à son interface de configuration.
* La compatibilité simultanée entre réversibilité, translation-invariance,
  symétrie par réflexion, inclusion des extrémités et polyligne reste inconnue.
* Le contrat visuel de la sortie ASCII thin de libcaca n'est pas comparable
  pixel pour pixel au contrat X11 sans définir un modèle de cellule de texte.
* Les publications accessibles ne suffisent pas à établir ce que le programme
  IBM du plotter faisait exactement au niveau de chaque octant.

## 11. Branches suivantes importantes

Au maximum trois branches semblent justifiées :

1. **Table analytique du clipping.** Comparer, sans benchmark, une ligne
   complète masquée, un pré-clipping par division entière et une initialisation
   du résidu ajustée, sur quelques intersections fractionnaires. C'est la
   branche la plus directement susceptible de distinguer un contrat de
   clipping.
2. **Reconstruction du biais Xorg.** Lire `miline.h` et les appels qui fixent
   `miGetZeroLineBias` afin de relier précisément le paramètre de biais aux
   égalités et aux invariances annoncées.
3. **Contrat de polyline/EXOR.** Construire seulement une table de points pour
   deux segments avec extrémité partagée, sans benchmark, afin de séparer
   inclusion, cap et réversibilité.

La branche recommandée est **1 — table analytique du clipping**, car elle
oppose deux mécanismes réels observés dans Xorg et libcaca et peut produire une
différence de points sans introduire une nouvelle famille de lignes.

## 12. Arrêt de la branche

L'arrêt est justifié ici : les sources supplémentaires parcourues répètent
principalement la boucle d'accumulation entière. Les distinctions nouvelles
les plus susceptibles de changer un résultat sont désormais identifiées :

* tie-breaking ;
* réversibilité comme relation entre appels ;
* translation-invariance ;
* inclusion des extrémités et composition ;
* clipping intégré versus pré-clipping ;
* représentation consommée.

Une future étape ne devrait partir que d'un cas analytique qui tranche l'une
de ces questions.

## Inventaire

Fichier créé :

* `expeditions/bresenham-paper-to-code/bresenham-line-contracts.md`

Aucun code, benchmark, ontologie ou artefact historique existant n'a été
modifié.
