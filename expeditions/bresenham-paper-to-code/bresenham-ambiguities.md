# Bresenham 1987 — ambiguïtés, égalités et réversibilité

Cette note poursuit la question laissée ouverte par la lecture de 1965. Elle
ne définit pas une nouvelle implémentation et ne constitue pas un benchmark.

## 1. Question héritée de 1965

Le papier de 1965 fixe, dans le premier octant développé, la règle `V < 0 →
M1` et `V >= 0 → M2`. Il ne suffit pas à établir que cette convention reste
réversible lorsque le segment est parcouru en sens inverse, ni qu'elle produit
la même décision après changement d'octant.

La question héritée est donc :

> Une convention d'égalité donnée par la récurrence de 1965 définit-elle une
> trajectoire indépendante du sens de parcours, des transformations d'octant
> et du contexte d'utilisation de la ligne ?

## 2. Référence bibliographique et version lue

Référence primaire : Jack E. Bresenham, “Ambiguities in Incremental Line
Rastering”, *IEEE Computer Graphics and Applications*, vol. 7, no 5, pp.
31–43, May 1987, DOI
[`10.1109/MCG.1987.276986`](https://doi.org/10.1109/MCG.1987.276986).
La notice bibliographique et le statut d'accès fermé sont confirmés par
[DBLP](https://dblp.org/rec/journals/cga/Bresenham87.html) et la notice
OpenAlex [W2140336303](https://openalex.org/W2140336303).

Le texte indexé de la publication expose explicitement les problèmes d'égalité
de métrique, de réversibilité, de clipping, d'intersections en espace raster,
d'EXOR pour les polylignes et d'arrondi des extrémités fractionnaires. Le texte
intégral IEEE n'étant pas librement accessible, les exemples détaillés et les
figures ont été contrôlés dans l'exposé développé par le même auteur : Jack
E. Bresenham, “Anomalies in Incremental Line Rastering”, dans *Theoretical
Foundations of Computer Graphics and CAD*, 1988, pp. 329–358,
[DOI 10.1007/978-3-642-83539-1_12](https://doi.org/10.1007/978-3-642-83539-1_12).

Cette distinction de version est importante : les affirmations ci-dessous
attribuées directement à 1987 sont limitées au contenu bibliographique et
textuel indexé de cet article ; les exemples nommés comme tels sont indiqués
comme provenant de l'exposé de 1988 ou comme cas dérivés. Le chapitre de 1988
est une source de clarification de l'auteur, pas une preuve que chaque détail
était déjà formulé de la même manière dans l'article de 1987.

## 3. Problème étudié par la publication

### SOURCE FACT — publication de 1987

L'article ne traite pas seulement de la boucle incrémentale. Il étudie les
choix implicites nécessaires lorsqu'une géométrie continue est représentée
par des points de grille : définition d'une métrique d'erreur, résolution des
égalités, compromis entre vitesse, espace de code, fidélité, complexité et
cohérence du système.

Le résumé indexé donne quatre familles d'anomalies :

* égalité de la métrique d'erreur ;
* effets d'une perturbation due au clipping ;
* intersections en espace raster ;
* interprétation EXOR des polylignes ;
* réversibilité et arrondi d'extrémités fractionnaires.

### DERIVED INTERPRETATION

La question n'est plus seulement « quel point est le plus proche ? », mais
« quel contrat de discrétisation reste cohérent quand le résultat est réutilisé
par d'autres opérations ? ». Une règle locale de tie-breaking peut donc avoir
des effets visibles sur une polyline, une suppression par redessin inverse ou
une construction de courbe.

## 4. Faits source

### SOURCE FACT — égalité et métrique

Une implémentation doit choisir une métrique de proximité entre la ligne
géométrique et les points de grille candidats. Lorsque deux candidats ont la
même valeur de cette métrique, elle doit résoudre explicitement ou
implicitement l'égalité.

### SOURCE FACT — réversibilité

Le texte de 1987 indique qu'une égalité peut conduire à sélectionner des points
différents pour le segment de `(X0,Y0)` vers `(X1,Y1)` et pour le même segment
parcouru en sens inverse. Il indique aussi qu'imposer une réversibilité exacte
peut créer des problèmes lorsqu'on rasterise des lignes utilisées pour
approximer un cercle polygonal.

### SOURCE FACT — contexte système

Les choix doivent être évalués dans le contexte des primitives associées, et
pas seulement ligne par ligne. Le résumé cite notamment le clipping, les
intersections raster, les polylignes et EXOR : la cohérence entre primitives
peut compter davantage qu'une propriété isolée de la ligne.

### SOURCE FACT — 1988, utilisé comme clarification

L'exposé de 1988 nomme explicitement quatre préoccupations :
`RETRACEABILITY`, `FIDELITY`, `POLYLINE` et `SPECIFICATION`. Il donne comme
exemple de réversibilité le segment `(0,0) → (2,1)` et discute aussi des
extrémités fractionnaires, du clipping avant ou après rasterisation, et d'une
construction de secteur circulaire.

## 5. Ambiguïtés et conventions identifiées

### 5.1 Égalité de métrique

**ALREADY_EXPLICIT_IN_1965.** Le cas développé de 1965 contient déjà une
convention : `V = 0` prend la branche `V >= 0`, donc `M2`. L'égalité n'est pas
absente de la récurrence.

**LATER_CLARIFICATION.** 1987 explicite que cette décision est un choix de
contrat, pas une conséquence unique du mot « proche ». La métrique doit être
connue et la règle de tie-breaking documentée.

### 5.2 Réversibilité

**IMPLICIT_BUT_NOT_ESTABLISHED.** La table des octants et l'état incrémental de
1965 donnent une procédure directionnelle, mais ne démontrent pas que
l'inversion des extrémités conserve l'ensemble des points.

**LATER_CHANGE.** Une variante qui force la réversibilité exacte change le
contrat de comportement dans les contextes où l'orientation des segments et
les jonctions de courbes comptent. 1987 ne la présente pas comme une
amélioration universelle.

### 5.3 Interaction entre primitives

**NEW_REQUIREMENT.** Le contrat d'une ligne doit être confronté à son usage
dans le clipping, les intersections raster, EXOR et les polylignes. 1965
décrit le contrôle du plotter et ses mouvements ; il ne spécifie pas ces
compositions de primitives.

### 5.4 Extrémités non entières

**NEW_REQUIREMENT.** L'arrondi d'une extrémité fractionnaire doit être défini
si l'algorithme reçoit des coordonnées non entières ou si une transformation
géométrique produit de telles coordonnées. Ce n'est pas le domaine d'entrée
entier du papier de 1965.

### 5.5 Clipping

**NEW_REQUIREMENT.** Le clipping peut intervenir avant la rasterisation ou
après celle-ci. Ces deux ordres ne sont pas garantis équivalents au niveau des
points de grille lorsque le segment est ambigu.

## 6. Comparaison explicite avec 1965

| Question | 1965 | 1987 | Classification |
|---|---|---|---|
| Métrique de proximité | Comparaison géométrique des deux candidats dans le cas développé | Une métrique doit être explicitée pour donner un sens à « proche » | `LATER_CLARIFICATION` |
| Égalité | `V >= 0` choisit `M2` dans le premier cas | L'égalité est une source d'ambiguïté observable | `ALREADY_EXPLICIT_IN_1965` + `LATER_CLARIFICATION` |
| Huit octants | Table de transformations et affectations | Les conséquences de la convention doivent être examinées après transformation et inversion | `IMPLICIT_BUT_NOT_ESTABLISHED` |
| Parcours inverse | Non démontré | Peut produire une sélection différente ; la réversibilité exacte est un choix | `LATER_CLARIFICATION` |
| Sortie | Mouvements de plotter entre points de maille | Points/pels dans des primitives raster réutilisées | `LATER_CHANGE` de contexte, pas nécessairement de récurrence |
| Clipping | Non traité | Ordre géométrie/raster pertinent | `NEW_REQUIREMENT` |
| Polylignes et EXOR | Non traité | Les jonctions et la répétition de pels deviennent des questions de contrat | `NEW_REQUIREMENT` |
| Extrémités fractionnaires | Coordonnées d'entrée entières | Arrondi et fidélité doivent être spécifiés | `NEW_REQUIREMENT` |

La publication de 1987 ne réfute donc pas la récurrence de 1965. Elle montre
que cette récurrence est insuffisante comme spécification complète d'un système
de rasterisation.

## 7. Cas discriminants

### Cas 1 — segment `(0,0) → (2,1)`

**SOURCE FACT.** L'exposé détaillé de 1988 utilise ce cas pour poser la
question de la réversibilité. Il est cohérent avec la classe d'égalité discutée
par 1987.

**DERIVED TEST CASE.** Avec la convention du premier octant de 1965 (`V = 0`
choisit `M2`), une exécution orientée de `(0,0)` vers `(2,1)` peut donner le
chemin :

```text
(0,0), (1,1), (2,1)
```

Après inversion des extrémités, la même règle appliquée dans l'octant orienté
opposé peut donner :

```text
(2,1), (1,0), (0,0)
```

Les ensembles diffèrent au point intermédiaire `(1,1)` contre `(1,0)`. Ce cas
discrimine donc au moins deux contrats : tie-breaking directionnel ordinaire
versus chemin exactement réversible. Il s'agit d'une dérivation à partir de la
règle 1965, pas d'une transcription d'une figure 1987.

### Cas 2 — polyligne EXOR aller-retour

**SOURCE FACT — clarification 1988.** La polyligne `(10,0) → (0,0) →
(10,0)` en mode EXOR pose la question de savoir si le point partagé et les
segments répétés doivent laisser plusieurs pels, un pel ou aucun pel.

**CONSEQUENCE.** Même si chaque segment est individuellement « proche », la
composition dépend de l'inclusion des extrémités et de la réversibilité. Le
choix ne peut pas être déduit de la seule métrique locale.

### Cas 3 — clipping avant/après rasterisation

**SOURCE FACT — clarification 1988.** Un segment peut être coupé dans l'espace
géométrique avant rasterisation ou rasterisé puis limité dans l'espace des
pels.

**CONSEQUENCE.** Près d'une frontière et d'une égalité, ces ordres peuvent
produire des points différents. La question n'est pas tranchée par la seule
récurrence de 1965.

## 8. Statut question initiale

**QUESTION_REFINED.** La question « le chemin est-il réversible ? » est trop
large. 1987 établit que la réversibilité est une propriété de contrat à choisir
et à confronter aux autres primitives ; il ne fournit pas, dans le contenu
accessible ici, une convention unique qui résoudrait tous les octants,
égalités, jonctions et arrondis.

La question devient :

> Pour quel contrat de rasterisation (tie-breaking, extrémités, clipping et
> composition) faut-il garantir la réversibilité, et quelles propriétés
> incompatibles cette garantie introduit-elle ?

## 9. Distinctions candidates sans ontologie

Ces distinctions servent uniquement à lire les sources et à préparer une
éventuelle expérience ; elles ne constituent pas des concepts Atlas :

* **métrique** versus **règle d'égalité** : la première définit la proximité,
  la seconde choisit entre candidats équivalents ;
* **réversibilité d'un segment** versus **cohérence d'une polyligne** : la
  première compare deux parcours, la seconde concerne les jonctions et les
  modes de composition ;
* **géométrie avant rasterisation** versus **espace raster après** : l'ordre
  du clipping est une partie du contrat ;
* **coordonnée d'entrée entière** versus **extrémité fractionnaire** : le
  second cas ajoute une convention d'arrondi ;
* **génération de points** versus **usage des points** : EXOR, effacement ou
  intersection peuvent rendre visibles des choix qui sont indifférents pour
  un trait isolé.

## 10. Questions nouvelles

1. Une règle de tie-breaking peut-elle être choisie pour être à la fois
   translation-invariante, symétrique par réflexion et exactement réversible ?
2. Quelles conventions d'inclusion des extrémités rendent une polyline
   composable sans double traitement au point partagé ?
3. Le clipping géométrique et le clipping raster peuvent-ils être rendus
   équivalents par une spécification précise, ou faut-il choisir un ordre ?
4. Quels effets sont réellement visibles pour les courbes polygonales, plutôt
   que seulement possibles dans le cas d'un segment isolé ?

## 11. Branches suivantes

Au plus trois investigations sont nécessaires :

1. **Table de cas analytiques minimale** : calculer, sans benchmark, les
   chemins des segments courts avec égalité selon plusieurs règles et dans les
   deux sens.
2. **Lecture primaire de compaction** : vérifier si une sortie en runs change
   le contrat de points ou seulement sa représentation.
3. **Source historique d'implémentation** : retrouver une réalisation de
   contrôle de plotter et vérifier la traduction de la table d'octants.

## 12. Branche recommandée

La prochaine branche recommandée est la **table de cas analytiques minimale**.
Elle est la plus discriminante pour la question héritée, ne demande pas de
nouveau code de production ni de benchmark, et sépare immédiatement :

* une différence due au tie-breaking ;
* une différence due à l'orientation des octants ;
* une différence due à l'inclusion des extrémités.

## 13. Confirmed

* 1987 traite l'ambiguïté des métriques d'erreur et exige qu'une égalité soit
  résolue par une convention, même si cette convention reste fixe.
* 1987 relie explicitement la rasterisation à la réversibilité et aux effets
  de contexte : clipping, intersections raster et polylignes EXOR.
* La réversibilité exacte n'est pas un simple synonyme de « meilleur proche » ;
  elle peut entrer en conflit avec d'autres objectifs de rasterisation.
* Le cas `(0,0) → (2,1)` est un discriminant concret pour tester le contrat de
  parcours inverse, via la clarification de 1988 et la règle de 1965.

## 14. Disproved

* Il est infirmé que la règle d'égalité de 1965 suffise, à elle seule, à
  spécifier le comportement d'un système raster moderne composé de plusieurs
  primitives.
* Il est infirmé qu'une réversibilité exacte puisse être ajoutée sans
  examiner ses effets sur l'approximation de courbes et de polylignes.
* Il est infirmé qu'un segment isolé suffise à définir le contrat d'une
  rasterisation utilisée avec clipping, EXOR ou des jonctions.

## 15. Unknown

* La politique exacte de tie-breaking proposée par l'article IEEE pour chaque
  octant et chaque sens n'est pas établie par une implémentation exécutable
  dans cette étape.
* La compatibilité simultanée de la réversibilité avec translation, réflexion,
  inclusion des extrémités et cohérence de polyline reste inconnue.
* L'effet exact du clipping avant ou après rasterisation sur une convention
  donnée reste à calculer sur une table de cas dédiée.
* La frontière entre le contenu de l'article de 1987 et les exemples plus
  détaillés de l'exposé de 1988 reste une limite documentaire importante.

## Inventaire

Fichier créé :

* `expeditions/bresenham-paper-to-code/bresenham-ambiguities.md`

Aucun code, benchmark, JSON historique, ontologie ou document 1965 n'a été
modifié.
