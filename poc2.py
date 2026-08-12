#!/usr/bin/env python3
"""POC 2: vecteur algorithmique, puis coût selon un profil de plateforme."""

import json
import random
import time
from pathlib import Path


FEATURES = (
    "comparisons", "probes", "slots_visited", "sequential_reads",
    "random_accesses", "writes", "capacity_reserved", "allocations",
)

WORKLOADS = {
    "lookup_heavy": {"n": 10_000, "lookup": 95, "walk": 3, "update": 1},
    "walk_heavy": {"n": 10_000, "lookup": 5, "walk": 90, "update": 4},
}

# Profils synthétiques : aucun ne prétend modéliser une machine réelle.
PLATFORMS = {
    "compact": {"sequential_reads": 1.0, "random_accesses": 2.0,
                 "comparisons": .2, "probes": .2, "writes": .5,
                 "capacity_reserved": .05, "allocations": 1.0},
    "cache_rich": {"sequential_reads": .001, "random_accesses": .4,
                   "comparisons": .2, "probes": .2, "writes": .5,
                   "capacity_reserved": .001, "allocations": 1.0},
}


def empty_features():
    return {name: 0 for name in FEATURES}


def workload(scenario, seed=7):
    keys = list(range(scenario["n"]))
    random.Random(seed).shuffle(keys)
    result = []
    cursor = 0
    for operation in ("lookup", "walk", "update"):
        for key in keys[cursor:cursor + scenario[operation] * 10]:
            result.append((operation, key if operation != "walk" else None))
        cursor += scenario[operation] * 10
    random.Random(seed).shuffle(result)
    return result


def hash_slot(key, keys):
    index = key % len(keys)
    while keys[index] is not None and keys[index] != key:
        index = (index + 1) % len(keys)
    return index


def predicted_vector(candidate, scenario, operations):
    """Calcul exactement les compteurs attendus, sans exécuter le candidat."""
    n = scenario["n"]
    vector = empty_features()
    if candidate == "sorted":
        vector["capacity_reserved"] = n * 2       # items + index des clés
        vector["allocations"] = 1                 # construction logique
        vector["sequential_reads"] = sum(op == "walk" for op, _ in operations) * n
        keys = list(range(n))
        for operation, key in operations:
            if operation in ("lookup", "update"):
                low, high = 0, n
                while low < high:
                    index = (low + high) // 2
                    vector["comparisons"] += 1
                    vector["random_accesses"] += 1
                    if keys[index] < key:
                        low = index + 1
                    else:
                        high = index
                vector["comparisons"] += 1
                vector["random_accesses"] += 1
                if operation == "update":
                    vector["writes"] += 1
    else:
        capacity = 1
        while capacity < n * 2:
            capacity *= 2
        vector["capacity_reserved"] = capacity * 2  # deux tableaux
        vector["allocations"] = 1
        keys = [None] * capacity
        for key in range(n):
            index = hash_slot(key, keys)
            keys[index] = key
        for operation, key in operations:
            if operation == "walk":
                vector["slots_visited"] += capacity
                vector["sequential_reads"] += capacity
            else:
                index = key % capacity
                while True:
                    vector["probes"] += 1
                    vector["comparisons"] += 1
                    vector["random_accesses"] += 1
                    if keys[index] == key:
                        break
                    index = (index + 1) % capacity
                if operation == "update":
                    vector["writes"] += 1
    return vector


class Sorted:
    def __init__(self, n):
        self.items = list(range(n))
        self.stats = empty_features()
        self.stats["capacity_reserved"] = n * 2
        self.stats["allocations"] = 1

    def index(self, key):
        low, high = 0, len(self.items)
        while low < high:
            index = (low + high) // 2
            self.stats["comparisons"] += 1
            self.stats["random_accesses"] += 1
            if self.items[index] < key:
                low = index + 1
            else:
                high = index
        self.stats["comparisons"] += 1
        self.stats["random_accesses"] += 1
        return low

    def run(self, operations):
        for operation, key in operations:
            if operation == "walk":
                self.stats["sequential_reads"] += len(self.items)
                sum(self.items)
            else:
                self.index(key)
                if operation == "update":
                    self.stats["writes"] += 1


class Hash:
    def __init__(self, n):
        capacity = 1
        while capacity < n * 2:
            capacity *= 2
        self.keys = [None] * capacity
        self.stats = empty_features()
        self.stats["capacity_reserved"] = capacity * 2
        self.stats["allocations"] = 1
        for key in range(n):
            index = hash_slot(key, self.keys)
            self.keys[index] = key

    def slot(self, key):
        index = key % len(self.keys)
        while True:
            self.stats["probes"] += 1
            self.stats["comparisons"] += 1
            self.stats["random_accesses"] += 1
            if self.keys[index] == key:
                return index
            index = (index + 1) % len(self.keys)

    def run(self, operations):
        for operation, key in operations:
            if operation == "walk":
                self.stats["slots_visited"] += len(self.keys)
                self.stats["sequential_reads"] += len(self.keys)
            else:
                self.slot(key)
                if operation == "update":
                    self.stats["writes"] += 1


def cost(vector, profile):
    return sum(vector[name] * profile[name] for name in profile)


def main():
    results = []
    for scenario_name, scenario in WORKLOADS.items():
        operations = workload(scenario)
        for platform_name, profile in PLATFORMS.items():
            predictions = {name: predicted_vector(name, scenario, operations)
                           for name in ("sorted", "hash")}
            selected = min(predictions, key=lambda name: (cost(predictions[name], profile), name))
            for candidate in predictions:
                start = time.perf_counter_ns()
                implementation = Sorted(scenario["n"]) if candidate == "sorted" else Hash(scenario["n"])
                implementation.run(operations)
                wall_ns = time.perf_counter_ns() - start
                observed = implementation.stats
                results.append({"scenario": scenario_name, "platform": platform_name,
                                "candidate": candidate, "selected": candidate == selected,
                                "predicted": predictions[candidate], "observed": observed,
                                "vector_equal": predictions[candidate] == observed,
                                "predicted_cost": cost(predictions[candidate], profile),
                                "wall_ns": wall_ns})
            print(f"{scenario_name:12} / {platform_name:10}: choose {selected}")
            for candidate in predictions:
                row = results[-2 + list(predictions).index(candidate)]
                print(f"  {candidate:6} cost={row['predicted_cost']:10.1f} "
                      f"vector_equal={row['vector_equal']} wall={row['wall_ns']/1e6:.2f} ms")
    Path("poc2_measurements.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
