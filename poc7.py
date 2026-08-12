#!/usr/bin/env python3
"""POC 7 jetable: choisir une acquisition pour sa valeur décisionnelle."""

import json
import math
import random
import time
from pathlib import Path


FEATURES = (
    "comparisons", "probes", "sequential_reads", "random_accesses",
    "base_writes", "auxiliary_writes", "reserved_cells", "allocations",
)

SOLUTIONS = {
    "sorted+binary_lookup+dense_walk": {
        "storage": "dense_sorted", "lookup": "binary", "walk": "dense",
        "auxiliary": False,
    },
    "hash+linear_probe+dense_view": {
        "storage": "open_addressed", "lookup": "linear_probe", "walk": "dense",
        "auxiliary": True,
    },
}

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

# L'utilité annoncée est antérieure à toute observation. Elle indique seulement
# à quel point l'action cible directement l'incertitude et pourrait la réduire.
ACTIONS = {
    "sample16": {"kind": "sample", "size": 16, "expected_cost": 16,
                 "expected_reduction": .15, "directness": .3,
                 "targets": ["hash_dispersion"]},
    "sample64": {"kind": "sample", "size": 64, "expected_cost": 64,
                 "expected_reduction": .50, "directness": .5,
                 "targets": ["hash_dispersion"]},
    "probe16": {"kind": "probe", "size": 16, "expected_cost": 32,
                "expected_reduction": .75, "directness": .9,
                "targets": ["hash_dispersion"]},
    "probe64": {"kind": "probe", "size": 64, "expected_cost": 128,
                "expected_reduction": .95, "directness": 1.0,
                "targets": ["hash_dispersion"]},
}


def capacity_for(final_count):
    capacity = 1
    while capacity < final_count * 2:
        capacity *= 2
    return capacity


def dim(status, central, low, high, assumptions, source):
    return {
        "status": status, "central": round(central, 2),
        "interval": [round(low, 2), round(high, 2)],
        "assumptions": assumptions, "source": source,
    }


def best_observation(observations, kind):
    candidates = [value for value in observations.values() if value["kind"] == kind]
    return max(candidates, key=lambda value: value["size"], default=None)


def analyze(description, workload, observations):
    """Analyse déclarative; aucune observation future ni oracle n'est visible."""
    n = workload["initial_n"]
    final_n = n + workload["insert"]
    accesses = workload["lookup"] + workload["update"]
    vector = {}
    if description["storage"] == "dense_sorted":
        low = accesses
        high = accesses * (math.ceil(math.log2(n)) + 2)
        central = accesses * (math.ceil(math.log2(n)) + 1)
        vector["comparisons"] = dim(
            "bound", central, low, high, ["clés triées"], "borne dichotomique")
        vector["random_accesses"] = dim(
            "bound", central, low, high, ["un accès par comparaison"], "borne dérivée")
        vector["probes"] = dim("exact", 0, 0, 0, [], "aucun probing")
        cells, allocations = final_n * 2, 2
    else:
        capacity = capacity_for(final_n)
        events = n + workload["insert"] + accesses
        alpha = final_n / capacity
        successful = .5 * (1 + 1 / (1 - alpha))
        unsuccessful = .5 * (1 + 1 / ((1 - alpha) ** 2))
        uniform = (n + workload["insert"]) * unsuccessful + accesses * successful
        probe = best_observation(observations, "probe")
        sample = best_observation(observations, "sample")
        if probe:
            scale = final_n / probe["size"]
            extrapolated = 1 + (probe["mean_probes"] - 1) * scale
            if probe["size"] >= 64:
                low_mean, high_mean = extrapolated * .6, extrapolated * 1.6
            else:
                low_mean, high_mean = extrapolated * .35, extrapolated * 2.0
            low, high, central = events * max(1, low_mean), events * high_mean, events * extrapolated
            source = f"micro-probe de {probe['size']} clés"
            assumptions = ["croissance approximativement linéaire des clusters échantillonnés"]
        elif sample:
            scale = final_n / sample["size"]
            possible_cluster = max(4, sample["max_home_bucket"] * scale * 2)
            low, high, central = events, events * min(final_n, possible_cluster), uniform
            source = f"statistique de dispersion sur {sample['size']} clés"
            assumptions = ["l'échantillon reflète les bits bas de toutes les clés"]
        else:
            low, high, central = events, events * final_n, uniform
            source = "facteur de charge seul"
            assumptions = ["dispersion uniforme non vérifiée"]
        for feature in ("comparisons", "probes", "random_accesses"):
            vector[feature] = dim("estimate", central, low, high, assumptions, source)
        cells, allocations = capacity * 3 + final_n, 4

    reads = workload["walk"] * final_n
    vector["sequential_reads"] = dim(
        "exact", reads, reads, reads, ["parcours après insertions"], "taille × parcours")
    base = n * 2 + workload["update"] + workload["insert"] * 2
    vector["base_writes"] = dim("exact", base, base, base, [], "maintenance primaire")
    auxiliary = base if description["auxiliary"] else 0
    vector["auxiliary_writes"] = dim(
        "exact", auxiliary, auxiliary, auxiliary,
        ["vue miroir" if auxiliary else "aucune vue"], "maintenance auxiliaire")
    vector["reserved_cells"] = dim("exact", cells, cells, cells, [], "capacité déclarée")
    vector["allocations"] = dim("exact", allocations, allocations, allocations, [], "tableaux")
    return vector


