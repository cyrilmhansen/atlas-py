#!/usr/bin/env python3
"""POC 6 jetable: hypothèses, incertitude et acquisition sélective."""

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

SOLUTIONS = {
    "sorted+binary_lookup+dense_walk": {
        "storage": "dense_sorted", "lookup": "binary", "walk": "dense",
        "auxiliary": "none", "maintenance": "append_above_max",
    },
    "hash+linear_probe+slot_scan": {
        "storage": "open_addressed", "lookup": "linear_probe", "walk": "slots",
        "auxiliary": "none", "maintenance": "primary_only",
    },
    "hash+linear_probe+dense_view": {
        "storage": "open_addressed", "lookup": "linear_probe", "walk": "dense",
        "auxiliary": "dense_view", "maintenance": "mirror_values",
    },
}

WORKLOADS = {
    "lookup_heavy": {"initial_n": 512, "lookup": 400, "walk": 5,
                     "update": 20, "insert": 20},
    "walk_heavy": {"initial_n": 512, "lookup": 50, "walk": 100,
                   "update": 20, "insert": 20},
}

# Profil synthétique, sans prétention de calibration physique.
PLATFORM = {
    "comparisons": .05, "probes": .08, "sequential_reads": .1,
    "random_accesses": .2, "slots_visited": .3,
    "base_writes": .3, "auxiliary_writes": .2,
    "reserved_cells": .001, "allocations": .5,
}


def capacity_for(final_count):
    capacity = 1
    while capacity < final_count * 2:
        capacity *= 2
    return capacity


def dimension(status, central, low, high, assumptions, source):
    return {
        "status": status,
        "central": round(central, 2),
        "interval": [round(low, 2), round(high, 2)],
        "assumptions": assumptions,
        "source": source,
    }


def analyze(description, workload, knowledge):
    """Analyse sans accès aux clés complètes ni à l'oracle instrumenté."""
    n = workload["initial_n"]
    final_n = n + workload["insert"]
    accesses = workload["lookup"] + workload["update"]
    result = {}

    if description["storage"] == "dense_sorted":
        low = accesses
        high = accesses * (math.ceil(math.log2(n)) + 2)
        # Valeur centrale réfutée au POC 5, conservée sans correction ; seule
        # une borne sûre explicite empêche de la traiter comme un fait exact.
        central = accesses * (math.ceil(math.log2(n)) + 1)
        result["comparisons"] = dimension(
            "bound", central, low, high,
            ["clés triées", "insertions au-dessus du maximum"],
            "borne sûre de recherche dichotomique")
        result["random_accesses"] = dimension(
            "bound", central, low, high,
            ["un accès par comparaison"], "borne dérivée des comparaisons")
        result["probes"] = dimension("exact", 0, 0, 0, [], "absence de probing")
        result["reserved_cells"] = dimension(
            "exact", final_n * 2, final_n * 2, final_n * 2, [],
            "deux tableaux préalloués")
        result["allocations"] = dimension("exact", 2, 2, 2, [], "deux tableaux")
    else:
        capacity = capacity_for(final_n)
        probe_events = n + workload["insert"] + accesses
        alpha = final_n / capacity
        uniform_success = .5 * (1 + 1 / (1 - alpha))
        uniform_failure = .5 * (1 + 1 / ((1 - alpha) ** 2))
        uniform_total = ((n + workload["insert"]) * uniform_failure
                         + accesses * uniform_success)
        level = knowledge["level"]
        if level == "A":
            low, high, central = probe_events, probe_events * final_n, uniform_total
            assumptions = ["dispersion uniforme non vérifiée"]
            source = "facteur de charge et intervalle prudent"
        elif level == "B":
            stats = knowledge["statistics"]
            scale = final_n / stats["sample_size"]
            possible_cluster = max(4, stats["max_home_bucket"] * scale * 2)
            low, high = probe_events, probe_events * min(final_n, possible_cluster)
            central = uniform_total
            assumptions = ["l'échantillon reflète la dispersion des bits bas"]
            source = "distincts et maximum par bucket modulo capacité"
        else:
            probe = knowledge["micro_probe"]
            scale = final_n / probe["sample_size"]
            extrapolated_mean = 1 + (probe["mean_probes"] - 1) * scale
            low_mean = max(1, extrapolated_mean * .6)
            high_mean = min(final_n, extrapolated_mean * 1.6)
            low, high = probe_events * low_mean, probe_events * high_mean
            central = probe_events * extrapolated_mean
            assumptions = ["croissance approximativement linéaire des clusters de l'échantillon"]
            source = "micro-probe de 64 insertions, extrapolation prudente"
        for feature in ("comparisons", "probes", "random_accesses"):
            result[feature] = dimension(
                "estimate", central, low, high, assumptions, source)
        primary_cells = capacity * 2
        extra_cells = capacity + final_n if description["auxiliary"] != "none" else 0
        cells = primary_cells + extra_cells
        allocations = 4 if description["auxiliary"] != "none" else 2
        result["reserved_cells"] = dimension(
            "exact", cells, cells, cells, [], "politique de capacité déclarée")
        result["allocations"] = dimension(
            "exact", allocations, allocations, allocations, [], "tableaux déclarés")

    if description["walk"] == "dense":
        reads = workload["walk"] * final_n
        result["sequential_reads"] = dimension(
            "exact", reads, reads, reads, ["parcours après insertions"], "taille × parcours")
        result["slots_visited"] = dimension("exact", 0, 0, 0, [], "pas de scan sparse")
    else:
        visits = workload["walk"] * capacity_for(final_n)
        result["sequential_reads"] = dimension("exact", 0, 0, 0, [], "scan sparse séparé")
        result["slots_visited"] = dimension(
            "exact", visits, visits, visits, [], "capacité × parcours")

    base = n * 2 + workload["update"] + workload["insert"] * 2
    result["base_writes"] = dimension(
        "exact", base, base, base, [], "construction et maintenance primaire")
    auxiliary = 0
    if description["auxiliary"] != "none":
        auxiliary = n * 2 + workload["update"] + workload["insert"] * 2
    result["auxiliary_writes"] = dimension(
        "exact", auxiliary, auxiliary, auxiliary,
        ["vue miroir" if auxiliary else "aucune vue"], "règle de maintenance")
    return result


