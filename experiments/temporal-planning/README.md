# Temporal Planning POC — étape 1

Ce micro-POC compare deux stratégies sur un modèle CP-SAT minimal :

- `select_then_schedule` choisit d'abord la réalisation la plus courte, sans
  contraintes temporelles, puis tente de la planifier sans retour arrière ;
- `joint_select_and_schedule` choisit les réalisations et les intervalles dans
  un même modèle, avec capacité `scratch` et deadline.

La reproduction utilise l'environnement OR-Tools déjà validé :

```sh
/tmp/atlas-semantic-kernel-venv/bin/python experiments/temporal-planning/run.py
```

Version observée : `ortools 9.15.6755`.

## Étape 2 — lifetimes

La même reproduction couvre aussi des ressources persistantes. Une ressource
est live sur l'intervalle `[fin_du_producteur, fin_du_dernier_consommateur)`.
Les intervalles de vie sont générés depuis le planning ; leur capacité
cumulative calcule la contrainte de mémoire et le résultat rapporte le peak
live memory.

## Étape 3 — choix de réalisation et lifetimes

`solve_composite` contient simultanément deux réalisations de l'intention
`compute_result` : `wide` produit A et B en parallèle puis les combine ;
`streamed` consomme A avant de produire B. Le solver sélectionne l'une des deux
réalisations et planifie ses opérations internes dans le même modèle.

```text
memory=12 -> wide     makespan=2  peak=12
memory=6  -> streamed makespan=3  peak=6
memory=6, deadline=2 -> infeasible
```

La reproduction utilise toujours OR-Tools `9.15.6755`.

## Étape 4.6 — surprise tests de clôture

La reproduction est dans `step4_6_surprises.py` :

```sh
/tmp/atlas-semantic-kernel-venv/bin/python experiments/temporal-planning/step4_6_surprises.py
```

Elle teste trois variations qui n'ont pas servi à construire les modèles
précédents :

- une préparation de durée 25 réutilisée par 12 appels dans une fenêtre longue
  est choisie une fois, avec `makespan=47` ;
- un appel nécessitant deux faits, connus respectivement à 4 et 10, avec des
  fenêtres `[4,18)` et `[10,24)`, est spécialisé après deux préparations
  distinctes (`P=(4,7)`, `Q=(10,13)`) et termine à 14 ;
- une variante rapide de durée 1 et de peak 6 est choisie sous capacité 6,
  tandis que la variante générique de durée 4 et de peak 1 est choisie sous
  capacité 5.

Le premier cas réutilise directement `SpecializationScenario`. Les deux autres
utilisent dans le script des structures locales minimales pour exprimer une
conjonction de fenêtres et une demande mémoire par variante ; ce n'est pas une
modification du modèle antérieur ni une règle spécifique à un scénario.

## Étape 4 — connaissance disponible dans le temps

`step4_specialization.py` modélise une fenêtre `[known_from, valid_until)`.
Une préparation optionnelle est une vraie opération CP-SAT, placée après la
disponibilité du fait et avant les appels spécialisés. Les appels peuvent être
génériques ou spécialisés, mais pas les deux.

```text
A : 2 appels dans la fenêtre sur 8 -> aucun spécialisé, makespan=18
B : 6 appels dans la fenêtre      -> tous spécialisés, makespan=19
C : appels [10,20]                -> spécialisés, makespan=17
C : appels [21,30]                -> génériques, makespan=29
```

La spécialisation n'est pas du code généré : seule la décision et le placement
temporel de la préparation et des appels sont expérimentés.

## Étape 4 — composition de plusieurs intentions

Le harnais ajoute deux intentions indépendantes, `compute_x` et `compute_y`,
chacune avec `fast` et `compact`. Chaque alternative porte son propre graphe
d'opérations et ses ressources ; le modèle joint sélectionne exactement une
alternative par intention.

```text
localement : X -> fast (3), Y -> fast (3)
memory=8, deadline=4 : fast+fast fixé -> infeasible
memory=8, deadline=4 : joint -> compact+fast, makespan=4, peak=6
memory=12, deadline=3: joint -> fast+fast, makespan=3, peak=12
```

La baseline fixe les deux choix locaux avant le scheduling. Le modèle joint
utilise les mêmes opérations, lifetimes et contraintes ; aucune relation de
conflit entre X et Y n'est ajoutée.

## Étape 5 — cartographie de la séparabilité

La grille réutilise exactement le modèle X/Y de l'étape 4, pour les capacités
6 à 12 et les deadlines `None`, 3, 4 et 5. `None` signifie aucune deadline
effective ; le domaine CP-SAT est borné à 20, au-dessus de tous les plannings
de ce micro-modèle.

Quelques régimes observés :

```text
memory=12, deadline=None : FF / FF, makespan=3 / 3, Equivalent
memory=8,  deadline=None : FF / CF, makespan=5 / 4, local globally suboptimal
memory=8,  deadline=4    : FF infeasible / CF makespan=4, local infeasible
memory=12, deadline=3    : FF / FF, makespan=3 / 3, Equivalent
memory=8,  deadline=3    : Both infeasible
```

La mémoire seule peut donc être absorbée par le scheduling dans certains cas,
mais le planning résultant peut être plus lent. La deadline seule ne modifie
pas le choix dans ce modèle lorsque la mémoire est abondante.

## Étape 3 — recherche bornée de contre-exemples

`step3_counterexamples.py` génère de petites instances à deux alternatives,
énumère les sélections et les horaires entiers pour obtenir un oracle exact,
puis compare cet oracle au modèle CP-SAT joint.

Le premier contre-exemple trouvé dans la famille bornée est :

```text
G=2, A=2, D=0, capacity=3, deadline=2
local : fast/fast -> infeasible
joint : compact/fast -> makespan=2
oracle: compact/fast -> makespan=2
```

La grille du même motif donne aussi :

```text
capacity=3, deadline=None : local FF makespan=4, joint FC makespan=3
capacity=4, deadline=None : local FF = joint FF, makespan=2
capacity=3, deadline=3    : local infeasible, joint CC makespan=3
capacity=3, deadline=4    : local FF makespan=4, joint FC makespan=3
```

La commande de reproduction est :

```sh
/tmp/atlas-semantic-kernel-venv/bin/python experiments/temporal-planning/step3_counterexamples.py
```