def cost_interval(vector):
    return {
        "central": round(sum(vector[f]["central"] * PLATFORM[f] for f in FEATURES), 2),
        "interval": [
            round(sum(vector[f]["interval"][0] * PLATFORM[f] for f in FEATURES), 2),
            round(sum(vector[f]["interval"][1] * PLATFORM[f] for f in FEATURES), 2),
        ],
    }


def current_state(workload, observations):
    vectors = {name: analyze(description, workload, observations)
               for name, description in SOLUTIONS.items()}
    costs = {name: cost_interval(vector) for name, vector in vectors.items()}
    ranking = sorted(costs, key=lambda name: (costs[name]["central"], name))
    selected = None
    for candidate in ranking:
        if all(candidate == other or costs[candidate]["interval"][1] < costs[other]["interval"][0]
               for other in costs):
            selected = candidate
            break
    return {
        "vectors": vectors, "costs": costs,
        "decision": {"status": "decidable" if selected else "needs_information",
                     "selected": selected, "ranking_by_central": ranking},
    }


def evaluate_actions(state, available):
    """Évalue des capacités annoncées, jamais les futures observations."""
    costs = state["costs"]
    sorted_interval = costs["sorted+binary_lookup+dense_walk"]["interval"]
    hash_interval = costs["hash+linear_probe+dense_view"]["interval"]
    overlap = max(0, min(sorted_interval[1], hash_interval[1])
                  - max(sorted_interval[0], hash_interval[0]))
    hash_width = hash_interval[1] - hash_interval[0]
    evaluations = {}
    for name in available:
        action = ACTIONS[name]
        remaining = hash_width * (1 - action["expected_reduction"])
        could_decide = remaining <= overlap
        utility = (overlap * action["expected_reduction"] * action["directness"]
                   / action["expected_cost"] if overlap else 0)
        evaluations[name] = {
            "expected_cost": action["expected_cost"],
            "targets_decision_uncertainty": overlap > 0,
            "overlap": round(overlap, 2),
            "expected_remaining_width": round(remaining, 2),
            "could_decide_alone": could_decide,
            "decision_utility_per_cost": round(utility, 6),
        }
    return evaluations


