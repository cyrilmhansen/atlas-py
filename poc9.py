#!/usr/bin/env python3
"""POC 9 jetable: contrats épistémiques pour extrapoler des micro-probes."""

import json
import math
import random
import time
from pathlib import Path


FEATURES = (
    "comparisons", "probes", "sequential_reads", "random_accesses",
    "base_writes", "auxiliary_writes", "reserved_cells", "allocations",
)

WORKLOADS = {
    "lookup_heavy": {"initial_n": 512, "lookup": 400, "walk": 5,
                     "update": 20, "insert": 20},
    "walk_heavy": {"initial_n": 512, "lookup": 50, "walk": 100,
                   "update": 20, "insert": 20},
}

PLATFORM = {
    "comparisons": .05, "probes": .08, "sequential_reads": .1,
    "random_accesses": .2, "base_writes": .3,
    "auxiliary_writes": .2, "reserved_cells": .001, "allocations": .5,
}

PROBES = {
    "probe16": {"observes": "probe_count", "size": 16},
    "probe32": {"observes": "probe_count", "size": 32},
    "probe64": {"observes": "probe_count", "size": 64},
}

# Contrats locaux et explicites, sans moteur générique.
CONTRACTS = {
    "naive_representative": {
        "observes": "probe_count",
        "assumptions": ["un échantillon est représentatif", "rayon relatif 1/√k"],
        "required_scales": 1,
        "acceptance": "au moins un micro-probe",
        "output": "estimate_interval",
    },
    "conservative": {
        "observes": "probe_count",
        "assumptions": ["les clés non vues peuvent former des clusters plus grands"],
        "required_scales": 1,
        "acceptance": "au moins un micro-probe; borne structurelle conservée",
        "output": "bound_interval",
    },
    "multi_scale": {
        "observes": "probe_count",
        "assumptions": ["stabilité entre trois tailles emboîtées"],
        "required_scales": 3,
        "acceptance": "trois échelles et variation relative maximale ≤ 0,20",
        "stability_threshold": .20,
        "output": "estimate_interval_or_insufficient_evidence",
    },
}


def capacity_for(count):
    capacity = 1
    while capacity < count * 2:
        capacity *= 2
    return capacity


def dim(status, central, low, high, assumptions, source):
    return {"status": status, "central": round(central, 2),
            "interval": [round(low, 2), round(high, 2)],
            "assumptions": assumptions, "source": source}


def sorted_vector(workload):
    n = workload["initial_n"]
    final_n = n + workload["insert"]
    accesses = workload["lookup"] + workload["update"]
    low, high = accesses, accesses * (math.ceil(math.log2(n)) + 2)
    central = accesses * (math.ceil(math.log2(n)) + 1)
    vector = {
        "comparisons": dim("bound", central, low, high, ["clés triées"], "borne dichotomique"),
        "probes": dim("exact", 0, 0, 0, [], "aucun probing"),
        "random_accesses": dim("bound", central, low, high,
                               ["un accès par comparaison"], "borne dérivée"),
    }
    return exact_dimensions(vector, workload, auxiliary=False)


def exact_dimensions(vector, workload, auxiliary):
    n = workload["initial_n"]
    final_n = n + workload["insert"]
    reads = workload["walk"] * final_n
    base = n * 2 + workload["update"] + workload["insert"] * 2
    if auxiliary:
        capacity = capacity_for(final_n)
        cells, allocations, auxiliary_writes = capacity * 3 + final_n, 4, base
    else:
        cells, allocations, auxiliary_writes = final_n * 2, 2, 0
    vector.update({
        "sequential_reads": dim("exact", reads, reads, reads,
                                ["parcours après insertions"], "taille × parcours"),
        "base_writes": dim("exact", base, base, base, [], "maintenance primaire"),
        "auxiliary_writes": dim("exact", auxiliary_writes, auxiliary_writes,
                                auxiliary_writes, ["vue miroir"] if auxiliary else [],
                                "maintenance auxiliaire"),
        "reserved_cells": dim("exact", cells, cells, cells, [], "capacité déclarée"),
        "allocations": dim("exact", allocations, allocations, allocations, [], "tableaux"),
    })
    return vector


