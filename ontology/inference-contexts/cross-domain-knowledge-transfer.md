# Transfert de connaissance inter-domaines — intersection directe B1 × B1

Type : analyse manuelle d'un seul rapprochement. Ce document ne modifie pas
les proto-ontologies et ne définit ni moteur, ni score, ni relation permanente.

## 1. Correspondance examinée

Le mécanisme graphique étudié est :

```text
horizontal_run_representation(R1)
× horizontal_run_representation(R2)
→ horizontal_run_representation(R1 ∩ R2)
```

Le candidat externe est :

```text
elementary_algorithms.ordered_merge
```

### Propriétés communes

- deux entrées sont ordonnées selon une même dimension de parcours ;
- les éléments courants peuvent être examinés conjointement ;
- la progression est monotone dans chaque entrée ;
- l'ordre des éléments émis est conservé ;
- les entrées sont consommées sans retour arrière dans la partie déjà traitée.

### Préconditions communes

- les entrées sont disponibles dans un ordre exploitable ;
- les positions courantes peuvent être avancées indépendamment ;
- une règle détermine quel élément ou intervalle doit progresser ;
- le résultat peut être produit au fil du parcours.

### Différences

`ordered_merge` est formulé comme un mécanisme général sur des séquences
ordonnées. L'opération QuickDraw est une opération géométrique 2D structurée
par scanlines :

- les unités parcourues sont des intervalles horizontaux, pas des éléments
  génériques ;
- les flux sont regroupés par ligne ;
- l'opération est une intersection d'appartenance, pas une fusion générique de
  valeurs ;
- l'émission calcule `max(left)` et `min(right)` et élimine les intervalles
  vides ;
- l'avancement dépend de la plus petite borne droite ;
- les intervalles d'une même ligne doivent rester valides et non chevauchants.

### Propriétés locales QuickDraw

Ces propriétés ne viennent pas de `ordered_merge` :

- conventions de coordonnées et de demi-ouverture des intervalles ;
- association des runs aux scanlines ;
- absence de chevauchement interne des runs ;
- sémantique d'appartenance de l'intersection ;
- gestion des lignes sans intervalle ;
- identité logique de la région résultat ;
- coût et stockage propres aux représentations B1 et aux formes QuickDraw.

Il existe donc une correspondance structurelle, mais pas une identité entre
`ordered_merge` et l'opération graphique.

## 2. Connaissance déjà locale au domaine graphique

Sans utiliser `ordered_merge`, le contexte QuickDraw sait déjà exprimer :

- deux régions représentées par des runs horizontaux ordonnés ;
- un parcours scanline par scanline ;
- deux positions courantes dans les runs de chaque ligne ;
- la comparaison des bornes gauche et droite ;
- l'émission de l'intersection non vide ;
- l'avancement du run dont la borne droite arrive en premier ;
- la progression monotone et la conservation de l'ordre ;
- les invariants de non-chevauchement et de validité du résultat ;
- la validation contre une appartenance logique ou un oracle indépendant.

La connaissance locale inclut également les conséquences observées : la
fusion B1 est très rapide pour `sparse_sparse/intersection`, mais peut devenir
coûteuse et produire beaucoup de stockage lorsque le résultat est fragmenté.

## 3. Connaissance potentiellement importable

La fiche locale `ordered_merge` fournit les éléments suivants :

| Élément attaché au concept externe | Déjà présent localement ? | Gain actuel |
|---|---|---|
| entrées ordonnées | oui, explicitement dans les runs | aucun |
| parcours coordonné | oui, dans le mécanisme par scanline | aucun |
| production ordonnée | oui, invariant du résultat B1 | aucun |
| progression monotone | oui, dans la règle des bornes droites | aucun |
| coût sensible à la quantité et à la fragmentation | oui, dans les résultats QuickDraw | aucun |
| variante ou cas pathologique générique | non détaillé dans les artefacts | non établi |
| alternative algorithmique transférable | non détaillée pour ce cas | non établie |
| preuve de réutilisation hors QuickDraw | non démontrée dans ce contexte | non établie |

Le concept externe n'apporte donc actuellement ni borne nouvelle, ni variante
nouvelle, ni cas pathologique supplémentaire, ni mesure nouvelle. Il apporte
un nom générique qui pourrait faciliter une recherche ultérieure, mais ce nom
ne constitue pas une connaissance transférée.

Il ne faut pas inventer une complexité ou une variante au seul motif que la
littérature algorithmique pourrait en contenir. La proto-ontologie disponible
ne fournit ici que la définition générale et les propriétés déjà recouvertes
par le contexte graphique.

## 4. Nouveau test de sélection

Le test de retrait précédent reste utile comme premier filtre, mais il est trop
fort s'il est utilisé comme critère suffisant : un mécanisme externe peut être
redécrit localement sans que cela dise si sa connaissance est transférable.

Pour ce cas, un rapprochement est intéressant seulement si les trois
conditions suivantes sont réunies :

1. une correspondance structurelle suffisamment précise existe ;
2. le concept externe apporte au moins une connaissance absente du contexte
   local ;
3. cette connaissance est pertinente pour le besoin courant ou pour une
   exploration explicitement demandée.

Ces conditions restent un test de conception, pas une logique formelle.

