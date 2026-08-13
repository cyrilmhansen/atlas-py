# Semantic Core v1 — conversion et décision de cycle de vie

## Ce que v0 ne savait pas exprimer

La multiplication `count * duration` acceptait une famille trop large de
counts. Elle rendait donc `run_count * apply_time` aussi plausible que la
répétition d'une application. De plus, le résultat de
`build + op + N * apply` n'avait pas d'identité propre de scénario ni de vue
directe de ses dépendances.

## Ajout minimal

v1 introduit `repeat(reuse_count, duration)` : la relation exige précisément
`ReuseCount`, puis produit une `Duration`. `run_count` est refusé. Les
expressions de cycle de vie sont enveloppées par `derived_duration(scenario,
expression)`. Elles conservent leur expression, leur scénario et les feuilles
`Quantity`, donc les mesures physiques et leurs provenances.

Il n'y a toujours ni parser, ni solver, ni simplificateur, ni système de types
général.

## Conversion mesurée

Le cas choisi est bitmap résultat B0 → runs B1. QuickDraw 3 mesure, sur
`sparse_sparse/intersection`, B0 comme opérateur de combinaison rapide mais B1
comme applicateur très rapide. Le cas `fragmented_fragmented/intersection`
sert de contre-exemple, car son résultat B1 contient 21 887 runs et 177 200
octets.

`semantic_core_conversion.py` mesure une conversion locale déterministe du
masque bitmap vers les runs, après échauffement, sur 31 échantillons. Les temps
d'application viennent des mesures C de QuickDraw 3 ; ils restent
contextualisés par plateforme, workload et statistique. La conversion Python
est une observation distincte, pas une propriété universelle de B0/B1.

Dans le relevé committé (`semantic_core_v1_measurements.json`), le cas sparse
coûte environ 5,11 ms à convertir et économise environ 77,90 µs par
application ; le premier entier favorable est `N=66`. Le cas fragmenté coûte
environ 7,54 ms à convertir et n'économise qu'environ 63,41 µs par application
; le premier entier favorable est `N=119`. Ces nombres peuvent varier entre
exécutions et sont conservés comme observations de ce relevé, non comme
constantes de la représentation.

## Décision exprimée

Pour chaque cas, v1 construit :

```text
without_conversion(N) = production_initiale + repeat(N, apply_bitmap)
with_conversion(N) = production_initiale + conversion
                       + repeat(N, apply_runs)
```

Une boucle entière cherche le premier `N` strictement favorable. Le coût de
production initiale est conservé même s'il s'annule algébriquement dans la
comparaison. Le contre-exemple peut rester sans break-even dans la limite
testée.

Le contre-exemple fragmenté est donc défavorable dans le régime court et
requiert une réutilisation nettement plus longue ; il ne justifie pas une
règle universelle « convertir les résultats B0 ».

## Limites

La v1 ne mesure qu'une conversion B0→B1 et ne réutilise pas le code C de
QuickDraw 3. Elle ne choisit pas automatiquement une représentation et ne
prédit aucun temps. Le seuil dépend des observations choisies. La conversion
ne change pas l'objet logique, seulement sa représentation.

Le Semantic Core apporte ici une capacité réelle mais limitée par rapport à un
script de benchmark : il rejette `repeat(run_count, apply_time)`, donne une
identité de scénario à l'expression dérivée, expose ses feuilles de provenance
et permet de comparer deux cycles de vie symboliques avec la même boucle de
recherche. Le benchmark seul pouvait déjà calculer le seuil numérique ; il ne
portait pas ces contraintes sémantiques.

Restent hors périmètre : conversions B1/B2, incertitude, intervalles,
multi-plateforme, coût des allocations, entiers machine, overflow,
optimisation d'expressions et généralisation hors QuickDraw.
