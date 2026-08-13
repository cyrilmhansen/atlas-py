# Semantic Spider — stabilité du break-even B0 → B1

**investigation_id:** `b0-b1-break-even-stability`

## STARTING KNOWLEDGE

QuickDraw 3 établit que B0 bitmap est une représentation efficace pour
combiner des régions et que B1 runs peut être beaucoup plus rapide à appliquer
sur un résultat sparse. Semantic Core v1.1 a mesuré une conversion C homogène
sur le résultat B0 réel. Le relevé donne `N=7` par point-estimates pour sparse
et `N=4` pour fragmented, mais décrit la frontière fragmented comme bruitée.

## TENSION

Un entier calculé à partir de médianes de composants est-il une décision
stable, ou faut-il conserver une zone d'incertitude lorsque conversion et
application ont des variances différentes ?

## WHY IT MATTERS

Choisir une conversion à partir d'un seuil exact peut transformer une mesure
locale en règle d'ingénierie trop forte. Cela affecte directement le cycle de
vie d'une région et la représentation choisie pour des applications répétées.

## STOP CONDITION

Arrêter lorsque des reruns du même harness distinguent une frontière robuste
d'un seuil instable, ou montrent que les données ne permettent pas cette
distinction.

## TRAJECTORY

1. Le réservoir Atlas a été recherché avant toute acquisition : QuickDraw 3,
   Semantic Core v1/v1.1 et `algorithm-knowledge.md` contenaient déjà la
   tension et le protocole C.
2. La question a été resserrée sur deux fixtures existantes, sans nouveau
   workload ni modification de code : `sparse_sparse/intersection` et
   `fragmented_fragmented/intersection`.
3. Le même programme C a été recompilé depuis les sources existantes et
   exécuté cinq fois. Chaque passage contient 31 médianes internes, le même
   `CLOCK_MONOTONIC_RAW`, le même CPU demandé, le même résultat B0 exact, la
   conversion B0→B1 et les mesures end-to-end aux positions calculées.
4. Un test ASan/UBSan existant a été exécuté sur 12 800 paires déterministes,
   bit-identiques pour les trois représentations.

## EVIDENCE

Les fichiers `run-1.json` à `run-5.json` sont les sorties brutes du harness.
`rerun-summary.json` en extrait les comparaisons sans recalculer les mesures.

| cas | seuils calculés sur 5 passages | frontière juste avant | frontière calculée |
|---|---:|---|---|
| sparse/intersection | `3, 3, 3, 3, 3` | conversion défavorable dans 5/5 | conversion favorable dans 5/5 |
| fragmented/intersection | `4, 5, 4, 4, 4` | conversion défavorable dans 5/5 | conversion favorable dans 5/5 |

Les valeurs sont des médianes locales et non des temps universels. Pour
fragmented, le choix de l'entier entre 4 et 5 varie, mais l'ordre des deux
régimes testés reste le même : juste avant la frontière, sans conversion est
meilleur ; à la frontière calculée, avec conversion est meilleur.

Le test fonctionnel ASan/UBSan a produit `12800 deterministic pairs x
operations, 3 variants, bit-identical`.

## CONFIRMED

- La conversion B0→B1 sur le résultat B0 réel reste logiquement identique
  dans le harness existant.
- Pour le cas sparse retenu, le seuil point-estimate est stable à `N=3` dans
  les cinq passages et le changement de classement est end-to-end reproductible
  à cette frontière.
- Pour le cas fragmented, l'entier exact n'est pas stable (`N=4` ou `N=5`),
  mais la décision de régime observée est stable autour de la frontière testée.
- Une représentation qui gagne à l'application peut donc être choisie selon
  le cycle de vie, mais la connaissance utile est une frontière locale avec
  une précision expérimentale, pas nécessairement un entier exact.
- Le coût de conversion, le gain par application et le bruit du protocole
  sont des observations distinctes ; les confondre masque la stabilité réelle
  de la décision.

## DISPROVED

- Un seuil entier calculé par addition de médianes ne doit pas être présenté
  automatiquement comme un break-even physique stable.
- La valeur historique `N=4` de fragmented ne constitue pas à elle seule une
  frontière exacte : les reruns donnent aussi `N=5`.
- La forme « résultat fragmenté » ne suffit pas à produire une constante de
  conversion réutilisable hors du résultat, du protocole et de la plateforme
  mesurés.

## UNKNOWN

- Une bande d'incertitude statistique explicite permettant de décider
  automatiquement quand l'entier est indéterminé.
- La généralisation à d'autres tailles d'image, opérations, plateformes et
  allocateurs.
- Le nombre minimal de répétitions nécessaire pour séparer un vrai gain d'un
  bruit de frontière.
- L'effet d'une conversion B0→B1 amortie dans une chaîne de plusieurs
  opérations.

## FRONTIER

- Déterminer si un intervalle de coût simple suffit pour représenter une
  décision `convert / do not convert / measure more`.
- Tester d'autres résultats B0 uniquement si une future décision de production
  en dépend.
- Comparer le coût de conversion avec le coût mémoire réel lorsque la région
  dépasse l'univers cache-hot actuel.

## Architecture évaluée

1. **Recherche externe :** non nécessaire. Le réservoir Atlas et les sources
   QuickDraw déjà étudiées suffisaient ; aucune source externe n'aurait
   discriminé cette question mieux que le rerun homogène du harness.
2. **Sélection de source :** suffisante ici. La source discriminante était le
   programme C déjà figé et les deux fixtures existantes.
3. **Investigation Context dans Corpus Miner :** aucune valeur démontrée dans
   cette branche, qui n'a pas utilisé Corpus Miner. L'intention a servi à
   sélectionner l'expérience, pas à modifier l'extraction.
4. **État local nécessaire :** identifiant stable, tension, protocole, hashes
   des sources, sorties des reruns et résumé des décisions.
5. **État global :** connaissances confirmées/disprouvées/inconnues, identité
   des sources, résultats QuickDraw historiques et provenance durable.
6. **Collisions actuelles à plusieurs branches :** noms temporaires génériques,
   sorties JSON communes, binaires de harness et mises à jour concurrentes de
   `knowledge.md`.
7. **Plus petit changement avant 3–4 branches :** imposer un répertoire
   `investigations/<investigation_id>/` avec manifeste immuable, sorties
   namespacées et harvest global soumis séparément. Aucun scheduler n'est
   nécessaire à ce stade.

## STOP

La tension est résolue au niveau utile : sparse permet une frontière robuste
dans ce protocole ; fragmented ne justifie pas un entier exact, tout en
confirmant un changement de régime autour de la frontière. Une mesure
supplémentaire dans cette branche serait redondante ; l'incertitude statistique
et les autres workloads sont laissés à la FRONTIER.
