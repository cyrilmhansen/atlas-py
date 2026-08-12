#!/usr/bin/env python3
"""POC 4 jetable: effets d'interaction entre table sparse et vue dense."""

import json
import random
import time
from pathlib import Path


FEATURES = (
    "comparisons", "probes", "sequential_reads", "random_accesses",
    "slots_visited", "writes", "auxiliary_writes",
    "capacity_reserved", "allocations",
)

WORKLOADS = {
    "lookup_heavy": {"n": 10_000, "lookup": 800, "walk": 20,
                     "update": 20, "insert": 20},
    "walk_heavy": {"n": 10_000, "lookup": 100, "walk": 100,
                   "update": 20, "insert": 20},
    "update_heavy": {"n": 10_000, "lookup": 50, "walk": 10,
                      "update": 400, "insert": 200},
}

# Profils synthétiques : ils pondèrent un vecteur, sans représenter une machine.
PLATFORMS = {
    "compact": {"comparisons": .1, "probes": .3, "sequential_reads": 1.0,
                 "random_accesses": .6, "slots_visited": 1.0,
                 "writes": .6, "auxiliary_writes": .8,
                 "capacity_reserved": .05, "allocations": 1.0},
    "cache_rich": {"comparisons": .05, "probes": .1, "sequential_reads": .1,
                    "random_accesses": .2, "slots_visited": .4,
                    "writes": .3, "auxiliary_writes": .2,
                    "capacity_reserved": .001, "allocations": .5},
}

MECHANISMS = {
    "lookup": ("sorted_index", "hash_index"),
    "representation": ("dense_elements", "sparse_slots"),
    "walk": ("dense_scan", "slot_scan"),
    "auxiliary": ("none", "dense_view"),
}


def empty_vector():
    return {name: 0 for name in FEATURES}


def make_workload(scenario, seed=11):
    """Ordre fixe : les parcours ont lieu avant les insertions."""
    rng = random.Random(seed)
    existing = list(range(scenario["n"]))
    rng.shuffle(existing)
    operations = []
    cursor = 0
    for operation in ("lookup", "walk", "update"):
        for key in existing[cursor:cursor + scenario[operation]]:
            operations.append((operation, key if operation != "walk" else None))
        cursor += scenario[operation]
    for offset in range(scenario["insert"]):
        operations.append(("insert", scenario["n"] + offset))
    return operations


def valid(combo):
    lookup, representation, walk, auxiliary = combo
    if lookup == "sorted_index" and representation != "dense_elements":
        return False
    if lookup == "hash_index" and representation != "sparse_slots":
        return False
    if walk == "slot_scan" and representation != "sparse_slots":
        return False
    if walk == "dense_scan" and representation == "sparse_slots" and auxiliary != "dense_view":
        return False
    if representation == "dense_elements" and auxiliary != "none":
        return False
    if walk == "slot_scan" and auxiliary != "none":
        return False
    return True


def combinations():
    return [combo for combo in __import__("itertools").product(*MECHANISMS.values()) if valid(combo)]


def slot_capacity(size):
    slots = 1
    while slots < size * 2:
        slots *= 2
    return slots


def sorted_lookup(n, key, vector):
    low, high = 0, n
    while low < high:
        index = (low + high) // 2
        vector["comparisons"] += 1
        vector["random_accesses"] += 1
        if index < key:
            low = index + 1
        else:
            high = index
    vector["comparisons"] += 1
    vector["random_accesses"] += 1


def hash_probe(vector):
    vector["probes"] += 1
    vector["comparisons"] += 1
    vector["random_accesses"] += 1


