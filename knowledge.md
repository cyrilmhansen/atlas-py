# Atlas — Knowledge

Ce fichier contient l'état consolidé des connaissances durables acquises par les
POC Atlas. Il n'est pas un journal chronologique : les scripts sont les preuves
exécutables et les README conservent protocoles, scénarios et résultats détaillés.

## Confirmed

### Collecte de connaissance réelle

- La première collecte de connaissances techniques réelles continue de
  soutenir le noyau `Description` + relations/faits : les difficultés
  rencontrées jusqu'ici ont pu être ramenées à l'identité des descriptions,
  à la sémantique des relations, au scope, à la provenance et au statut
  épistémique, sans imposer de nouveau type fondamental.
- Une identité nominale destinée à participer à des relations sémantiques
  telles que `realizes` doit correspondre à un contrat observable suffisamment
  déterminé. Une proximité lexicale ou algorithmique ne suffit pas à établir
  une identité commune.
- Le scope ne peut pas réparer une identité trop générale. Si deux descriptions
  diffèrent par leur résultat observable, leur comportement d'absence,
  multiplicité, position, projection, mutation ou autre propriété pertinente,
  elles doivent rester distinctes ou partager explicitement une abstraction
  dont le contrat commun est défini.
- Transformer une source en connaissance Atlas est une opération sémantique,
  pas une transcription. L'identité, le prédicat, le scope, les hypothèses, le
  statut épistémique et la provenance de l'assertion résultante doivent être
  établis séparément.
- Le fait qu'une source affirme explicitement une proposition ne rend pas
  automatiquement l'assertion Atlas correspondante `exact`. La provenance et
  le statut épistémique sont orthogonaux.
- Un prédicat de relation destiné au raisonnement doit conserver une sémantique
  stable. Un même prédicat ne peut pas servir de verbe générique dont le sens
  réel change selon `value`, `evidence` ou le domaine.

### Représentation sémantique

- Une intention reste stable lorsque ses réalisations disponibles changent.
  L'absence d'une ressource nécessaire à une réalisation ne modifie pas
  l'intention.
- Les cas testés n'exigent pas de types fondamentaux distincts `Intent`,
  `Realization` ou `Resource`. Une `Description` générique, utilisée dans des
  rôles différents et reliée par des faits et relations, a suffi.
- Les relations `realizes`, `requires`, `builds`/`produces`, `represents`,
  `present` et `enabled`, complétées par des faits de scénario, suffisent aux
  exemples statiques testés sans branches propres aux noms du domaine.
- Une ressource auxiliaire peut être présente, constructible dans le scénario,
  ou sans producteur admissible connu. Ce dernier état n'est pas une preuve
  d'impossibilité universelle.
- `constructible`, `available`, `admissible` et `selected` sont distincts et
  contextuels. Une ressource peut notamment être constructible alors que la
  réalisation qui l'utilise est inadmissible sous une contrainte locale.
- Plusieurs consommateurs peuvent référencer la même `Description` et partager
  son identité. Dans les moteurs génériques ultérieurs, son producteur est alors
  compté une seule fois.
- Les coûts dépendent du workload et du contexte : une préparation non rentable
  pour peu d'usages peut le devenir lorsqu'elle est suffisamment amortie.

### Composition, découverte et espace des possibilités

- Plusieurs intentions peuvent converger sur une même préparation ou ressource ;
  son coût peut être partagé lorsque l'identité commune est représentée.
- Une spécialisation peut rester une réalisation de la même intention, avec une
  préparation supplémentaire et un coût réduit sur les usages suivants ; aucun
  nouveau type fondamental n'a été nécessaire pour l'exprimer.
- Un moteur générique piloté par le catalogue peut découvrir les réalisations,
  fermer récursivement leurs dépendances de producteurs et composer plusieurs
  intentions dans les cas statiques acycliques testés.
- L'ajout d'un troisième consommateur d'une même ressource partagée ne demande
  pas de nouvelle règle métier dans ce moteur ; des plans joints utilisant des
  ressources distinctes émergent également du catalogue sans candidat composite
  spécialisé.
