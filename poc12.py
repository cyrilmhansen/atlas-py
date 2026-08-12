#!/usr/bin/env python3
"""POC 12: compare consequences of two legitimate, non-isomorphic extractions."""

import hashlib
import importlib
import itertools
import json
import math
from pathlib import Path


SCENARIOS = {
    "sparse_memory": {
        "count": 4096, "mode": "sparse", "survivors": 512,
        "effort": 2, "memory_limit": 600,
    },
    "dense_throughput": {
        "count": 4096, "mode": "dense", "survivors": 3584,
        "effort": 8, "memory_limit": 8000,
    },
}

X_AXES = {
    "handoff": ("fused_handoff", "retained_handoff"),
    "dispatch": ("per_record_dispatch", "compact_block64_dispatch"),
    "reduction": ("running_reduction", "deferred_reduction"),
}

Y_AXES = {
    "feed_shape": ("direct_item_feed", "compacted_batch_feed"),
    "completion": ("rolling_fold", "collected_finish"),
}

X_WEIGHTS = {
    "filter_tests": .1,
    "transform_work": 1,
    "transform_dispatches": 30,
    "retained_writes": 1.5,
    "retained_reads": 1,
    "aggregate_updates": 10,
    "output_writes": 1.5,
    "reduction_reads": .5,
    "reduction_calls": 10,
    "peak_temp_records": .02,
}

# Y deliberately uses different dimensions. Paired traffic is valued by its
# combined source-observed work, not expanded into X's read/write vocabulary.
Y_WEIGHTS = {
    "records_examined": .1,
    "map_effort": 1,
    "map_groups": 30,
    "staging_traffic": 1.25,
    "fold_events": 10,
    "completion_traffic": 1,
    "finish_operations": 10,
    "max_live_values": .02,
}


def checked_fixture_hashes():
    extraction = json.loads(Path("poc12_extractions.json").read_text())
    actual = {}
    for filename, expected in extraction["fixture_hashes"].items():
        digest = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        if digest != expected:
            raise RuntimeError(f"frozen fixture changed: {filename}")
        actual[filename] = digest
    return actual


def x_space():
    result = []
    for combo in itertools.product(*X_AXES.values()):
        handoff, dispatch, _ = combo
        if dispatch == "compact_block64_dispatch" and handoff != "retained_handoff":
            continue
        result.append(combo)
    return result


def y_space():
    return list(itertools.product(*Y_AXES.values()))


def x_vector(combo, scenario):
    handoff, dispatch, reduction = combo
    survivors = scenario["survivors"]
    retained = survivors if handoff == "retained_handoff" else 0
    dispatches = (survivors if dispatch == "per_record_dispatch"
                  else math.ceil(survivors / 64))
    working = 1 if dispatch == "per_record_dispatch" else min(64, survivors)
    if reduction == "running_reduction":
        updates, output, calls = survivors, 0, 0
    else:
        updates, output, calls = 0, survivors, 1 if survivors else 0
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
        "transform_work": survivors * scenario["effort"],
        "transform_dispatches": dispatches,
        "retained_writes": retained,
        "retained_reads": retained,
        "aggregate_updates": updates,
        "output_writes": output,
        "reduction_reads": output,
        "reduction_calls": calls,
        "peak_temp_records": peak,
    }


def y_vector(combo, scenario):
    feed, completion = combo
    survivors = scenario["survivors"]
    compacted = feed == "compacted_batch_feed"
    collected = completion == "collected_finish"
    groups = math.ceil(survivors / 64) if compacted else survivors
    staging_traffic = 2 * survivors if compacted else 0
    completion_traffic = 2 * survivors if collected else 0
    fold_events = 0 if collected else survivors
    finish_operations = 1 if collected and survivors else 0
    if compacted and collected:
        live = 2 * survivors
    elif compacted:
        live = survivors + min(64, survivors)
    elif collected:
        live = survivors
    else:
        live = 1 if survivors else 0
    return {
        "records_examined": scenario["count"],
        "map_effort": survivors * scenario["effort"],
        "map_groups": groups,
        "staging_traffic": staging_traffic,
        "fold_events": fold_events,
        "completion_traffic": completion_traffic,
        "finish_operations": finish_operations,
        "max_live_values": live,
    }


