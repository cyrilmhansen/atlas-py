#!/usr/bin/env python3
"""POC 8 jetable: dériver la pertinence d'une observation par dépendances."""

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
    "sorted+binary_lookup+dense_walk": {"storage": "sorted", "auxiliary": False},
    "hash+linear_probe+dense_view": {"storage": "hash", "auxiliary": True},
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

# Graphe local suffisant pour cette expérience, pas un moteur causal générique.
DEPENDENCIES = {
    "sorted_search_depth": ["comparisons", "random_accesses"],
    "hash_dispersion": ["probe_count"],
    "probe_count": ["comparisons", "probes", "random_accesses"],
}

# Les actions déclarent uniquement ce qu'elles observent, leur taille et leur
# travail minimal connu. Aucune note de directness ou de réduction attendue.
ACTIONS = {
    "sample16": {"observes": "hash_dispersion", "kind": "sample", "size": 16},
    "sample64": {"observes": "hash_dispersion", "kind": "sample", "size": 64},
    "probe16": {"observes": "probe_count", "kind": "probe", "size": 16},
    "probe64": {"observes": "probe_count", "kind": "probe", "size": 64},
}

MANUAL_POC7 = {
    "sample16": {"reduction": .15, "directness": .3},
    "sample64": {"reduction": .50, "directness": .5},
    "probe16": {"reduction": .75, "directness": .9},
    "probe64": {"reduction": .95, "directness": 1.0},
}


def capacity_for(count):
    capacity = 1
    while capacity < count * 2:
        capacity *= 2
    return capacity


def dim(status, central, low, high, cause, assumptions, source):
    return {
        "status": status,
        "central": round(central, 2),
        "interval": [round(low, 2), round(high, 2)],
        "cause": cause,
        "assumptions": assumptions,
        "source": source,
    }


def largest_probe(observations):
    probes = [item for item in observations.values() if item["observes"] == "probe_count"]
    return max(probes, key=lambda item: item["size"], default=None)


def analyze(description, workload, observations):
    n = workload["initial_n"]
    final_n = n + workload["insert"]
    accesses = workload["lookup"] + workload["update"]
    vector = {}
    if description["storage"] == "sorted":
        low = accesses
        high = accesses * (math.ceil(math.log2(n)) + 2)
        central = accesses * (math.ceil(math.log2(n)) + 1)
        vector["comparisons"] = dim(
            "bound", central, low, high, "sorted_search_depth",
            ["clés triées"], "borne dichotomique")
        vector["random_accesses"] = dim(
            "bound", central, low, high, "sorted_search_depth",
            ["un accès par comparaison"], "borne dérivée")
        vector["probes"] = dim("exact", 0, 0, 0, None, [], "aucun probing")
        cells, allocations = final_n * 2, 2
    else:
        capacity = capacity_for(final_n)
        events = n + workload["insert"] + accesses
        alpha = final_n / capacity
        successful = .5 * (1 + 1 / (1 - alpha))
        unsuccessful = .5 * (1 + 1 / ((1 - alpha) ** 2))
        uniform = (n + workload["insert"]) * unsuccessful + accesses * successful
        probe = largest_probe(observations)
        if probe:
            scale = final_n / probe["size"]
            mean = 1 + (probe["mean_probes"] - 1) * scale
            relative_radius = 1 / math.sqrt(probe["size"])
            low = events * max(1, mean * (1 - relative_radius))
            high = events * mean * (1 + relative_radius)
            central = events * mean
            source = f"probe direct sur {probe['size']} clés"
            assumptions = ["échantillon représentatif", "rayon relatif 1/√k"]
        else:
            low, high, central = events, events * final_n, uniform
            source = "facteur de charge seul"
            assumptions = ["dispersion uniforme non vérifiée"]
        for feature in ("comparisons", "probes", "random_accesses"):
            vector[feature] = dim(
                "estimate", central, low, high, "probe_count", assumptions, source)
        cells, allocations = capacity * 3 + final_n, 4

    reads = workload["walk"] * final_n
    vector["sequential_reads"] = dim(
        "exact", reads, reads, reads, None,
        ["parcours après insertions"], "taille × parcours")
    base = n * 2 + workload["update"] + workload["insert"] * 2
    vector["base_writes"] = dim(
        "exact", base, base, base, None, [], "maintenance primaire")
    auxiliary = base if description["auxiliary"] else 0
    vector["auxiliary_writes"] = dim(
        "exact", auxiliary, auxiliary, auxiliary, None,
        ["vue miroir" if auxiliary else "aucune vue"], "maintenance auxiliaire")
    vector["reserved_cells"] = dim(
        "exact", cells, cells, cells, None, [], "capacité déclarée")
    vector["allocations"] = dim(
        "exact", allocations, allocations, allocations, None, [], "tableaux")
    return vector