- Le partage réduit le travail répété et le coût des solutions mais ne supprime
  pas les alternatives réellement distinctes. Quelques dizaines de descriptions
  ont suffi à induire plusieurs milliers de plans complets dans le générateur
  synthétique.
- Dans les familles mesurées, la croissance n'était pas principalement due à des
  doublons valides accidentels : les doublons stricts et équivalents canoniques
  étaient souvent nuls.
- Mémoïsation et partage réduisent les sous-problèmes répétés sans supprimer
  l'explosion combinatoire des choix réels.
- Un pruning par dominance n'est sûr que relativement aux propriétés
  représentées. Un producteur moins cher ne domine un autre que si résultats,
  préconditions et effets pertinents sont équivalents dans le modèle courant.

### Formulation par contraintes

- Un espace exponentiel de réalisations complètes n'implique pas une
  représentation exponentielle du problème de décision.
- Dans les cas statiques testés, le catalogue relationnel peut être compilé vers
  une formulation CP-SAT qui sélectionne directement une solution sans
  matérialiser tous les plans candidats.
- Sur les petites instances où l'énumérateur termine, CP-SAT et l'oracle
  énumératif retrouvent le même coût et la même signature sémantique.
- CP-SAT a également résolu plusieurs petites instances où l'énumérateur avait
  atteint sa borne avec un modèle de quelques dizaines de variables et
  contraintes. Cela démontre une représentation compacte dans ces cas, pas une
  scalabilité générale.
- Le partage par identité se représente naturellement par une unique décision de
  ressource/producteur, sans contrainte métier spéciale pour les scénarios
  multi-consommateurs testés.
- L'hypothèse de travail désormais la mieux soutenue est qu'Atlas décrit un
  espace de possibilités, relations et contraintes, puis cherche ce qui doit
  être vrai pour obtenir une réalisation préférable, plutôt que de générer
  d'abord toutes les réalisations complètes.

### Temps, lifetimes et choix de réalisation

- Le temps ne peut pas toujours être ajouté après le choix de réalisation.
  Capacité, chevauchement, deadline et lifetimes peuvent modifier la faisabilité
  ou l'optimalité du choix.
- Une sélection locale suivie d'un scheduling fixe peut perdre la faisabilité,
  alors qu'une sélection et un planning joints choisissent une autre réalisation
  et restent faisables.
- Même lorsque la sélection locale reste schedulable, un modèle joint peut
  produire un meilleur makespan. La séparation n'est donc pas généralement sûre.
- Des régimes de convergence existent également : les expériences ne justifient
  ni « toujours séparer » ni « toujours tout joindre ».
- Pour les cas testés, un lifetime minimal est l'intervalle semi-ouvert allant de
  la fin de production d'une ressource à la fin de son dernier usage.
- Le peak live memory dépend du planning et des lifetimes, pas de la somme de
  toutes les ressources construites. Deux ressources non simultanément live
  peuvent réutiliser la même capacité.
- Cette réutilisation émerge du non-chevauchement des intervalles sous contrainte
  cumulative ; aucune relation métier `reuses` ou `shares_storage_with` n'a été
  nécessaire.
- Deux réalisations peuvent être contextuellement non dominées : une variante
  rapide peut exiger davantage de peak mémoire, tandis qu'une variante streamée
  plus lente reste faisable avec moins de capacité.
- Des interactions entre intentions indépendantes peuvent émerger uniquement de
  leurs opérations, précédences, lifetimes et contraintes globales, sans relation
  de conflit explicite entre leurs réalisations.

### Connaissance située dans le temps

- Une connaissance a pu être représentée par une fenêtre
  `known_from(P, t1)` / `valid_until(P, t2)` dans les cas testés.
- Une spécialisation dépendant de cette connaissance n'est admissible que dans sa
  fenêtre. Sa préparation est une opération temporelle réelle, placée après la
  disponibilité du fait et avant les usages spécialisés.
- La décision de spécialiser dépend des usages réellement placés dans la fenêtre,
  pas seulement de leur nombre global. Les mêmes appels déplacés hors de la
  fenêtre peuvent supprimer la spécialisation.
- Une préparation longue peut rester préférable si suffisamment d'usages futurs
  situés dans la fenêtre l'amortissent.