def contract_inference(contract_name, observations, workload):
    contract = CONTRACTS[contract_name]
    ordered = sorted(observations.values(), key=lambda item: item["size"])
    evidence = {"available_scales": [item["size"] for item in ordered],
                "means": [item["mean_probes"] for item in ordered],
                "maxima": [item["max_probes"] for item in ordered]}
    if len(ordered) < contract["required_scales"]:
        return {"status": "insufficient_evidence", "contract": contract,
                "evidence": evidence,
                "reason": f"{contract['required_scales']} échelle(s) requise(s)"}

    largest = ordered[-1]
    n = workload["initial_n"]
    final_n = n + workload["insert"]
    events = n + workload["insert"] + workload["lookup"] + workload["update"]

    if contract_name == "naive_representative":
        scale = final_n / largest["size"]
        global_mean = 1 + (largest["mean_probes"] - 1) * scale
        radius = 1 / math.sqrt(largest["size"])
        low_mean = max(1, global_mean * (1 - radius))
        high_mean = global_mean * (1 + radius)
        status, reason = "accepted", "représentativité supposée dès la première échelle"
        interval = [events * low_mean, events * high_mean]
        central = events * global_mean
    elif contract_name == "conservative":
        scale_ceiling = math.ceil(final_n / largest["size"])
        low_mean = max(1, largest["mean_probes"])
        high_mean = min(final_n, largest["max_probes"] * scale_ceiling)
        status, reason = "accepted", "borne des clés non vues conservée"
        interval = [events * low_mean, events * high_mean]
        central = (interval[0] + interval[1]) / 2
    else:
        relative_changes = []
        for previous, current in zip(ordered, ordered[1:]):
            relative_changes.append(abs(current["mean_probes"] - previous["mean_probes"])
                                    / max(previous["mean_probes"], 1))
        evidence["relative_changes"] = [round(value, 4) for value in relative_changes]
        maximum_change = max(relative_changes)
        evidence["maximum_relative_change"] = round(maximum_change, 4)
        if maximum_change > contract["stability_threshold"]:
            return {"status": "insufficient_evidence", "contract": contract,
                    "evidence": evidence,
                    "reason": "instabilité supérieure au seuil prédéfini"}
        global_mean = largest["mean_probes"]
        radius = max(maximum_change, 1 / math.sqrt(largest["size"]))
        low_mean = max(1, global_mean * (1 - radius))
        high_mean = global_mean * (1 + radius)
        status, reason = "accepted", "stabilité multi-échelle soutenue"
        interval = [events * low_mean, events * high_mean]
        central = events * global_mean

    return {"status": status, "contract": contract, "evidence": evidence,
            "reason": reason,
            "probe_count": {"status": contract["output"],
                            "central": round(central, 2),
                            "interval": [round(interval[0], 2), round(interval[1], 2)]}}


def hash_vector(workload, inference):
    if inference["status"] != "accepted":
        return None
    probe = inference["probe_count"]
    vector = {}
    for feature in ("comparisons", "probes", "random_accesses"):
        vector[feature] = dim(
            "estimate" if "estimate" in probe["status"] else "bound",
            probe["central"], probe["interval"][0], probe["interval"][1],
            inference["contract"]["assumptions"], inference["reason"])
    return exact_dimensions(vector, workload, auxiliary=True)


def cost_interval(vector):
    return {"central": round(sum(vector[f]["central"] * PLATFORM[f] for f in FEATURES), 2),
            "interval": [
                round(sum(vector[f]["interval"][0] * PLATFORM[f] for f in FEATURES), 2),
                round(sum(vector[f]["interval"][1] * PLATFORM[f] for f in FEATURES), 2),
            ]}


def decide(sorted_cost, hash_cost):
    if hash_cost is None:
        return {"status": "insufficient_evidence", "selected": None}
    if sorted_cost["interval"][1] < hash_cost["interval"][0]:
        return {"status": "decidable", "selected": "sorted+binary_lookup+dense_walk"}
    if hash_cost["interval"][1] < sorted_cost["interval"][0]:
        return {"status": "decidable", "selected": "hash+linear_probe+dense_view"}
    return {"status": "undetermined", "selected": None}


def keys_for(kind, n):
    if kind == "clustered":
        return [index * 64 for index in range(n)]
    return list(range(n))


def nested_sample(keys, size):
    indexes = list(range(len(keys)))
    random.Random(53).shuffle(indexes)
    return [keys[index] for index in indexes[:size]]


def execute_probe(name, keys, final_count):
    size = PROBES[name]["size"]
    sample = nested_sample(keys, size)
    slots = [None] * capacity_for(final_count)
    probes = []
    for key in sample:
        slot = key % len(slots)
        count = 1
        while slots[slot] is not None:
            slot = (slot + 1) % len(slots)
            count += 1
        slots[slot] = key
        probes.append(count)
    return {"name": name, "size": size, "insertions": size,
            "total_probes": sum(probes),
            "mean_probes": round(sum(probes) / size, 6),
            "max_probes": max(probes), "acquisition_cost": size + sum(probes)}


