"""Closing tests for shared consumers and coexisting resources."""

from __future__ import annotations

import json

from semantic_kernel_poc import (
    Description,
    available,
    build_graph,
    composition_paths,
    constructible,
    lookup_paths,
    provable,
    realizes,
    requires,
    scan_paths,
    Scenario,
)


def test_three_consumers() -> dict[str, object]:
    scenario = Scenario(
        "three-consumers-of-S",
        64,
        lookups=20,
        mode="composition",
        enabled_builders=("build_sorted(collection)->S",),
    )
    graph, d = build_graph(scenario)
    third_consumer = Description("summary_sorted(sorted_representation)")
    summary_intent = Description("summarize(collection)")
    graph.register(
        realizes(third_consumer, summary_intent),
        requires(third_consumer, d["S"]),
    )
    graph.run(10)
    assert provable(graph, available(third_consumer, d["scenario"]))

    existing = composition_paths(graph, d, scenario)
    known_consumers = existing["shared_resource"]["consumers"]
    assert len(known_consumers) == 2
    assert "summary_sorted(sorted_representation)" not in known_consumers
    return {
        "scenario": scenario.name,
        "third_consumer_available_from_S": True,
        "existing_composition_consumers": known_consumers,
        "third_consumer_discovered_by_composition_paths": False,
        "manual_composite_extension_required": True,
    }


def test_coexisting_resources() -> dict[str, object]:
    existing_scenario = Scenario(
        "coexisting-H-D-existing",
        64,
        lookups=20,
        present_resources=("H", "D"),
        memory_budget_value=128,
    )
    existing_graph, existing_d = build_graph(existing_scenario)
    existing_lookup = lookup_paths(existing_graph, existing_d, existing_scenario)
    existing_scan = scan_paths(existing_graph, existing_d, existing_scenario)
    assert existing_lookup["selected"] == "hash_lookup"
    assert existing_scan["selected"] == "scan_dense"
    assert existing_lookup["constructible"]["H"] is False
    assert existing_scan["constructible"]["D"] is False

    constructible_scenario = Scenario(
        "coexisting-H-D-constructible",
        64,
        lookups=20,
        enabled_builders=(
            "build_hash_index(collection)->H",
            "build_dense_view(collection)->D",
        ),
        memory_budget_value=128,
    )
    constructible_graph, constructible_d = build_graph(constructible_scenario)
    constructible_lookup = lookup_paths(
        constructible_graph, constructible_d, constructible_scenario
    )
    constructible_scan = scan_paths(
        constructible_graph, constructible_d, constructible_scenario
    )
    assert provable(
        constructible_graph,
        constructible(
            constructible_d["H"], constructible_d["scenario"]
        ),
    )
    assert provable(
        constructible_graph,
        constructible(
            constructible_d["D"], constructible_d["scenario"]
        ),
    )
    assert constructible_lookup["selected"] == "hash_lookup"
    assert constructible_scan["selected"] == "linear_scan"
    return {
        "existing": {
            "resources": ["H", "D"],
            "lookup": existing_lookup,
            "scan": existing_scan,
            "identities_distinct": True,
        },
        "constructible": {
            "resources": ["H", "D"],
            "lookup": constructible_lookup,
            "scan": constructible_scan,
            "identities_distinct": True,
            "manual_composite_extension_required": False,
        },
    }


def run() -> dict[str, object]:
    return {
        "test_a_three_consumers": test_three_consumers(),
        "test_b_coexisting_resources": test_coexisting_resources(),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
