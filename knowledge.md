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

## POC 4 — interactions entre mécanismes

### Confirmed

- L'espace reste généré par les mêmes mécanismes et préconditions : famille
  triée, hash sparse avec scan des slots, et hash sparse avec `dense_view`.
  Aucune combinaison nommée `hybrid` n'est ajoutée comme candidat monolithique.
- L'interaction `sparse_slots + dense_view` modifie effectivement les
  caractéristiques : la vue dense remplace le parcours de tous les slots par
  un parcours de `n` éléments, mais ajoute sa capacité mémoire et une écriture
  auxiliaire lors de chaque update ou insert.
- Ces effets sont dérivés avant exécution dans `predicted_vector()`, puis
  retrouvés par l'instrumentation : les vecteurs prédits et observés sont égaux
  pour les trois compositions et les trois workloads
  (`poc4_measurements.json`). Les deux chemins décrivent toutefois des branches
  et hypothèses très proches ; cette égalité valide leur cohérence interne, pas
  encore un modèle réellement indépendant de l'implémentation.
- Les workloads rendent le compromis visible : dans `walk_heavy`, le scan des
  slots parcourt 3 276 800 slots, contre 1 000 000 lectures séquentielles avec
  `dense_view`; dans `update_heavy`, la vue dense produit 600 écritures
  auxiliaires pour 400 updates et 200 inserts.
- Avec les profils synthétiques retenus, la famille triée reste sélectionnée
  dans tous les workloads. L'expérience établit donc l'effet d'interaction et
  son coût explicable, mais ne démontre pas qu'il suffit à changer le choix.

### Disproved

- L'hypothèse selon laquelle le vecteur complet pourrait être obtenu par une
  simple addition indépendante des mécanismes est réfutée pour cette
  composition : `dense_view` dépend de la présence de `sparse_slots` et change
  simultanément capacité, écritures et coût du parcours.
- L'hypothèse d'un basculement obligatoire vers la vue dense n'est pas soutenue :
  aucun des profils et workloads testés ne la sélectionne. Les coefficients
  n'ont pas été forcés pour obtenir ce résultat.

### Unknown

- Il reste inconnu jusqu'où ces règles locales suffisent lorsque les mécanismes
  interagissent davantage, notamment avec suppressions, collisions ou resize.
- On ne sait pas quand une interaction nécessiterait une modélisation globale,
  ni si cette granularité resterait exploitable avec davantage de mécanismes.
- Les profils restent synthétiques ; le calibrage sur une plateforme réelle et
  les dimensions supplémentaires nécessaires restent inconnus.

Inventaire POC 4 : `poc4.py` (~290 lignes), `poc4_measurements.json` généré,
aucune dépendance externe. Reproduction : `python3 poc4.py`.

## POC 5 — modèle indépendant de l'implémentation

### Confirmed

- Le chemin analytique part uniquement de descriptions structurelles et du
  résumé des workloads. Il ne reçoit ni les clés concrètes ni la fonction de
  hachage exécutée. Les trois implémentations instrumentées n'appellent aucune
  formule de `analyze()` ; les calculs de capacité et les algorithmes y sont
  dupliqués localement. Les deux chemins peuvent donc diverger réellement.
- Les propriétés déclarées exactes sont toutes retrouvées par l'exécution pour
  les neuf couples solution/workload : lectures séquentielles, slots visités,
  écritures primaires et auxiliaires, cellules réservées et allocations. Les
  checksums des trois implémentations concordent dans chaque workload
  (`poc5_measurements.json`).
- Les erreurs sont localisables par dimension et niveau de confiance avant
  toute pondération plateforme. Le modèle plateforme synthétique n'est appliqué
  qu'après cette comparaison.
- Une prédiction algorithmique doit donc conserver son statut : valeur exacte,
  borne à vérifier, ou estimation conditionnelle accompagnée de l'hypothèse
  nécessaire. Ces catégories ne sont pas interchangeables même si elles portent
  toutes un nombre.
- L'écart de probing est expliqué par une hypothèse manquante : l'analyse suppose
  un hachage uniforme, alors que l'exécution utilise des clés multiples de 64
  avec une capacité puissance de deux. Les probes observés valent 8 257 contre
  1 245,14 estimés sur `lookup_heavy`, 5 283 contre 833,73 sur `walk_heavy`, et
  8 299 contre 1 231,68 sur `update_heavy`.