def choose_adaptive_action(state, available):
    evaluations = evaluate_actions(state, available)
    relevant = [name for name in available
                if evaluations[name]["targets_decision_uncertainty"]]
    sufficient = [name for name in relevant if evaluations[name]["could_decide_alone"]]
    if sufficient:
        chosen = min(sufficient, key=lambda name: (ACTIONS[name]["expected_cost"], name))
        reason = "action potentiellement décisive la moins coûteuse"
    else:
        chosen = max(relevant,
                     key=lambda name: (evaluations[name]["decision_utility_per_cost"],
                                       -ACTIONS[name]["expected_cost"], name))
        reason = "meilleur compromis réduction décisionnelle / coût"
    return chosen, reason, evaluations


def all_keys(n):
    return [index * 64 for index in range(n)]


def selected_sample(keys, size):
    indexes = list(range(len(keys)))
    random.Random(37).shuffle(indexes)
    return [keys[index] for index in indexes[:size]]


def execute_action(name, keys, final_count):
    action = ACTIONS[name]
    sample = selected_sample(keys, action["size"])
    capacity = capacity_for(final_count)
    if action["kind"] == "sample":
        buckets = {}
        for key in sample:
            home = key % capacity
            buckets[home] = buckets.get(home, 0) + 1
        observation = {
            "kind": "sample", "size": len(sample),
            "distinct_home_buckets": len(buckets),
            "distinct_home_ratio": round(len(buckets) / len(sample), 4),
            "max_home_bucket": max(buckets.values()),
        }
        actual_cost = len(sample)
        work = {"keys_inspected": len(sample), "insertions": 0, "probes": 0}
    else:
        slots = [None] * capacity
        probes = []
        for key in sample:
            slot = key % capacity
            count = 1
            while slots[slot] is not None:
                slot = (slot + 1) % capacity
                count += 1
            slots[slot] = key
            probes.append(count)
        observation = {
            "kind": "probe", "size": len(sample),
            "total_probes": sum(probes),
            "mean_probes": round(sum(probes) / len(probes), 4),
            "max_probes": max(probes),
        }
        actual_cost = len(sample) + sum(probes)
        work = {"keys_inspected": 0, "insertions": len(sample), "probes": sum(probes)}
    return observation, actual_cost, work


def run_policy(policy, workload, keys):
    observations = {}
    available = list(ACTIONS)
    history = []
    total_cost = 0
    fixed = ["sample64", "probe64"]
    while True:
        state = current_state(workload, observations)
        record = {"state": {"costs": state["costs"], "decision": state["decision"]},
                  "available_actions": available[:],
                  "action_evaluations": None, "chosen_action": None,
                  "choice_reason": None, "observation": None,
                  "acquisition_cost": 0}
        if policy == "always_expensive" and not history:
            chosen, reason = "probe64", "baseline imposée, même si la décision est robuste"
            evaluations = None
        elif state["decision"]["status"] == "decidable":
            history.append(record)
            break
        elif policy == "always_none":
            state["decision"]["status"] = "undetermined"
            history.append(record)
            break
        elif policy == "fixed_sequence":
            chosen = next((name for name in fixed if name in available), None)
            if chosen is None:
                state["decision"]["status"] = "undetermined"
                history.append(record)
                break
            reason, evaluations = "ordre prescrit sample64 → probe64", None
        else:
            chosen, reason, evaluations = choose_adaptive_action(state, available)
        observation, actual_cost, work = execute_action(
            chosen, keys, workload["initial_n"] + workload["insert"])
        observations[chosen] = observation
        available.remove(chosen)
        total_cost += actual_cost
        record.update({"action_evaluations": evaluations, "chosen_action": chosen,
                       "choice_reason": reason, "observation": observation,
                       "acquisition_work": work, "acquisition_cost": actual_cost})
        history.append(record)
        if len(history) > len(ACTIONS):
            break
    final_state = current_state(workload, observations)
    if final_state["decision"]["status"] != "decidable":
        final_state["decision"]["status"] = "undetermined"
    return {"policy": policy, "history": history, "observations": observations,
            "total_acquisition_cost": total_cost,
            "acquisition_steps": len(observations), "final_state": final_state}


