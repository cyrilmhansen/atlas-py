# Claim scope — dériver sans élargir

## Périmètre et méthode

Cette expédition relit les extractions V4 et leurs audits conservés dans
`reports/nist-v4-pilot.md` et `reports/claims-questions-v4-pilot.md`, ainsi que
les réponses JSON correspondantes. Corpus Miner V4, son prompt, son validateur
et ses facets restent inchangés.

## Cas connus

### Binary search

Observations citées : `obs_linked_list_traversal` (lignes 48–50), qui établit
`O(n)` traversals sur liste chaînée, et `obs_linked_list_comparisons`
(lignes 50–52), qui établit `O(log n)` comparaisons. Le claim ajoutait :
« unlike on arrays where traversal is O(1) ». Le rapport le considère utile
mais plus large que le texte borné : les observations établissent le coût sur
liste, pas le contrat de traversal d'un tableau.

### Histogram sort

Les observations de la ligne 26 disent que bucket sort utilise des buckets de
taille fixe, qu'histogram sort prépare des buckets de la bonne taille au
premier passage, et que counting sort est un histogram sort avec un bucket par
valeur de clé possible. Le claim ajoutait qu'histogram sort pouvait avoir
« fewer buckets than key values ». Cette conséquence est plausible dans
certains domaines de clés, mais n'est pas établie par ces observations.

### SQLite indexed ORDER BY

Les observations citées établissent le stockage temporaire potentiellement
substantiel du sorter, le moindre stockage généralement utilisé par l'index,
la dépendance du choix à la taille de table et aux contraintes `WHERE`, ainsi
que le bénéfice d'un covering index. Le claim `TOO_BROAD` transforme « moindre
stockage temporaire » en « raison principale de la préférence ». Le saut est :

```text
un facteur favorable parmi plusieurs → règle de préférence principale
```

Il efface aussi la dépendance au workload et au cost-based planner.

## Dérivations contrastantes supportées

Le claim du midpoint sûr compose les observations `binary-search`, lignes
43–46 : une formule peut déborder, l'autre donne le même résultat et ne
débordera pas sous la précondition d'indices non négatifs. La recommandation
d'utiliser la seconde forme ajoute une conséquence opérationnelle, mais pas un
nouveau quantificateur, domaine ou mécanisme externe.

Le claim SQLite supporté relie mêmes ordres asymptotiques, cost-based planner,
estimation du temps total et dépendance à la taille de table/aux contraintes
`WHERE` (ligne 3). Il reformule une règle conditionnelle sans prétendre qu'un
plan gagne toujours ni qu'un facteur unique explique le choix.

Le claim sur la variante Select de quicksort compose le pire cas `Theta(n^2)`
et la variante à `O(n log n)` pire cas explicitement décrite (lignes 46–56).
La formulation « can be improved » respecte cette portée ; elle serait trop
forte si elle supprimait la précondition de sélection de pivot.

## Distinction minimale

La distinction utile n'est pas « littéral contre dérivé » :

> Un claim dérivé peut ajouter une conséquence, une relation ou une
> recommandation locale si elle est entraînée par l'ensemble des observations
> citées, sous les mêmes sujets, préconditions, modalités et portée. Il ne doit
> pas augmenter silencieusement la portée logique des observations.

Le paquet de portée à conserver comprend au minimum : sujet et domaine,
préconditions, modalité (`can`, `may`, `typically`, `generally`, nécessité),
niveau de comparaison, et nature du lien (association, comparaison,
mécanisme ou explication).

Les renforcements suivants franchissent typiquement la frontière :

```text
some / may / generally → primary / always / does
local case → universal class
one advantage → decision rule or preference
association → causal explanation
example or named variant → property of the whole class
```

## Contre-exemples aux règles trop simples

« Ne jamais ajouter de conséquence » est trop strict : le midpoint sûr est une
recommandation directement impliquée par le risque et la formule sûre.

« Toute combinaison d'observations est valide » est trop permissif : les
observations SQLite autorisent une formulation conditionnelle du choix, mais
pas « le stockage est la raison principale ».

« Une provenance valide suffit » est faux : le claim SQLite cite les bonnes
observations, mais le connecteur `primarily` n'est pas entraîné par elles.

## CONFIRMED

- Les échecs observés sont des élargissements de portée, pas principalement des
  erreurs de localisation.
- Le signal récurrent est `one factor → decision rule`, avec effacement de
  conditions de workload.
- Une dérivation utile peut ajouter une conséquence opérationnelle si elle est
  entraînée par les observations et conserve leur paquet de portée.
- `supported_by` et les locators prouvent la provenance des prémisses, pas la
  validité de chaque renforcement rhétorique.
- Le problème concerne au moins portée, modalité et force comparative. La force
  causale doit être auditée séparément ; ce corpus ne permet pas de la réduire
  à une simple portée.

## DISPROVED

- Toute conclusion plausible reliée à des observations est une
  `SUPPORTED_DERIVATION`.
- Un seul facteur de coût suffit à conclure à une préférence du planner.
- Il faut interdire toute information ajoutée par un claim dérivé.
- Un locator valide garantit la validité sémantique du claim.

## UNKNOWN

- Comment représenter automatiquement le paquet de portée sans logique
  universelle.
- Quand une différence de modalité est une paraphrase acceptable ou un
  renforcement substantiel.
- Comment auditer la force causale lorsqu'un texte mêle corrélation, mécanisme
  et mesure.
- Si les claims multi-étapes demandent une décomposition en sous-claims.

## Règle durable et validation ultérieure

Un futur validateur devrait auditer séparément : (1) couverture des prémisses,
(2) conservation de l'enveloppe de portée, (3) type de relation affirmée et
(4) hypothèses ou préconditions ajoutées. Une conclusion peut ajouter une
conséquence locale ; elle doit être refusée ou abaissée en hypothèse lorsqu'elle
ajoute priorité, universalité, explication causale ou garantie non observée.

Cette règle est une connaissance d'audit, pas une modification de V4 ni un
contrat automatisé fiable.

## Prochaine question expérimentale unique

Sur un petit corpus à paires, peut-on distinguer reproductiblement une
paraphrase qui conserve `generally/can/may` d'une paraphrase qui la renforce en
`primarily/always/is the reason`, avec les mêmes observations citées ?
