#!/usr/bin/env python3
"""POC 10 jetable: transfert des concepts Atlas vers un mini-batch."""

import itertools
import json
import math
import random
import time
from pathlib import Path


CHUNK_SIZE = 64
FEATURES = (
    "source_reads", "filter_tests", "records_passed", "source_batches",
    "transform_batches", "transform_work", "intermediate_writes",
    "intermediate_reads", "aggregate_calls", "aggregate_work",
    "output_writes", "reduction_reads", "peak_temp_records",
)

MECHANISMS = {
    "processing": ("item_by_item", "chunk64"),
    "handoff": ("fused", "materialized_filter"),
    "aggregation": ("incremental", "deferred_reduce"),
}

SCENARIOS = {
    "filter_heavy": {
        "n": 4096, "transform_cost": 2,
        "filter": "multiple_of_8", "expected_behavior": "low_selectivity",
    },
    "transform_heavy": {
        "n": 4096, "transform_cost": 8,
        "filter": "not_multiple_of_8", "expected_behavior": "high_selectivity",
    },
}

# Les poids sont synthétiques et ne représentent pas une machine mesurée.
PLATFORMS = {
    "throughput": {
        "memory_limit": 4096,
        "weights": {
            "source_reads": .2, "filter_tests": .1, "records_passed": 0,
            "source_batches": 8, "transform_batches": 30,
            "transform_work": 1, "intermediate_writes": 1.5,
            "intermediate_reads": 1, "aggregate_calls": 10,
            "aggregate_work": .3, "output_writes": 1.5,
            "reduction_reads": .5, "peak_temp_records": .02,
        },
    },
    "memory_tight": {
        "memory_limit": 1,
        "weights": {
            "source_reads": .2, "filter_tests": .1, "records_passed": 0,
            "source_batches": 8, "transform_batches": 30,
            "transform_work": 1, "intermediate_writes": 1.5,
            "intermediate_reads": 1, "aggregate_calls": 10,
            "aggregate_work": .3, "output_writes": 1.5,
            "reduction_reads": .5, "peak_temp_records": 2,
        },
    },
}

TRANSFER_REVIEW = {
    "transfers_naturally": [
        "besoin décrit par n, transformation, mémoire et filtre opaque",
        "espace généré par mécanismes fins et recherche exhaustive",
        "interactions dérivées avant coût scalaire",
        "vecteur algorithmique séparé du profil plateforme",
        "exact / bound / estimate avec hypothèses",
        "acquisition seulement si l'inconnue peut changer la décision",
    ],
    "requires_adaptation": [
        "le vecteur devient batches, matérialisations, agrégation et mémoire temporaire",
        "les interactions portent sur buffers simultanés et densification des survivants",
        "l'incertitude partagée de sélectivité doit être propagée de façon corrélée",
    ],
    "does_not_transfer": [
        "probes, slots, dispersion des clés et contrats spécifiques au hachage",
        "les contrats épistémiques multiples du POC 9 ne sont pas nécessaires ici",
    ],
}


def combinations():
    return list(itertools.product(*MECHANISMS.values()))


def label(combo):
    return "+".join(combo)


def analytical_vector(combo, scenario, passed):
    """Modèle batch calculé depuis les mécanismes et un nombre de survivants."""
    processing, handoff, aggregation = combo
    n = scenario["n"]
    source_batches = n if processing == "item_by_item" else math.ceil(n / CHUNK_SIZE)
    if processing == "item_by_item":
        transform_batches = passed
    elif handoff == "fused":
        # Un appel de transformation est lancé pour chaque chunk source,
        # même si aucun enregistrement ne survit dans le chunk.
        transform_batches = source_batches
    else:
        transform_batches = math.ceil(passed / CHUNK_SIZE)
    intermediate = passed if handoff == "materialized_filter" else 0
    if aggregation == "incremental":
        aggregate_calls, output = passed, 0
    else:
        aggregate_calls, output = (1 if passed else 0), passed
    base_buffer = 1 if processing == "item_by_item" else CHUNK_SIZE
    simultaneous_materializations = ((1 if handoff == "materialized_filter" else 0)
                                     + (1 if aggregation == "deferred_reduce" else 0))
    peak = max(base_buffer, passed * simultaneous_materializations)
    return {
        "source_reads": n,
        "filter_tests": n,
        "records_passed": passed,
        "source_batches": source_batches,
        "transform_batches": transform_batches,
        "transform_work": passed * scenario["transform_cost"],
        "intermediate_writes": intermediate,
        "intermediate_reads": intermediate,
        "aggregate_calls": aggregate_calls,
        "aggregate_work": passed,
        "output_writes": output,
        "reduction_reads": output,
        "peak_temp_records": peak,
    }


