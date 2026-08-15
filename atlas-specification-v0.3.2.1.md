# Atlas — Specification v0.3.2.1

**Status:** révision normative mineure de la v0.3.2 ; clarification de l’interopérabilité des structures, des préconditions négatives, de la révision des dérivations et des critères de conformité  
**Nature:** spécification fonctionnelle et architecturale ; les choix de bibliothèques, formats de stockage et solveurs ne sont normatifs que lorsqu'ils sont explicitement indiqués comme tels.

---

## 1. Objet

Atlas est un système destiné à transformer une description abstraite d'un besoin de calcul en une réalisation concrète adaptée :

- au sens de ce qui doit être obtenu ;
- aux connaissances disponibles ;
- au workload attendu ;
- aux ressources et contraintes ;
- à la plateforme cible ;
- au temps, lorsque celui-ci influence la faisabilité ou l'intérêt des réalisations.

Atlas ne se réduit ni à un optimiseur de code, ni à un ordonnanceur, ni à un système de recommandation d'algorithmes. Il maintient et exploite un espace de connaissances sur les calculs, les représentations, les transformations, leurs conditions d'application et leurs conséquences.

La formulation de travail retenue en v0.3 est :

> **Atlas décrit un espace de possibilités, de relations et de faits contextuels, puis cherche quelles conditions doivent être satisfaites pour obtenir une réalisation admissible et préférable, sans exiger la génération préalable de toutes les réalisations complètes.**

Une réalisation sélectionnée peut ensuite être matérialisée en code, structures de données, configuration ou autre artefact exécutable.

---

## 2. Terminologie normative

Dans cette spécification :

- **DOIT** exprime une exigence normative ;
- **NE DOIT PAS** exprime une interdiction normative ;
- **DEVRAIT** exprime une exigence souhaitable dont une implémentation peut s'écarter avec justification ;
- **PEUT** exprime une possibilité non obligatoire.

Les termes `Description`, `Relation`, `Fact`, `Context`, `Workload`, `Platform`, `Solution` et `Materialization` désignent des rôles conceptuels. Leur traduction en types techniques n'est pas imposée sauf mention contraire.

---

## 3. Principes fondamentaux

### 3.1 Intention indépendante des ressources

Une intention exprime ce qui doit être obtenu.

L'absence d'une ressource, d'une représentation ou d'un producteur NE DOIT PAS modifier ou supprimer l'intention. Elle peut seulement rendre certaines réalisations non disponibles ou non admissibles dans le contexte courant.

### 3.2 Rôles plutôt que hiérarchie ontologique

Atlas NE DOIT PAS supposer que `Intent`, `Realization` et `Resource` sont nécessairement des types fondamentaux distincts.

Une même représentation générique, appelée ici `Description`, PEUT jouer différents rôles selon les relations dans lesquelles elle intervient.

Exemples :

- une description I peut être l'objet d'une relation `realizes(R, I)` et jouer le rôle d'intention ;
- R joue alors le rôle de réalisation ;
- une description S requise par R peut jouer le rôle de représentation auxiliaire ou de ressource ;
- une opération B reliée par `produces(B, S)` peut jouer le rôle de producteur.

Cette économie de concepts est une hypothèse architecturale désormais suffisamment soutenue pour constituer la base de la v0.3, sans prétendre à sa complétude universelle.

### 3.3 Monde ouvert

L'absence d'une connaissance n'est pas sa négation.

Atlas DOIT distinguer au minimum :

- « connu vrai dans ce contexte » ;
- « connu faux dans ce contexte », lorsque cette information existe réellement ;
- « non connu » ;
- « aucun moyen admissible connu actuellement ».

En particulier, l'absence d'un producteur connu NE DOIT PAS être transformée en impossibilité universelle.

### 3.4 Contexte

La constructibilité, l'admissibilité, le coût, la disponibilité, la préférence et parfois la validité d'une réalisation sont contextuels.

Atlas DOIT distinguer les connaissances de catalogue, qui décrivent des possibilités relativement stables, des faits de scénario, qui décrivent la situation courante.

### 3.5 Connaissance imparfaite comme état normal

Atlas ne garantit ni que son corpus est complet, ni que toute connaissance qu'il contient est vraie.

Il DOIT en revanche permettre de représenter :

- l'origine d'une connaissance ;
- son statut épistémique ;
- ses hypothèses ;
- son domaine de validité ;
- sa portée de plateforme et de workload ;
- sa validité temporelle lorsque pertinente ;
- les décisions qui en dépendent, directement ou indirectement.

Une connaissance plus précise ou mieux établie DOIT pouvoir remplacer ou restreindre une connaissance antérieure sans exiger la reconstruction manuelle de toute la base.

### 3.6 Connaissance durable, réalisations régénérables

Les descriptions de besoins, relations sémantiques, faits établis, modèles de plateforme, mesures et hypothèses constituent des actifs plus durables que leurs matérialisations particulières.

Atlas DEVRAIT permettre le modèle suivant :

> besoins modifiés → nouvelle résolution globale → nouvelle réalisation

plutôt que d'imposer :

> besoins modifiés → modification incrémentale de la matérialisation précédente

Une réalisation antérieure PEUT être conservée comme observation, exemple ou candidat connu ; elle ne doit pas être traitée comme architecture sacrée si elle peut être régénérée à partir d'une connaissance plus durable.

---

## 4. Modèle conceptuel

### 4.1 Description et identité

Une `Description` est une entité identifiable sur laquelle Atlas peut énoncer des faits et relations.

Une description PEUT représenter notamment :

- une intention ;
- une opération ;
- un algorithme ;
- une réalisation ;
- une structure ou représentation de données ;
- une préparation ;
- un résultat intermédiaire ;
- une capacité ;
- un état de plateforme ;
- un fait ou une propriété réifiée lorsque cela est utile.

La liste n'est pas exhaustive.

#### Identité nominale

L'identité persistante d'une `Description` est **nominale et stable**.

Deux références désignent la même description si et seulement si elles portent ou résolvent vers le même identifiant persistant selon le mécanisme d'identité du Knowledge Store.

Une égalité de structure, un hash identique, une similarité de contenu ou une équivalence sémantique NE DOIVENT PAS suffire à fusionner deux identités nominales distinctes.

Les règles d'identité, d'égalité, d'ordre, de hachage et de coercition des identifiants et valeurs sémantiques DOIVENT être définies par Atlas lorsqu'elles influencent le raisonnement.

Elles NE DOIVENT PAS être introduites implicitement par :

- l'égalité ou le hachage du langage hôte ;
- l'ordre naturel d'une structure de données d'implémentation ;
- l'interning ;
- une conversion automatique de types ;
- toute autre commodité de représentation technique.

Une implémentation PEUT réutiliser les mécanismes du langage hôte uniquement lorsqu'elle établit explicitement qu'ils implémentent les règles Atlas requises.

Une opération de canonicalisation PEUT établir une relation entre deux descriptions ou choisir une représentation canonique pour un calcul particulier ; elle NE DOIT PAS réécrire silencieusement leur identité historique.

Cette règle permet notamment de conserver séparément :

- provenance ;
- coûts ;
- propriétés ;
- effets ;
- lifetimes ;
- versions ;
- domaines de validité.

#### Identité, équivalence et partage

Atlas DOIT distinguer au minimum :

1. **identité de description** : deux références désignent la même entité persistante ;
2. **équivalence sémantique** : deux descriptions sont interchangeables relativement à un domaine d'observation déclaré ;
3. **partage d'instance** : une même instance concrète d'une description peut satisfaire plusieurs usages dans une solution donnée.

Ces trois notions ne s'impliquent pas mutuellement.

En particulier :