def cost_interval(vector):
    return {
        "central": round(sum(vector[f]["central"] * PLATFORM[f] for f in FEATURES), 2),
        "interval": [
            round(sum(vector[f]["interval"][0] * PLATFORM[f] for f in FEATURES), 2),
            round(sum(vector[f]["interval"][1] * PLATFORM[f] for f in FEATURES), 2),
        ],
    }


def state(workload, observations):
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
    decision = {"status": "decidable" if selected else "needs_information",
                "selected": selected, "ranking_by_central": ranking}
    return {"vectors": vectors, "costs": costs, "decision": decision}


def descendants(node):
    result = set()
    frontier = [node]
    while frontier:
        current = frontier.pop()
        for child in DEPENDENCIES.get(current, []):
            if child not in result:
                result.add(child)
                frontier.append(child)
    return result


def decision_causes(current):
    """Remonte les largeurs pondérées qui peuvent encore changer le classement."""
    if current["decision"]["status"] == "decidable":
        return {"overlap": 0, "dimensions": [], "causes": []}
    names = list(SOLUTIONS)
    first, second = names[0], names[1]
    overlap = max(0, min(current["costs"][first]["interval"][1],
                         current["costs"][second]["interval"][1])
                  - max(current["costs"][first]["interval"][0],
                        current["costs"][second]["interval"][0]))
    dimensions = []
    cause_widths = {}
    for solution, vector in current["vectors"].items():
        for feature, item in vector.items():
            width = item["interval"][1] - item["interval"][0]
            contribution = width * PLATFORM[feature]
            if contribution > 0:
                cause = item["cause"]
                dimensions.append({
                    "solution": solution, "feature": feature,
                    "cause": cause,
                    "weighted_width": round(contribution, 2),
                })
                if cause:
                    cause_widths[cause] = cause_widths.get(cause, 0) + contribution
    decision_causes = {cause for cause, width in cause_widths.items() if width >= overlap}
    for item in dimensions:
        item["can_change_ranking"] = item["cause"] in decision_causes
    return {"overlap": round(overlap, 2),
            "dimensions": sorted(dimensions, key=lambda item: -item["weighted_width"]),
            "cause_weighted_widths": {cause: round(width, 2)
                                      for cause, width in sorted(cause_widths.items())},
            "causes": sorted(decision_causes)}


def projection_for_probe(action, workload, current):
    """Teste les observations extrêmes possibles, jamais le résultat futur réel."""
    size = action["size"]
    events = (workload["initial_n"] + workload["insert"]
              + workload["lookup"] + workload["update"])
    final_n = workload["initial_n"] + workload["insert"]
    radius = 1 / math.sqrt(size)
    outcomes = []
    for possible_mean in (1, size):
        extrapolated = 1 + (possible_mean - 1) * final_n / size
        low = events * max(1, extrapolated * (1 - radius))
        high = events * extrapolated * (1 + radius)
        hash_vector = current["vectors"]["hash+linear_probe+dense_view"]
        projected = {feature: dict(value) for feature, value in hash_vector.items()}
        for feature in ("comparisons", "probes", "random_accesses"):
            projected[feature] = dict(projected[feature])
            projected[feature]["interval"] = [low, high]
            projected[feature]["central"] = events * extrapolated
        costs = dict(current["costs"])
        costs["hash+linear_probe+dense_view"] = cost_interval(projected)
        sorted_cost = costs["sorted+binary_lookup+dense_walk"]["interval"]
        hash_cost = costs["hash+linear_probe+dense_view"]["interval"]
        robust = hash_cost[1] < sorted_cost[0] or sorted_cost[1] < hash_cost[0]
        outcomes.append({"possible_sample_mean": possible_mean,
                         "hash_cost_interval": hash_cost, "robust": robust})
    return {"mechanical_radius": round(radius, 4), "possible_outcomes": outcomes,
            "could_make_robust": any(item["robust"] for item in outcomes)}