- Cet écart algorithmique peut changer la décision ultérieure : pour
  `lookup_heavy`, les deux profils choisissent `hash+dense_view` depuis le
  vecteur prédit, mais `sorted` depuis le vecteur observé pondéré. Cela ne
  constitue toujours pas une validation physique des profils.

### Disproved

- La borne analytique de comparaison binaire utilisée est fausse : elle prévoit
  4 200/700/2 500 comparaisons selon le workload, contre 4 202/701/2 501
  observées. Certaines recherches sur 512 éléments nécessitent une itération
  de dichotomie supplémentaire avant la comparaison finale. La formule est
  conservée telle quelle afin de rendre la réfutation visible.
- L'estimation de probing fondée seulement sur le facteur de charge ne prédit
  pas cette distribution de clés. Comparaisons et accès aléatoires, dérivés du
  même nombre de probes estimé, héritent du même écart. Le modèle n'a pas été
  ajusté après mesure pour le faire disparaître.
- `vector_equal: true` dans les POC précédents ne suffisait donc pas à démontrer
  une capacité de prédiction indépendante : les chemins découplés du POC 5
  exposent deux divergences que leur proximité masquait.

### Unknown

- La généralisation des estimations à d'autres distributions de clés, fonctions
  de hachage, facteurs de charge et politiques de resize reste inconnue.
- On ne sait pas encore quel niveau de granularité déclarative suffirait pour
  analyser des implémentations externes plus complexes sans recopier leur code.
- Le calibrage physique des dimensions et les caractéristiques supplémentaires
  requises par une plateforme réelle restent inconnus.

Inventaire POC 5 : `poc5.py` (~415 lignes), `poc5_measurements.json` généré,
aucune dépendance externe. Reproduction : `python3 poc5.py`.

## POC 6 — hypothèses, incertitude et acquisition sélective

### Confirmed

- Chaque dimension conserve un statut `exact`, `bound` ou `estimate`, un
  intervalle, sa source et ses hypothèses. Le coût plateforme synthétique est
  lui aussi un intervalle obtenu seulement après le vecteur ; une solution
  n'est sélectionnée que si son maximum est inférieur aux minima de toutes les
  alternatives.
- Au niveau A de `lookup_heavy`, l'hypothèse de dispersion uniforme est marquée
  non vérifiée. Les intervalles de `sorted` `[698,26 ; 1 748,26]` et de
  `hash+dense_view` `[1 130,84 ; 167 949,80]` se chevauchent : la décision est
  `needs_information` plutôt qu'un choix fondé sur les valeurs centrales.
- Au niveau B, la lecture de 64 clés trouve 31 résidus distincts modulo la
  capacité, un bucket maximal de 5 et un ratio de dispersion de 0,4844. Cette
  statistique réfute le support de l'hypothèse uniforme et réduit la borne haute
  de `hash+dense_view` à 26 931,23, sans suffire à décider.
- Au niveau C, un micro-probe limité aux mêmes 64 clés effectue 64 insertions et
  113 probes (moyenne 1,7656, maximum 5). L'extrapolation prudente donne à
  `hash+dense_view` `[2 204,77 ; 4 518,26]`, désormais dominé par la borne de
  `sorted`; la décision devient `decidable` et choisit `sorted`.
- L'oracle complet est exécuté seulement après la décision. Il confirme
  `sorted` (`1 643,76`) devant `hash+dense_view` (`3 554,69`) et observe 8 297
  probes. Toutes les dimensions observées restent dans les intervalles finaux,
  et les checksums concordent.
- `walk_heavy` est robuste dès le niveau A : le maximum de `sorted` (5 839,76)
  est inférieur au minimum de `hash+dense_view` (6 069,34). Aucune statistique
  ni micro-probe n'est acquis, puis l'oracle confirme la décision.
- L'acquisition est sélective quant à l'arrêt, mais pas quant au choix de
  l'information : lorsque des données sont nécessaires, le POC impose encore
  la séquence niveau A → statistique B → micro-probe C. Atlas ne compare ni leur
  coût ni leur utilité attendue.

### Disproved

- Considérer la dispersion uniforme comme vraie par défaut est réfuté par la
  statistique de bits bas et par les 8 297 probes de l'oracle `lookup_heavy`.
- Toujours choisir la meilleure valeur centrale est réfuté : au niveau A de
  `lookup_heavy`, elle classe `hash+dense_view` premier, tandis que l'information
  acquise et l'oracle choisissent `sorted`.
