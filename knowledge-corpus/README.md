# Premier corpus réel Atlas — structures associatives

Ce sous-projet est le premier corpus concret de la branche
`develop/knowledge-corpus`. Il ne constitue ni une ontologie générale ni un
benchmark. Il conserve 55 assertions atomiques sur des séquences, structures
associatives et opérations de recherche, avec leur provenance.

## Format

`associative-search.json` contient trois collections :

- `sources` : identifiant stable, titre, URL et locator consultable ;
- `descriptions` : identifiants nominaux des intentions, opérations,
  représentations et structures ;
- `assertions` : relation ou propriété atomique, statut épistémique, portée,
  hypothèses et provenance.

Une assertion utilise `subject`, `predicate` et au moins l'un de `object` ou
`value`. `object` est une référence nominale résolue dans `descriptions` ;
`value` est une qualification littérale de la relation ou de la propriété.
Les deux peuvent coexister : par exemple un objet décrit la propriété visée et
une valeur décrit sa borne ou son comportement dans la portée déclarée.
La présence de `source_id`, `locator` et d'une brève note d'évidence rend la
provenance inspectable sans confondre la source avec une garantie de vérité.
Une provenance directe a `kind: "source"` par défaut. Une provenance dérivée
porte `kind: "derived"` et `basis`, une liste d'identifiants d'assertions
existantes dont elle dépend. Ces références forment un graphe auditable ; le
validateur vérifie leur résolution et l'absence de cycles.

Les complexités sont conservées comme propriétés textuelles bornées par le
contexte de la source ; elles ne sont pas converties en lois universelles.

## Vérification et inspection

```sh
python3 knowledge-corpus/validate.py
python3 knowledge-corpus/inspect.py id a026
python3 knowledge-corpus/inspect.py predicate requires
python3 knowledge-corpus/inspect.py subject algorithm.binary_search
python3 knowledge-corpus/inspect.py object representation.sorted_representation
python3 knowledge-corpus/inspect.py source sqlite_queryplanner
python3 knowledge-corpus/inspect.py status bound
```

Le validateur vérifie la structure, l'unicité des identifiants, les références
résolues, les champs requis, les statuts et le graphe de provenance dérivée. Il
ne prouve pas la vérité sémantique des assertions.

Les prédicats utilisés ici ont des sens locaux stables : `realizes` relie une
réalisation à un contrat d'intention, `provides` exprime une capacité
opérationnelle, `requires` une précondition, `supports_strategy` une stratégie
de mise en œuvre, `satisfies` une requête ou propriété demandée, `uses` une
dépendance d'exécution, `produces` un résultat, `preserves` une propriété
conservée et `has_property` une propriété qualifiée par `value`. Les autres
prédicats du corpus restent des relations littérales de même niveau ; aucune
liste fermée n'est imposée par le validateur.

`scope` décrit le domaine de validité de l'assertion. Il ne remplace ni la
provenance documentaire ni l'identité du contrat.

Pour le sous-graphe SQLite, `indexes(index, key)` associe explicitement une
occurrence d'index à une colonne ou clé nominale et `searches_by(lookup, key)`
associe une occurrence de recherche à cette même identité. La règle locale de
compatibilité exige aussi que la recherche requière cet index. Une composition
`index_lookup` n'est donc applicable que lorsque les deux faits désignent la
même clé ; un index sur `data.column_x` ne satisfait pas une recherche sur
`data.column_y`. Le cas concret courant est représenté par
`representation.ordered_index_x` et `operation.index_lookup_x`.

## Sources retenues

- NIST Dictionary of Algorithms and Data Structures : array, binary search,
  hash table, hash function, AVL tree, red-black tree et trie ;
- Python 3.14 documentation : module `bisect` ;
- SQLite Query Planning et Query Optimizer Overview.

Les dates d'accès et locators sont stockés dans le corpus. Le statut Atlas
reste distinct de la provenance : `exact` signifie exact dans la portée
déclarée, tandis que la provenance indique ce que la source permet de
justifier. `bound` et `estimate` restent distincts et les hypothèses de
portée sont conservées explicitement.

## Bilan de collecte

Le format minimal a suffi pour représenter les réalisations, requirements,
productions, propriétés, capacités et des avertissements distincts sur l'usage
concurrent et la mutation concurrente, ainsi que quelques portées non triviales.
Les champs réellement nécessaires sont l'identité
nominale, la relation ou propriété, la provenance, le statut, les hypothèses
et la portée. Les champs temporels et les mesures physiques ne sont pas requis
par ce premier corpus.

La provenance reste raisonnable lorsqu'elle pointe vers un locator stable,
mais les descriptions SQLite montrent déjà qu'une même affirmation peut
dépendre d'une portée d'exécution et d'une plateforme documentaire. La
granularité atomique est exploitable pour ce corpus ; sa maintenance à grande
échelle et la validation de la sémantique restent ouvertes.