def evaluate_structural_actions(current, workload, available):
    causes = decision_causes(current)
    evaluations = {}
    for name in available:
        action = ACTIONS[name]
        affected = descendants(action["observes"]) | {action["observes"]}
        relevant_causes = sorted(set(causes["causes"]) & affected)
        expected_minimum_cost = action["size"] if action["kind"] == "sample" else action["size"] * 2
        if action["observes"] == "probe_count" and relevant_causes:
            projection = projection_for_probe(action, workload, current)
            quantitative = True
            limitation = None
        elif relevant_causes:
            projection = None
            quantitative = False
            limitation = "aucune traduction déclarée de hash_dispersion vers un intervalle de probe_count"
        else:
            projection = None
            quantitative = False
            limitation = "aucune cause décisionnelle atteinte"
        evaluations[name] = {
            "observes": action["observes"],
            "affected_nodes": sorted(affected),
            "relevant_causes": relevant_causes,
            "expected_minimum_cost": expected_minimum_cost,
            "can_produce_quantitative_interval": quantitative,
            "projection": projection,
            "limitation": limitation,
        }
    return causes, evaluations


def choose_structural(current, workload, available):
    causes, evaluations = evaluate_structural_actions(current, workload, available)
    capable = [name for name in available
               if evaluations[name]["can_produce_quantitative_interval"]
               and evaluations[name]["projection"]["could_make_robust"]]
    if not capable:
        return None, "aucune action structurellement susceptible de suffire", causes, evaluations
    chosen = min(capable, key=lambda name: (evaluations[name]["expected_minimum_cost"], name))
    return chosen, "observation quantitative pertinente la moins coûteuse susceptible de suffire", causes, evaluations


def keys_for(n):
    return [index * 64 for index in range(n)]


def sample_from(keys, size):
    indexes = list(range(len(keys)))
    random.Random(43).shuffle(indexes)
    return [keys[index] for index in indexes[:size]]


def acquire(name, keys, final_count):
    action = ACTIONS[name]
    sample = sample_from(keys, action["size"])
    capacity = capacity_for(final_count)
    if action["kind"] == "sample":
        buckets = {}
        for key in sample:
            home = key % capacity
            buckets[home] = buckets.get(home, 0) + 1
        observation = {"observes": "hash_dispersion", "kind": "sample",
                       "size": len(sample), "distinct_home_buckets": len(buckets),
                       "max_home_bucket": max(buckets.values())}
        cost = len(sample)
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
        observation = {"observes": "probe_count", "kind": "probe",
                       "size": len(sample), "mean_probes": round(sum(probes) / len(probes), 4),
                       "max_probes": max(probes), "total_probes": sum(probes)}
        cost = len(sample) + sum(probes)
        work = {"keys_inspected": 0, "insertions": len(sample), "probes": sum(probes)}
    return observation, cost, work


def manual_choice(current, available):
    first, second = list(SOLUTIONS)
    overlap = max(0, min(current["costs"][first]["interval"][1],
                         current["costs"][second]["interval"][1])
                  - max(current["costs"][first]["interval"][0],
                        current["costs"][second]["interval"][0]))
    scores = {}
    for name in available:
        action = ACTIONS[name]
        expected_cost = action["size"] if action["kind"] == "sample" else action["size"] * 2
        manual = MANUAL_POC7[name]
        scores[name] = overlap * manual["reduction"] * manual["directness"] / expected_cost
    return max(available, key=lambda name: (scores[name], -ACTIONS[name]["size"], name)), scores