- deux descriptions distinctes PEUVENT être sémantiquement équivalentes sans être identiques ;
- une même description PEUT donner lieu à plusieurs instances concrètes ;
- deux usages de la même description NE DOIVENT PAS être forcés à partager une instance si mutation, effets, placement, isolation, plateforme ou lifetimes rendent ce partage invalide.

La décision de partager une instance est donc contextuelle et appartient à la résolution, non au mécanisme d'identité nominale.

### 4.2 Relation

Une `Relation` exprime un lien entre descriptions.

Le vocabulaire relationnel DOIT être extensible. La v0.3.2.1 retient comme formes déjà démontrées :

- `realizes(R, I)` : R satisfait l'intention I ;
- `requires(X, Y)` : X dépend de Y ;
- `produces(B, Y)` ou `builds(B, Y)` : B peut produire Y ;
- `represents(R, X)` : R est une représentation de X ;
- `present(X, C)` : X est présent dans le contexte C ;
- `enabled(B, C)` : B est disponible ou autorisé dans C ;
- précédence temporelle ;
- dépendance d'une réalisation à un ou plusieurs faits contextuels.

Ces noms ne constituent pas nécessairement une API définitive.

#### Stabilité sémantique des prédicats

Un prédicat utilisé pour le raisonnement DOIT avoir une sémantique stable.

Son domaine de validité, ses hypothèses, son statut épistémique ou son evidence PEUVENT restreindre l'applicabilité d'une assertion ; ils NE DOIVENT PAS redéfinir silencieusement le sens du prédicat.

Une évolution incompatible du sens d'un prédicat DOIT être représentée comme une évolution explicite du vocabulaire, de la version ou de l'identité concernée.

#### Participants et propriétés

Toute propriété consommée par une règle DOIT être résolue relativement à l'identité du ou des participants auxquels elle s'applique.

Le fait qu'une propriété de même nom existe pour une autre description NE DOIT PAS suffire à satisfaire cette règle.

Un identifiant de propriété syntaxiquement ou structurellement valide NE DOIT PAS être assimilé à une propriété reconnue par la règle courante. L'appartenance au vocabulaire consommé par cette règle DOIT être établie séparément.

#### Conclusions dérivées

Une conclusion relationnelle dérivée qui participe au raisonnement DOIT conserver, directement ou par référence récupérable :

- son prédicat ;
- ses participants groundés ;
- son statut épistémique lorsque pertinent ;
- ses dépendances effectives suffisantes pour expliquer la dérivation.

Un résultat booléen indiquant qu'une condition a été évaluée à vrai ou faux NE DOIT PAS être assimilé, à lui seul, à la conclusion relationnelle groundée qui peut en découler.

#### Relations multivaluées

Une relation NE DOIT être traitée comme une fonction que si l'unicité pertinente est :

- déclarée comme invariant ;
- dérivée des connaissances disponibles ;
- ou vérifiée au moment où cette fonctionnalisation est utilisée.

Une structure technique à clé unique, un écrasement de valeur ou la sélection implicite d'un premier résultat NE DOIVENT PAS créer artificiellement cette unicité.

### 4.3 Fact

Un `Fact` associe une information à une ou plusieurs descriptions dans un contexte déterminé.

Exemples :

- cardinalité ;
- taille ;
- durée ;
- coût ;
- capacité ;
- latence ;
- bande passante ;
- propriété structurelle ;
- présence ;
- valeur mesurée ;
- hypothèse de workload ;
- fenêtre de validité ;
- propriété d'un producteur.

Un fait NE DOIT PAS devenir implicitement universel lorsque sa valeur dépend du scénario, de la plateforme, du workload ou du temps.

#### Valeurs et expressions structurées

La valeur d'un fait ou d'une assertion PEUT être structurée.

Lorsqu'une structure interne participe à la correction, à la validité, à l'applicabilité ou aux conséquences d'une connaissance, cette structure DOIT être conservée sous une forme exploitable par le raisonnement.

Sa conservation uniquement dans :

- un champ narratif ;
- `scope` ;
- `assumptions` ;
- `evidence` ;
- ou toute autre métadonnée non interprétée par le raisonnement

ne suffit pas.

Cette exigence n'impose ni AST universel, ni algèbre générale de termes, ni nouveau type fondamental.

Lorsque plusieurs composants échangent des connaissances structurées destinées à être composées ou raisonnées conjointement, ils DOIVENT partager une représentation d'échange dont la sémantique pertinente est explicite et versionnée, ou fournir une traduction dont la préservation de cette sémantique est explicite.

Cette obligation d'interopérabilité n'impose pas qu'Atlas définisse un AST universel unique pour toutes les connaissances ni que toute représentation interne soit identique entre composants.

### 4.4 Context / Scenario

Un `Context` regroupe les informations locales nécessaires à une décision.

Il PEUT inclure :

- les descriptions demandées ;
- les ressources présentes ;
- les producteurs activés ;
- les contraintes ;
- le workload ;
- la plateforme ;
- le temps ou les fenêtres temporelles ;
- les faits actuellement connus ;
- la politique d'objectif ;
- les hypothèses spécifiques à la résolution.

### 4.5 Solution

Une `Solution` est un ensemble cohérent de décisions satisfaisant les intentions et les contraintes retenues.

Elle PEUT inclure :

- les réalisations sélectionnées ;
- les producteurs sélectionnés ;
- les représentations produites ou réutilisées ;
- les décisions de placement temporel ;
- les propriétés dérivées ;
- les coûts et limites calculés ;
- les faits dont la solution dépend ;
- les alternatives équivalentes ou non dominées.

Une solution n'est pas nécessairement une matérialisation.

---

## 5. Sémantique observable

### 5.1 Réalisation

`realizes(R, I)` signifie que R satisfait la sémantique observable requise par I dans le domaine où la relation est déclarée valable.

La relation `realizes` n'est pas une égalité d'identité.

Deux réalisations différentes PEUVENT réaliser la même intention tout en ayant :

- des représentations différentes ;
- des besoins de ressources différents ;
- des coûts différents ;
- des lifetimes différents ;
- des effets secondaires différents lorsque ceux-ci sont admissibles ;
- des domaines de validité différents.

### 5.2 Équivalence

Une relation d'équivalence sémantique PEUT être introduite lorsqu'elle est utile, mais elle est plus forte que le simple fait que deux descriptions réalisent une même intention.

Atlas NE DOIT PAS déduire automatiquement qu'une équivalence sémantique implique :

- identité physique ;
- coût identique ;
- lifetime identique ;
- mêmes effets secondaires ;
- interchangeabilité de producteurs ;
- partage sûr d'une même ressource.

Le domaine d'observation sous lequel l'équivalence est affirmée DOIT être explicite ou récupérable.

### 5.3 Décomposition et convergence

Atlas DOIT pouvoir représenter comme exigence générale :

- qu'une intention se décompose en plusieurs sous-intentions ou dépendances ;
- que plusieurs intentions ou sous-intentions convergent vers une préparation, une représentation ou un calcul partagé ;
- qu'une réalisation puisse satisfaire ou contribuer à plusieurs intentions.

La v0.3.2.1 ne prétend pas que la découverte automatique de toute décomposition ou convergence sémantique est résolue.

---

## 6. Modèle épistémique des connaissances

### 6.1 Statut épistémique

Une information quantitative ou qualitative DEVRAIT pouvoir être qualifiée au minimum comme :

- `exact` ;
- `bound` ;
- `estimate` ;
- `unknown`.

Une implémentation PEUT raffiner cette taxonomie.

Pour les valeurs quantitatives non exactes, Atlas DEVRAIT conserver un intervalle ou une représentation de l'incertitude suffisante pour permettre un raisonnement prudent.