def vector_interval(combo, scenario, passed_interval, knowledge):
    low_passed, high_passed = passed_interval
    values = [analytical_vector(combo, scenario, passed)
              for passed in range(low_passed, high_passed + 1)]
    result = {}
    for feature in FEATURES:
        low = min(vector[feature] for vector in values)
        high = max(vector[feature] for vector in values)
        if low == high:
            status, assumptions = "exact", []
        else:
            status = knowledge["status"]
            assumptions = knowledge["assumptions"]
        result[feature] = {
            "status": status, "interval": [low, high],
            "assumptions": assumptions,
            "source": "mécanismes batch + interactions",
        }
    return result


def scalar_cost(vector, platform):
    return sum(vector[name] * platform["weights"][name] for name in FEATURES)


def decision(combo_space, scenario, platform, passed_interval):
    """Cherche une composition optimale pour chaque valeur encore possible."""
    winners = []
    robust_candidates = set(combo_space)
    for passed in range(passed_interval[0], passed_interval[1] + 1):
        vectors = {combo: analytical_vector(combo, scenario, passed) for combo in combo_space}
        admissible = [combo for combo in combo_space
                      if vectors[combo]["peak_temp_records"] <= platform["memory_limit"]]
        costs = {combo: scalar_cost(vectors[combo], platform) for combo in admissible}
        minimum = min(costs.values())
        optimal = {combo for combo, cost in costs.items() if abs(cost - minimum) < 1e-9}
        winners.append(sorted(label(combo) for combo in optimal))
        robust_candidates &= optimal
    selected = min(robust_candidates, key=label) if robust_candidates else None
    return {
        "status": "decidable" if selected else "needs_information",
        "selected": label(selected) if selected else None,
        "possible_winners": sorted({winner for group in winners for winner in group}),
        "passed_interval": list(passed_interval),
    }


def cost_summary(combo, scenario, platform, passed_interval):
    rows = []
    admissible_count = 0
    for passed in range(passed_interval[0], passed_interval[1] + 1):
        vector = analytical_vector(combo, scenario, passed)
        rows.append(scalar_cost(vector, platform))
        admissible_count += vector["peak_temp_records"] <= platform["memory_limit"]
    total = passed_interval[1] - passed_interval[0] + 1
    return {
        "interval": [round(min(rows), 2), round(max(rows), 2)],
        "admissibility": ("always" if admissible_count == total
                          else "never" if admissible_count == 0 else "conditional"),
    }


def source_records(n):
    return [(index, (index * 17 + 3) % 1009) for index in range(n)]


def keep_record(record, scenario):
    if scenario["filter"] == "multiple_of_8":
        return record[0] % 8 == 0
    return record[0] % 8 != 0


def transform_record(record, effort):
    value = record[1]
    for step in range(effort):
        value = (value * 3 + step + 1) % 1_000_003
    return value


def sample_selectivity(records, scenario, size=128):
    indexes = random.Random(71).sample(range(len(records)), size)
    passed = sum(keep_record(records[index], scenario) for index in indexes)
    rate = passed / size
    radius = .03  # contrat simple fixé avant observation
    low_rate, high_rate = max(0, rate - radius), min(1, rate + radius)
    return {
        "kind": "filter_selectivity_sample",
        "records_examined": size,
        "records_passed": passed,
        "observed_rate": round(rate, 6),
        "contract": {
            "status": "estimate",
            "assumptions": ["échantillon représentatif de la source"],
            "rate_interval": [round(low_rate, 6), round(high_rate, 6)],
        },
        "passed_interval": [math.floor(low_rate * len(records)),
                            math.ceil(high_rate * len(records))],
        "acquisition_cost": size,
    }


def empty_observed():
    return {feature: 0 for feature in FEATURES}


def execute(combo, records, scenario):
    """Exécution instrumentée sans appeler le modèle analytique."""
    processing, handoff, aggregation = combo
    stats = empty_observed()
    filtered = []
    outputs = []
    aggregate = 0
    base_buffer = 1 if processing == "item_by_item" else CHUNK_SIZE
    stats["peak_temp_records"] = base_buffer

    def update_peak():
        temporary = len(filtered) + len(outputs)
        stats["peak_temp_records"] = max(stats["peak_temp_records"], temporary)

    def consume(record):
        nonlocal aggregate
        value = transform_record(record, scenario["transform_cost"])
        stats["transform_work"] += scenario["transform_cost"]
        if aggregation == "incremental":
            stats["aggregate_calls"] += 1
            stats["aggregate_work"] += 1
            aggregate += value
        else:
            outputs.append(value)
            stats["output_writes"] += 1
            update_peak()

    if handoff == "materialized_filter":
        step = 1 if processing == "item_by_item" else CHUNK_SIZE
        for start in range(0, len(records), step):
            stats["source_batches"] += 1
            for record in records[start:start + step]:
                stats["source_reads"] += 1
                stats["filter_tests"] += 1
                if keep_record(record, scenario):
                    filtered.append(record)
                    stats["records_passed"] += 1
                    stats["intermediate_writes"] += 1
                    update_peak()
        transform_step = 1 if processing == "item_by_item" else CHUNK_SIZE
        for start in range(0, len(filtered), transform_step):
            stats["transform_batches"] += 1
            for record in filtered[start:start + transform_step]:
                stats["intermediate_reads"] += 1
                consume(record)
    else:
        step = 1 if processing == "item_by_item" else CHUNK_SIZE
        for start in range(0, len(records), step):
            stats["source_batches"] += 1
            batch = []
            for record in records[start:start + step]:
                stats["source_reads"] += 1
                stats["filter_tests"] += 1
                if keep_record(record, scenario):
                    stats["records_passed"] += 1
                    batch.append(record)
            if processing == "chunk64":
                stats["transform_batches"] += 1
            for record in batch:
                if processing == "item_by_item":
                    stats["transform_batches"] += 1
                consume(record)

    if aggregation == "deferred_reduce" and outputs:
        stats["aggregate_calls"] += 1
        for value in outputs:
            stats["reduction_reads"] += 1
            stats["aggregate_work"] += 1
            aggregate += value
    return stats, aggregate


