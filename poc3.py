#!/usr/bin/env python3
"""POC 3 jetable: composer des mécanismes clé-valeur fins."""

import itertools
import json
import random
import time
from pathlib import Path


FEATURES = (
    "comparisons", "probes", "sequential_reads", "random_accesses",
    "writes", "capacity_reserved", "allocations",
)

WORKLOADS = {
    "lookup_heavy": {"n": 10_000, "lookup": 95, "walk": 3, "update": 1},
    "walk_heavy": {"n": 10_000, "lookup": 5, "walk": 90, "update": 4},
}

# Coefficients synthétiques, appliqués seulement après le vecteur algorithmique.
PLATFORMS = {
    "compact": {"comparisons": .1, "probes": .2, "sequential_reads": 1.0,
                 "random_accesses": .7, "writes": .5,
                 "capacity_reserved": .05, "allocations": 1.0},
    "cache_rich": {"comparisons": .02, "probes": .02, "sequential_reads": .1,
                   "random_accesses": .2, "writes": .3,
                   "capacity_reserved": .0005, "allocations": .5},
}

MECHANISMS = {
    "lookup": ("sorted_index", "hash_index"),
    "representation": ("dense_elements", "sparse_slots"),
    "walk": ("dense_scan", "slot_scan"),
    "auxiliary": ("none", "dense_view"),
}


def empty_vector():
    return {name: 0 for name in FEATURES}


def make_workload(scenario, seed=7):
    keys = list(range(scenario["n"]))
    random.Random(seed).shuffle(keys)
    operations = []
    cursor = 0
    for operation in ("lookup", "walk", "update"):
        count = scenario[operation] * 10
        operations.extend((operation, key if operation != "walk" else None)
                           for key in keys[cursor:cursor + count])
        cursor += count
    random.Random(seed).shuffle(operations)
    return operations


def valid(combo):
    """Préconditions locales des mécanismes, pas un solveur général."""
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
    return [combo for combo in itertools.product(*MECHANISMS.values()) if valid(combo)]


def capacity(n):
    slots = 1
    while slots < n * 2:
        slots *= 2
    return slots


def sorted_search_cost(n, key, vector):
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


def hash_lookup_cost(capacity_value, key, vector):
    # Les clés 0..n-1 sont placées sans collision, mais le probing est compté.
    vector["probes"] += 1
    vector["comparisons"] += 1
    vector["random_accesses"] += 1


def predicted_vector(combo, scenario, operations):
    """Vecteur algorithmique calculé avant l'exécution de la combinaison."""
    lookup, representation, walk, auxiliary = combo
    n = scenario["n"]
    vector = empty_vector()
    if representation == "dense_elements":
        vector["capacity_reserved"] = n
        vector["allocations"] = 1
    else:
        slots = capacity(n)
        vector["capacity_reserved"] = slots * 2 + (n if auxiliary == "dense_view" else 0)
        vector["allocations"] = 1
        # Construction of the open-addressed table.
        vector["probes"] += n
        vector["comparisons"] += n
        vector["random_accesses"] += n
    if auxiliary == "dense_view":
        vector["allocations"] += 1
    for operation, key in operations:
        if operation in ("lookup", "update"):
            if lookup == "sorted_index":
                sorted_search_cost(n, key, vector)
            else:
                hash_lookup_cost(capacity(n), key, vector)
            if operation == "update":
                vector["writes"] += 1 + (auxiliary == "dense_view")
        else:
            if walk == "dense_scan":
                vector["sequential_reads"] += n
            else:
                vector["sequential_reads"] += capacity(n)
    return vector


def execute(combo, n, operations):
    """Matérialise uniquement les combinaisons générées et instrumente les mêmes champs."""
    lookup, representation, walk, auxiliary = combo
    vector = empty_vector()
    if representation == "dense_elements":
        elements = list(range(n))
        vector["capacity_reserved"] = n
        vector["allocations"] = 1
        slots = None
    else:
        slots = [None] * capacity(n)
        elements = list(range(n)) if auxiliary == "dense_view" else None
        vector["capacity_reserved"] = len(slots) * 2 + (n if elements is not None else 0)
        vector["allocations"] = 1 + (auxiliary == "dense_view")
        for key in range(n):
            index = key % len(slots)
            vector["probes"] += 1
            vector["comparisons"] += 1
            vector["random_accesses"] += 1
            slots[index] = key
    for operation, key in operations:
        if operation in ("lookup", "update"):
            if lookup == "sorted_index":
                sorted_search_cost(n, key, vector)
            else:
                hash_lookup_cost(len(slots), key, vector)
            if operation == "update":
                vector["writes"] += 1 + (auxiliary == "dense_view")
        else:
            if walk == "dense_scan":
                vector["sequential_reads"] += n
                sum(elements)
            else:
                vector["sequential_reads"] += len(slots)
                for key_in_slot in slots:
                    if key_in_slot is not None:
                        pass
    return vector


def cost(vector, platform):
    return sum(vector[name] * platform[name] for name in FEATURES)


def label(combo):
    return "+".join(combo)


def main():
    all_combinations = combinations()
    print("combinaisons admissibles:")
    for combo in all_combinations:
        print(" ", label(combo))
    results = []
    for scenario_name, scenario in WORKLOADS.items():
        operations = make_workload(scenario)
        for platform_name, platform in PLATFORMS.items():
            predicted = {combo: predicted_vector(combo, scenario, operations)
                         for combo in all_combinations}
            selected = min(all_combinations,
                           key=lambda combo: (cost(predicted[combo], platform), label(combo)))
            for combo in all_combinations:
                start = time.perf_counter_ns()
                observed = execute(combo, scenario["n"], operations)
                wall_ns = time.perf_counter_ns() - start
                results.append({"scenario": scenario_name, "platform": platform_name,
                                "combination": label(combo), "selected": combo == selected,
                                "predicted": predicted[combo], "observed": observed,
                                "vector_equal": predicted[combo] == observed,
                                "predicted_cost": cost(predicted[combo], platform),
                                "wall_ns": wall_ns})
            print(f"{scenario_name:12} / {platform_name:10}: choose {label(selected)}")
            for row in results[-len(all_combinations):]:
                print(f"  {row['combination']:62} cost={row['predicted_cost']:10.1f} "
                      f"equal={row['vector_equal']} wall={row['wall_ns']/1e6:.2f} ms")
    Path("poc3_measurements.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