### 6.2 Provenance

Toute connaissance utilisée pour une décision non triviale DEVRAIT pouvoir référencer sa provenance.

La provenance PEUT pointer vers :

- une source documentaire ;
- une publication ;
- une spécification ;
- une mesure ;
- un benchmark ;
- une preuve ;
- un test ;
- un auteur humain ;
- un agent ;
- une dérivation interne ;
- une connaissance antérieure.

La provenance n'est pas une garantie de vérité ; elle rend la connaissance inspectable et révisable.

Toute connaissance dérivée destinée à être persistée ou réutilisée durablement DOIT :

- être identifiable comme dérivée ;
- conserver des dépendances structurées suffisantes pour l'audit ;
- permettre de retrouver les connaissances dont sa validité dépend ;
- permettre, au moins conceptuellement, la révision ou la reproduction de la dérivation lorsque ces dépendances changent.

Une justification exclusivement narrative NE DOIT PAS être considérée comme suffisante pour une dérivation persistée.

Cette obligation ne s'applique pas nécessairement aux valeurs intermédiaires éphémères d'un solveur ou d'une évaluation locale qui ne sont ni persistées ni réutilisées comme connaissance.

La conservation de ces dépendances N'IMPOSE PAS, en particulier pour la V1, un système réactif de maintenance de vérité propageant automatiquement toute invalidation en cascade. Une implémentation PEUT marquer une dérivation persistée comme obsolète, suspecte ou à recalculer lorsque l'une de ses dépendances change, puis effectuer sa révision ou sa reproduction de manière paresseuse.

### 6.3 Hypothèses et domaine de validité

Un fait ou une relation PEUT être conditionné par :

- une plateforme ;
- une version ;
- un jeu d'entrées ;
- un workload ;
- une distribution ;
- une taille ;
- une précondition structurelle ;
- une durée de stabilité ;
- une contrainte de concurrence ;
- un mode d'exécution.

Atlas DOIT éviter de promouvoir une observation locale en loi universelle sans justification explicite.

Toute précondition dont dépend la validité ou l'applicabilité d'une connaissance DOIT être représentée de manière structurée et participer mécaniquement à la détermination de son applicabilité.

L'absence d'une telle précondition dans le contexte NE DOIT PAS être interprétée comme sa satisfaction.

Une précondition PEUT être satisfaite par un fait directement présent, une dérivation, une preuve ou un autre mécanisme explicite prévu par Atlas.

Une précondition négative, une absence d'effet ou une absence d'événement NE DOIT PAS être établie par la seule absence d'une assertion positive dans le corpus. Elle PEUT être établie notamment par :

- un fait négatif explicite ;
- un invariant ou une garantie constructive, par exemple immutabilité, ownership exclusif ou absence d'aliasing ;
- une preuve ou une dérivation ;
- une portée localement fermée explicitement déclarée pour la dimension considérée ;
- une hypothèse explicite, provenancée et qualifiée épistémiquement, lorsque la politique de décision autorise son usage.

Atlas NE DOIT PAS appliquer implicitement une sémantique globale de négation par échec (`Negation as Failure`) dans son corpus en monde ouvert.

### 6.4 Validité temporelle

Lorsque le temps est pertinent, Atlas DEVRAIT pouvoir distinguer :

- `known_from` : moment à partir duquel l'information est disponible pour la décision ;
- `valid_from` : début de validité du fait dans le monde représenté ;
- `valid_until` : fin de validité connue ou supposée ;
- `invalidated_by` : événement ou condition susceptible d'invalider le fait.

Toutes ces dimensions ne sont pas obligatoires pour tous les faits.

### 6.5 Contradictions et révisions

Plusieurs assertions incompatibles PEUVENT coexister tant que leur provenance, portée ou statut permet de les distinguer.

Atlas NE DOIT PAS résoudre silencieusement une contradiction par écrasement arbitraire.

Une politique de résolution PEUT :

- sélectionner la connaissance la mieux établie dans le contexte ;
- conserver plusieurs hypothèses concurrentes ;
- demander une information supplémentaire ;
- produire plusieurs solutions conditionnelles.

---

## 7. Base de connaissances et collecte

### 7.1 Rôle de la base de connaissances

La base de connaissances est un composant de premier rang d'Atlas.

Elle contient les descriptions, relations, propriétés, modèles de coût, faits de plateforme, mesures, preuves, hypothèses et provenance nécessaires au raisonnement.

Atlas n'attend pas qu'une encyclopédie complète existe avant de fonctionner. Il DOIT pouvoir raisonner avec un corpus partiel et s'améliorer à mesure que celui-ci s'enrichit.

### 7.2 Granularité

La connaissance DEVRAIT être enregistrée sous des assertions aussi atomiques que raisonnable.

Exemples :

- une opération réalise une intention ;
- une réalisation requiert une propriété ;
- une transformation produit une représentation ;
- une propriété est invalidée par une mutation ;
- un coût dépend d'une cardinalité ;
- une opération est disponible sur une plateforme ;
- une mesure borne une durée dans un contexte.

L'objectif est de rendre les assertions composables et réutilisables par la machine, plutôt que d'accumuler uniquement des fiches narratives.

### 7.3 Ingestion

Atlas DEVRAIT permettre l'ingestion de connaissances depuis :

- saisie humaine ;
- documentation structurée ;
- extraction assistée par LLM ;
- benchmarks ;
- tests ;
- analyse de code ;
- publications ;
- bases externes ;
- autres agents.

Une connaissance importée par un agent NE DOIT PAS perdre son statut de provenance ni être implicitement assimilée à un fait exact.

### 7.4 Curation

Le corpus DOIT pouvoir être :

- enrichi ;
- corrigé ;
- déprécié ;
- restreint à un domaine plus précis ;
- remplacé par une observation plus solide ;
- audité.

La curation est une fonction normale du système, pas une opération exceptionnelle de migration.

---

## 8. Workload

Le `Workload` décrit comment les intentions et réalisations seront réellement utilisées.

Il PEUT inclure :

- nombre d'appels ;
- fréquence ;
- cardinalités ;
- distributions d'entrées ;
- ordre des opérations ;
- taux de lecture/écriture ;
- horizon d'utilisation ;
- concurrence ;
- répétitions ;
- stabilité attendue de certains paramètres.

Le workload est une connaissance de scénario de premier rang.

Atlas NE DOIT PAS supposer qu'une réalisation est préférable indépendamment du workload lorsque ses coûts comprennent une préparation, une construction, une conversion ou une spécialisation amortissable.

---

## 9. Semantic Recovery

Le `Semantic Recovery` vise à reconstruire depuis un programme, une trace, une API ou un artefact existant des descriptions sémantiques utilisables par Atlas.

Cette fonction est un adaptateur d'entrée, pas une condition d'existence d'Atlas.

La v0.3.2.1 ne requiert pas une décompilation sémantique générale.

Une implémentation initiale PEUT alimenter Atlas avec des intentions et relations déclarées manuellement, assistées par agent ou extraites de domaines limités.

Toute connaissance issue d'une récupération sémantique DEVRAIT conserver :

- sa source ;
- son niveau de confiance ;
- les observations sur lesquelles elle repose ;
- les hypothèses nécessaires à sa validité.

---

## 10. Semantic Workshop

Le `Semantic Workshop` est l'ensemble des mécanismes permettant d'enrichir et de relier les descriptions.

Il vise notamment à découvrir ou proposer :

- des réalisations d'une intention ;
- des décompositions ;
- des recompositions ;
- des factorisations ;
- des représentations intermédiaires ;
- des transformations ;
- des préparations ;
- des spécialisations ;
- des relations entre sous-intentions.