def cost_interval(vector):
    low = sum(vector[name]["interval"][0] * PLATFORM[name] for name in FEATURES)
    high = sum(vector[name]["interval"][1] * PLATFORM[name] for name in FEATURES)
    central = sum(vector[name]["central"] * PLATFORM[name] for name in FEATURES)
    return {"central": round(central, 2), "interval": [round(low, 2), round(high, 2)]}


def decide(costs, final_stage=False):
    ranking = sorted(costs, key=lambda name: (costs[name]["central"], name))
    for candidate in ranking:
        if all(candidate == other
               or costs[candidate]["interval"][1] < costs[other]["interval"][0]
               for other in costs):
            return {"status": "decidable", "selected": candidate,
                    "ranking_by_central": ranking}
    return {"status": "undetermined" if final_stage else "needs_information",
            "selected": None, "ranking_by_central": ranking}


def concrete_keys(n):
    # Distribution inconnue au niveau A : groupement général dans les bits bas.
    return [index * 64 for index in range(n)]


def sample_keys(keys, count=64, seed=29):
    rng = random.Random(seed)
    indexes = rng.sample(range(len(keys)), count)
    return [keys[index] for index in indexes]


def cheap_statistics(sample, capacity):
    buckets = {}
    for key in sample:
        home = key % capacity
        buckets[home] = buckets.get(home, 0) + 1
    distinct_ratio = len(buckets) / len(sample)
    maximum = max(buckets.values())
    return {
        "sample_size": len(sample),
        "distinct_home_buckets": len(buckets),
        "distinct_home_ratio": round(distinct_ratio, 4),
        "max_home_bucket": maximum,
        "uniform_dispersion_supported": distinct_ratio >= .8 and maximum <= 2,
        "keys_read": len(sample),
    }


def empirical_micro_probe(sample, capacity):
    # Observation ciblée indépendante; elle n'appelle pas l'implémentation oracle.
    slots = [None] * capacity
    probes = []
    for key in sample:
        index = key % capacity
        count = 1
        while slots[index] is not None:
            index = (index + 1) % capacity
            count += 1
        slots[index] = key
        probes.append(count)
    return {
        "sample_size": len(sample), "insertions": len(sample),
        "total_probes": sum(probes),
        "mean_probes": round(sum(probes) / len(probes), 4),
        "max_probes": max(probes),
    }