- Plusieurs faits temporels ont pu être composés comme contraintes distinctes
  lorsqu'un usage spécialisé exige leur conjonction, sans imposer de type
  fondamental `KnowledgeWindow` ou `FactWindow`.
- Une variante spécialisée plus rapide peut devenir inadmissible lorsque sa
  demande de capacité dépasse la ressource disponible.

### Substrats expérimentaux

- Egglog a suffi pour enregistrer descriptions, identités et relations et pour
  dériver certains faits contextuels tels que `constructible`/`available` dans
  les premiers POC.
- Les expériences ultérieures séparent ce rôle relationnel de la découverte, de
  la sélection et du scheduling ; leur répartition actuelle entre Python,
  egglog et CP-SAT est expérimentale.
- CP-SAT exprime naturellement, dans le périmètre testé, choix exactement-un,
  intervalles optionnels, précédences, capacités cumulatives, fenêtres
  temporelles et makespan.
- Des oracles indépendants ont été utilisés sur de petites instances : le
  solveur n'est pas considéré comme sa propre preuve de fidélité au modèle.

## Refuted

- Un terme lexical commun tel que `lookup`, `insert` ou `supports` ne constitue
  pas à lui seul une identité ou une relation sémantique commune.
- Un scope plus précis ne suffit pas à rendre correcte une assertion dont le
  sujet, le prédicat ou le contrat observable sont mal choisis.
- Une intention change ou disparaît parce qu'une ressource nécessaire à une de
  ses réalisations est absente.
- `Intent`, `Realization` et `Resource` doivent nécessairement être des types
  fondamentaux séparés dans le noyau testé.
- L'absence de ressource présente ou de producteur connu permet d'affirmer une
  impossibilité globale.
- Une ressource constructible est nécessairement admissible ou préférable.
- Une représentation disponible est nécessairement le meilleur choix
  indépendamment du workload et des contraintes.
- Factorisation ou spécialisation exigent nécessairement un nouveau type
  ontologique dédié dans les cas testés.
- Les compositions simples multi-intentions doivent être pré-énumérées comme
  candidats métier dans le moteur générique.
- Un espace compact de descriptions implique un espace compact de plans.
- Le partage structurel suffit à supprimer l'explosion combinatoire des choix.
- Les réductions observées par canonicalisation proviennent principalement de
  nombreux plans valides dupliqués dans les familles synthétiques mesurées.
- Un producteur moins cher domine automatiquement tout producteur plus cher qui
  produit la même ressource principale, quels que soient ses autres effets ou
  propriétés.
- Tous les plans candidats doivent être matérialisés avant de sélectionner un
  optimum dans les modèles statiques testés.
- Une sélection indépendante des réalisations suivie du scheduling est toujours
  sûre ou optimale.
- La réalisation localement la plus rapide possède un rang global indépendant
  des autres réalisations et des contraintes.
- Le peak mémoire est nécessairement égal à la somme des tailles construites.
- Un même ensemble de réalisations possède un peak indépendant du planning.
- La réutilisation de mémoire doit être une stratégie métier explicitement
  sélectionnée.
- Une connaissance disponible rend automatiquement tous les usages spécialisés.
- Le seul nombre total d'usages suffit à décider d'une spécialisation temporelle.
- Le coût d'une préparation peut toujours être traité comme une constante
  statique indépendante de son placement.
- Une préparation lente est nécessairement non rentable.
- Une variante spécialisée plus rapide reste préférable indépendamment de sa
  consommation de ressources.

## Uncertain

### Sémantique et identité

- Comment établir et valider en général les relations sémantiques alimentant
  Atlas (`realizes`, équivalences, préconditions, effets), plutôt que les
  supposer correctes dans un catalogue expérimental ?
- Quelle preuve ou provenance doit accompagner ces relations ?
- Jusqu'où `Description + relations/faits` reste-t-il suffisant avec mutation,
  état partagé et autres effets non couverts par les POC ?
- Le partage repose aujourd'hui sur l'identité stricte de `Description`.
  Dédupliquer en sécurité deux descriptions distinctes mais sémantiquement
  équivalentes reste ouvert.
- Les cycles de producteurs et de dépendances ne sont pas couverts par les
  expériences statiques acycliques actuelles.