def predicted_vector(combo, scenario, operations):
    """Dérive les effets de l'interaction dense_view + sparse_slots localement."""
    lookup, representation, walk, auxiliary = combo
    n = scenario["n"]
    inserts = scenario["insert"]
    vector = empty_vector()
    if representation == "dense_elements":
        vector["capacity_reserved"] = n + inserts
        vector["allocations"] = 1
    else:
        slots = slot_capacity(n + inserts)
        vector["capacity_reserved"] = slots * 2
        vector["allocations"] = 1
        if auxiliary == "dense_view":
            # Interaction: sparse table + dense view, pas une addition aveugle.
            vector["capacity_reserved"] += n + inserts
            vector["allocations"] += 1
        for _ in range(n):
            hash_probe(vector)
    for operation, key in operations:
        if operation in ("lookup", "update"):
            if lookup == "sorted_index":
                sorted_lookup(n, key, vector)
            else:
                hash_probe(vector)
            if operation == "update":
                vector["writes"] += 1
                if auxiliary == "dense_view":
                    vector["writes"] += 1
                    vector["auxiliary_writes"] += 1
        elif operation == "insert":
            if lookup == "sorted_index":
                vector["writes"] += 1
            else:
                hash_probe(vector)
                vector["writes"] += 1
                if auxiliary == "dense_view":
                    vector["writes"] += 1
                    vector["auxiliary_writes"] += 1
        else:
            if walk == "dense_scan":
                vector["sequential_reads"] += n
            else:
                vector["sequential_reads"] += slot_capacity(n + inserts)
                vector["slots_visited"] += slot_capacity(n + inserts)
    return vector


def execute(combo, scenario, operations):
    """Instrumentation indépendante du calcul ci-dessus."""
    lookup, representation, walk, auxiliary = combo
    n = scenario["n"]
    inserts = scenario["insert"]
    vector = empty_vector()
    if representation == "dense_elements":
        elements = list(range(n))
        slots = None
        vector["capacity_reserved"] = n + inserts
        vector["allocations"] = 1
    else:
        slots = [None] * slot_capacity(n + inserts)
        elements = list(range(n)) if auxiliary == "dense_view" else None
        vector["capacity_reserved"] = len(slots) * 2
        vector["allocations"] = 1
        if elements is not None:
            vector["capacity_reserved"] += n + inserts
            vector["allocations"] += 1
        for key in range(n):
            hash_probe(vector)
            slots[key % len(slots)] = key
    for operation, key in operations:
        if operation in ("lookup", "update"):
            if lookup == "sorted_index":
                sorted_lookup(n, key, vector)
            else:
                hash_probe(vector)
            if operation == "update":
                vector["writes"] += 1
                if auxiliary == "dense_view":
                    vector["writes"] += 1
                    vector["auxiliary_writes"] += 1
        elif operation == "insert":
            if lookup == "sorted_index":
                elements.append(key)
                vector["writes"] += 1
            else:
                hash_probe(vector)
                slots[key % len(slots)] = key
                vector["writes"] += 1
                if auxiliary == "dense_view":
                    elements.append(key)
                    vector["writes"] += 1
                    vector["auxiliary_writes"] += 1
        elif walk == "dense_scan":
            vector["sequential_reads"] += n
            sum(elements)
        else:
            vector["sequential_reads"] += len(slots)
            vector["slots_visited"] += len(slots)
            for key_in_slot in slots:
                if key_in_slot is not None:
                    pass
    return vector


def cost(vector, platform):
    return sum(vector[name] * platform[name] for name in FEATURES)


def label(combo):
    return "+".join(combo)


def main():
    candidates = combinations()
    print("combinaisons admissibles:")
    for combo in candidates:
        print(" ", label(combo))
    results = []
    for scenario_name, scenario in WORKLOADS.items():
        operations = make_workload(scenario)
        for platform_name, platform in PLATFORMS.items():
            predicted = {combo: predicted_vector(combo, scenario, operations)
                         for combo in candidates}
            selected = min(candidates,
                           key=lambda combo: (cost(predicted[combo], platform), label(combo)))
            block = []
            for combo in candidates:
                start = time.perf_counter_ns()
                observed = execute(combo, scenario, operations)
                wall_ns = time.perf_counter_ns() - start
                row = {"scenario": scenario_name, "platform": platform_name,
                       "combination": label(combo), "selected": combo == selected,
                       "predicted": predicted[combo], "observed": observed,
                       "vector_equal": predicted[combo] == observed,
                       "predicted_cost": cost(predicted[combo], platform),
                       "wall_ns": wall_ns}
                results.append(row)
                block.append(row)
            print(f"{scenario_name:13} / {platform_name:10}: choose {label(selected)}")
            for row in block:
                print(f"  {row['combination']:62} cost={row['predicted_cost']:10.1f} "
                      f"equal={row['vector_equal']} wall={row['wall_ns']/1e6:.2f} ms")
    Path("poc4_measurements.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
