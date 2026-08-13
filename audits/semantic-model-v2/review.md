# Review de l’audit Laguna — Semantic Model v2

L’audit Laguna est conservé verbatim dans `laguna.md`.

Sa conclusion générale est retenue : l’architecture en proto-ontologies locales et contexte d’inférence reste cohérente, mais plusieurs formulations du document de conception doivent éviter de transformer des distinctions nécessaires en entités universelles.

## Arbitrages

1. **`counts_occurrences_of` reste une distinction forcée.**  
   L’absence de cette relation dans v1 est précisément ce qui permettrait une composition erronée comme `repeat(reuse_count, production)`. En revanche, son implémentation comme entité ou ontologie d’événements n’est pas forcée : un identifiant local d’opération suffit.

2. **Protocole et exécution : distinction informationnelle, pas entités imposées.**  
   Le contexte expérimental doit distinguer programme, protocole, exécution et artefact lorsque nécessaire. Cela ne requiert pas aujourd’hui des classes autonomes ; une provenance structurée peut suffire.

3. **`reuse_count`, `workload` et `memory_constraint` ne doivent pas être rattachés artificiellement au domaine algorithmique.**  
   Ils relèvent actuellement du besoin, du scénario ou du cycle de vie.

4. **Objet logique / représentation / instance reste la distinction la plus solide.**  
   v1.1 justifie cette séparation. Un hash est un moyen de preuve adapté au cas QuickDraw, pas un attribut universel obligatoire des instances.

5. **`QuantityKind.family` ne doit jamais constituer une règle de compatibilité sémantique.**  
   `count`, `duration`, etc. sont des classifications grossières ; la validité d’une composition dépend aussi de ce que les quantités qualifient ou comptent.

## Clarification de méthode

Les statuts **forcé / probable / candidat / repoussé** portent sur la nécessité de préserver une distinction sémantique. Ils ne prescrivent ni une classe, ni une entité autonome, ni une relation persistée, ni une appartenance au noyau transversal.

## Suite

Après intégration de ces corrections dans `semantic-model-v2-design.md`, ne pas relancer un nouvel audit abstrait. Tester l’architecture par une première instanciation concrète des domaines et par un contexte d’inférence transversal.
