#!/usr/bin/env python3
"""POC 5 jetable: analyse déclarative séparée du code instrumenté."""

import json
import math
import random
import time
from pathlib import Path


FEATURES = (
    "comparisons", "probes", "sequential_reads", "random_accesses",
    "slots_visited", "base_writes", "auxiliary_writes",
    "reserved_cells", "allocations",
)

# Descriptions déclaratives : aucune fonction d'implémentation ou de mesure.
DESCRIPTIONS = {
    "sorted+binary_lookup+dense_walk": {
        "storage": "dense_sorted",
        "lookup": "binary",
        "walk": "dense",
        "auxiliary": "none",
        "capacity": "final_count",
        "maintenance": "append_above_max",
    },
    "hash+linear_probe+slot_scan": {
        "storage": "open_addressed",
        "lookup": "linear_probe",
        "walk": "slots",
        "auxiliary": "none",
        "capacity": "power_of_two_below_half_full",
        "maintenance": "primary_only",
    },
    "hash+linear_probe+dense_view": {
        "storage": "open_addressed",
        "lookup": "linear_probe",
        "walk": "dense",
        "auxiliary": "dense_view_with_slot_position",
        "capacity": "power_of_two_below_half_full",
        "maintenance": "mirror_values",
    },
}

WORKLOADS = {
    "lookup_heavy": {"initial_n": 512, "lookup": 400, "walk": 5,
                     "update": 20, "insert": 20},
    "walk_heavy": {"initial_n": 512, "lookup": 50, "walk": 100,
                   "update": 20, "insert": 20},
    "update_heavy": {"initial_n": 512, "lookup": 50, "walk": 10,
                     "update": 200, "insert": 100},
}

# Modèles synthétiques appliqués après la comparaison dimensionnelle.
PLATFORMS = {
    "compact": {"comparisons": .1, "probes": .2, "sequential_reads": 1.0,
                "random_accesses": .5, "slots_visited": 1.0,
                "base_writes": .5, "auxiliary_writes": .8,
                "reserved_cells": .05, "allocations": 1.0},
    "cache_rich": {"comparisons": .05, "probes": .08, "sequential_reads": .1,
                   "random_accesses": .2, "slots_visited": .3,
                   "base_writes": .3, "auxiliary_writes": .2,
                   "reserved_cells": .001, "allocations": .5},
}


def prediction(kind, value, reason):
    return {"kind": kind, "value": value, "reason": reason}


def analytical_capacity(final_count):
    result = 1
    while result < final_count * 2:
        result *= 2
    return result


def analyze(description, workload):
    """Analyse uniquement les propriétés déclarées et le résumé du workload."""
    n = workload["initial_n"]
    final_n = n + workload["insert"]
    accesses = workload["lookup"] + workload["update"]
    result = {}

    if description["storage"] == "dense_sorted":
        comparison_bound = accesses * (math.ceil(math.log2(n)) + 1)
        result["comparisons"] = prediction(
            "upper_bound", comparison_bound, "borne de recherche dichotomique")
        result["probes"] = prediction("exact", 0, "aucun probing")
        result["random_accesses"] = prediction(
            "upper_bound", comparison_bound, "un accès par comparaison au plus")
        result["reserved_cells"] = prediction(
            "exact", final_n * 2, "tableaux préalloués de clés et valeurs")
        result["allocations"] = prediction("exact", 2, "deux tableaux denses")
        build_writes = n * 2
    else:
        capacity = analytical_capacity(final_n)
        alpha = final_n / capacity
        # Estimation classique sous hypothèse de hachage uniforme. L'analyseur
        # ne voit ni les clés concrètes ni la fonction exécutée.
        successful = .5 * (1 + 1 / (1 - alpha))
        unsuccessful = .5 * (1 + 1 / ((1 - alpha) ** 2))
        estimated_probes = ((n + workload["insert"]) * unsuccessful
                            + accesses * successful)
        result["probes"] = prediction(
            "estimate", round(estimated_probes, 2),
            "hachage uniforme, linear probing, alpha final")
        result["comparisons"] = prediction(
            "estimate", round(estimated_probes, 2), "une comparaison par probe")
        result["random_accesses"] = prediction(
            "estimate", round(estimated_probes, 2), "un accès de slot par probe")
        primary_cells = capacity * 2
        auxiliary_cells = capacity + final_n if description["auxiliary"] != "none" else 0
        result["reserved_cells"] = prediction(
            "exact", primary_cells + auxiliary_cells,
            "clés+valeurs, plus positions et vue si présentes")
        result["allocations"] = prediction(
            "exact", 4 if description["auxiliary"] != "none" else 2,
            "nombre de tableaux déclarés")
        build_writes = n * 2

    if description["walk"] == "dense":
        result["sequential_reads"] = prediction(
            "exact", workload["walk"] * final_n,
            "les parcours suivent les insertions")
        result["slots_visited"] = prediction("exact", 0, "pas de scan sparse")
    else:
        capacity = analytical_capacity(final_n)
        result["sequential_reads"] = prediction("exact", 0, "scan de slots séparé")
        result["slots_visited"] = prediction(
            "exact", workload["walk"] * capacity, "tous les slots sont parcourus")

    result["base_writes"] = prediction(
        "exact", build_writes + workload["update"] + workload["insert"] * 2,
        "construction, updates de valeur, insertions clé+valeur")
    auxiliary_writes = 0
    if description["auxiliary"] != "none":
        auxiliary_writes = n * 2 + workload["update"] + workload["insert"] * 2
    result["auxiliary_writes"] = prediction(
        "exact", auxiliary_writes, "maintenance déclarée de la vue et des positions")
    return result