def build_operations(spec, keys):
    rng = random.Random(31)
    shuffled = keys[:]
    rng.shuffle(shuffled)
    operations = [("lookup", key) for key in shuffled[:spec["lookup"]]]
    operations += [("update", key) for key in shuffled[-spec["update"]:]]
    operations += [("insert", (spec["initial_n"] + offset) * 64)
                   for offset in range(spec["insert"])]
    operations += [("walk", None) for _ in range(spec["walk"])]
    return operations


class SortedOracle:
    def __init__(self, keys, inserts):
        final_size = len(keys) + inserts
        self.keys = [None] * final_size
        self.values = [None] * final_size
        self.size = len(keys)
        self.stats = {name: 0 for name in FEATURES}
        self.stats["reserved_cells"] = final_size * 2
        self.stats["allocations"] = 2
        for index, key in enumerate(keys):
            self.keys[index] = key
            self.values[index] = key * 2
            self.stats["base_writes"] += 2

    def locate(self, key):
        low, high = 0, self.size
        while low < high:
            middle = (low + high) // 2
            self.stats["comparisons"] += 1
            self.stats["random_accesses"] += 1
            if self.keys[middle] < key:
                low = middle + 1
            else:
                high = middle
        self.stats["comparisons"] += 1
        self.stats["random_accesses"] += 1
        return low

    def run(self, operations):
        checksum = 0
        for operation, key in operations:
            if operation == "lookup":
                checksum += self.values[self.locate(key)]
            elif operation == "update":
                index = self.locate(key)
                self.values[index] += 1
                self.stats["base_writes"] += 1
            elif operation == "insert":
                self.keys[self.size] = key
                self.values[self.size] = key * 2
                self.size += 1
                self.stats["base_writes"] += 2
            else:
                for index in range(self.size):
                    self.stats["sequential_reads"] += 1
                    checksum += self.values[index]
        return checksum


class HashOracle:
    def __init__(self, keys, inserts, dense_view):
        needed = (len(keys) + inserts) * 2
        capacity = 1
        while capacity < needed:
            capacity *= 2
        self.keys = [None] * capacity
        self.values = [None] * capacity
        self.dense_view = dense_view
        self.positions = [None] * capacity if dense_view else None
        self.dense_values = [None] * (len(keys) + inserts) if dense_view else None
        self.size = 0
        self.stats = {name: 0 for name in FEATURES}
        self.stats["reserved_cells"] = capacity * 2
        self.stats["allocations"] = 2
        if dense_view:
            self.stats["reserved_cells"] += capacity + len(self.dense_values)
            self.stats["allocations"] += 2
        for key in keys:
            slot = self.locate(key)
            self.keys[slot] = key
            self.values[slot] = key * 2
            self.stats["base_writes"] += 2
            if dense_view:
                self.positions[slot] = self.size
                self.dense_values[self.size] = key * 2
                self.stats["auxiliary_writes"] += 2
            self.size += 1

    def locate(self, key):
        slot = key % len(self.keys)
        while True:
            self.stats["probes"] += 1
            self.stats["comparisons"] += 1
            self.stats["random_accesses"] += 1
            if self.keys[slot] is None or self.keys[slot] == key:
                return slot
            slot = (slot + 1) % len(self.keys)

    def run(self, operations):
        checksum = 0
        for operation, key in operations:
            if operation == "walk":
                if self.dense_view:
                    for index in range(self.size):
                        self.stats["sequential_reads"] += 1
                        checksum += self.dense_values[index]
                else:
                    for slot in range(len(self.keys)):
                        self.stats["slots_visited"] += 1
                        if self.keys[slot] is not None:
                            checksum += self.values[slot]
                continue
            slot = self.locate(key)
            if operation == "lookup":
                checksum += self.values[slot]
            elif operation == "update":
                self.values[slot] += 1
                self.stats["base_writes"] += 1
                if self.dense_view:
                    dense = self.positions[slot]
                    self.dense_values[dense] += 1
                    self.stats["auxiliary_writes"] += 1
            else:
                value = key * 2
                self.keys[slot] = key
                self.values[slot] = value
                self.stats["base_writes"] += 2
                if self.dense_view:
                    self.positions[slot] = self.size
                    self.dense_values[self.size] = value
                    self.stats["auxiliary_writes"] += 2
                self.size += 1
        return checksum