def run_policy(policy, workload, keys):
    observations = {}
    available = list(ACTIONS)
    history = []
    total_cost = 0
    while True:
        current = state(workload, observations)
        record = {"costs": current["costs"], "decision": current["decision"],
                  "chosen_action": None, "reason": None, "causal_analysis": None,
                  "action_evaluations": None, "observation": None,
                  "acquisition_cost": 0}
        if policy == "always_expensive" and not history:
            chosen, reason = "probe64", "baseline imposée"
        elif current["decision"]["status"] == "decidable":
            history.append(record)
            break
        elif policy == "always_none":
            history.append(record)
            break
        elif policy == "poc7_manual":
            chosen, scores = manual_choice(current, available)
            reason = f"score manuel maximal; scores={scores}"
        else:
            chosen, reason, causes, evaluations = choose_structural(current, workload, available)
            record["causal_analysis"] = causes
            record["action_evaluations"] = evaluations
            if chosen is None:
                history.append(record)
                break
        observation, cost, work = acquire(
            chosen, keys, workload["initial_n"] + workload["insert"])
        observations[chosen] = observation
        available.remove(chosen)
        total_cost += cost
        record.update({"chosen_action": chosen, "reason": reason,
                       "observation": observation, "acquisition_cost": cost,
                       "acquisition_work": work})
        history.append(record)
        if len(history) > len(ACTIONS):
            break
    final = state(workload, observations)
    if final["decision"]["status"] != "decidable":
        final["decision"]["status"] = "undetermined"
    return {"policy": policy, "history": history, "observations": observations,
            "total_acquisition_cost": total_cost, "actions_count": len(observations),
            "final_state": final}


def workload_operations(workload, keys):
    shuffled = keys[:]
    random.Random(47).shuffle(shuffled)
    result = [("lookup", key) for key in shuffled[:workload["lookup"]]]
    result += [("update", key) for key in shuffled[-workload["update"]:]]
    result += [("insert", (workload["initial_n"] + index) * 64)
               for index in range(workload["insert"])]
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
        capacity = 1
        while capacity < (len(keys) + inserts) * 2:
            capacity *= 2
        self.keys = [None] * capacity
        self.values = [None] * capacity
        self.positions = [None] * capacity
        self.dense = [None] * (len(keys) + inserts)
        self.size = 0
        self.stats = {feature: 0 for feature in FEATURES}
        self.stats["reserved_cells"], self.stats["allocations"] = capacity * 3 + len(self.dense), 4
        for key in keys:
            slot = self.locate(key)
            self.keys[slot], self.values[slot] = key, key * 2
            self.positions[slot], self.dense[self.size] = self.size, key * 2
            self.stats["base_writes"] += 2
            self.stats["auxiliary_writes"] += 2
            self.size += 1

    def locate(self, key):
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
            slot = self.locate(key)
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
    operations = workload_operations(workload, keys)
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


def coverage(final, observed):
    result = {}
    for solution, vector in final["vectors"].items():
        result[solution] = {}
        for feature, predicted in vector.items():
            value = observed["solutions"][solution]["vector"][feature]
            low, high = predicted["interval"]
            result[solution][feature] = {"interval": predicted["interval"],
                                         "observed": value,
                                         "within_interval": low <= value <= high}
    return result


def main():
    policies = ("always_none", "always_expensive", "poc7_manual", "structural")
    results = []
    for workload_name, workload in WORKLOADS.items():
        keys = keys_for(workload["initial_n"])
        policies_result = {name: run_policy(name, workload, keys) for name in policies}
        observed = oracle(workload, keys)
        for result in policies_result.values():
            selected = result["final_state"]["decision"]["selected"]
            result["oracle_evaluation"] = {
                "oracle_selected": observed["selected"],
                "decision_correct": None if selected is None else selected == observed["selected"],
                "dimension_coverage": coverage(result["final_state"], observed),
            }
            del result["final_state"]["vectors"]
        results.append({"workload": workload_name, "dependencies": DEPENDENCIES,
                        "actions": ACTIONS, "policies": policies_result,
                        "oracle": observed})
        print(workload_name, "oracle=", observed["selected"])
        for policy, result in policies_result.items():
            actions = [step["chosen_action"] for step in result["history"] if step["chosen_action"]]
            print(f"  {policy:16} actions={actions} cost={result['total_acquisition_cost']} "
                  f"decision={result['final_state']['decision']['status']} "
                  f"selected={result['final_state']['decision']['selected']}")
            if policy == "structural":
                for step in result["history"]:
                    if step["causal_analysis"]:
                        print(f"    causes={step['causal_analysis']['causes']} "
                              f"dimensions={[(d['feature'], d['weighted_width']) for d in step['causal_analysis']['dimensions']]}")
                    if step["chosen_action"]:
                        print(f"    chose {step['chosen_action']}: {step['reason']}")
                        print(f"      observation={step['observation']}")
    Path("poc8_measurements.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