def concrete_workload(spec, seed=23):
    """Jeu exécuté; ses clés volontairement groupées ne sont pas vues par analyze()."""
    initial_keys = [index * 64 for index in range(spec["initial_n"])]
    rng = random.Random(seed)
    shuffled = initial_keys[:]
    rng.shuffle(shuffled)
    operations = []
    operations.extend(("lookup", key) for key in shuffled[:spec["lookup"]])
    operations.extend(("update", key) for key in shuffled[-spec["update"]:])
    operations.extend(("insert", (spec["initial_n"] + offset) * 64)
                      for offset in range(spec["insert"]))
    operations.extend(("walk", None) for _ in range(spec["walk"]))
    return initial_keys, operations


class SortedImplementation:
    """Code exécuté; aucune fonction analytique n'est appelée."""

    def __init__(self, initial_keys, insert_count):
        limit = len(initial_keys) + insert_count
        self.keys = [None] * limit
        self.values = [None] * limit
        self.size = len(initial_keys)
        self.stats = {name: 0 for name in FEATURES}
        self.stats["reserved_cells"] = len(self.keys) + len(self.values)
        self.stats["allocations"] = 2
        for index, key in enumerate(initial_keys):
            self.keys[index] = key
            self.values[index] = key * 2
            self.stats["base_writes"] += 2

    def find(self, key):
        low, high = 0, self.size
        while low < high:
            middle = (low + high) // 2
            self.stats["random_accesses"] += 1
            self.stats["comparisons"] += 1
            if self.keys[middle] < key:
                low = middle + 1
            else:
                high = middle
        self.stats["random_accesses"] += 1
        self.stats["comparisons"] += 1
        return low

    def run(self, operations):
        checksum = 0
        for operation, key in operations:
            if operation == "walk":
                for index in range(self.size):
                    self.stats["sequential_reads"] += 1
                    checksum += self.values[index]
            elif operation == "insert":
                self.keys[self.size] = key
                self.values[self.size] = key * 2
                self.size += 1
                self.stats["base_writes"] += 2
            else:
                index = self.find(key)
                if operation == "lookup":
                    checksum += self.values[index]
                else:
                    self.values[index] += 1
                    self.stats["base_writes"] += 1
        return checksum


class SlotScanImplementation:
    """Table concrète à adressage ouvert, avec son propre calcul de capacité."""

    def __init__(self, initial_keys, insert_count):
        wanted = (len(initial_keys) + insert_count) * 2
        slots = 1
        while slots < wanted:
            slots <<= 1
        self.keys = [None] * slots
        self.values = [None] * slots
        self.stats = {name: 0 for name in FEATURES}
        self.stats["reserved_cells"] = len(self.keys) + len(self.values)
        self.stats["allocations"] = 2
        for key in initial_keys:
            index = self.locate(key)
            self.keys[index] = key
            self.values[index] = key * 2
            self.stats["base_writes"] += 2

    def locate(self, key):
        index = key % len(self.keys)
        while True:
            self.stats["probes"] += 1
            self.stats["comparisons"] += 1
            self.stats["random_accesses"] += 1
            if self.keys[index] is None or self.keys[index] == key:
                return index
            index = (index + 1) % len(self.keys)

    def run(self, operations):
        checksum = 0
        for operation, key in operations:
            if operation == "walk":
                for index in range(len(self.keys)):
                    self.stats["slots_visited"] += 1
                    if self.keys[index] is not None:
                        checksum += self.values[index]
            else:
                index = self.locate(key)
                if operation == "lookup":
                    checksum += self.values[index]
                elif operation == "update":
                    self.values[index] += 1
                    self.stats["base_writes"] += 1
                else:
                    self.keys[index] = key
                    self.values[index] = key * 2
                    self.stats["base_writes"] += 2
        return checksum