- Toujours mesurer avant de décider est inutile dans `walk_heavy`, dont les
  intervalles initiaux suffisent. Inversement, la statistique bon marché seule
  n'est pas toujours suffisante : `lookup_heavy` reste indécidable au niveau B.

### Unknown

- Le POC ne choisit pas automatiquement parmi plusieurs informations possibles
  à acquérir et ne valorise pas leur coût dans la décision.
- La représentation de plusieurs hypothèses dépendantes et le choix d'intervalles
  d'extrapolation restent ouverts.
- La généralisation à d'autres distributions, implémentations externes et
  plateformes physiques, ainsi que leur calibration, reste inconnue.

Inventaire POC 6 : `poc6.py` (~455 lignes), `poc6_measurements.json` généré,
aucune dépendance externe. Reproduction : `python3 poc6.py`.

## POC 7 — choisir l'information à acquérir

### Confirmed

- `sample16`, `sample64`, `probe16` et `probe64` sont proposés simultanément.
  Avant observation, la politique ne connaît que leur cible
  (`hash_dispersion`), leur coût attendu, leur caractère direct et une réduction
  grossière d'intervalle. Le résultat futur de l'action et l'oracle ne sont pas
  accessibles au choix.
- Sur l'état initial indécidable de `lookup_heavy`, les utilités décisionnelles
  par coût annoncées sont 1,736 (`sample16`), 2,412 (`sample64`), 13,024
  (`probe16`) et 4,582 (`probe64`). La politique choisit donc `probe16` pour son
  compromis coût/réduction attendu, et non parce que son observation est connue.
- `probe16` réalise 16 insertions et 20 probes, soit un coût d'acquisition réel
  de 36. La moyenne observée de 1,25 probe resserre `hash+dense_view` de
  `[1 130,84 ; 167 949,80]` à `[1 840,64 ; 6 667,91]`. Comme le maximum de
  `sorted` reste 1 748,26, la décision devient robuste après une seule action.
- L'oracle complet, exécuté après l'arrêt, confirme `sorted` (1 643,76) devant
  `hash+dense_view` (3 573,83, 8 355 probes). Toutes les dimensions observées
  sont contenues dans les intervalles finaux et les checksums concordent.
- Sur `lookup_heavy`, `adaptive` décide correctement pour 36 unités, contre 189
  pour `always_expensive` (`probe64`) et 253 pour `fixed_sequence`
  (`sample64`, puis `probe64`). `always_none` dépense 0 mais reste
  `undetermined` ; sa valeur centrale aurait choisi le mauvais candidat hash.
- Sur `walk_heavy`, l'état initial est déjà robuste : `adaptive`,
  `fixed_sequence` et `always_none` n'acquièrent rien et l'oracle confirme
  `sorted`. `always_expensive` dépense inutilement 189 unités pour `probe64`.

### Disproved

- Toujours choisir l'action réputée la plus informative et la plus coûteuse est
  réfuté : `probe64` coûte plus de cinq fois `probe16` sur `lookup_heavy` sans
  améliorer la décision, et apporte zéro valeur décisionnelle sur `walk_heavy`.
- La séquence fixe du POC 6 est réfutée comme politique de coût : elle acquiert
  `sample64` puis `probe64` pour 253 unités là où la sélection adaptative s'arrête
  après `probe16` pour 36.
- Acquérir malgré une dominance déjà robuste est réfuté par `walk_heavy`.
- L'estimation préalable d'utilité reste grossière : elle indiquait qu'aucune
  action ne serait probablement décisive seule, alors que `probe16` suffit en
  pratique. Elle a correctement ordonné les actions dans ce cas, sans prédire
  exactement leur résultat.

### Unknown

- Le choix automatique de la meilleure information reste dépendant de facteurs
  de réduction et de directness fixés manuellement ; leur estimation fiable est
  inconnue. POC 7 ne démontre donc pas encore qu'Atlas puisse dériver lui-même
  la valeur décisionnelle d'une observation depuis les dépendances du modèle.
- La comparaison d'informations de nature très différente, l'intégration du
  coût d'acquisition au coût global du programme et plusieurs décisions ou
  hypothèses dépendantes restent ouvertes.
- La généralisation à des implémentations externes et plateformes physiques,
  ainsi que leur calibration, reste inconnue.