### Temps et changement

- Aucun critère général ne reconnaît encore à l'avance les régions où sélection
  et scheduling peuvent être séparés sans perte.
- Mutation, invalidation, renouvellement et coexistence de plusieurs versions
  d'un fait temporel restent non testés.
- Les lifetimes avec plusieurs producteurs, consommateurs conditionnels ou
  ressources persistantes plus complexes restent à étudier.
- Le temps continu, les durées non entières et les règles d'arrondi ne sont pas
  couverts par les harnais actuels à temps entier.
- L'économie générale de spécialisation au-delà d'une fenêtre de validité et
  d'un objectif de makespan reste ouverte.

### Coûts et décision

- Les POC utilisent surtout des coûts exacts simples, mémoire et makespan. Les
  coûts multiples, objectifs multiples, compromis temps/mémoire plus riches et
  coûts incertains restent à intégrer à la formulation actuelle.
- La dominance reste relative aux propriétés représentées ; aucun mécanisme ne
  garantit encore qu'une propriété utile n'a pas été omise avant pruning.
- L'acquisition d'information et les décisions fondées sur des observations ne
  sont pas intégrées au modèle temporel/solver actuel.
- Les plateformes physiques, caches, bande passante et concurrence système ne
  sont pas représentés par ces POC.

### Scalabilité et architecture

- Les modèles CP-SAT sont compacts sur de petites familles synthétiques, mais la
  scalabilité générale de la formulation jointe n'est pas démontrée.
- Le coût de construction du modèle, les symétries, les grands graphes et les
  stratégies éventuelles de décomposition restent à caractériser.
- Le rôle à long terme d'egglog, CP-SAT ou d'autres solveurs n'est pas fixé ; ce
  sont des substrats expérimentaux.
- La génération puis l'exécution de code spécialisé réel restent hors
  démonstration.

## Semantic kernel

Le noyau ci-dessous est un inventaire conceptuel minimal justifié par les POC,
pas un schéma de types définitif.

### Description

`Description` fournit une identité générique aux choses sur lesquelles Atlas
raisonne. Selon ses relations, elle peut jouer le rôle d'intention, réalisation,
représentation auxiliaire, producteur ou opération. Les POC ne justifient pas de
promouvoir chacun de ces rôles en type fondamental.

### Relations structurelles démontrées

| Relation / forme | Rôle démontré |
|---|---|
| `realizes(R, I)` | R satisfait l'intention I |
| `requires(X, Y)` | X dépend de Y |
| `builds(B, Y)` / `produces(B, Y)` | B peut produire Y |
| `represents(R, X)` | R est une représentation de X |
| `present(X, scenario)` | X est déjà présent dans le scénario |
| `enabled(B, scenario)` | B est utilisable dans le scénario |
| précédence | une opération doit en précéder une autre |
| usage requiert faits P… | une réalisation dépend de faits contextuels |

Les noms précis restent expérimentaux ; le tableau retient surtout les formes de
relations dont les expériences ont eu besoin.

### Faits de contexte démontrés

Les scénarios ont porté notamment : workload, coûts, tailles, capacité,
release/deadline, présence ou activation locale d'un producteur,
`known_from`/`valid_until` et propriétés pertinentes d'une réalisation ou d'un
producteur.

Ces faits sont contextuels et ne doivent pas devenir des propriétés universelles
lorsque leur validité dépend du scénario.

### États et propriétés dérivés

- `constructible` : une ressource peut être produite dans le scénario selon les
  producteurs et préconditions connus ;
- `available` : une dépendance nécessaire est présente ou obtenable selon le
  modèle courant ;
- `admissible` : une réalisation respecte les contraintes du scénario ;
- `selected` : la réalisation appartient à la solution choisie ;
- lifetime : intervalle dérivé des producteurs, consommateurs et du planning ;
- peak live resource : maximum des ressources simultanément vivantes ;
- makespan : propriété du planning et objectif utilisé dans les POC temporels.

L'absence de dérivation n'est pas une négation universelle : Atlas doit
préserver la différence entre « non connu ici » et « impossible ».

### Décisions et temps