La découverte PEUT être :

- déclarative ;
- algorithmique ;
- guidée par règles ;
- proposée par LLM ;
- issue de mesures ;
- confirmée par tests ou preuves.

Le workshop NE DOIT PAS être confondu avec le solveur. Il enrichit l'espace de connaissances ; le solveur exploite un sous-ensemble pertinent de cet espace pour une décision concrète.

---

## 11. Espace sémantique

Atlas PEUT être implémenté comme graphe, base relationnelle, e-graph, système logique, base de faits ou combinaison de ces formes.

La spécification n'impose pas qu'un unique « semantic graph » soit matérialisé en mémoire.

Conceptuellement, l'espace sémantique contient :

- des descriptions ;
- leurs relations ;
- des faits ;
- leurs conditions de validité ;
- des dépendances ;
- des dérivations.

La représentation DOIT préserver suffisamment d'identité et de structure pour permettre le partage, la provenance, l'applicabilité, la dérivation et l'explication.

Lorsqu'une structure interne influence les conséquences sémantiques, elle DOIT rester accessible au raisonnement et ne pas être aplatie en métadonnée narrative.

Lorsque l'ordre des éléments modifie les conséquences, cet ordre fait partie de la connaissance représentée et DOIT être préservé pendant le raisonnement.

Une représentation non ordonnée NE DOIT PAS être substituée à une représentation ordonnée lorsque cette substitution peut modifier la validité, l'applicabilité ou le résultat d'une dérivation.

Le corpus persistant NE DOIT PAS être fermé normativement sur les seules constructions comprises par un évaluateur ou backend particulier.

Une implémentation PEUT rejeter, isoler ou différer les constructions qu'elle ne sait pas actuellement évaluer, mais cette limite technique NE DOIT PAS être assimilée à la limite du vocabulaire Atlas.

---

## 12. Ressources

### 12.1 Ressource comme rôle

`Resource` n'est pas un type fondamental imposé.

Toute description nécessaire à une autre description et possiblement produite, présente, consommée, partagée ou limitée PEUT jouer le rôle de ressource.

Exemples :

- représentation triée ;
- index ;
- buffer temporaire ;
- mémoire ;
- résultat intermédiaire ;
- capacité de worker ;
- information stable ;
- primitive de plateforme.

### 12.2 Présence et constructibilité

Atlas DOIT distinguer :

1. une possibilité connue dans le catalogue ;
2. une ressource présente dans le scénario ;
3. une ressource constructible dans le scénario ;
4. une réalisation admissible sous les contraintes ;
5. une réalisation sélectionnée.

Ces états NE DOIVENT PAS être confondus.

### 12.3 Partage

Lorsque plusieurs consommateurs requièrent la même **description nominale**, Atlas DEVRAIT pouvoir considérer la production d'une instance partagée.

Cette identité commune est une condition utile de partage, mais elle n'est pas une preuve suffisante que la même instance concrète peut être réutilisée.

Le partage d'instance DOIT rester compatible avec les propriétés pertinentes du contexte, notamment lorsqu'elles existent :

- mutation et effets ;
- lifetime ;
- placement temporel ;
- plateforme ou espace mémoire ;
- isolation ;
- préconditions du producteur ;
- contraintes propres aux consommateurs.

Lorsque ces conditions sont satisfaites, Atlas DEVRAIT éviter de compter plusieurs fois la production d'une même instance effectivement partagée.

À l'inverse, plusieurs instances d'une même description PEUVENT être nécessaires dans une même solution.

Le partage entre descriptions nominalement distinctes mais sémantiquement équivalentes est une opération plus forte. Il NE DOIT PAS être appliqué sans une justification explicite d'interchangeabilité physique dans le contexte courant.

---

## 13. Temps et lifecycle

### 13.1 Temps comme dimension du problème

Le temps PEUT influencer :

- la faisabilité ;
- l'admissibilité ;
- le choix de réalisation ;
- le peak de ressources ;
- la rentabilité d'une préparation ;
- la disponibilité d'une connaissance.

Atlas NE DOIT PAS imposer un pipeline universel :

> sélectionner les réalisations → planifier ensuite

La résolution PEUT joindre les décisions structurelles et temporelles lorsque leurs contraintes interagissent.

Inversement, une implémentation PEUT séparer les problèmes lorsqu'elle possède un critère justifiant que cette séparation ne change pas la solution pertinente.

### 13.2 Opérations temporelles

Une opération temporelle PEUT avoir :

- une durée ;
- un début ;
- une fin ;
- une release ;
- une deadline ;
- des précédences ;
- une consommation de capacité ;
- une présence conditionnelle.

### 13.3 Lifetime

Pour une ressource produite puis consommée, une convention minimale démontrée est :

> `[fin_du_producteur, fin_du_dernier_consommateur)`

D'autres conventions PEUVENT être nécessaires pour des ressources plus complexes.

Le lifetime DEVRAIT être dérivé de la réalisation et du planning plutôt qu'enregistré comme une propriété statique lorsqu'il dépend effectivement de ceux-ci.

### 13.4 Peak resource consumption

La consommation peak d'une ressource cumulative est une propriété du planning.

Atlas NE DOIT PAS assimiler en général :

> somme des ressources construites

et :

> ressources simultanément live.

Des ressources dont les lifetimes ne se chevauchent pas PEUVENT réutiliser une capacité sans relation métier explicite de réutilisation.

---

## 14. Stabilité et spécialisation

Une propriété ou connaissance suffisamment stable PEUT rendre admissible une réalisation spécialisée.

Une spécialisation PEUT comporter :

- une préparation ;
- une compilation ;
- une conversion ;
- une structure auxiliaire ;
- un coût initial ;
- un coût réduit par usage ultérieur.

Atlas DOIT évaluer la spécialisation dans le contexte de ses usages réellement admissibles.

Le seul nombre total d'usages n'est pas suffisant lorsque :

- les usages ne tombent pas tous dans la fenêtre de validité ;
- la préparation consomme du temps ou des ressources ;
- les contraintes de planning changent leur placement ;
- plusieurs connaissances doivent être simultanément valides.

La v0.3.2.1 n'impose pas de spécialisation dynamique à l'exécution. Elle exige seulement que le modèle ne l'interdise pas conceptuellement.

---

## 15. Platform Knowledge

La connaissance de plateforme décrit ce qui est vrai ou mesuré pour une cible concrète.

Elle PEUT inclure :

- primitives disponibles ;
- tailles et alignements ;
- capacités mémoire ;
- coûts d'instructions ou d'opérations ;
- caractéristiques de cache ;
- bande passante ;
- concurrence ;
- coûts d'allocation ;
- coûts de transfert ;
- limites de l'environnement ;
- propriétés du runtime ou du compilateur.

La connaissance de plateforme DOIT être séparée de la matérialisation.

Le fait qu'une plateforme supporte une primitive ou qu'une opération y coûte X ne détermine pas à lui seul la manière dont une réalisation sélectionnée est encodée en code.

Les faits de plateforme DEVRAIENT être versionnés et provenancés lorsque leur validité dépend d'un matériel, logiciel ou benchmark précis.

---

## 16. Coûts

### 16.1 Coût contextualisé

Un coût est une information dépendant potentiellement :

- du workload ;
- de la plateforme ;
- d'une taille ;
- d'une représentation ;
- d'un ordre temporel ;
- d'une préparation ;
- de ressources déjà présentes.

Un coût PEUT être un nombre, une borne, un intervalle, une fonction ou une expression dérivable.

### 16.2 Dimensions

Atlas NE DOIT PAS imposer un unique scalaire universel de coût.

Les dimensions PEUVENT inclure :

