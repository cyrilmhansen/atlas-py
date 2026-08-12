#!/usr/bin/env python3
"""POC 11: analyze mechanisms extracted after two foreign sources were frozen."""

import argparse
import hashlib
import importlib
import itertools
import json
import math
import time
from pathlib import Path


AXES = {
    "handoff": ("fused_handoff", "retained_handoff"),
    "dispatch": ("per_record_dispatch", "compact_block64_dispatch"),
    "reduction": ("running_reduction", "deferred_reduction"),
}

SCENARIOS = {
    "sparse_memory": {"count": 4096, "accepted": 512, "effort": 2,
                      "memory_limit": 600},
    "dense_throughput": {"count": 4096, "accepted": 3584, "effort": 8,
                         "memory_limit": 8000},
}

WEIGHTS = {
    "filter_tests": .1, "transform_work": 1,
    "transform_dispatches": 30, "retained_writes": 1.5,
    "retained_reads": 1, "aggregate_updates": 10,
    "output_writes": 1.5, "reduction_reads": .5,
    "reduction_calls": 10, "peak_temp_records": .02,
}

SOURCES = {
    "A": "fused_handoff+per_record_dispatch+running_reduction",
    "B": "retained_handoff+compact_block64_dispatch+deferred_reduction",
    "C": "retained_handoff+compact_block64_dispatch+running_reduction",
}


def valid(combo):
    handoff, dispatch, _ = combo
    return not (dispatch == "compact_block64_dispatch"
                and handoff != "retained_handoff")


def combinations():
    return [combo for combo in itertools.product(*AXES.values()) if valid(combo)]


def label(combo):
    return "+".join(combo)


def vector(combo, scenario):
    handoff, dispatch, reduction = combo
    passed = scenario["accepted"]
    retained = passed if handoff == "retained_handoff" else 0
    dispatches = (passed if dispatch == "per_record_dispatch"
                  else math.ceil(passed / 64))
    if reduction == "running_reduction":
        aggregate_updates, output, reduction_calls = passed, 0, 0
    else:
        aggregate_updates, output, reduction_calls = 0, passed, 1 if passed else 0
    working = 1 if dispatch == "per_record_dispatch" else min(64, passed)
    if retained and output:
        peak = retained + output
    elif retained:
        peak = retained + working
    elif output:
        peak = output
    else:
        peak = working
    return {
        "filter_tests": scenario["count"],
        "transform_work": passed * scenario["effort"],
        "transform_dispatches": dispatches,
        "retained_writes": retained,
        "retained_reads": retained,
        "aggregate_updates": aggregate_updates,
        "output_writes": output,
        "reduction_reads": output,
        "reduction_calls": reduction_calls,
        "peak_temp_records": peak,
    }


def cost(features):
    return sum(features[name] * WEIGHTS[name] for name in WEIGHTS)


def frozen_hashes_ok():
    expected = json.loads(Path("poc11_fixtures.json").read_text())
    actual = {}
    for filename, digest in expected.items():
        if filename == "functional_results":
            continue
        actual[filename] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        if actual[filename] != digest:
            raise RuntimeError(f"frozen fixture changed: {filename}")
    return actual


def predict():
    frozen_hashes_ok()
    space = combinations()
    predictions = {}
    for scenario_name, scenario in SCENARIOS.items():
        rows = {}
        for combo in space:
            features = vector(combo, scenario)
            rows[label(combo)] = {
                "features": features,
                "admissible": features["peak_temp_records"] <= scenario["memory_limit"],
                "cost": round(cost(features), 2),
            }
        admissible = {name: row for name, row in rows.items() if row["admissible"]}
        selected = min(admissible, key=lambda name: (admissible[name]["cost"], name))
        predictions[scenario_name] = {"selected": selected, "compositions": rows}
        print(f"{scenario_name}: {selected}")
    return predictions


def blank_observation():
    return {name: 0 for name in WEIGHTS}


def observe_a(scenario):
    module = importlib.import_module("poc11_source_a")
    observed = blank_observation()
    original_keep = module.keep
    original_transform = module.transform

    def keep(record, mode):
        observed["filter_tests"] += 1
        return original_keep(record, mode)

    def transform(record, effort):
        observed["transform_dispatches"] += 1
        observed["transform_work"] += effort
        result = original_transform(record, effort)
        observed["aggregate_updates"] += 1
        return result

    module.keep = keep
    module.transform = transform
    started = time.perf_counter_ns()
    try:
        result = module.run(scenario["count"], scenario["mode"], scenario["effort"])
    finally:
        elapsed = time.perf_counter_ns() - started
        module.keep = original_keep
        module.transform = original_transform
    observed["peak_temp_records"] = 1 if result["accepted"] else 0
    return result, observed, elapsed