def run_contract(contract_name, workload, keys):
    observations = {}
    history = []
    sorted_cost = cost_interval(sorted_vector(workload))
    initial_hash = {feature: dim("estimate", 0,
                                workload["initial_n"] + workload["insert"]
                                + workload["lookup"] + workload["update"],
                                (workload["initial_n"] + workload["insert"]
                                 + workload["lookup"] + workload["update"])
                                * (workload["initial_n"] + workload["insert"]),
                                ["dispersion inconnue"], "aucune observation")
                    for feature in ("comparisons", "probes", "random_accesses")}
    initial_hash = exact_dimensions(initial_hash, workload, auxiliary=True)
    if decide(sorted_cost, cost_interval(initial_hash))["status"] == "decidable":
        return {"contract": contract_name, "history": [], "observations": {},
                "total_acquisition_cost": 0,
                "final_inference": {"status": "not_needed"},
                "final_costs": {"sorted": sorted_cost, "hash": cost_interval(initial_hash)},
                "decision": decide(sorted_cost, cost_interval(initial_hash))}

    for probe_name in sorted(PROBES, key=lambda name: PROBES[name]["size"]):
        observation = execute_probe(
            probe_name, keys, workload["initial_n"] + workload["insert"])
        observations[probe_name] = observation
        inference = contract_inference(contract_name, observations, workload)
        vector = hash_vector(workload, inference)
        hash_cost = cost_interval(vector) if vector else None
        decision = decide(sorted_cost, hash_cost)
        history.append({"acquired": probe_name, "observation": observation,
                        "inference": inference,
                        "costs": {"sorted": sorted_cost, "hash": hash_cost},
                        "decision": decision})
        if inference["status"] == "accepted" and decision["status"] == "decidable":
            break
    final = history[-1]
    if final["decision"]["status"] != "decidable":
        final["decision"]["status"] = (
            "insufficient_evidence" if final["inference"]["status"] != "accepted"
            else "undetermined")
    return {"contract": contract_name, "history": history,
            "observations": observations,
            "total_acquisition_cost": sum(item["acquisition_cost"] for item in observations.values()),
            "final_inference": final["inference"], "final_costs": final["costs"],
            "decision": final["decision"]}


def operations_for(workload, keys):
    shuffled = keys[:]
    random.Random(59).shuffle(shuffled)
    result = [("lookup", key) for key in shuffled[:workload["lookup"]]]
    result += [("update", key) for key in shuffled[-workload["update"]:]]
    if keys[1] - keys[0] == 64:
        inserted = [(workload["initial_n"] + index) * 64 for index in range(workload["insert"])]
    else:
        inserted = [workload["initial_n"] + index for index in range(workload["insert"])]
    result += [("insert", key) for key in inserted]
    result += [("walk", None) for _ in range(workload["walk"])]
    return result


class SortedOracle:
    def __init__(self, keys, inserts):
        count = len(keys) + inserts
        self.keys = [None] * count
        self.values = [None] * count
        self.size = len(keys)
        self.stats = {feature: 0 for feature in FEATURES}
        self.stats["reserved_cells"], self.stats["allocations"] = count * 2, 2
        for index, key in enumerate(keys):
            self.keys[index], self.values[index] = key, key * 2
            self.stats["base_writes"] += 2

    def find(self, key):
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
                checksum += self.values[self.find(key)]
            elif operation == "update":
                index = self.find(key)
                self.values[index] += 1
                self.stats["base_writes"] += 1
            elif operation == "insert":
                self.keys[self.size], self.values[self.size] = key, key * 2
                self.size += 1
                self.stats["base_writes"] += 2
            else:
                for index in range(self.size):
                    self.stats["sequential_reads"] += 1
                    checksum += self.values[index]
        return checksum


class HashOracle:
    def __init__(self, keys, inserts):
        capacity = capacity_for(len(keys) + inserts)
        self.keys = [None] * capacity
        self.values = [None] * capacity
        self.positions = [None] * capacity
        self.dense = [None] * (len(keys) + inserts)
        self.size = 0
        self.stats = {feature: 0 for feature in FEATURES}
        self.stats["reserved_cells"], self.stats["allocations"] = capacity * 3 + len(self.dense), 4
        for key in keys:
            slot = self.find(key)
            self.keys[slot], self.values[slot] = key, key * 2
            self.positions[slot], self.dense[self.size] = self.size, key * 2
            self.stats["base_writes"] += 2
            self.stats["auxiliary_writes"] += 2
            self.size += 1

    def find(self, key):
        slot = key % len(self.keys)
        while True:
            self.stats["comparisons"] += 1
            self.stats["probes"] += 1
            self.stats["random_accesses"] += 1
            if self.keys[slot] is None or self.keys[slot] == key:
                return slot
            slot = (slot + 1) % len(self.keys)

    def run(self, operations):
        checksum = 0
        for operation, key in operations:
            if operation == "walk":
                for index in range(self.size):
                    self.stats["sequential_reads"] += 1
                    checksum += self.dense[index]
                continue
            slot = self.find(key)
            if operation == "lookup":
                checksum += self.values[slot]
            elif operation == "update":
                self.values[slot] += 1
                self.dense[self.positions[slot]] += 1
                self.stats["base_writes"] += 1
                self.stats["auxiliary_writes"] += 1
            else:
                value = key * 2
                self.keys[slot], self.values[slot] = key, value
                self.positions[slot], self.dense[self.size] = self.size, value
                self.stats["base_writes"] += 2
                self.stats["auxiliary_writes"] += 2
                self.size += 1
        return checksum


