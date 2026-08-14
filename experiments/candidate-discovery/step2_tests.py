"""Step 2 tests: generic multi-intent sharing and joint resources."""

from __future__ import annotations

import json
from collections import Counter

from candidate_discovery import (
    Catalog,
    Producer,
    Realization,
    Scenario,
    choose_best,
    discover_plans,
)


def shared_catalog(consumer_count: int) -> tuple[Catalog, tuple[str, ...]]:
    names = ["lookup"]
    if consumer_count >= 2:
        names.append("scan")
    if consumer_count >= 3:
        names.append("summary")
    names.extend(
        f"summary_{index}" for index in range(4, consumer_count + 1)
    )
    realizations = []
    for name in names:
        realizations.extend(
            (
                Realization(f"{name}_direct", name, (), 50),
                Realization(f"{name}_shared", name, ("S",), 3),
            )
        )
    return (
        Catalog(
            tuple(realizations),
            (Producer("build_shared", "S", (), 35),),
        ),
        tuple(names),
    )


def structural_duplicates(plans: tuple[object, ...]) -> int:
    signatures = [
        (
            plan.goals,
            plan.realizations,
            tuple(sorted(plan.producers)),
            plan.present_resources,
            plan.produced_resources,
        )
        for plan in plans
    ]
    return len(signatures) - len(Counter(signatures))


def variable_consumers() -> list[dict[str, object]]:
    results = []
    for count in (1, 2, 3, 5, 10):
        catalog, goals = shared_catalog(count)
        plans = discover_plans(
            goals,
            catalog,
            Scenario(enabled_producers=frozenset({"build_shared"})),
        )
        selected = choose_best(plans)
        assert selected is not None
        assert selected.producers == ("build_shared",)
        assert selected.produced_resources == ("S",)
        assert selected.realizations == tuple(
            f"{name}_shared" for name in goals
        )
        results.append({
            "consumer_count": count,
            "goals": goals,
            "candidate_count": len(plans),
            "duplicate_count_before_canonicalization": structural_duplicates(plans),
            "selected": selected.__dict__,
            "producer_occurrences_in_selected_plan": selected.producers.count(
                "build_shared"
            ),
        })
    return results


def joint_catalog() -> Catalog:
    return Catalog(
        (
            Realization("lookup_linear", "lookup", (), 50),
            Realization("lookup_hash", "lookup", ("H",), 4),
            Realization("lookup_sorted", "lookup", ("S",), 3),
            Realization("scan_linear", "scan", (), 60),
            Realization("scan_dense", "scan", ("D",), 6),
            Realization("scan_sorted", "scan", ("S",), 5),
        ),
        (
            Producer("build_H", "H", (), 20),
            Producer("build_D", "D", (), 25),
            Producer("build_S", "S", (), 35),
        ),
    )


def joint_resources() -> dict[str, object]:
    catalog = joint_catalog()
    h_and_d = discover_plans(
        ("lookup", "scan"),
        catalog,
        Scenario(enabled_producers=frozenset({"build_H", "build_D"})),
    )
    selected_h_and_d = choose_best(h_and_d)
    assert selected_h_and_d is not None
    assert selected_h_and_d.realizations == ("lookup_hash", "scan_dense")
    assert selected_h_and_d.producers == ("build_D", "build_H")
    assert selected_h_and_d.cost == 55

    all_alternatives = discover_plans(
        ("lookup", "scan"),
        catalog,
        Scenario(
            enabled_producers=frozenset({"build_H", "build_D", "build_S"})
        ),
    )
    names = {plan.realizations for plan in all_alternatives}
    assert ("lookup_hash", "scan_dense") in names
    assert ("lookup_sorted", "scan_sorted") in names
    selected_all = choose_best(all_alternatives)
    assert selected_all is not None
    assert selected_all.realizations == ("lookup_sorted", "scan_sorted")
    assert selected_all.producers == ("build_S",)
    return {
        "h_and_d_preferred": {
            "candidate_count": len(h_and_d),
            "duplicate_count_before_canonicalization": structural_duplicates(h_and_d),
            "selected": selected_h_and_d.__dict__,
        },
        "all_alternatives": {
            "candidate_count": len(all_alternatives),
            "duplicate_count_before_canonicalization": structural_duplicates(
                all_alternatives
            ),
            "selected": selected_all.__dict__,
            "realization_pairs": sorted(names),
        },
    }


def run() -> dict[str, object]:
    variable = variable_consumers()
    joint = joint_resources()
    return {
        "variable_consumers": variable,
        "joint_resources": joint,
        "search_responsibility": {
            "egglog": "none in this step-2 discovery harness",
            "python": "catalogue expansion, dependency closure, sharing and cost selection",
        },
        "new_ontology_concept_required": False,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
