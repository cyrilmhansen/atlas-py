#!/usr/bin/env python3
"""POC jetable: besoin -> choix explique -> implémentations -> mesure."""

import json
import math
import random
import time
from pathlib import Path


PLATFORMS = {
    # Les budgets sont des unités relatives par élément, pas une promesse
    # d'estimation d'octets. Ils servent uniquement à rendre l'hypothèse testable.
    "compact": {
        "memory_budget": 2.2,
        "random_access_cost": 1.0,
        "hash_access_cost": 1.4,
    },
    "cache_rich": {
        "memory_budget": 5.0,
        "random_access_cost": 3.5,
        "hash_access_cost": 1.0,
    },
}

SCENARIOS = {
    "lookup_heavy": {
        "n": 10_000,
        "load": 1,
        "lookup": 95,
        "walk": 3,
        "update": 1,
    },
    "walk_heavy": {
        "n": 10_000,
        "load": 1,
        "lookup": 5,
        "walk": 90,
        "update": 4,
    },
}


class LinearCollection:
    memory_units = 1.0

    def __init__(self, pairs):
        self.items = list(pairs)
        self.stats = {"comparisons": 0, "probes": 0, "visits": 0, "writes": 0, "allocations": len(self.items)}

    def lookup(self, key):
        for item_key, value in self.items:
            self.stats["comparisons"] += 1
            if item_key == key:
                return value
        raise KeyError(key)

    def walk(self):
        total = 0
        for _, value in self.items:
            self.stats["visits"] += 1
            total += value
        return total

    def update(self, key, value):
        for index, (item_key, _) in enumerate(self.items):
            self.stats["comparisons"] += 1
            if item_key == key:
                self.items[index] = (key, value)
                self.stats["writes"] += 1
                return
        raise KeyError(key)


class SortedCollection:
    memory_units = 2.0

    def __init__(self, pairs):
        self.items = merge_sort(list(pairs))
        self.keys = [key for key, _ in self.items]
        self.stats = {"comparisons": 0, "probes": 0, "visits": 0, "writes": 0, "allocations": len(self.items) * 2}

    def _index(self, key):
        low, high = 0, len(self.keys)
        while low < high:
            index = (low + high) // 2
            self.stats["comparisons"] += 1
            if self.keys[index] < key:
                low = index + 1
            else:
                high = index
        index = low
        self.stats["comparisons"] += 1
        if index == len(self.keys) or self.keys[index] != key:
            raise KeyError(key)
        return index

    def lookup(self, key):
        return self.items[self._index(key)][1]

    def walk(self):
        total = 0
        for _, value in self.items:
            self.stats["visits"] += 1
            total += value
        return total

    def update(self, key, value):
        index = self._index(key)
        self.items[index] = (key, value)
        self.stats["writes"] += 1


class HashCollection:
    memory_units = 4.0

    def __init__(self, pairs):
        capacity = 1
        while capacity < len(pairs) * 2:
            capacity *= 2
        self.keys = [None] * capacity
        self.values = [None] * capacity
        self.stats = {"comparisons": 0, "probes": 0, "visits": 0, "writes": 0, "allocations": capacity * 2}
        for key, value in pairs:
            self._put(key, value)

    def _slot(self, key):
        index = key % len(self.keys)
        while True:
            self.stats["probes"] += 1
            self.stats["comparisons"] += 1
            if self.keys[index] is None or self.keys[index] == key:
                return index
            index = (index + 1) % len(self.keys)

    def _put(self, key, value):
        index = self._slot(key)
        self.keys[index] = key
        self.values[index] = value

    def lookup(self, key):
        return self.values[self._slot(key)]

    def walk(self):
        total = 0
        for key, value in zip(self.keys, self.values):
            self.stats["visits"] += 1
            if key is not None:
                total += value
        return total

    def update(self, key, value):
        index = self._slot(key)
        self.values[index] = value
        self.stats["writes"] += 1


CANDIDATES = {
    "linear": (LinearCollection, 1.0),
    "sorted": (SortedCollection, 2.0),
    "hash": (HashCollection, 4.0),
}