def compare_vector(predicted, observed):
    result = {}
    for feature in FEATURES:
        low, high = predicted[feature]["interval"]
        result[feature] = {
            "status": predicted[feature]["status"],
            "interval": predicted[feature]["interval"],
            "observed": observed[feature],
            "within_interval": low <= observed[feature] <= high,
        }
    return result


def run():
    combo_space = combinations()
    print("combinaisons générées:")
    for combo in combo_space:
        print(" ", label(combo))
    results = []
    for scenario_name, scenario in SCENARIOS.items():
        records = source_records(scenario["n"])
        executions = {}
        for combo in combo_space:
            start = time.perf_counter_ns()
            observed, checksum = execute(combo, records, scenario)
            executions[label(combo)] = {
                "vector": observed, "checksum": checksum,
                "wall_ns": time.perf_counter_ns() - start,
            }
        for platform_name, platform in PLATFORMS.items():
            knowledge = {"status": "bound", "assumptions": ["sélectivité inconnue"]}
            passed_interval = (0, scenario["n"])
            initial = decision(combo_space, scenario, platform, passed_interval)
            acquisition = None
            final = initial
            if initial["status"] == "needs_information":
                acquisition = sample_selectivity(records, scenario)
                passed_interval = tuple(acquisition["passed_interval"])
                knowledge = {"status": "estimate",
                             "assumptions": acquisition["contract"]["assumptions"]}
                final = decision(combo_space, scenario, platform, passed_interval)
            final_vectors = {label(combo): vector_interval(
                combo, scenario, passed_interval, knowledge) for combo in combo_space}
            summaries = {label(combo): cost_summary(
                combo, scenario, platform, passed_interval) for combo in combo_space}
            observed_admissible = {
                name: row for name, row in executions.items()
                if row["vector"]["peak_temp_records"] <= platform["memory_limit"]
            }
            oracle_selected = min(
                observed_admissible,
                key=lambda name: (scalar_cost(observed_admissible[name]["vector"], platform), name))
            observed_costs = {name: round(scalar_cost(row["vector"], platform), 2)
                              for name, row in executions.items()}
            comparisons = {name: compare_vector(final_vectors[name], executions[name]["vector"])
                           for name in executions}
            all_covered = all(
                item["within_interval"]
                for solution in comparisons.values() for item in solution.values())
            exact_at_observed = all(
                analytical_vector(combo, scenario,
                                  executions[label(combo)]["vector"]["records_passed"])
                == executions[label(combo)]["vector"]
                for combo in combo_space)
            selected = final["selected"]
            results.append({
                "scenario": scenario_name, "platform": platform_name,
                "platform_profile": platform,
                "mechanisms": MECHANISMS,
                "initial": {"decision": initial},
                "decision_sensitive_unknown": {
                    "name": "filter_selectivity",
                    "affects": ["records_passed", "transform_batches", "transform_work",
                                "materializations", "aggregation", "peak_temp_records"],
                },
                "acquisition": acquisition,
                "final": {"decision": final,
                          "selected_predicted_vector": final_vectors[selected],
                          "cost_summaries": summaries},
                "oracle": {"selected": oracle_selected,
                           "observed_costs": observed_costs,
                           "selected_observed_vector": executions[selected]["vector"],
                           "checksums": {name: row["checksum"] for name, row in executions.items()},
                           "wall_ns": {name: row["wall_ns"] for name, row in executions.items()},
                           "decision_correct": final["selected"] == oracle_selected,
                           "selected_vector_comparison": comparisons[selected],
                           "all_vector_intervals_cover_observations": all_covered,
                           "all_exact_vectors_match_at_observed_selectivity": exact_at_observed},
            })
            print(f"{scenario_name:15} / {platform_name:12}: "
                  f"initial={initial['status']} acquired="
                  f"{acquisition['records_examined'] if acquisition else 0} "
                  f"selected={final['selected']} oracle={oracle_selected}")
    Path("poc10_measurements.json").write_text(json.dumps(
        {"experiments": results, "transfer_review": TRANSFER_REVIEW}, indent=2) + "\n")


if __name__ == "__main__":
    run()
