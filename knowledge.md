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