Les formulations testées peuvent décider : réalisation, producteur, ressource,
présence d'une préparation et placement temporel d'opérations optionnelles sous
précédences et capacités.

Le temps n'a pas exigé de nouveau type ontologique général. Les POC utilisent la
durée comme fait d'opération ; début/fin comme décisions ; précédence comme
relation/contrainte ; release, deadline et fenêtres de validité comme faits de
scénario ; lifetime, peak et makespan comme propriétés dérivées.

Cette intégration est démontrée dans les cas testés sans prouver que le noyau
temporel est complet.

### Catalogue, scénario, solution

Le catalogue décrit les possibilités connues : réalisations, dépendances,
producteurs et propriétés structurelles.

Le scénario ajoute les faits locaux : workload, ressources présentes,
producteurs activés, capacités, contraintes temporelles et connaissances
valides.

La solution résulte de leur composition sous contraintes. `constructible`,
`admissible`, sélection, lifetime, peak et makespan ne sont pas des vérités
intrinsèques du catalogue.

### Formulation dominante actuelle

> Atlas décrit un espace de possibilités, de relations et de faits contextuels,
> puis cherche quelles conditions doivent être satisfaites pour obtenir une
> réalisation admissible et préférable, sans exiger la génération préalable de
> toutes les réalisations complètes.

Cette formulation est mieux soutenue par les POC que le modèle « générer les
candidats, évaluer leurs coûts, puis choisir » dans le périmètre où une
compilation vers un problème de contraintes est possible.

## Complexity smells

- La connaissance dérivée exige une provenance distincte de la provenance
  directement sourcée. Des bases de dérivation conservées uniquement comme
  texte libre ne permettent ni résolution, ni audit mécanique, ni détection de
  dépendances ou de cycles.
- Un validateur purement structurel peut accepter un corpus syntaxiquement
  cohérent mais sémantiquement dangereux. À mesure que le corpus grandit, les
  identités trop larges, prédicats polysémiques, scopes réparateurs et
  informations essentielles enfermées dans `evidence` peuvent produire des
  compositions plausibles mais fausses.
- Les rôles documentaires associés aux `Description` ne doivent pas être
  confondus prématurément avec une ontologie fermée.
- Les catalogues expérimentaux fournissent encore les relations sémantiques ;
  Atlas ne sait pas encore les découvrir ou les vérifier en général.
- Une propriété absente du modèle peut rendre un pruning apparemment correct
  faux. Toute dominance dépend de l'ensemble des propriétés jugées pertinentes.
- Le partage repose sur l'identité stricte des descriptions ; partager des
  descriptions seulement équivalentes peut être incorrect si coûts, lifetimes,
  effets ou contraintes diffèrent.
- Les dataclasses locales des harnais (`CompositeRealization`, `Call`, fenêtres
  de faits, etc.) sont des commodités expérimentales, pas une API Atlas.
- Les POC temporels utilisent des temps entiers, des horizons bornés et des
  modèles de concurrence simplifiés.
- Le peak est parfois dérivé hors solveur selon les mêmes conventions que le
  modèle ; cette duplication doit rester validée croisée.
- Les oracles exhaustifs sont exacts sur les petites instances mais ne passent
  pas à l'échelle.
- L'objectif de makespan masque les arbitrages réels entre temps, mémoire et
  autres coûts.
- Les égalités et symétries peuvent laisser plusieurs solutions équivalentes ;
  aucune règle générale de canonicalisation des solutions n'est établie.
- La frontière actuelle egglog / Python / CP-SAT vient des expériences et ne
  constitue pas l'architecture finale d'Atlas.
- La compacité observée de CP-SAT sur les cas synthétiques ne garantit pas que
  variables, contraintes ou temps de résolution resteront maîtrisables lorsque
  le modèle s'enrichira.
- Mutation et invalidation constituent une frontière critique : elles peuvent
  changer simultanément admissibilité, lifetimes et bénéfice d'une
  spécialisation.
- Gouvernance documentaire : `knowledge.md` doit rester une consolidation de
  l'état courant. Les étapes intermédiaires, preuves détaillées et sorties de
  benchmark appartiennent aux scripts et README des POC et ne doivent plus être
  ajoutées chronologiquement ici.