- durée / latence ;
- throughput ;
- mémoire peak ;
- mémoire persistante ;
- allocations ;
- bande passante ;
- I/O ;
- énergie ;
- taille de code ;
- temps de préparation ;
- coût monétaire ;
- autres dimensions propres au domaine.

### 16.3 Construction et amortissement

Le coût d'une préparation ou ressource partagée DEVRAIT être compté selon son identité et son lifecycle réel.

Une préparation payée une fois et réutilisée N fois NE DOIT PAS être automatiquement facturée N fois.

### 16.4 Préférences

Le contexte DOIT pouvoir fournir une politique de préférence combinant :

- contraintes dures ;
- objectifs ;
- priorités ;
- éventuellement ordre lexicographique, pondération ou Pareto.

La v0.3.2.1 ne définit pas une politique multiobjectif universelle.

---

## 17. Dérivation du problème de décision

### 17.1 Entrées

Une résolution Atlas prend conceptuellement :

- une ou plusieurs intentions ;
- un snapshot de connaissances ;
- un contexte ;
- un workload ;
- une plateforme ou famille de plateformes ;
- des contraintes ;
- une politique d'objectif ;
- une politique de grounding.

### 17.2 Decision Scope et politique de grounding

Atlas raisonne sur un corpus en monde ouvert, mais un backend de résolution reçoit nécessairement un problème fini.

Le `Decision Scope` décrit le domaine que le Decision Compiler est autorisé à considérer pour une résolution donnée.

La `Grounding Policy` décrit comment le Decision Compiler construit un problème fini à partir de ce domaine.

Elle DEVRAIT rendre explicites, lorsque pertinents :

- le snapshot du corpus interrogé ;
- les catégories de relations ou règles suivies ;
- les plateformes considérées ;
- la profondeur ou forme de fermeture autorisée ;
- les bornes de taille, coût ou temps de construction ;
- les horizons temporels artificiels éventuels ;
- les règles de pertinence ou de pruning appliquées ;
- les raisons qui arrêtent l'expansion.

Atlas DEVRAIT dériver un sous-ensemble pertinent des descriptions, relations et faits avant ou pendant la résolution. Il n'est pas requis de charger ou d'explorer intégralement la base de connaissances.

### 17.3 Fermeture dans le scope déclaré

La résolution DOIT pouvoir suivre récursivement les dépendances nécessaires dans le périmètre supporté :

- réalisation → ressource ;
- ressource → producteur ;
- producteur → prérequis ;
- réalisation → fait ;
- opération → précédence.

La fermeture s'effectue relativement au `Decision Scope` et à la `Grounding Policy`.

Les cycles restent une question ouverte ; une implémentation V1 PEUT les refuser explicitement.

L'arrêt de l'expansion NE DOIT PAS être confondu avec la preuve qu'aucune autre connaissance pertinente n'existe dans le monde ouvert.

### 17.4 Grounded Decision Problem

Le résultat du Decision Compiler est un `Grounded Decision Problem` fini.

Il DOIT être possible de relier ce problème à :

- son snapshot de connaissances ;
- son `Decision Scope` ;
- sa `Grounding Policy` ;
- les descriptions et faits effectivement inclus ;
- les exclusions ou bornes pertinentes.

Le grounding DOIT exposer un statut de couverture. La v0.3.2.1 retient au minimum les classes conceptuelles suivantes :

- `complete_for_declared_scope` : le compilateur peut justifier que la fermeture requise a été effectuée pour le scope déclaré et le snapshot courant ;
- `bounded` : une borne explicite a interrompu ou limité l'expansion ;
- `heuristic` : des règles de pertinence ou de pruning non prouvées complètes ont limité le problème.

`complete_for_declared_scope` ne signifie jamais que la base de connaissances est complète dans le monde réel. Il signifie seulement que le grounding est complet relativement au scope et au snapshot déclarés.

### 17.5 Pas d'obligation d'énumération des plans

Atlas NE DOIT PAS exiger que toutes les réalisations complètes soient matérialisées avant la sélection.

Lorsque cela est possible, le `Grounded Decision Problem` DEVRAIT être exprimé sous une forme compacte :

- variables ;
- contraintes ;
- objectifs ;
- relations de présence ou implication.

L'espace des solutions PEUT être exponentiel sans que la représentation grounded le soit.

### 17.6 Backend de résolution

Le backend de résolution n'est pas normatif.

Une implémentation PEUT utiliser :

- CP-SAT ;
- SAT/SMT ;
- MILP ;
- e-graphs ;
- programmation dynamique ;
- recherche spécialisée ;
- énumération bornée ;
- plusieurs backends combinés.

CP-SAT constitue un backend expérimental validé pour des cas booléens et temporels limités ; il ne définit pas l'architecture d'Atlas.

### 17.7 Résolution jointe

Lorsque choix de réalisation, ressources et temps s'influencent, le problème de décision DOIT pouvoir les représenter conjointement.

Une optimisation en phases séparées PEUT être utilisée lorsqu'elle est démontrée sûre ou acceptable pour le sous-problème considéré.

### 17.8 Statut du résultat

Atlas DOIT distinguer le statut du solveur du statut du grounding.

Un backend PEUT notamment établir :

- `optimal` ;
- `feasible` ;
- `infeasible` ;
- `unknown`.

Une affirmation `optimal` signifie uniquement :

> optimal dans le `Grounded Decision Problem` effectivement fourni au backend.

Elle NE DOIT PAS être présentée comme « meilleure réalisation possible dans le monde » ni comme preuve que le corpus contient toutes les alternatives pertinentes.

Une décision significative DEVRAIT donc exposer au minimum :

- le statut du solveur ;
- le statut du grounding ;
- l'identité du `Decision Scope`.

Exemples :

- `optimal + complete_for_declared_scope` ;
- `optimal + bounded` ;
- `feasible + heuristic` ;
- `infeasible + complete_for_declared_scope`.

La couche Atlas PEUT en outre produire :

- plusieurs solutions de même valeur ;
- un front de solutions non dominées ;
- une solution satisfaisante non prouvée optimale ;
- `needs_information` ;
- `no_known_admissible_realization` ;
- `unsatisfiable_under_current_model` ;
- `solver_unknown`.

Le statut composé DOIT rester explicite.

---

## 18. Incertitude et acquisition d'information

### 18.1 Politique d'incertitude

Les coûts, capacités ou propriétés incertains NE DOIVENT PAS être transformés silencieusement en valeurs exactes.

Chaque `Grounded Decision Problem` qui contient des valeurs non exactes DOIT déclarer une `Uncertainty Policy` ou une sémantique équivalente indiquant comment ces valeurs participent :

- aux contraintes de faisabilité ;
- aux comparaisons ;
- aux objectifs ;
- à la décision de demander davantage d'information.

La v0.3.2.1 n'impose pas une théorie universelle de décision sous incertitude.

Une politique PEUT notamment employer :

- bornes conservatrices ;
- dominance robuste par intervalles ;
- scénarios multiples ;
- optimisation robuste ;
- minimax ou minimax regret ;
- modèle probabiliste explicite ;
- autre méthode déclarée.

Le backend choisi DOIT être compatible avec la politique annoncée, ou la transformation de l'incertitude vers le backend DOIT être explicite.

### 18.2 Sémantique V1 recommandée

Pour réduire le périmètre de V1 :

- les contraintes structurelles et de faisabilité DEVRAIENT être exactes ou exprimées avec des bornes dont la sémantique conservatrice est claire ;
- les estimations quantitatives PEUVENT principalement servir à comparer des alternatives ;
- une dominance robuste PEUT être établie lorsque l'intervalle complet d'une alternative est préférable à celui d'une autre ;
- lorsque les domaines pertinents se chevauchent et que le choix peut changer, Atlas DEVRAIT pouvoir retourner `needs_information` plutôt que d'utiliser implicitement une valeur centrale.