Inventaire POC 7 : `poc7.py` (~500 lignes), `poc7_measurements.json` généré,
aucune dépendance externe. Reproduction : `python3 poc7.py`.

## POC 8 — dériver la valeur décisionnelle de l'information

### Confirmed

- La décision initiale `lookup_heavy` est indéterminée : `sorted` vaut
  `[698,26 ; 1 748,26]` et `hash+dense_view` `[1 130,84 ; 167 949,80]`.
  La remontée locale relie le chevauchement aux dimensions incertaines puis à
  leurs causes : `hash_dispersion → probe_count → comparisons/probes/
  random_accesses → coût`, et `sorted_search_depth → comparisons/
  random_accesses → coût`.
- La largeur pondérée dominante vient de `probe_count` : 101 102,40 unités via
  les accès aléatoires, 40 440,96 via les probes et 25 275,60 via les
  comparaisons. Les dimensions exactes de largeur nulle ne déclenchent aucune
  acquisition.
- Les quatre actions ne portent ni `directness` ni réduction attendue dans la
  politique structurelle. `sample16/64` observent `hash_dispersion` en amont ;
  `probe16/64` observent directement `probe_count`. La taille `k` détermine
  mécaniquement le rayon relatif `1/√k` du modèle d'extrapolation des probes.
- Les échantillons statistiques sont causalement pertinents, mais le modèle ne
  sait pas traduire seuls leurs résidus en intervalle quantitatif de probes.
  Les deux micro-probes le peuvent et une observation possible pourrait rendre
  le classement robuste ; `probe16` est donc choisi comme le moins coûteux
  susceptible de suffire, avant de connaître son résultat.
- `probe16` observe 18 probes pour 16 insertions (moyenne 1,125, maximum 2),
  soit un coût réel de 34. L'intervalle de coût hash devient
  `[2 031,59 ; 2 841,54]`, au-dessus du maximum 1 748,26 de `sorted`; la
  décision devient robuste et choisit `sorted`.
- L'oracle postérieur confirme `sorted` (1 643,76) devant hash (3 527,96,
  8 216 probes), et les checksums concordent. Sur `walk_heavy`, le classement
  est robuste initialement : la politique structurelle n'analyse ni n'exécute
  aucune acquisition, tandis que `always_expensive` dépense inutilement 180.
- Sur `lookup_heavy`, `structural` et `poc7_manual` choisissent tous deux
  `probe16` pour un coût 34 ; `always_expensive` coûte 180 et `always_none`
  reste indéterminé. Le gain de POC 8 est l'explication structurelle du choix,
  pas une amélioration de coût sur ce cas minuscule.

### Disproved

- Les dépendances structurelles seules ne suffisent pas à quantifier toute
  acquisition pertinente : observer indirectement `hash_dispersion` ne donne
  pas un intervalle de `probe_count` sans modèle externe de traduction. Les
  actions `sample16/64` ne peuvent donc pas être classées quantitativement ici.
- La pertinence causale ne garantit pas la qualité de l'extrapolation. Après
  `probe16`, l'intervalle prédit `[3 681,56 ; 6 135,94]` pour probes,
  comparaisons et accès aléatoires ne contient pas les 8 216 événements de
  l'oracle. La décision reste correcte, mais sa couverture annoncée est fausse.
- Une relation directe n'est donc pas, à elle seule, une estimation fiable de
  la valeur future d'une observation. L'hypothèse de représentativité et le
  rayon `1/√k` restent un modèle supplémentaire, non dérivé du graphe.

### Unknown

- Il reste inconnu comment quantifier rigoureusement l'effet futur d'une
  observation sans connaître son résultat, notamment pour une relation
  indirecte potentiellement moins chère.
- Plusieurs causes corrélées, plusieurs chaînes d'acquisition et l'intégration
  du coût de connaissance au coût du programme restent ouvertes.
- La généralisation à des implémentations externes et plateformes physiques,
  ainsi que leur calibration, reste inconnue.

Inventaire POC 8 : `poc8.py` (~570 lignes), `poc8_measurements.json` généré,
aucune dépendance externe. Reproduction : `python3 poc8.py`.

## POC 9 — contrats épistémiques pour l'extrapolation

### Confirmed

