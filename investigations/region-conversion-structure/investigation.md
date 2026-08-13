# Semantic Spider — structure du résultat et conversion B0 → B1

**investigation_id:** `region-conversion-structure`

## STARTING KNOWLEDGE

QuickDraw 3 et le premier Semantic Spider établissent que B0 combine
efficacement, que B1 peut accélérer l'application répétée d'un résultat sparse,
et qu'un seuil calculé par médianes peut être instable. La connaissance ne dit
pas encore quelles propriétés du résultat rendent une conversion réellement
admissible lorsque le temps et la mémoire sont considérés ensemble.

## TENSION

Les catégories « sparse » et « fragmented », ou la densité seule, suffisent-
elles pour décider si un résultat B0 doit être converti en B1 ?

## WHY IT MATTERS

Une politique fondée uniquement sur le gain d'application peut convertir un
résultat qui devient des centaines de fois plus volumineux. Elle peut donc
améliorer un temps local tout en dégradant la contrainte mémoire du programme.

## STOP CONDITION

Arrêter lorsqu'un contre-exemple contrôlé montre soit que la forme du résultat
change la décision à densité comparable, soit que la tension ne peut pas être
discriminée avec les mécanismes existants.

## TRAJECTORY

1. Le reservoir Atlas a d'abord été recherché : `quickdraw-region-ops-results.md`,
   `semantic-core-v1-1-conversion-results.md`, `algorithm-knowledge.md` et le
   précédent dossier de reruns montraient un seuil temporel local, mais pas la
   suffisance de la densité.
2. Le résultat initial `sparse` a été opposé à un cas construit à densité
   identique plutôt qu'à un nouveau workload arbitraire : bandes horizontales
   de 8 pixels et damier alterné, chacun occupant exactement 50 % d'un univers
   512×256.
3. Un petit harness C local produit dans chaque cas un résultat B0 réel par
   `B0(mask ∩ full)`, convertit ce même résultat en B1, vérifie les hash
   canoniques, puis mesure conversion et application avec le protocole à 31
   échantillons déjà utilisé.
4. Le damier a été choisi comme challenge direct : s'il avait le même avantage
   de conversion que les bandes, le nombre de runs ne serait pas une
   propriété décisionnelle utile.

## EVIDENCE

Les sorties brutes sont `run-1.json` à `run-5.json`; `summary.json` les
rassemble. Le code expérimental est `experiment.c`. Il ne modifie aucun code
QuickDraw et appelle les implémentations existantes.

| résultat B0 | aire | densité | runs | stockage B1 | application B0 | application B1 | seuil point-estimate |
|---|---:|---:|---:|---:|---:|---:|---:|
| bandes horizontales | 65 536 | 0,5 | 128 | 3 128 octets | ~64–66 µs | ~1,3 µs | `N=4–7` |
| damier | 65 536 | 0,5 | 65 536 | 526 392 octets | ~849–883 µs | ~778–800 µs | `N=4–5` |

Les deux formes conservent leur identité logique après conversion dans les
5 passages (`logical_identity=true`). Les bandes ont 512 fois moins de runs
et environ 168 fois moins de stockage B1 que le damier, malgré la même aire
et la même densité. Le gain d'application est massif pour les bandes et faible
pour le damier.

## CONFIRMED

- La densité et l'aire ne déterminent pas seules le coût ou l'admissibilité de
  B1 : deux résultats de densité identique ont des structures de runs très
  différentes.
- Le nombre de runs et le stockage de la représentation cible sont des
  propriétés décisionnelles indépendantes du gain temporel par application.
- Une conversion peut être temporellement amortissable et néanmoins mauvaise
  sous une contrainte mémoire. Le test du damier fournit ce contre-exemple.
- Le raisonnement doit donc conserver au moins deux axes séparés : coût du
  cycle de vie et coût/limite de stockage. Un seuil temporel unique ne peut
  pas représenter les deux.

## DISPROVED

- « Résultat à 50 % de densité » comme critère suffisant pour choisir B1.
- « Atteindre le break-even temporel » comme condition suffisante de conversion.
- L'idée que le nom de workload `sparse` ou `fragmented` soit une propriété
  assez précise pour remplacer les mesures structurelles du résultat.

## UNKNOWN

- Le seuil mémoire ou la fonction d'objectif appropriée lorsque temps et
  mémoire entrent en conflit.
- La généralisation à des univers non cache-hot, à d'autres opérations
  booléennes et à B2.
- La meilleure statistique compacte pour estimer le coût B1 avant conversion.
- La possibilité de décider avec des bornes structurelles sans effectuer la
  conversion complète.

## FRONTIER

- Tester une décision sous une limite mémoire explicite, sans fusionner cette
  contrainte avec le temps.
- Chercher si `run_count`, stockage prédit et gain d'application suffisent à
  construire une bande de décision locale.
- Comparer le même résultat logique sous B1 et B2 seulement si le conflit
  mémoire/temps le rend nécessaire.

## CHALLENGE

Le challenge a maintenu la plateforme, l'univers, l'opération, le protocole,
la densité et l'aire ; seule la structure spatiale a changé. Il réfute donc
une explication par la densité seule. Il ne réfute pas une politique qui
utiliserait explicitement le nombre de runs et une limite mémoire : cette
politique est précisément la distinction nouvellement retenue.

## STOP

La tension est résolue au niveau matériel : la même densité peut produire une
conversion B1 compacte et très utile, ou une conversion volumineuse avec un
gain temporel marginal. Une source supplémentaire générale ne devrait pas
changer cette distinction locale ; les seuils exacts et la fonction d'objectif
restent dans la FRONTIER.

## Architecture Spider

- **Recherche externe :** inutile ; le réservoir QuickDraw et le harness local
  suffisaient.
- **Sélection de source :** suffisante pour focaliser l'expérience ; le test
  contrôlé a varié une propriété à la fois.
- **Investigation Context dans Corpus Miner :** aucune valeur démontrée ; la
  question a été résolue par code réel et mesures, sans extraction textuelle.
- **État local :** identifiant, tension, forme des fixtures, protocole, sorties
  et résumé.
- **État global :** connaissances QuickDraw, identités des représentations,
  provenance des sources et résultats durables.
- **Collisions en parallèle :** binaires, noms de sorties et mises à jour
  simultanées de `knowledge.md` si les branches ne sont pas namespacées.
- **Minimum avant 3–4 branches :** manifests et sorties sous des IDs de branche
  distincts, puis harvest global explicite ; aucun scheduler n'est requis.
