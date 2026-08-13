# Proto-ontologie locale — Algorithmique et structures de données élémentaires

- Nom FR : **Algorithmique et structures de données élémentaires**
- Nom en-GB : **Elementary algorithms and data structures**
- Identifiant : `elementary_algorithms`

Cette proto-ontologie rassemble uniquement les mécanismes effectivement
utilisés dans les POC 1–5 et les formes de recombinaison observées dans les
POC 11–12. Elle ne décrit ni les workloads, ni les contraintes de plateforme,
ni la provenance expérimentale comme concepts de ce domaine. Ces éléments
peuvent qualifier une expérience ou un besoin sans devenir des concepts
algorithmiques locaux.

## Concepts retenus

### Collection

- ID : `elementary_algorithms.collection`
- FR : **collection**
- en-GB : **collection**
- Définition : ensemble de valeurs clé-valeur manipulé comme une unité par un
  mécanisme de stockage et d'accès.
- Alias : aucun.
- Statut : **forcé**.
- Relations locales établies :
  - est représentée par une séquence triée ou une table de hachage ;
  - supporte une recherche ou un parcours.
- Justification Atlas : le POC 1 décrit le besoin clé-valeur sans imposer
  initialement une représentation ; les candidats sont ensuite comparés sur
  les mêmes opérations logiques.

### Séquence

- ID : `elementary_algorithms.sequence`
- FR : **séquence**
- en-GB : **sequence**
- Définition : suite ordonnée d'éléments pouvant être parcourue dans cet
  ordre.
- Alias : aucun.
- Statut : **forcé**.
- Relations locales établies :
  - possède un ordre exploitable par une recherche ou un parcours ;
  - peut être une séquence triée.
- Justification Atlas : la recherche dichotomique, le parcours dense et la
  fusion de séquences dans les expériences exigent cette propriété d'ordre.

### Recherche

- ID : `elementary_algorithms.lookup`
- FR : **recherche**
- en-GB : **lookup**
- Définition : opération qui tente de retrouver la valeur associée à une clé
  dans une collection.
- Alias : **lookup** (terme de code et de mesure).
- Statut : **forcé**.
- Relations locales établies :
  - opère sur une collection ;
  - peut utiliser une recherche dichotomique ou un adressage ouvert.
- Justification Atlas : `lookup_heavy` est l'opération qui provoque les choix
  et basculements des POC 1–9.

### Parcours

- ID : `elementary_algorithms.traversal`
- FR : **parcours**
- en-GB : **traversal**
- Définition : opération qui visite successivement les éléments accessibles
  d'une collection.
- Alias : **walk** (terme historique des workloads).
- Statut : **forcé**.
- Relations locales établies :
  - opère sur une collection ;
  - peut être séquentiel sur une séquence ou parcourir des cases réservées.
- Justification Atlas : `walk_heavy` distingue le coût de parcourir les
  éléments denses de celui de scanner les slots d'une table sparse.

### Séquence triée

- ID : `elementary_algorithms.sorted_sequence`
- FR : **séquence triée**
- en-GB : **sorted sequence**
- Définition : séquence dont l'ordre des clés permet une recherche par
  comparaison et une position déterminée par dichotomie.
