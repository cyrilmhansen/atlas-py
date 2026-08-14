"""Step 4 surprise tests; intentionally does not extend the search layer."""

from __future__ import annotations

import json

from semantic_kernel_poc import architecture_assertions, scenario_result
from semantic_kernel_poc import Scenario


def run_surprise_tests() -> list[dict[str, object]]:
    architecture_assertions()
    cases = [
        (
            "existing_hash_but_not_profitable",
            Scenario("existing-hash-not-worthwhile", 1, lookups=1, present_resources=("H",)),
            "lookup",
            "linear_lookup",
        ),
        (
            "constructible_hash_but_too_costly",
            Scenario(
                "expensive-hash",
                64,
                lookups=1,
                enabled_builders=("build_hash_index(collection)->H",),
            ),
            "lookup",
            "linear_lookup",
        ),
        (
            "two_representations_valid_simultaneously",
            Scenario(
                "sorted-and-hash-existing",
                64,
                lookups=20,
                present_resources=("S", "H"),
            ),
            "lookup",
            "hash_lookup",
        ),
        (
            "specialization_at_ten_calls",
            Scenario(
                "specialization-ten",
                1,
                operation_repetitions=10,
                mode="specialization",
                present_resources=("P",),
            ),
            "specialization",
            "generic_operation",
        ),
        (
            "specialization_at_one_thousand_calls",
            Scenario(
                "specialization-one-thousand",
                1,
                operation_repetitions=1000,
                mode="specialization",
                present_resources=("P",),
            ),
            "specialization",
            "prepare_then_specialize",
        ),
        (
            "shared_sorted_result_reused_by_two_intentions",
            Scenario(
                "shared-sorted-existing",
                64,
                lookups=20,
                mode="composition",
                present_resources=("S",),
            ),
            "composition",
            "shared_sorted_preparation",
        ),
        (
            "resource_without_known_producer",
            Scenario("resource-unavailable", 64, lookups=20),
            "lookup",
            "linear_lookup",
        ),
    ]
    results = []
    for name, scenario, result_kind, expected in cases:
        result = scenario_result(scenario)[result_kind]
        selected = result["selected"]
        assert selected == expected, (name, selected, expected)
        record: dict[str, object] = {
            "name": name,
            "selected": selected,
            "paths": result["paths"],
        }
        if result_kind == "composition":
            record["shared_resource"] = result["shared_resource"]
            record["composition_extensions_required"] = 0
        if name == "shared_sorted_result_reused_by_two_intentions":
            assert result["shared_resource"]["build_count"] == 0
            assert len(result["shared_resource"]["consumers"]) == 2
        results.append(record)
    return results


if __name__ == "__main__":
    print(json.dumps(run_surprise_tests(), indent=2))