def weighted_cost(vector, weights):
    return round(sum(vector[name] * weight for name, weight in weights.items()), 2)


def x_signature(combo):
    handoff, dispatch, reduction = combo
    return {
        "retains_survivors": handoff == "retained_handoff",
        "transform_group": 64 if dispatch == "compact_block64_dispatch" else 1,
        "buffers_outputs": reduction == "deferred_reduction",
        "reduction": "terminal" if reduction == "deferred_reduction" else "rolling",
    }


def y_signature(combo):
    feed, completion = combo
    return {
        "retains_survivors": feed == "compacted_batch_feed",
        "transform_group": 64 if feed == "compacted_batch_feed" else 1,
        "buffers_outputs": completion == "collected_finish",
        "reduction": "terminal" if completion == "collected_finish" else "rolling",
    }


def x_audit(vector):
    return {
        "records_examined": vector["filter_tests"],
        "transform_work": vector["transform_work"],
        "transform_invocations": vector["transform_dispatches"],
        "survivor_buffer_traffic": vector["retained_writes"] + vector["retained_reads"],
        "output_buffer_traffic": vector["output_writes"] + vector["reduction_reads"],
        "rolling_fold_updates": vector["aggregate_updates"],
        "terminal_folds": vector["reduction_calls"],
        "peak_temp_records": vector["peak_temp_records"],
    }


def y_audit(vector):
    return {
        "records_examined": vector["records_examined"],
        "transform_work": vector["map_effort"],
        "transform_invocations": vector["map_groups"],
        "survivor_buffer_traffic": vector["staging_traffic"],
        "output_buffer_traffic": vector["completion_traffic"],
        "rolling_fold_updates": vector["fold_events"],
        "terminal_folds": vector["finish_operations"],
        "peak_temp_records": vector["max_live_values"],
    }


def combo_label(combo):
    return "+".join(combo)


def build_model(space, analyze, signature, audit, weights, peak_dimension, scenario):
    rows = {}
    for combo in space:
        native = analyze(combo, scenario)
        name = combo_label(combo)
        rows[name] = {
            "native_vector": native,
            "observable_consequences": audit(native),
            "signature": signature(combo),
            "cost": weighted_cost(native, weights),
            "admissible": native[peak_dimension] <= scenario["memory_limit"],
        }
    candidates = {name: row for name, row in rows.items() if row["admissible"]}
    selected = min(candidates, key=lambda name: (candidates[name]["cost"], name))
    return {
        "selected": selected,
        "selected_signature": rows[selected]["signature"],
        "memory_exclusions": sorted(name for name, row in rows.items()
                                    if not row["admissible"]),
        "compositions": rows,
    }


def blank_observation():
    return {
        "records_examined": 0,
        "transform_work": 0,
        "transform_invocations": 0,
        "survivor_buffer_traffic": 0,
        "output_buffer_traffic": 0,
        "rolling_fold_updates": 0,
        "terminal_folds": 0,
        "peak_temp_records": 0,
    }


def observe_a(scenario):
    module = importlib.import_module("poc11_source_a")
    events = blank_observation()
    original_keep, original_transform = module.keep, module.transform

    def keep(record, mode):
        events["records_examined"] += 1
        return original_keep(record, mode)

    def transform(record, effort):
        events["transform_invocations"] += 1
        events["transform_work"] += effort
        events["rolling_fold_updates"] += 1
        return original_transform(record, effort)

    module.keep, module.transform = keep, transform
    try:
        result = module.run(scenario["count"], scenario["mode"], scenario["effort"])
    finally:
        module.keep, module.transform = original_keep, original_transform
    events["peak_temp_records"] = 1 if result["accepted"] else 0
    return result, events