- Observation et inférence sont séparées : `probe16/32/64` produisent seulement
  taille, moyenne, maximum et total de probes. Trois contrats définis avant les
  observations décident ensuite si ces faits autorisent une estimation, une
  borne ou `insufficient_evidence`, avec leurs hypothèses et critères
  d'acceptation explicites.
- Sur `lookup_heavy`, les micro-probes emboîtés observent des moyennes
  1,125/1,34375/1,859375 et des maxima 2/3/4. La même grandeur causalement
  pertinente est donc interprétée différemment selon le contrat.
- `naive_representative` accepte `probe16`, suppose immédiatement la
  représentativité et choisit correctement `sorted`, mais son intervalle
  `[3 681,56 ; 6 135,94]` ne contient pas les 8 253 probes de l'oracle. Le
  résultat est explicitement classé `correct_decision_bad_coverage`, et non
  comme validation du contrat.
- `conservative` conserve après `probe64` une borne `[1 770,12 ; 34 272]` qui
  couvre l'oracle, mais ne permet pas de départager les solutions. Il dépense
  292 unités sur trois probes puis s'arrête `undetermined` plutôt que de
  transformer la pertinence de la mesure en fausse précision.
- `multi_scale` exige trois tailles et une variation relative maximale ≤ 0,20.
  Les variations observées 0,1944 puis 0,3837 violent ce contrat ; après les
  trois probes et un coût 292, il retourne `insufficient_evidence` sans produire
  d'intervalle global.
- L'oracle postérieur confirme `sorted` (1 643,76) devant hash (3 540,17,
  8 253 probes), et les checksums concordent. Décision correcte et couverture
  correcte sont ainsi évaluées séparément.
- Le contrôle positif à clés séquentielles observe des moyennes et maxima égaux
  à 1 aux trois échelles. `multi_scale` accepte alors `[952 ; 1 071]`, qui
  contient les 952 probes de l'oracle : le refus n'est donc pas systématique.
- Sur `walk_heavy`, la décision est robuste avant toute inférence de probing ;
  les trois contrats n'acquièrent rien et le résultat est classé
  `correct_decision_no_inference_needed`.

### Disproved

- La représentativité automatique d'un petit échantillon est réfutée :
  `probe16` mesure la bonne grandeur et conduit à la bonne décision, mais son
  intervalle naïf ne couvre pas l'observation complète.
- Une confiance fondée uniquement sur la taille `k` et le rayon `1/√k` est
  réfutée sur la distribution groupée. Ce rayon est une hypothèse de contrat,
  pas une garantie dérivée de la causalité ou de la taille seule.
- Davantage de données ne garantit pas une décision : le contrat conservateur
  couvre correctement après `probe64` tout en restant indéterminé, et le contrat
  multi-échelle découvre davantage d'instabilité au lieu de gagner en confiance.

### Unknown

- Il reste inconnu comment obtenir de bons contrats épistémiques et choisir
  entre plusieurs contrats plausibles sans consulter l'oracle. Cette question
  n'est pas poursuivie immédiatement afin d'éviter de spécialiser davantage les
  expériences sur le seul domaine clé-valeur.
- Les distributions non stationnaires ou adversariales, plusieurs hypothèses
  dépendantes et la valeur du coût de preuve supplémentaire restent ouvertes.
- Le transfert d'une connaissance empirique entre implémentations ou plateformes
  physiques, ainsi que leur calibration, reste inconnu.

Inventaire POC 9 : `poc9.py` (~485 lignes), `poc9_measurements.json` généré,
aucune dépendance externe. Reproduction : `python3 poc9.py`.

## POC 10 — transfert vers un mini-batch

### Confirmed

- Un besoin batch neuf est décrit par 4 096 enregistrements, un filtre opaque,
  un effort de transformation et une limite mémoire, sans présupposer une
  architecture. Le produit de `item_by_item/chunk64`,
  `fused/materialized_filter` et `incremental/deferred_reduce` génère huit
  compositions, sans candidats monolithiques nommés.
- Les interactions sont explicites dans un vecteur propre au batch. `chunk64`
  remplace 4 096 unités source par 64 batches ; `materialized_filter` écrit et
  relit les survivants mais les redensifie en batches de transformation ;
  `deferred_reduce` remplace une agrégation par survivant par un appel, au prix
  d'écritures, de relectures et d'un buffer. La coexistence des deux
  matérialisations porte le pic temporaire à deux fois les survivants.
