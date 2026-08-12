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

## POC 2 — séparation algorithmique / plateforme

### Confirmed

- `poc2.py` calcule d'abord un vecteur de caractéristiques pour `sorted` et
  `hash`, puis applique séparément les profils synthétiques `compact` et
  `cache_rich`. Les vecteurs sont identiques entre plateformes pour un même
  candidat (`poc2_measurements.json`, `vector_equal: true`).
- Les compteurs prédits et observés concordent exactement pour les deux
  candidats et les deux workloads : comparaisons, probes, visites de slots,
  lectures séquentielles, accès aléatoires, écritures, capacité réservée et
  allocations.
- Le profil synthétique de plateforme peut changer le choix sans changer le
  vecteur : `lookup_heavy` choisit `sorted` sur `compact` et `hash` sur
  `cache_rich`. Ce basculement appartient au modèle de décision et n'est pas
  démontré sur deux machines physiques.
- Les vecteurs de caractéristiques sont l'information principale ; leur
  transformation en coût intervient seulement dans le modèle plateforme. Les
  caractéristiques structurelles comme la capacité réservée appartiennent au
  mécanisme choisi, tandis que le coût scalaire appartient au profil plateforme.
  Le temps mural est conservé séparément et n'est pas utilisé pour construire
  le coût.
- L'égalité exacte entre vecteurs prédits et observés valide ici la séparation
  des couches, mais ne démontre pas encore qu'un modèle analytique indépendant
  puisse prédire fidèlement une implémentation réelle.

### Disproved

- L'hypothèse implicite selon laquelle une seule durée ou un score précoce
  suffirait à expliquer le choix est contredite : les vecteurs conservent les
  phénomènes distincts, puis les profils les pondèrent différemment.
- Les compteurs hétérogènes du POC 1 (`comparisons + probes + visits + writes +
  allocations`) ne constituent pas une unité physique commune ; leur somme
  non pondérée n'est pas une mesure calibrée.

### Unknown

- Le POC ne dit pas si ces vecteurs sont suffisants pour une machine réelle,
  ni comment calibrer leurs poids en unités physiques.
- Il reste inconnu comment calibrer ces caractéristiques sur des plateformes
  réelles et quelles dimensions supplémentaires seraient nécessaires.
- Les caractéristiques de branchement, de cache réel et de runtime restent
  non modélisées ; les temps muraux ne permettent pas de les attribuer.

Inventaire POC 2 : `poc2.py` (~230 lignes), `poc2_measurements.json` généré,
aucune dépendance externe. Reproduction : `python3 poc2.py`.

## POC 3 — composition de mécanismes

### Confirmed

- L'espace de solutions n'est plus une liste de candidats monolithiques : le
  produit de `lookup`, `representation`, `walk` et `auxiliary`, filtré par des
  préconditions locales, génère les combinaisons admissibles. Les deux familles
  de départ sont `sorted_index + dense_elements + dense_scan + none` et
  `hash_index + sparse_slots + slot_scan + none` ; l'hybride est généré comme
  `hash_index + sparse_slots + dense_scan + dense_view`, sans être déclaré
  comme un troisième candidat monolithique.
- L'hybride est sélectionné sur `lookup_heavy` avec le profil synthétique
  `cache_rich`, tandis que la famille triée est sélectionnée sur `compact` et
  reste sélectionnée sur `walk_heavy`. Le changement vient des pondérations du
  modèle plateforme, pas d'une modification du vecteur algorithmique
  (`poc3_measurements.json`).
- Les vecteurs calculés avant exécution sont exactement égaux aux vecteurs
  instrumentés pour les trois combinaisons et les deux workloads. Dans ce
  domaine déterministe, les probes sans collision, les recherches binaires,
  les lectures de parcours, les écritures, la capacité et les allocations sont
  donc calculables et vérifiables (`vector_equal: true`). Cette égalité valide
  la structure de l'expérience, mais pas encore la prédiction indépendante
  d'une implémentation complexe.
- Les mécanismes ne sont pas indépendants sans contraintes : l'index trié
  requiert une représentation dense, le probing requiert des slots sparse, et
  le parcours dense d'une table hachée requiert la vue dense auxiliaire. Ces
  dépendances sont explicites dans `valid()`.
- Une granularité située sous les familles d'implémentation ouvre donc un
  espace de solutions qui n'existait pas au niveau des candidats initiaux.

### Disproved

- L'idée que les deux familles monolithiques suffiraient à explorer le choix est
  contredite dans ce scénario : une combinaison nouvelle est la meilleure sur
  un workload et un profil plateforme donnés.
- Le temps mural n'explique pas ce résultat : il est mesuré séparément et les
  plateformes restent synthétiques ; il ne constitue pas une validation
  matérielle de leurs coefficients.

### Unknown

- Le POC ne montre pas que cette granularité resterait utile avec d'autres
  distributions, collisions, tailles ou opérations de mise à jour réelles.
- La solution hybride reste simple : ses caractéristiques sont essentiellement
  composées de mécanismes dont les effets restent séparables. Le POC ne
  démontre donc pas que les propriétés d'une composition peuvent être dérivées
  lorsque les mécanismes interagissent et modifient mutuellement leurs
  caractéristiques.
- Il reste inconnu quelles caractéristiques supplémentaires seraient nécessaires
  sur des plateformes physiques et comment calibrer leurs poids. Les vecteurs
  sont ici exacts pour le mécanisme instrumenté, mais cela ne prouve pas qu'une
  analyse indépendante prédirait fidèlement toutes les implémentations réelles.
- Les profils plateforme restent synthétiques et ne constituent pas une
  validation sur des machines physiques.

Inventaire POC 3 : `poc3.py` (~260 lignes), `poc3_measurements.json` généré,
aucune dépendance externe. Reproduction : `python3 poc3.py`.
