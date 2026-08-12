# Atlas Core POC — connaissance acquise

## Confirmed

- Un même besoin (10 000 éléments, charge de lecture majoritaire) peut produire
  des choix différents quand la plateforme change : `sorted` sur `compact`,
  `hash` sur `cache_rich` (scénario `lookup_heavy`). La mémoire admissible et
  le coût relatif d'un accès aléatoire suffisent à provoquer ce basculement
  dans ce catalogue minimal.
- Le choix est explicable et reproductible : préconditions, formule de coût et
  tie-break lexicographique sont dans `experiment.py`; les alternatives sont
  ensuite mesurées dans `measurements.json`.
- Des candidats codés au même niveau peuvent être comparés par compteurs : la
  lecture lourde donne `sorted` 333 781 unités instrumentées contre `linear`
  5 258 185 (`lookup_heavy`), tandis que les parcours rendent `sorted` et
  `linear` proches (`walk_heavy`).
- Audit de comparabilité : chaque candidat reçoit exactement le même `pairs` et
  le même `workload` déterministe par scénario ; les 950/30/10 opérations de
  `lookup_heavy` et 50/900/40 de `walk_heavy` sont donc logiquement identiques
  entre candidats (le chargement est la construction de la même collection).
- Audit de la table de hachage : pour 10 000 éléments, elle vise au moins deux
  fois cette taille, puis arrondit à la puissance de deux, soit 32 768 slots.
  `keys` et `values` ont chacun 32 768 cases ; `allocations = 65 536` désigne
  ces deux tableaux, et non une capacité de 65 536 slots.
- Audit des visites : `HashCollection.walk()` parcourt `zip(keys, values)` et
  incrémente `visits` une fois par slot, vide ou non. Il y a 30 parcours dans
  `lookup_heavy`, donc 32 768 × 30 = 983 040 visites ; il y en a 900 dans
  `walk_heavy`, donc 32 768 × 900 = 29 491 200. C'est un coût réel du parcours
  choisi, mais une visite de slot vide n'est pas une visite d'élément.
- La chaîne besoin → propriétés → plateforme → candidats → coût → choix →
  implémentation → exécution → mesure existe dans une expérience de petite
  taille (`SCENARIOS`, `PLATFORMS`, `predicted_cost`, `measure`).

## Disproved

- Le modèle de coût proposé est insuffisant comme prédicteur quantitatif : il
  choisit `hash` sur `cache_rich`, alors que les compteurs instrumentés le
  rendent plus coûteux que `sorted` dans les deux scénarios (`measurements.json`).
- Le modèle ne compte pas correctement les visites de parcours, les probes et
  le coût du chargement/tri ; ses unités relatives ne sont donc pas calibrées
  sur les compteurs élémentaires.
- `instrumented_cost` est exactement la somme non pondérée de
  `comparisons + probes + visits + writes + allocations`. Ces compteurs sont
  hétérogènes et cette addition ne constitue donc pas une mesure physique
  calibrée ; elle sert uniquement de trace instrumentée pour confronter les
  candidats.

## Unknown

- Ce POC ne tranche pas la stabilité du choix pour d'autres tailles, distributions,
  ratios d'opérations, runtimes ou machines.
- Il ne mesure pas directement la mémoire réelle et ne permet pas d'étalonner les
  unités du modèle en octets ou en nanosecondes.

## Reproduction et inventaire

- Fichiers : `experiment.py` (~190 lignes), `knowledge.md`, et
  `measurements.json` généré par l'expérience.
- Dépendances externes : aucune (bibliothèque standard Python).
- Commande : `python3 experiment.py`.

Conclusion : le critère de réussite expérimental est atteint : la plateforme
provoque un basculement déterministe `sorted`/`hash`, les alternatives sont
exécutées et les compteurs montrent explicitement que le modèle peut être
réfuté. Le résultat porte sur la capacité de la chaîne et sur ses limites, pas
sur une performance absolue ni sur une architecture Atlas. Le temps mural est
conservé comme observation secondaire seulement.