class DenseViewImplementation:
    """Table et vue dense concrètes, instrumentées sans réutiliser analyze()."""

    def __init__(self, initial_keys, insert_count):
        maximum = len(initial_keys) + insert_count
        slot_count = 1
        while slot_count < maximum * 2:
            slot_count *= 2
        self.keys = [None] * slot_count
        self.values = [None] * slot_count
        self.positions = [None] * slot_count
        self.dense_values = [None] * maximum
        self.size = 0
        self.stats = {name: 0 for name in FEATURES}
        self.stats["reserved_cells"] = (len(self.keys) + len(self.values)
                                        + len(self.positions) + len(self.dense_values))
        self.stats["allocations"] = 4
        for key in initial_keys:
            index = self.locate(key)
            self.keys[index] = key
            self.values[index] = key * 2
            self.stats["base_writes"] += 2
            self.positions[index] = self.size
            self.dense_values[self.size] = key * 2
            self.stats["auxiliary_writes"] += 2
            self.size += 1

    def locate(self, key):
        index = key % len(self.keys)
        while True:
            self.stats["probes"] += 1
            self.stats["comparisons"] += 1
            self.stats["random_accesses"] += 1
            if self.keys[index] is None or self.keys[index] == key:
                return index
            index = (index + 1) % len(self.keys)

    def run(self, operations):
        checksum = 0
        for operation, key in operations:
            if operation == "walk":
                for index in range(self.size):
                    self.stats["sequential_reads"] += 1
                    checksum += self.dense_values[index]
            else:
                slot = self.locate(key)
                if operation == "lookup":
                    checksum += self.values[slot]
                elif operation == "update":
                    self.values[slot] += 1
                    self.stats["base_writes"] += 1
                    dense_index = self.positions[slot]
                    self.dense_values[dense_index] += 1
                    self.stats["auxiliary_writes"] += 1
                else:
                    value = key * 2
                    self.keys[slot] = key
                    self.values[slot] = value
                    self.stats["base_writes"] += 2
                    self.positions[slot] = self.size
                    self.dense_values[self.size] = value
                    self.stats["auxiliary_writes"] += 2
                    self.size += 1
        return checksum


IMPLEMENTATIONS = {
    "sorted+binary_lookup+dense_walk": SortedImplementation,
    "hash+linear_probe+slot_scan": SlotScanImplementation,
    "hash+linear_probe+dense_view": DenseViewImplementation,
}


def compare(predicted, observed):
    comparison = {}
    for name in FEATURES:
        item = predicted[name]
        expected = item["value"]
        actual = observed[name]
        if item["kind"] == "exact":
            status = "equal" if expected == actual else "mismatch"
        elif item["kind"] == "upper_bound":
            status = "within_bound" if actual <= expected else "bound_violated"
        else:
            status = "estimated"
        comparison[name] = {
            "kind": item["kind"], "predicted": expected, "observed": actual,
            "difference": round(actual - expected, 2), "status": status,
        }
    return comparison


def platform_cost(vector, profile):
    return sum(vector[name] * profile[name] for name in FEATURES)


def main():
    results = []
    for workload_name, spec in WORKLOADS.items():
        initial_keys, operations = concrete_workload(spec)
        print(workload_name)
        block = []
        for name, description in DESCRIPTIONS.items():
            predicted = analyze(description, spec)
            start = time.perf_counter_ns()
            implementation = IMPLEMENTATIONS[name](initial_keys, spec["insert"])
            checksum = implementation.run(operations)
            wall_ns = time.perf_counter_ns() - start
            observed = implementation.stats
            dimensions = compare(predicted, observed)
            predicted_values = {feature: predicted[feature]["value"] for feature in FEATURES}
            platform = {
                platform_name: {
                    "predicted_cost": platform_cost(predicted_values, profile),
                    "observed_cost": platform_cost(observed, profile),
                }
                for platform_name, profile in PLATFORMS.items()
            }
            result = {
                "workload": workload_name, "solution": name,
                "description": description, "predicted": predicted,
                "observed": observed, "comparison": dimensions,
                "platform_costs": platform, "checksum": checksum,
                "wall_ns": wall_ns,
            }
            results.append(result)
            block.append(result)
            deviations = [f"{feature}:{item['status']}({item['difference']:+.2f})"
                          for feature, item in dimensions.items()
                          if item["status"] in ("mismatch", "bound_violated", "estimated")
                          and item["difference"] != 0]
            print(f"  {name:38} deviations={','.join(deviations) or 'none'} "
                  f"wall={wall_ns / 1e6:.2f} ms")
            if description["storage"] == "open_addressed":
                print(f"    probes estimate={predicted['probes']['value']:.2f} "
                      f"observed={observed['probes']}")
        for platform_name in PLATFORMS:
            predicted_choice = min(
                block, key=lambda row: (row["platform_costs"][platform_name]["predicted_cost"],
                                        row["solution"]))
            observed_choice = min(
                block, key=lambda row: (row["platform_costs"][platform_name]["observed_cost"],
                                        row["solution"]))
            for row in block:
                costs = row["platform_costs"][platform_name]
                costs["predicted_selected"] = row is predicted_choice
                costs["observed_selected"] = row is observed_choice
            print(f"    {platform_name}: predicted={predicted_choice['solution']} "
                  f"observed-vector={observed_choice['solution']}")
    Path("poc5_measurements.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