def oracle(workload, keys):
    operations = operations_for(workload, keys)
    implementations = {
        "sorted+binary_lookup+dense_walk": SortedOracle(keys, workload["insert"]),
        "hash+linear_probe+dense_view": HashOracle(keys, workload["insert"]),
    }
    rows = {}
    for name, implementation in implementations.items():
        start = time.perf_counter_ns()
        checksum = implementation.run(operations)
        wall_ns = time.perf_counter_ns() - start
        cost = sum(implementation.stats[f] * PLATFORM[f] for f in FEATURES)
        rows[name] = {"vector": implementation.stats, "cost": round(cost, 2),
                      "checksum": checksum, "wall_ns": wall_ns}
    return {"solutions": rows, "selected": min(rows, key=lambda name: (rows[name]["cost"], name))}


def evaluate_contract(result, observed):
    probe_interval = (result["final_inference"].get("probe_count", {})
                      .get("interval"))
    observed_probes = observed["solutions"]["hash+linear_probe+dense_view"]["vector"]["probes"]
    coverage = None if probe_interval is None else probe_interval[0] <= observed_probes <= probe_interval[1]
    selected = result["decision"]["selected"]
    decision_correct = None if selected is None else selected == observed["selected"]
    if result["final_inference"]["status"] == "not_needed" and decision_correct:
        outcome = "correct_decision_no_inference_needed"
    elif selected is None:
        outcome = "refusal_to_conclude"
    elif decision_correct and coverage:
        outcome = "correct_decision_correct_coverage"
    elif decision_correct:
        outcome = "correct_decision_bad_coverage"
    else:
        outcome = "wrong_decision"
    return {"observed_probes": observed_probes, "probe_interval": probe_interval,
            "coverage": coverage, "decision_correct": decision_correct,
            "outcome": outcome}


def positive_control(workload):
    keys = keys_for("uniform", workload["initial_n"])
    observations = {}
    stages = []
    for name in sorted(PROBES, key=lambda item: PROBES[item]["size"]):
        observations[name] = execute_probe(
            name, keys, workload["initial_n"] + workload["insert"])
        inference = contract_inference("multi_scale", observations, workload)
        stages.append({"acquired": name, "observation": observations[name],
                       "inference": inference})
        if inference["status"] == "accepted":
            break
    observed = oracle(workload, keys)
    probe_interval = stages[-1]["inference"]["probe_count"]["interval"]
    actual = observed["solutions"]["hash+linear_probe+dense_view"]["vector"]["probes"]
    return {"key_distribution": "sequential distinct keys", "stages": stages,
            "oracle_probes": actual, "interval": probe_interval,
            "coverage": probe_interval[0] <= actual <= probe_interval[1]}


def main():
    results = []
    for workload_name, workload in WORKLOADS.items():
        keys = keys_for("clustered", workload["initial_n"])
        initial_sorted = cost_interval(sorted_vector(workload))
        contracts = {name: run_contract(name, workload, keys) for name in CONTRACTS}
        observed = oracle(workload, keys)
        for result in contracts.values():
            result["oracle_evaluation"] = evaluate_contract(result, observed)
        row = {"workload": workload_name, "contracts": contracts,
               "initial_sorted_cost": initial_sorted, "oracle": observed}
        results.append(row)
        print(workload_name, "oracle=", observed["selected"])
        for name, result in contracts.items():
            acquired = [stage["acquired"] for stage in result["history"]]
            evaluation = result["oracle_evaluation"]
            print(f"  {name:22} probes={acquired} decision={result['decision']['status']} "
                  f"selected={result['decision']['selected']} outcome={evaluation['outcome']}")
            if result["history"]:
                print(f"    final inference={result['final_inference']['status']} "
                      f"reason={result['final_inference']['reason']}")
                print(f"    interval={evaluation['probe_interval']} observed={evaluation['observed_probes']}")
    control = positive_control(WORKLOADS["lookup_heavy"])
    print("positive_control multi_scale", "interval=", control["interval"],
          "oracle=", control["oracle_probes"], "coverage=", control["coverage"])
    Path("poc9_measurements.json").write_text(
        json.dumps({"experiments": results, "positive_control": control}, indent=2) + "\n")


if __name__ == "__main__":
    main()