def acquire_and_decide(workload_name, spec, keys):
    stages = []
    knowledge = {"level": "A"}
    sample = sample_keys(keys)
    capacity = capacity_for(spec["initial_n"] + spec["insert"])
    acquired = None
    for level in ("A", "B", "C"):
        knowledge["level"] = level
        if level == "B":
            acquired = {"type": "low_bit_statistics",
                        "observation": cheap_statistics(sample, capacity)}
            knowledge["statistics"] = acquired["observation"]
        elif level == "C":
            acquired = {"type": "micro_probe", "observation": empirical_micro_probe(sample, capacity)}
            knowledge["micro_probe"] = acquired["observation"]
        vectors = {name: analyze(description, spec, knowledge)
                   for name, description in SOLUTIONS.items()}
        costs = {name: cost_interval(vector) for name, vector in vectors.items()}
        decision = decide(costs, final_stage=level == "C")
        stages.append({"level": level, "information_acquired": acquired,
                       "vectors": vectors, "costs": costs, "decision": decision})
        if decision["status"] == "decidable":
            break
    return stages


def full_oracle(spec, keys):
    operations = build_operations(spec, keys)
    implementations = {
        "sorted+binary_lookup+dense_walk": SortedOracle(keys, spec["insert"]),
        "hash+linear_probe+slot_scan": HashOracle(keys, spec["insert"], False),
        "hash+linear_probe+dense_view": HashOracle(keys, spec["insert"], True),
    }
    rows = {}
    for name, implementation in implementations.items():
        start = time.perf_counter_ns()
        checksum = implementation.run(operations)
        wall_ns = time.perf_counter_ns() - start
        observed_cost = sum(implementation.stats[feature] * PLATFORM[feature]
                            for feature in FEATURES)
        rows[name] = {"vector": implementation.stats, "cost": round(observed_cost, 2),
                      "checksum": checksum, "wall_ns": wall_ns}
    selected = min(rows, key=lambda name: (rows[name]["cost"], name))
    return {"solutions": rows, "selected": selected}


def compare_with_oracle(final_stage, oracle):
    comparison = {}
    for solution, vector in final_stage["vectors"].items():
        observed = oracle["solutions"][solution]["vector"]
        comparison[solution] = {}
        for feature, predicted in vector.items():
            low, high = predicted["interval"]
            comparison[solution][feature] = {
                "status": predicted["status"],
                "interval": predicted["interval"],
                "observed": observed[feature],
                "within_interval": low <= observed[feature] <= high,
            }
    return comparison


def main():
    results = []
    for workload_name, spec in WORKLOADS.items():
        keys = concrete_keys(spec["initial_n"])
        stages = acquire_and_decide(workload_name, spec, keys)
        oracle = full_oracle(spec, keys)
        oracle_comparison = compare_with_oracle(stages[-1], oracle)
        final_decision = stages[-1]["decision"]
        results.append({
            "workload": workload_name,
            "stages": stages,
            "oracle": oracle,
            "oracle_comparison": oracle_comparison,
            "decision_matches_oracle": final_decision["selected"] == oracle["selected"],
        })
        print(workload_name)
        for stage in stages:
            decision = stage["decision"]
            acquired = stage["information_acquired"]
            print(f"  level {stage['level']}: {decision['status']} "
                  f"selected={decision['selected']} acquired={acquired['type'] if acquired else 'none'}")
            for name, cost in stage["costs"].items():
                print(f"    {name:38} {cost['interval']} central={cost['central']}")
            if acquired:
                print(f"    observation={acquired['observation']}")
        print(f"  oracle: {oracle['selected']} "
              f"decision_matches={final_decision['selected'] == oracle['selected']}")
        for name in SOLUTIONS:
            print(f"    {name:38} observed_probes="
                  f"{oracle['solutions'][name]['vector']['probes']}")
    Path("poc6_measurements.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