Exemple conceptuel :

- A ∈ [10, 14] et B ∈ [20, 25] : A peut dominer B selon un objectif de minimisation ;
- A ∈ [10, 22] et B ∈ [18, 25] : la comparaison n'est pas robuste sans politique supplémentaire.

Cette sémantique volontairement limitée n'interdit pas des backends plus riches.

### 18.3 Propagation

Atlas DEVRAIT préserver les bornes, intervalles ou scénarios assez longtemps pour distinguer :

- une décision robuste ;
- une décision sensible à l'incertitude ;
- une impossibilité de départager les alternatives avec la politique courante.

La provenance et le domaine de validité des valeurs incertaines doivent suivre les valeurs dérivées suffisamment pour permettre leur audit.

### 18.4 Acquisition sélective

Atlas PEUT rechercher une nouvelle information lorsque celle-ci a une chance de changer la décision.

Une action d'acquisition PEUT être :

- benchmark ;
- mesure ;
- inspection ;
- lecture d'une source ;
- test ;
- preuve ;
- question à l'utilisateur ;
- analyse complémentaire.

La valeur attendue de cette acquisition PEUT elle-même être comparée à son coût.

Les nouvelles observations doivent entrer dans la base de connaissances avec leur provenance et leur domaine de validité.

---

## 19. Materialization

### 19.1 Responsabilité

La `Materialization` transforme une solution sémantique sélectionnée en artefact concret.

Elle PEUT produire :

- code source ;
- code machine ;
- IR ;
- structures de données ;
- configuration ;
- plan d'allocation ;
- script ;
- artefact composé.

La matérialisation est distincte de la sélection.

### 19.2 Contrat de matérialisation

Une solution destinée à être matérialisée DEVRAIT exposer les hypothèses et propriétés dont sa correction ou son admissibilité dépend.

Ces exigences sont appelées ici `Materialization Obligations`.

Elles PEUVENT porter par exemple sur :

- alignement ;
- absence d'aliasing ;
- lifetime ;
- ownership ;
- largeur vectorielle ;
- disposition mémoire ;
- version de runtime ou compilateur ;
- disponibilité d'une primitive ;
- ordre ou atomicité ;
- contraintes temporelles ;
- propriété de représentation.

Un materializer DOIT pouvoir identifier :

- les descriptions qu'il matérialise ;
- la plateforme et la toolchain cibles ;
- les obligations qu'il reçoit ;
- les propriétés qu'il garantit par construction ;
- les obligations qu'il délègue à la validation.

### 19.3 Traitement des obligations

Pour chaque obligation pertinente, le materializer DOIT faire au moins l'une des choses suivantes :

1. la garantir par construction ;
2. l'encoder dans la cible par un mécanisme approprié ;
3. générer un contrôle runtime ;
4. produire une obligation de validation explicite ;
5. déclarer qu'il ne sait pas matérialiser la solution sous cette obligation.

La spécification n'impose pas le mécanisme concret : type système, ABI, attribut, pragma, option de compilation, assertion, wrapper, preuve ou test peuvent tous être appropriés selon la cible.

Une obligation non traitée NE DOIT PAS être silencieusement abandonnée.

La sortie conceptuelle d'une matérialisation est donc :

> `Artifact + Materialization Evidence + Remaining Validation Obligations`

où l'évidence indique quelles obligations sont déjà garanties et par quel mécanisme.

### 19.4 Toolchain et transformations aval

Lorsqu'un compilateur, linker, runtime ou autre transformation aval peut affecter une propriété nécessaire, cette toolchain fait partie du contexte de matérialisation.

Atlas NE DOIT PAS supposer qu'une propriété abstraite est préservée simplement parce qu'elle était vraie avant une transformation aval.

La version et les hypothèses pertinentes de la toolchain DEVRAIENT être intégrées à la connaissance de plateforme et au snapshot reproductible.

### 19.5 Régénération

La régénération complète d'un artefact est une opération normale.

Atlas NE DOIT PAS exiger que la matérialisation précédente soit modifiée incrémentalement lorsqu'un nouveau besoin ou une nouvelle connaissance justifie une résolution globale différente.

La préservation porte prioritairement sur la connaissance et les intentions encore valides.

---

## 20. Validation

### 20.1 But

Une matérialisation DOIT pouvoir être validée par rapport aux descriptions qu'elle prétend réaliser et aux `Validation Obligations` qui restent ouvertes.

Les mécanismes PEUVENT inclure :

- tests ;
- propriétés ;
- comparaison différentielle ;
- preuve ;
- vérification statique ;
- benchmark ;
- mesure ;
- oracle ;
- observation de traces ;
- contrôles runtime.

La validation ferme la boucle ouverte par le contrat de matérialisation : une solution ne doit pas être considérée comme correctement matérialisée tant qu'une obligation requise reste ni garantie ni explicitement acceptée par la politique du contexte.

### 20.2 Validation sémantique et physique

La validation DEVRAIT distinguer :

- correction fonctionnelle ;
- respect des préconditions ;
- respect des contraintes de ressources ;
- respect des obligations de représentation ;
- propriétés de performance ;
- hypothèses de plateforme ;
- hypothèses de toolchain.

Une propriété peut être garantie par construction, établie statiquement, vérifiée dynamiquement ou mesurée. Le mode de garantie DEVRAIT être conservé dans l'évidence de validation.

### 20.3 Échec et retour vers la décision

Si une obligation requise ne peut être satisfaite :

- la matérialisation PEUT échouer ;
- Atlas PEUT rouvrir la résolution avec une contrainte supplémentaire ;
- Atlas PEUT sélectionner une autre solution ;
- Atlas PEUT demander une information ou une capacité supplémentaire.

Une violation constatée NE DOIT PAS être masquée comme simple problème de génération de code si elle invalide la solution sémantique sous le contexte courant.

### 20.4 Retour vers la connaissance

Une validation ou une mesure PEUT enrichir la base de connaissances.

Le résultat DOIT conserver sa provenance et NE DOIT PAS être généralisé hors de son domaine expérimental sans justification.

---

## 21. Explication

Atlas DOIT pouvoir expliquer une décision suffisamment pour permettre son audit.

Une explication DEVRAIT pouvoir répondre à des questions telles que :

- quelle intention est satisfaite ?
- quelle réalisation a été choisie ?
- quelles alternatives étaient connues ?
- pourquoi certaines étaient inadmissibles ?
- quelles ressources ou préparations sont partagées ?
- quels faits de workload ou de plateforme ont influencé le choix ?
- quelles connaissances incertaines restent décisives ?
- quelles contraintes temporelles ont changé le résultat ?
- quelles sources ou mesures soutiennent les faits importants ?
- quelle information supplémentaire pourrait changer la décision ?

L'explication DEVRAIT être produite à partir des dépendances effectives de la solution, et non par une justification narrative indépendante du calcul.

---

## 22. Reproductibilité

Une décision significative DEVRAIT pouvoir être reproduite à partir d'un snapshot comprenant au minimum :

- version ou identité du corpus de connaissances ;
- intentions ;
- contexte ;
- workload ;
- plateforme ;
- contraintes et objectifs ;
- `Decision Scope` et `Grounding Policy` ;
- statut du grounding ;
- `Uncertainty Policy` lorsqu'elle existe ;
- backend et paramètres de résolution pertinents ;
- versions des modèles de coût ou mesures utilisées ;
- toolchain et obligations de matérialisation lorsqu'un artefact concret est concerné.