- Sur `filter_heavy/throughput`, l'échantillon de 128 enregistrements observe
  15 survivants et estime `[357 ; 603]`; l'oracle en compte 512. La composition
  émergente `chunk64 + materialized_filter + deferred_reduce` transforme en 8
  batches, agrège en un appel et atteint un pic temporaire de 1 024. Elle est
  prédite et observée gagnante (coût synthétique 5 492,88).
- Sur `transform_heavy/throughput`, l'échantillon observe 113 survivants et
  estime `[3 493 ; 3 739]`; l'oracle en compte 3 584. La composition retenue
  devient `chunk64 + fused + deferred_reduce` : 64 batches, aucune
  matérialisation après filtre, une réduction et un pic de 3 584. Le modèle et
  l'oracle concordent (40 657,68).
- Sur `memory_tight`, la limite d'une unité rend
  `item_by_item + fused + incremental` robuste pour toute sélectivité possible.
  Aucun échantillon n'est acquis dans les deux scénarios ; l'oracle confirme un
  pic de 1 et les décisions. Une propriété inconnue n'exige donc une mesure que
  si elle peut changer le choix.
- Les vecteurs prédits à sélectivité connue et les vecteurs instrumentés sont
  égaux pour les huit compositions ; avec sélectivité estimée, toutes les
  observations sont dans les intervalles. Les huit exécutions produisent le
  même checksum par scénario. Le chemin exécuté n'appelle pas les formules du
  modèle analytique.
- La séparation `mécanismes + interactions → vecteur → plateforme → choix`, les
  statuts `exact/bound/estimate`, les hypothèses et l'acquisition conditionnelle
  restent donc opérants hors du domaine clé-valeur.
- La sélectivité est une inconnue commune à toutes les compositions : la
  décision cherche le gagnant pour chaque valeur encore possible et ne traite
  pas les intervalles des solutions comme des incertitudes indépendantes.

### Disproved

- Un schéma de caractéristiques supposé universel ne se transfère pas : probes,
  slots et dispersion des clés disparaissent. Le batch exige batches,
  matérialisations, appels d'agrégation, relectures et mémoire temporaire.
- L'idée que matérialiser serait toujours inférieur à fusionner est réfutée par
  `filter_heavy` : redensifier 512 survivants réduit 64 appels de transformation
  à 8 et compense les écritures/relectures intermédiaires sur `throughput`.
- L'idée qu'une inconnue importante doit toujours être mesurée est réfutée par
  `memory_tight`, où le classement est invariant sur toute sa borne.
- Les contrats de probing des POC 8–9 ne se transfèrent pas au mini-batch. Un
  contrat simple de sélectivité suffit ici ; les contrats multiples n'ont pas
  été reproduits artificiellement.

### Unknown

- Un troisième domaine est nécessaire pour mieux distinguer principes généraux
  et coïncidences communes à deux expériences contrôlées.
- La bonne granularité pour des mécanismes issus de code externe, leur
  instrumentation indépendante et l'extraction automatique de connaissances
  depuis bibliothèques ou frameworks restent inconnues.
- Il reste également inconnu si cette connaissance peut être recombinée sans
  importer l'ontologie ou l'architecture du code dont elle est extraite.
- Les profils sont synthétiques ; calibration et validité sur plateformes
  physiques restent inconnues. Le contrat d'échantillonnage de sélectivité n'a
  été testé que sur deux filtres déterministes.

### Bilan de transfert

| Classe | Concepts observés |
|---|---|
| Transfert naturel | besoin sans architecture, mécanismes fins, compatibilités, interactions, recherche exhaustive, vecteur avant coût, plateforme séparée, `exact/bound/estimate`, acquisition conditionnelle |
| Adaptation nécessaire | dimensions du vecteur, effets de buffers simultanés, redensification, propagation corrélée d'une sélectivité partagée |
| Non transféré | probes, slots, dispersion des clés et contrats épistémiques spécifiques au hachage |

Inventaire POC 10 : `poc10.py` (~405 lignes), `poc10_measurements.json` généré,
aucune dépendance externe. Reproduction : `python3 poc10.py`.

## POC 11 — extraction depuis des implémentations existantes

### Confirmed

- Deux programmes ordinaires ont été écrits et vérifiés avant toute extraction :
  A traite et agrège chaque survivant immédiatement, B sélectionne, transforme
  par blocs de 64 puis réduit un buffer. Ils produisent les mêmes résultats
  (`sparse`: 512/2 325 550 ; `dense`: 3 584/1 727 749 065). Leur gel est attesté
  dans `poc11_fixtures.json` par les SHA-256
  `30b1f876…2772` (A) et `37ae2958…e2c6` (B), encore vérifiés à chaque exécution.