### Application au cas QuickDraw

- Condition 1 : **satisfaite**. Les propriétés de parcours coordonné, d'ordre
  et de progression monotone correspondent réellement.
- Condition 2 : **non satisfaite avec les artefacts actuels**. Les propriétés
  disponibles autour de `ordered_merge` sont déjà exprimées ou observées dans
  le contexte graphique.
- Condition 3 : le besoin courant est bien l'intersection directe B1×B1→B1,
  mais aucune connaissance supplémentaire attachée au concept externe ne
  permet de mieux le décrire ou de choisir une variante.

Le cas est donc classé :

```text
MATCH_NO_NEW_KNOWLEDGE
```

Ce classement ne signifie pas « aucun rapport ». Il signifie « rapport
structurel sans transfert de connaissance établi ».

## 5. Classification légère

La classification appliquée ici est :

- `NO_MATCH` : aucune correspondance structurelle suffisamment précise ;
- `MATCH_NO_NEW_KNOWLEDGE` : correspondance, mais aucun apport non redondant
  établi ;
- `MATCH_WITH_KNOWLEDGE_TRANSFER` : correspondance et au moins une
  précondition, propriété, variante, pathologie ou preuve non locale est
  transférée ;
- `MATCH_RELEVANT_TO_CURRENT_NEED` : le transfert établi modifie ou éclaire
  directement le raisonnement du besoin courant.

Ces catégories ne sont pas ordonnées et ne produisent aucun score. Dans ce
contexte, seule `MATCH_NO_NEW_KNOWLEDGE` est retenue.

## 6. Conséquence pour un Context pack agentique

Injecter seulement le terme :

```text
ordered_merge
```

ajouterait un synonyme générique. Cela pourrait donner l'impression qu'une
connaissance a été importée alors que l'agent ne recevrait ni précondition,
ni invariant, ni propriété de coût, ni alternative vérifiée.

Injecter un véritable paquet devrait inclure, au minimum :

- les préconditions d'ordre des deux entrées ;
- la progression monotone des positions ;
- l'invariant de sortie ordonnée ;
- la règle de progression ou de consommation ;
- les variantes et cas pathologiques connus ;
- la provenance et le niveau de confiance de ces affirmations.

Pour l'intersection B1×B1 actuelle, ces informations sont déjà portées par le
vocabulaire graphique et ses connaissances contextuelles. L'agent n'a donc
pas besoin que `ordered_merge` soit injecté comme concept actif. Si une future
exploration demandait de transférer le mécanisme vers un autre domaine, le
paquet devrait être transféré avec ses propriétés et ses preuves, pas avec son
seul nom.

## 7. Conclusion

### 1. Le cas constitue-t-il une correspondance avec `ordered_merge` ?

Oui, au niveau structurel. Deux flux ordonnés sont parcourus conjointement,
avec progression monotone et production ordonnée. La correspondance ne vaut
pas identité : l'opération QuickDraw reste une intersection géométrique par
scanline, avec ses invariants et ses conventions propres.

### 2. Apporte-t-elle aujourd'hui une connaissance supplémentaire ?

Non. Les propriétés générales actuellement documentées pour `ordered_merge`
sont déjà présentes dans la description locale de l'intersection B1 et dans
les observations QuickDraw. Le concept externe apporte seulement un vocabulaire
générique. Le classement est donc `MATCH_NO_NEW_KNOWLEDGE`.

### 3. Quelle information Atlas devrait-il posséder autour d'un mécanisme pour
que le recollage devienne utile ?

Atlas devrait conserver, autour du mécanisme et non seulement dans son nom :

- les préconditions d'application ;
- les invariants préservés et produits ;
- les dimensions de caractéristique affectées ;
- les variantes et mécanismes concurrents ;
- les cas pathologiques ou limites ;
- les propriétés de transférabilité connues ;
- la provenance, le contexte et le niveau de confiance de chaque affirmation.

Dans le cas présent, cette enveloppe n'offre pas encore de contenu externe
non redondant. C'est précisément l'information manquante qui empêcherait de
classer le rapprochement comme un transfert utile.

### 4. Le test de retrait doit-il être conservé, affaibli ou abandonné ?

Il doit être **conservé comme test de nécessité d'expressibilité, mais
affaibli comme critère de sélection complet**. Le retrait répond à : « le
concept externe est-il indispensable pour décrire cette solution ? ». Le test
de transfert ajoute : « apporte-t-il une connaissance non déjà locale et
pertinente ? ». Aucun des deux tests ne justifie à lui seul une relation
permanente entre domaines.

## Limites observables

- Le cas ne montre pas comment identifier automatiquement une correspondance.
- Il ne permet pas de comparer plusieurs formulations de `ordered_merge`.
- Il ne fournit pas de connaissance nouvelle sur une variante de fusion ou
  sur un autre domaine d'application.
- La classification dépend de l'état actuel des connaissances documentées ;
  une future expérience pourrait faire passer le même rapprochement à
  `MATCH_WITH_KNOWLEDGE_TRANSFER`.

Conclusion : ce cas valide une correspondance structurelle, mais pas un gain
de connaissance inter-domaines. Aucune ontologie, aucun contexte existant et
aucun code n'a été modifié.