- Alias : **sorted list** (terme utilisé dans les POC, moins précis ici car la
  structure de liste n'est pas le point retenu).
- Statut : **forcé**.
- Relations locales établies :
  - est une séquence ;
  - utilise une recherche dichotomique pour le lookup ;
  - supporte un parcours séquentiel.
- Justification Atlas : la famille `sorted + binary_lookup + dense_walk` est
  exécutée et comparée dans les POC 2–5.

### Table de hachage

- ID : `elementary_algorithms.hash_table`
- FR : **table de hachage**
- en-GB : **hash table**
- Définition : représentation d'une collection qui localise une clé par une
  fonction de hachage et une politique de résolution des collisions.
- Alias : **hash** (abréviation de code et de résultats).
- Statut : **forcé**.
- Relations locales établies :
  - peut utiliser l'adressage ouvert ;
  - fournit une recherche par probing ;
  - peut conserver des slots sparse et une vue dense auxiliaire.
- Justification Atlas : les POC 1–5 mesurent la table, ses probes, sa capacité,
  son parcours et l'erreur d'estimation liée à la distribution des clés.

### Adressage ouvert

- ID : `elementary_algorithms.open_addressing`
- FR : **adressage ouvert**
- en-GB : **open addressing**
- Définition : résolution des collisions par recherche de cases successives
  dans le tableau de slots, sans chaîne externe par entrée.
- Alias : aucun.
- Statut : **forcé**.
- Relations locales établies :
  - est utilisé par une table de hachage ;
  - produit des probes et une capacité réservée ;
  - est sensible à la dispersion des clés et à la politique de capacité.
- Justification Atlas : les POC 5–9 montrent que le nombre de probes est une
  caractéristique décisionnelle et que son estimation uniforme peut être
  réfutée par une distribution réelle.

### Recherche dichotomique

- ID : `elementary_algorithms.binary_search`
- FR : **recherche dichotomique**
- en-GB : **binary search**
- Définition : recherche dans une séquence triée par subdivisions successives
  de l'intervalle de clés possible.
- Alias : **binary lookup** (terme des POC).
- Statut : **forcé**.
- Relations locales établies :
  - opère sur une séquence triée ;
  - produit des comparaisons de recherche ;
  - possède des bornes ou estimations qui doivent être distinguées des
    observations d'exécution.
- Justification Atlas : le POC 5 réfute explicitement une borne analytique de
  comparaison dichotomique sur l'implémentation exécutée.

### Fusion

- ID : `elementary_algorithms.ordered_merge`
- FR : **fusion ordonnée**
- en-GB : **ordered merge**
- Définition : parcours coordonné de séquences ordonnées pour produire une
  séquence ou un résultat combiné en respectant l'ordre.
- Alias : **merge** (terme de code et de QuickDraw 3).
- Statut : **forcé**, mais localement étroit.
- Relations locales établies :
  - opère sur des séquences ordonnées ;
  - produit une séquence ou une structure combinée ;
  - son coût dépend de la quantité et de la fragmentation des entrées.
- Justification Atlas : les POC 11–12 montrent une recombinaison de mécanismes
  batch et QuickDraw 3 compare la fusion ordonnée de runs aux opérations bitmap
  et différentielles.

## Concepts candidats ou écartés

### Tri fusion — candidat, non retenu

- ID potentiel : `elementary_algorithms.merge_sort`
- FR : **tri fusion**
- en-GB : **merge sort**
- Motif : le domaine contient la fusion, mais aucun POC ne mesure ou ne
  sélectionne un tri fusion comme mécanisme. Le nom ne doit pas être déduit
  automatiquement de `merge`.

### Représentation dense / sparse — mention de contexte, non concept autonome

Les POC utilisent effectivement les termes dense, sparse, slots et vue dense.
Dans cette proto-ontologie, ils restent des propriétés ou des variantes des
structures ci-dessus : aucun résultat ne force encore une taxonomie séparée
des représentations de stockage.

### Workload, contrainte mémoire, scénario, reuse count — hors domaine

Ces termes sont nécessaires pour décrire les expériences et les décisions,
mais ils n'appartiennent pas automatiquement à l'ontologie locale :

- `workload` décrit une charge expérimentale ;
- `memory constraint` décrit une contrainte de besoin ou de plateforme ;
- `scenario` décrit un cas d'utilisation ;
- `reuse count` compte des occurrences dans un cycle de vie.

Les intégrer ici confondrait les mécanismes algorithmiques avec les conditions
de leur évaluation. La relation entre un compteur et l'événement compté reste
une distinction sémantique à traiter dans le contexte concerné, pas un concept
local de cette ontologie.

## Limites locales

Cette proto-ontologie ne définit pas de relation avec `Region`, `Bitmap` ou
`Runs` du graphisme 2D classique. Une inférence future pourra rapprocher, dans
un contexte précis, une séquence ordonnée et des runs sans imposer qu'une
région soit une séquence.

Elle ne décrit pas non plus de plateforme, de modèle de coût, de niveau de
confiance ou de protocole de mesure. Ces informations qualifient les
expériences ; elles ne constituent pas des mécanismes de ce domaine.