- L'analyse manuelle postérieure n'a pas conservé les fonctions comme
  frontières. Elle extrait trois rôles communs : passage fusionné ou retenu des
  survivants, dispatch individuel ou par bloc compact, réduction courante ou
  différée. Par exemple, `run()` de A contient trois mécanismes, tandis que le
  passage retenu de B traverse `select()` et `run()`
  (`poc11_extraction.json`).
- Ces rôles génèrent six compositions admissibles, et non deux candidats A/B.
  La contrainte observée `compact_block64_dispatch` exige un passage retenu ;
  les deux réductions exigent ici une somme associative. Provenance issue des
  sources et relations ajoutées par l'analyste sont conservées séparément.
- Avant l'écriture de C, la recherche exhaustive sélectionne pour
  `sparse_memory` la composition nouvelle
  `retained_handoff + compact_block64_dispatch + running_reduction`. Elle
  combine passage/dispatch extraits de B et réduction extraite de A. Son
  implémentation C produit ensuite les mêmes checksums, sans reconstruire
  l'architecture complète d'aucune source.
- Sous la limite temporaire de 600, C a un pic prédit et observé de 576 ; B est
  inadmissible à 1 024, et A reste admissible mais supporte 512 dispatches et
  512 mises à jour d'agrégat. Le modèle sélectionne donc C (8 085,12 unités
  synthétiques). Sur `dense_throughput`, avec assez de mémoire, B reste retenue
  (47 042,96) devant C (75 634,56). L'oracle instrumenté confirme les deux
  classements (`poc11_measurements.json`).
- Les vecteurs prédits et observés sont égaux pour A, B et C dans les deux
  scénarios, et les implémentations n'appellent pas `vector()`. L'observation
  utilise néanmoins des adaptateurs propres à chaque source : elle vérifie les
  caractéristiques extraites dans cette expérience déterministe, sans prouver
  qu'une extraction ou une instrumentation générale serait immédiate.
- La granularité est utile dans ce cas étroit : elle est plus basse que les
  architectures A/B, plus haute que les instructions, porte des propriétés
  calculables et permet une recombinaison sous précondition explicite.

### Disproved

- Les frontières de fonctions ne constituent pas une granularité suffisante :
  elles auraient laissé A et B presque monolithiques et auraient masqué les
  rôles partagés ou recombinables.
- Les mécanismes extraits ne sont pas librement indépendants. Le dispatch par
  blocs observé ne peut pas être associé au passage fusionné sans inventer un
  autre mécanisme de buffering absent des sources.
- L'architecture bufferisée complète de B n'est pas nécessaire pour bénéficier
  de ses blocs compacts : C conserve ces blocs mais remplace son buffer de
  sorties et sa réduction différée par la réduction courante extraite de A.

### Unknown

- Rien ne démontre que la granularité extraite soit unique ou canonique :
  plusieurs découpages sémantiques plausibles pourraient décrire les mêmes
  sources tout en préservant, ou non, les conséquences nécessaires au choix.
- L'extraction reste entièrement manuelle ; son automatisation, son ambiguïté
  lorsque plusieurs granularités sont plausibles et son passage à un code plus
  gros restent inconnus.
- On ne sait pas si les mêmes rôles seraient reconnaissables lorsque les effets
  sont dispersés entre modules, masqués par un framework ou couplés à des états
  externes.
- La provenance et les licences de connaissances issues de code tiers,
  l'analyse de vrais frameworks et la calibration sur plateformes physiques
  ne sont pas traitées.
- L'égalité exacte des vecteurs ne teste ni des effets runtime non observés ni
  la fiabilité de propriétés approximatives ; les poids plateforme sont
  synthétiques.

Inventaire POC 11 : `poc11_source_a.py` (38 lignes), `poc11_source_b.py`
(45), `poc11_source_c.py` (43), `poc11.py` (~300),
`poc11_fixtures.json`, `poc11_extraction.json`, `poc11_predictions.json` et
`poc11_measurements.json`. Aucune dépendance externe. Reproduction complète :
`python3 poc11.py` ; prédiction seule : `python3 poc11.py --predict-only`.