def operations_for(workload, keys):
    shuffled = keys[:]
    random.Random(41).shuffle(shuffled)
    result = [("lookup", key) for key in shuffled[:workload["lookup"]]]
    result += [("update", key) for key in shuffled[-workload["update"]:]]
    result += [("insert", (workload["initial_n"] + offset) * 64)
               for offset in range(workload["insert"])]
    result += [("walk", None) for _ in range(workload["walk"])]
    return result


class SortedOracle:
    def __init__(self, keys, inserts):
        final_count = len(keys) + inserts
        self.keys = [None] * final_count
        self.values = [None] * final_count
        self.size = len(keys)
        self.stats = {feature: 0 for feature in FEATURES}
        self.stats["reserved_cells"], self.stats["allocations"] = final_count * 2, 2
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
        wanted = (len(keys) + inserts) * 2
        capacity = 1
        while capacity < wanted:
            capacity *= 2
        self.keys = [None] * capacity
        self.values = [None] * capacity
        self.positions = [None] * capacity
        self.dense = [None] * (len(keys) + inserts)
        self.size = 0
        self.stats = {feature: 0 for feature in FEATURES}
        self.stats["reserved_cells"] = capacity * 3 + len(self.dense)
        self.stats["allocations"] = 4
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
    selected = min(rows, key=lambda name: (rows[name]["cost"], name))
    return {"solutions": rows, "selected": selected}


def oracle_coverage(final_state, observed):
    coverage = {}
    for solution, vector in final_state["vectors"].items():
        coverage[solution] = {}
        oracle_vector = observed["solutions"][solution]["vector"]
        for feature, predicted in vector.items():
            low, high = predicted["interval"]
            coverage[solution][feature] = {
                "interval": predicted["interval"],
                "observed": oracle_vector[feature],
                "within_interval": low <= oracle_vector[feature] <= high,
            }
    return coverage


def main():
    results = []
    policies = ("always_none", "always_expensive", "fixed_sequence", "adaptive")
    for workload_name, workload in WORKLOADS.items():
        keys = all_keys(workload["initial_n"])
        initial_analysis = current_state(workload, {})
        policy_results = {name: run_policy(name, workload, keys) for name in policies}
        observed = oracle(workload, keys)
        for result in policy_results.values():
            selected = result["final_state"]["decision"]["selected"]
            coverage = oracle_coverage(result["final_state"], observed)
            result["oracle_evaluation"] = {
                "oracle_selected": observed["selected"],
                "decision_correct": None if selected is None else selected == observed["selected"],
                "central_choice_initial": result["history"][0]["state"]["decision"]["ranking_by_central"][0],
                "dimension_coverage": coverage,
            }
            del result["final_state"]["vectors"]
        results.append({"workload": workload_name, "actions": ACTIONS,
                        "initial_analysis": initial_analysis,
                        "policies": policy_results, "oracle": observed})
        print(workload_name, "oracle=", observed["selected"])
        for name, result in policy_results.items():
            chosen = [step["chosen_action"] for step in result["history"] if step["chosen_action"]]
            print(f"  {name:16} actions={chosen} cost={result['total_acquisition_cost']} "
                  f"decision={result['final_state']['decision']['status']} "
                  f"selected={result['final_state']['decision']['selected']}")
            if name == "adaptive":
                for step in result["history"]:
                    if step["chosen_action"]:
                        evaluation = step["action_evaluations"][step["chosen_action"]]
                        print(f"    chose {step['chosen_action']}: {step['choice_reason']}; "
                              f"expected_cost={evaluation['expected_cost']} "
                              f"utility/cost={evaluation['decision_utility_per_cost']}")
                        print(f"      observation={step['observation']}")
    Path("poc7_measurements.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