def observe_buffered(module_name, scenario, rolling):
    module = importlib.import_module(module_name)
    events = blank_observation()
    original_select = module.select
    transform_name = "transform_block" if rolling else "convert"
    original_transform = getattr(module, transform_name)

    def select(data, mode):
        events["records_examined"] += len(data)
        selected = original_select(data, mode)
        events["survivor_buffer_traffic"] += len(selected)
        return selected

    def transform(block, effort):
        events["transform_invocations"] += 1
        events["transform_work"] += len(block) * effort
        events["survivor_buffer_traffic"] += len(block)
        values = original_transform(block, effort)
        if rolling:
            events["rolling_fold_updates"] += len(values)
        else:
            events["output_buffer_traffic"] += len(values)
        return values

    module.select = select
    setattr(module, transform_name, transform)
    try:
        result = module.run(scenario["count"], scenario["mode"], scenario["effort"])
    finally:
        module.select = original_select
        setattr(module, transform_name, original_transform)
    if rolling:
        events["peak_temp_records"] = result["accepted"] + min(64, result["accepted"])
    else:
        events["output_buffer_traffic"] += result["accepted"]
        events["terminal_folds"] = 1 if result["accepted"] else 0
        events["peak_temp_records"] = 2 * result["accepted"]
    return result, events


def find_by_signature(model, wanted):
    return [name for name, row in model["compositions"].items()
            if row["signature"] == wanted]


def main():
    hashes = checked_fixture_hashes()
    results = {
        "fixture_hashes": hashes,
        "method": {
            "selection_paths_independent": True,
            "comparison_projection_used_for_selection": False,
            "oracle_executed_after_models": True,
            "peak_temp_records_evidence": "source-lifetime audit, not physical memory",
        },
        "spaces": {
            "X": {"composition_count": len(x_space())},
            "Y": {"composition_count": len(y_space())},
        },
        "scenarios": {},
    }
    expected = {
        "sparse": {"accepted": 512, "checksum": 2325550},
        "dense": {"accepted": 3584, "checksum": 1727749065},
    }
    for scenario_name, scenario in SCENARIOS.items():
        model_x = build_model(x_space(), x_vector, x_signature, x_audit,
                              X_WEIGHTS, "peak_temp_records", scenario)
        model_y = build_model(y_space(), y_vector, y_signature, y_audit,
                              Y_WEIGHTS, "max_live_values", scenario)

        # C is consulted only now, after both spaces and selections exist.
        observed = {}
        for source, observer in {
            "A": lambda: observe_a(scenario),
            "B": lambda: observe_buffered("poc11_source_b", scenario, False),
            "C": lambda: observe_buffered("poc11_source_c", scenario, True),
        }.items():
            outcome, events = observer()
            if outcome != expected[scenario["mode"]]:
                raise AssertionError(f"functional mismatch: {source}, {scenario_name}")
            observed[source] = {"outcome": outcome, "events": events}

        source_signatures = {
            "A": {"retains_survivors": False, "transform_group": 1,
                  "buffers_outputs": False, "reduction": "rolling"},
            "B": {"retains_survivors": True, "transform_group": 64,
                  "buffers_outputs": True, "reduction": "terminal"},
            "C": {"retains_survivors": True, "transform_group": 64,
                  "buffers_outputs": False, "reduction": "rolling"},
        }
        verification = {}
        for source, wanted in source_signatures.items():
            x_matches = find_by_signature(model_x, wanted)
            y_matches = find_by_signature(model_y, wanted)
            verification[source] = {
                "representable_in_X": x_matches,
                "representable_in_Y": y_matches,
                "X_matches_observation": all(
                    model_x["compositions"][name]["observable_consequences"]
                    == observed[source]["events"] for name in x_matches
                ),
                "Y_matches_observation": all(
                    model_y["compositions"][name]["observable_consequences"]
                    == observed[source]["events"] for name in y_matches
                ),
            }

        x_signatures = {json.dumps(row["signature"], sort_keys=True)
                        for row in model_x["compositions"].values()}
        y_signatures = {json.dumps(row["signature"], sort_keys=True)
                        for row in model_y["compositions"].values()}
        results["scenarios"][scenario_name] = {
            "workload": scenario,
            "X": model_x,
            "Y": model_y,
            "same_selected_consequence": (
                model_x["selected_signature"] == model_y["selected_signature"]
            ),
            "space_overlap": {
                "common_observable_signatures": len(x_signatures & y_signatures),
                "X_only_observable_signatures": len(x_signatures - y_signatures),
                "Y_only_observable_signatures": len(y_signatures - x_signatures),
            },
            "source_and_recombination_verification": verification,
            "oracle": observed,
        }
        print(f"{scenario_name}: X={model_x['selected']} | Y={model_y['selected']} "
              f"| same consequence={model_x['selected_signature'] == model_y['selected_signature']}")

    Path("poc12_measurements.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