Lorsqu'un solveur peut produire plusieurs solutions équivalentes, Atlas DOIT distinguer la reproductibilité de la valeur de décision de la reproductibilité bit-à-bit du choix particulier.

---

## 23. États d'échec

Atlas DOIT distinguer au minimum les situations suivantes lorsqu'elles sont pertinentes :

### 23.1 `no_known_realization`

Aucune réalisation de l'intention n'est connue dans le corpus courant.

Ce statut ne signifie pas que l'intention est irréalisable dans le monde.

### 23.2 `no_known_admissible_realization`

Des réalisations sont connues, mais aucune n'est admissible sous les faits et contraintes courants.

### 23.3 `unsatisfiable_under_current_model`

Le `Grounded Decision Problem` est contradictoire ou sans solution relativement au snapshot, au scope, au grounding et au modèle courants.

Ce statut NE DOIT PAS être interprété comme une impossibilité universelle lorsque le grounding est `bounded` ou `heuristic`.

### 23.4 `needs_information`

La connaissance disponible ne permet pas une décision suffisamment robuste selon la politique courante.

### 23.5 `solver_unknown`

Le backend n'a pas établi de solution ou d'infaisabilité dans les limites allouées.

### 23.6 `materialization_failure`

Une solution sémantique a été sélectionnée mais n'a pas pu être matérialisée.

### 23.7 `validation_failure`

L'artefact matérialisé ne satisfait pas une validation requise.

Aucun de ces statuts NE DOIT être automatiquement réinterprété comme impossibilité universelle.

---

## 24. Interfaces architecturales

La v0.3.2.1 distingue conceptuellement les responsabilités suivantes sans imposer qu'elles correspondent à des processus ou modules séparés.

### 24.1 Knowledge Store

Responsable de :

- descriptions ;
- relations ;
- faits ;
- provenance ;
- versions ;
- domaines de validité ;
- mesures ;
- modèles de coût ;
- respect des invariants sémantiques à ses frontières de lecture et d'écriture.

Les frontières du Knowledge Store DOIVENT faire respecter des invariants sémantiques cohérents pour l'identité, les valeurs, les participants et les structures.

Une donnée qui viole ces invariants DOIT être rejetée ou explicitement isolée avant de pouvoir participer au raisonnement.

Cette exigence porte sur les invariants observables, pas sur une technique particulière de validation ni sur la fermeture du Store à un évaluateur donné.

### 24.2 Knowledge Ingestion / Curation

Responsable de :

- import ;
- extraction ;
- normalisation ;
- révision ;
- dépréciation ;
- contrôle de provenance ;
- validation des invariants sémantiques avant admission au raisonnement.

Une voie d'ingestion NE DOIT PAS pouvoir contourner silencieusement les règles d'identité, de structure, de participants ou de vocabulaire imposées au Knowledge Store.

Les mécanismes de validation à l'écriture et à la lecture PEUVENT différer techniquement ; ils DOIVENT préserver des invariants sémantiques équivalents.

### 24.3 Semantic Recovery

Adaptateur facultatif depuis des artefacts existants vers l'espace de descriptions.

### 24.4 Semantic Workshop

Responsable de proposer ou établir de nouvelles relations, transformations, décompositions et recompositions.

### 24.5 Decision Compiler

Responsable de :

- dériver depuis les intentions et le contexte le sous-problème pertinent ;
- appliquer une `Grounding Policy` explicite ;
- produire un `Grounded Decision Problem` fini ;
- exposer le `Decision Scope` et le statut de couverture du grounding ;
- traduire le problème vers une ou plusieurs représentations de résolution.

### 24.6 Solver Backend

Responsable de résoudre la formulation reçue ou de retourner un statut explicite.

### 24.7 Platform Knowledge

Responsable de fournir les connaissances spécifiques à la cible, sans être confondu avec le générateur de code.

### 24.8 Materializer

Responsable de produire un artefact concret conforme à la solution sélectionnée, de traiter les `Materialization Obligations` et d'émettre l'évidence ou les obligations restantes.

### 24.9 Validator / Measurement

Responsable de vérifier l'artefact, de fermer les `Validation Obligations` requises et d'alimenter éventuellement de nouvelles observations.

Ces responsabilités peuvent être en boucle. La structure ne définit pas un pipeline strict à passage unique.

---

## 25. Frontière V1

La V1 doit être suffisamment petite pour permettre une collecte réelle de connaissances et des décisions utiles.

### 25.1 Inclus dans la cible V1

La V1 DEVRAIT supporter :

- descriptions génériques à identité nominale stable et règles d'identité indépendantes du langage hôte ;
- relations `realizes`, `requires`, `produces/builds`, `represents` ou équivalents ;
- prédicats à sémantique stable ;
- faits contextuels et valeurs structurées lorsque leur structure est sémantiquement pertinente ;
- distinction catalogue / scénario / solution ;
- provenance minimale ;
- dépendances structurées pour toute dérivation persistée ;
- validation sémantique aux frontières du Knowledge Store ;
- statuts `exact`, `bound`, `estimate`, `unknown` ou équivalents ;
- workload de premier rang ;
- coûts contextualisés simples ;
- ressources présentes ou produites ;
- partage candidat à partir de l'identité nominale, avec décision d'instance contextuelle ;
- dépendances acycliques ;
- contraintes dures ;
- sélection d'une réalisation ou combinaison de réalisations ;
- `Decision Scope`, `Grounding Policy` et statut de grounding ;
- formulation compacte lorsque possible ;
- au moins un backend de résolution ;
- `Uncertainty Policy` explicite dès qu'une décision utilise des valeurs non exactes ;
- explication des dépendances de décision ;
- ingestion et curation de connaissances ;
- snapshot reproductible d'une décision.

Un support temporel discret PEUT faire partie de V1 si nécessaire pour un premier domaine, notamment pour lifetimes, capacité cumulative ou préparation.

### 25.2 Hors cible V1 générale

La V1 ne requiert pas :

- décompilation sémantique générale ;
- découverte automatique universelle d'intentions ;
- preuve automatique générale d'équivalence ;
- mutation et invalidation arbitraires ;
- propagation réactive générale en cascade des invalidations ou Truth Maintenance System complet ;
- cycles de dépendances généraux ;
- temps continu ;
- modèle matériel complet ;
- optimisation multiobjectif universelle ;
- spécialisation dynamique à l'exécution ;
- synthèse de programme sans catalogue de connaissances ;
- garantie de scalabilité sur des graphes arbitraires ;
- matérialisation vers toutes les plateformes ;
- connaissance complète ou garantie vraie.

Ces capacités peuvent être expérimentées sans être des conditions de livraison de V1.

Pour les dérivations persistées, la V1 PEUT se limiter à une politique paresseuse : détecter qu'une dépendance a changé ou a été dépréciée, empêcher l'utilisation non qualifiée d'une dérivation devenue obsolète ou à recalculer, puis la réviser ou la reproduire à la demande.

---

## 26. Questions ouvertes et risques

Les POC ont suffisamment dérisqué certaines inconnues architecturales pour ne plus les traiter comme blocages immédiats :

- **R1 — abstraction sémantique fondamentale : fortement dérisqué.**
  `Description + relations/faits` constitue la base v0.3.2.1.
- **R2 — explosion de la découverte : fortement dérisqué pour les cas statiques étudiés.**
  L'espace des solutions peut être exponentiel sans imposer une énumération explicite. Le risque restant porte désormais davantage sur le coût et la complétude du grounding que sur l'obligation d'énumérer les plans.
- **R3 — couplage réalisation / temps : clarifié.**
  Le couplage est parfois nécessaire, mais pas universel.

Les risques ou conditions ouvertes prioritaires deviennent :

### R4 — validité et portée des relations sémantiques