def observe_b(scenario):
    module = importlib.import_module("poc11_source_b")
    observed = blank_observation()
    original_select = module.select
    original_convert = module.convert

    def select(data, mode):
        observed["filter_tests"] += len(data)
        result = original_select(data, mode)
        observed["retained_writes"] += len(result)
        return result

    def convert(block, effort):
        observed["transform_dispatches"] += 1
        observed["retained_reads"] += len(block)
        observed["transform_work"] += len(block) * effort
        result = original_convert(block, effort)
        observed["output_writes"] += len(result)
        return result

    module.select = select
    module.convert = convert
    started = time.perf_counter_ns()
    try:
        result = module.run(scenario["count"], scenario["mode"], scenario["effort"])
    finally:
        elapsed = time.perf_counter_ns() - started
        module.select = original_select
        module.convert = original_convert
    observed["reduction_reads"] = observed["output_writes"]
    observed["reduction_calls"] = 1 if result["accepted"] else 0
    observed["peak_temp_records"] = 2 * result["accepted"]
    return result, observed, elapsed


def observe_c(scenario):
    module = importlib.import_module("poc11_source_c")
    observed = blank_observation()
    original_select = module.select
    original_transform = module.transform_block

    def select(data, mode):
        observed["filter_tests"] += len(data)
        result = original_select(data, mode)
        observed["retained_writes"] += len(result)
        return result

    def transform_block(block, effort):
        observed["transform_dispatches"] += 1
        observed["retained_reads"] += len(block)
        observed["transform_work"] += len(block) * effort
        result = original_transform(block, effort)
        observed["aggregate_updates"] += len(result)
        return result

    module.select = select
    module.transform_block = transform_block
    started = time.perf_counter_ns()
    try:
        result = module.run(scenario["count"], scenario["mode"], scenario["effort"])
    finally:
        elapsed = time.perf_counter_ns() - started
        module.select = original_select
        module.transform_block = original_transform
    accepted = result["accepted"]
    observed["peak_temp_records"] = accepted + min(module.BLOCK, accepted)
    return result, observed, elapsed


def differences(predicted, observed):
    return {name: observed[name] - predicted[name]
            for name in predicted if observed[name] != predicted[name]}


def execute(predictions):
    expected = json.loads(Path("poc11_fixtures.json").read_text())
    observers = {"A": observe_a, "B": observe_b, "C": observe_c}
    measurements = {
        "frozen_hashes": frozen_hashes_ok(),
        "fixture_equivalence": expected["functional_results"],
        "source_compositions": SOURCES,
        "composition_count": len(combinations()),
        "scenarios": {},
    }
    for scenario_name, base in SCENARIOS.items():
        mode = "sparse" if scenario_name == "sparse_memory" else "dense"
        scenario = dict(base, mode=mode)
        rows = {}
        expected_result = expected["functional_results"][mode]
        for source_name, observer in observers.items():
            composition = SOURCES[source_name]
            predicted = predictions[scenario_name]["compositions"][composition]
            result, observed, elapsed = observer(scenario)
            if result != expected_result:
                raise AssertionError(f"semantic mismatch for {source_name}: {result}")
            delta = differences(predicted["features"], observed)
            rows[source_name] = {
                "composition": composition,
                "result": result,
                "predicted_vector": predicted["features"],
                "observed_vector": observed,
                "differences": delta,
                "vector_equal": not delta,
                "predicted_cost": predicted["cost"],
                "observed_cost": round(cost(observed), 2),
                "admissible": observed["peak_temp_records"] <= scenario["memory_limit"],
                "wall_time_ns_secondary": elapsed,
            }
        oracle_candidates = {name: row for name, row in rows.items()
                             if row["admissible"]}
        oracle_best = min(oracle_candidates,
                          key=lambda name: (oracle_candidates[name]["observed_cost"],
                                            name))
        measurements["scenarios"][scenario_name] = {
            "workload": scenario,
            "model_selected": predictions[scenario_name]["selected"],
            "oracle_best_source": oracle_best,
            "selection_verified": (
                predictions[scenario_name]["selected"]
                == SOURCES[oracle_best]
            ),
            "executed_sources": rows,
            "generated_space": predictions[scenario_name]["compositions"],
        }
        print(f"{scenario_name}: model={predictions[scenario_name]['selected']} "
              f"oracle={oracle_best}")
    return measurements


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--predict-only", action="store_true")
    args = parser.parse_args()
    predictions = predict()
    Path("poc11_predictions.json").write_text(json.dumps(predictions, indent=2) + "\n")
    if not args.predict_only:
        results = execute(predictions)
        Path("poc11_measurements.json").write_text(
            json.dumps(results, indent=2) + "\n"
        )