def merge_sort(items):
    """Tri local pour que le chargement ne délègue pas à une primitive C."""
    if len(items) < 2:
        return items
    middle = len(items) // 2
    left = merge_sort(items[:middle])
    right = merge_sort(items[middle:])
    merged = []
    left_i = right_i = 0
    while left_i < len(left) and right_i < len(right):
        if left[left_i][0] <= right[right_i][0]:
            merged.append(left[left_i])
            left_i += 1
        else:
            merged.append(right[right_i])
            right_i += 1
    return merged + left[left_i:] + right[right_i:]


def predicted_cost(candidate, scenario, platform):
    """Modèle volontairement simple, en unités relatives par opération."""
    n = scenario["n"]
    random_cost = platform["random_access_cost"]
    hash_cost = platform["hash_access_cost"]
    if candidate == "linear":
        costs = {"load": n, "lookup": n / 2, "walk": n, "update": n / 2}
    elif candidate == "sorted":
        costs = {
            "load": n * math.log2(n),
            "lookup": math.log2(n) * random_cost,
            "walk": n,
            "update": math.log2(n) * random_cost,
        }
    else:
        costs = {"load": n, "lookup": hash_cost, "walk": n, "update": hash_cost}
    return sum(costs[name] * scenario[name] for name in costs)


def admissible(candidate, scenario, platform):
    return CANDIDATES[candidate][1] <= platform["memory_budget"]


def make_workload(scenario, seed=7):
    n = scenario["n"]
    rng = random.Random(seed)
    keys = list(range(n))
    rng.shuffle(keys)
    # Les fréquences du besoin deviennent une charge de 1 000 opérations.
    # La recherche touche des positions variées et l'ordre est déterministe.
    workload = []
    for operation in ("lookup", "walk", "update"):
        count = scenario[operation] * 10
        for key in keys[len(workload):len(workload) + count]:
            workload.append((operation, key if operation != "walk" else None))
    rng.shuffle(workload)
    return workload


def measure(candidate, pairs, workload):
    implementation = CANDIDATES[candidate][0]
    start = time.perf_counter_ns()
    collection = implementation(pairs)
    load_ns = time.perf_counter_ns() - start
    checksum = 0
    start = time.perf_counter_ns()
    for operation, key in workload:
        if operation == "lookup":
            checksum += collection.lookup(key)
        elif operation == "walk":
            checksum += collection.walk()
        else:
            collection.update(key, key + 1)
    work_ns = time.perf_counter_ns() - start
    instrumented_cost = (
        collection.stats["comparisons"]
        + collection.stats["probes"]
        + collection.stats["visits"]
        + collection.stats["writes"]
        + collection.stats["allocations"]
    )
    return {
        "load_ns": load_ns,
        "work_ns": work_ns,
        "total_ns": load_ns + work_ns,
        "checksum": checksum,
        "instrumented_cost": instrumented_cost,
        "counters": collection.stats,
    }


def run():
    results = []
    for scenario_name, scenario in SCENARIOS.items():
        pairs = [(key, key * 2) for key in range(scenario["n"])]
        workload = make_workload(scenario)
        for platform_name, platform in PLATFORMS.items():
            candidates = [name for name in CANDIDATES if admissible(name, scenario, platform)]
            prediction = {name: predicted_cost(name, scenario, platform) for name in candidates}
            selected = min(candidates, key=lambda name: (prediction[name], name))
            for candidate in candidates:
                measured = measure(candidate, pairs, workload)
                results.append({
                    "scenario": scenario_name,
                    "platform": platform_name,
                    "candidate": candidate,
                    "admissible": True,
                    "predicted_cost": round(prediction[candidate], 2),
                    "selected": candidate == selected,
                    **measured,
                })
            print(f"{scenario_name:12} / {platform_name:10}: choose {selected:6} "
                  f"(admissible={','.join(candidates)})")
            for row in results[-len(candidates):]:
                print(f"  {row['candidate']:6} prediction={row['predicted_cost']:12.1f} "
                      f"counters={row['instrumented_cost']:10} "
                      f"wall={row['total_ns']/1e6:8.2f} ms")

    Path("measurements.json").write_text(json.dumps(results, indent=2) + "\n")
    print("\nmeasurements.json écrit; les temps sont indicatifs et la prédiction est relative.")


if __name__ == "__main__":
    run()