Atlas dépend nécessairement de connaissances susceptibles d'être fausses ou incomplètes.

La question n'est pas de supprimer cette condition, mais de rendre les assertions :

- provenancées ;
- contextualisées ;
- révisables ;
- qualifiées épistémiquement ;
- auditables.

Reste ouverte la manière pratique de construire à grande échelle des relations telles que `realizes` et les équivalences avec une qualité suffisante.

### R5 — Semantic Recovery

La récupération d'intentions depuis du code arbitraire reste largement ouverte.

Elle n'est pas bloquante pour une V1 alimentée par connaissance déclarée ou assistée.

### R6 — propriétés pertinentes omises

Une dominance ou une équivalence apparente peut être fausse si le modèle ignore une propriété pertinente.

Aucune architecture ne peut garantir en général la complétude de l'ensemble de propriétés.

Atlas doit donc préserver portée, provenance et possibilité de révision, et éviter les pruning dont les hypothèses ne sont pas explicites.

### R7 — incertitude composée

La v0.3.2.1 impose qu'une sémantique d'incertitude soit déclarée, mais ne choisit pas de théorie universelle. L'intégration de coûts incertains, faits estimés, contraintes temporelles et décisions jointes reste partiellement ouverte, notamment pour les politiques robustes ou scénarisées à grande échelle.

### R8 — qualité du modèle de plateforme

La séparation conceptuelle Platform Knowledge / Materialization est retenue, mais la couverture et la qualité prédictive des modèles de plateforme restent à construire.

### R9 — multiobjectif

Aucune politique générale n'est encore établie pour arbitrer de nombreuses dimensions de coût sans scalarisation arbitraire.

### R10 — acquisition d'information

L'acquisition sélective est conceptuellement supportée, mais doit être réintégrée à la formulation générale de décision et éprouvée sur un corpus réel.

### R11 — matérialisation et validation

La sélection abstraite est mieux comprise que la production automatique d'artefacts fidèles et leur validation. La v0.3.2.1 introduit des obligations explicites entre solution, materializer, toolchain et validator ; leur couverture pratique reste à démontrer sur une cible réelle.

### R12 — coût opérationnel de provenance et d'explication

Aucun problème majeur n'est encore démontré, mais la collecte à grande échelle devra mesurer le coût de maintien de provenance, versions, domaines de validité et dépendances structurées des dérivations persistées.

Le premier travail sur les règles structurées montre en outre qu'une représentation trop pauvre peut perdre des participants, de l'ordre ou des préconditions sémantiquement pertinents. La v0.3.2.1 impose leur préservation lorsque nécessaire, sans imposer une AST universelle.

### Risques transversaux

Restent également à surveiller :

- scalabilité des formulations jointes ;
- cycles ;
- mutation/invalidation ;
- identité sémantique versus identité de ressource ;
- symétries et solutions équivalentes ;
- coût et qualité du grounding du problème de décision ;
- risque d'annoncer un optimum sans exposer le scope et les bornes du grounding ;
- dérive de formats ou ontologies lors de la collecte de connaissances ;
- perte silencieuse de structure sémantiquement pertinente lors d'une conversion technique ;
- fonctionnalisation accidentelle de relations multivaluées ;
- divergence d'invariants entre les chemins d'écriture et de lecture du Knowledge Store.

---

## 27. Critères de conformité conceptuelle

Une implémentation se réclamant du noyau Atlas v0.3.2.1 DOIT au minimum respecter les invariants suivants.

### 27.1 Invariants sémantiques et décisionnels

1. une intention ne dépend pas de la disponibilité d'une réalisation particulière ;
2. absence de connaissance n'implique pas négation universelle ;
3. identité nominale, équivalence sémantique et partage d'instance sont des notions distinctes ;
4. un prédicat utilisé pour le raisonnement possède une sémantique stable ;
5. une propriété utilisée par une règle est résolue relativement à l'identité du participant auquel elle s'applique ;
6. une conclusion relationnelle dérivée conserve son prédicat, ses participants groundés, son statut épistémique lorsque pertinent et ses dépendances effectives de manière récupérable ;
7. un résultat booléen d'évaluation n'est pas assimilé à lui seul à une conclusion relationnelle groundée ;
8. l'absence d'une précondition requise n'est pas interprétée comme sa satisfaction ;
9. une précondition négative n'est pas établie par la seule absence d'une assertion positive dans le corpus en monde ouvert ;
10. possibilité, constructibilité, admissibilité et sélection sont distinctes ;
11. les décisions sont contextualisées par workload, contraintes et plateforme lorsque pertinent ;
12. les coûts de préparation et de partage peuvent être comptés à l'échelle du plan, pas seulement localement par appel ;
13. le passage du corpus en monde ouvert vers un problème fini est explicité par un `Decision Scope`, une `Grounding Policy` et un statut de grounding ;
14. un résultat `optimal` est toujours qualifié relativement au `Grounded Decision Problem` résolu ;
15. le système n'exige pas l'énumération préalable de toutes les solutions complètes ;
16. le modèle peut représenter conjointement choix et temps lorsqu'ils interagissent ;
17. le peak de ressources peut dépendre des lifetimes plutôt que d'une somme statique ;
18. une connaissance utilisée pour une décision peut être reliée à sa provenance et à son domaine de validité ;
19. toute dérivation persistée conserve des dépendances structurées suffisantes pour son audit et sa révision ou reproduction ;
20. une décision utilisant des valeurs non exactes déclare la sémantique selon laquelle l'incertitude est interprétée ;
21. la matérialisation est distincte de la connaissance de plateforme et de la décision sémantique ;
22. les hypothèses dont dépend une matérialisation sont conservées sous forme d'obligations garanties, encodées, vérifiées ou explicitement rejetées ;
23. une solution ou un échec est qualifié relativement au corpus, au contexte et au grounding courants ;
24. le corpus peut être enrichi ou corrigé sans traiter les matérialisations précédentes comme source de vérité unique.

### 27.2 Invariants d'intégrité de la connaissance et du moteur

25. les règles d'identité, d'égalité, d'ordre, de hachage et de coercition qui affectent la sémantique sont définies par Atlas et non introduites implicitement par le langage hôte ;
26. une relation n'est fonctionnalisée que si l'unicité pertinente est déclarée, dérivée ou vérifiée ;
27. toute structure interne, tout ordre et toute précondition qui influencent la validité, l'applicabilité ou les conséquences restent exploitables par le raisonnement ;
28. les représentations structurées échangées entre composants qui doivent être composées possèdent une sémantique d'échange explicite et versionnée, ou une traduction dont la préservation sémantique est explicite ;
29. les frontières d'écriture et de lecture du Knowledge Store font respecter des invariants sémantiques équivalents ;
30. la validité syntaxique d'un identifiant de propriété n'implique pas que cette propriété appartient au vocabulaire consommé par une règle ;
31. la capacité limitée d'un évaluateur courant ne ferme pas normativement le vocabulaire du corpus persistant.

---

## 28. Principe directeur

Atlas ne cherche pas à posséder une connaissance parfaite du logiciel ni à énumérer toutes les implémentations possibles.

Il cherche à conserver suffisamment de connaissances explicites, composables et contextualisées pour que les conséquences globales d'une décision puissent être calculées plutôt que redécouvertes localement à chaque modification.

La hiérarchie de valeur retenue par la v0.3.2.1 est :

> **intention, connaissances, invariants, relations, mesures et contexte sont les actifs durables ; la réalisation est une instanciation régénérable de ces actifs.**

La collecte de connaissance n'est donc pas une phase préparatoire extérieure au projet Atlas. Elle est une activité constitutive du système et l'un de ses principaux moyens de progresser.
