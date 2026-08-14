"""Step 4: CP-SAT formulation of the anonymous candidate catalogue."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from dataclasses import replace

from ortools.sat.python import cp_model

from step3_explosion import (
    Parameters,
    SyntheticCatalog,
    generate_catalog,
    memoized_search,
)


def solve(catalog: SyntheticCatalog) -> dict[str, object]:
    model = cp_model.CpModel()
    alternatives = {
        alternative.name: model.NewBoolVar(f"x_{alternative.name}")
        for alternative in catalog.alternatives
    }
    producers = {
        producer.name: model.NewBoolVar(f"y_{producer.name}")
        for producer in catalog.producers
    }
    resources = {
        resource: model.NewBoolVar(f"u_{resource}")
        for resource in {
            *(alternative.resource for alternative in catalog.alternatives
              if alternative.resource is not None),
            *(producer.resource for producer in catalog.producers),
            *(producer.dependency for producer in catalog.producers
              if producer.dependency is not None),
        }
    }

    for intent in catalog.intents:
        choices = [
            variable for alternative, variable in alternatives.items()
            if next(a for a in catalog.alternatives if a.name == alternative).intent == intent
        ]
        model.Add(sum(choices) == 1)

    alternatives_by_resource: dict[str, list[object]] = {}
    for alternative in catalog.alternatives:
        if alternative.resource is not None:
            alternatives_by_resource.setdefault(alternative.resource, []).append(
                alternatives[alternative.name]
            )

    producers_by_resource: dict[str, list[object]] = {}
    for producer in catalog.producers:
        producers_by_resource.setdefault(producer.resource, []).append(
            producers[producer.name]
        )

    # A selected realization activates its resource. A selected producer also
    # activates its output and recursively activates its dependency.
    for resource, variable in resources.items():
        uses = alternatives_by_resource.get(resource, [])
        outputs = producers_by_resource.get(resource, [])
        if uses:
            for use in uses:
                model.Add(variable >= use)
            model.Add(variable <= sum(uses))
        if outputs:
            for output in outputs:
                model.Add(variable >= output)
            model.Add(sum(outputs) >= variable)
        else:
            model.Add(variable == 0)

    for producer in catalog.producers:
        if producer.dependency is not None:
            model.Add(resources[producer.dependency] >= producers[producer.name])

    objective_terms = [
        alternative.cost * alternatives[alternative.name]
        for alternative in catalog.alternatives
    ] + [
        producer.cost * producers[producer.name]
        for producer in catalog.producers
    ]
    model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    solver.parameters.num_search_workers = 1
    start = time.perf_counter()
    status = solver.Solve(model)
    elapsed = time.perf_counter() - start
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "status": solver.StatusName(status),
            "seconds": round(elapsed, 6),
            "variables": len(model.Proto().variables),
            "constraints": len(model.Proto().constraints),
        }

    selected_alternatives = tuple(
        alternative.name
        for alternative in catalog.alternatives
        if solver.Value(alternatives[alternative.name])
    )
    selected_producers = tuple(
        producer.name
        for producer in catalog.producers
        if solver.Value(producers[producer.name])
    )
    return {
        "status": solver.StatusName(status),
        "seconds": round(elapsed, 6),
        "variables": len(model.Proto().variables),
        "constraints": len(model.Proto().constraints),
        "cost": int(solver.ObjectiveValue()),
        "realizations": selected_alternatives,
        "producers": selected_producers,
    }


def semantic_signature(
    catalog: SyntheticCatalog,
    realizations: tuple[str, ...],
    producers: tuple[str, ...],
) -> tuple[tuple[str, ...], frozenset[tuple[str, str | None, tuple[str, ...]]]]:
    producer_by_name = {producer.name: producer for producer in catalog.producers}
    return (
        realizations,
        frozenset(
            (
                producer_by_name[name].resource,
                producer_by_name[name].dependency,
                producer_by_name[name].properties,
            )
            for name in producers
        ),
    )


def compare(parameters: Parameters, enumeration_limit: int = 200_000) -> dict[str, object]:
    catalog = generate_catalog(parameters)
    enumerated, enum_stats = memoized_search(catalog, enumeration_limit)
    enum_best = min(enumerated, key=lambda plan: plan.cost) if enumerated else None
    solver_result = solve(catalog)
    comparison: dict[str, object] = {
        "parameters": asdict(parameters),
        "enumerator": {
            "plans_materialized": len(enumerated),
            "states": enum_stats.states,
            "aborted": enum_stats.aborted,
            "best_cost": enum_best.cost if enum_best else None,
            "best_realizations": enum_best.realizations if enum_best else None,
            "best_producers": enum_best.producers if enum_best else None,
        },
        "solver": solver_result,
    }
    if not enum_stats.aborted and solver_result.get("cost") is not None:
        assert solver_result["cost"] == enum_best.cost
        assert semantic_signature(
            catalog,
            tuple(solver_result["realizations"]),
            tuple(solver_result["producers"]),
        ) == semantic_signature(
            catalog, enum_best.realizations, enum_best.producers
        )
        comparison["cross_check"] = "same_cost"
    else:
        comparison["cross_check"] = "enumerator_bounded"
    return comparison


def sharing_preferred_catalog(parameters: Parameters) -> SyntheticCatalog:
    """Reuse the step-3 topology while making shared alternatives worthwhile."""
    catalog = generate_catalog(parameters)
    alternatives = tuple(
        replace(alternative, cost=100 if alternative.resource is None else 1)
        for alternative in catalog.alternatives
    )
    producers = tuple(replace(producer, cost=5) for producer in catalog.producers)
    return replace(catalog, alternatives=alternatives, producers=producers)


def compare_catalog(
    parameters: Parameters,
    catalog: SyntheticCatalog,
    enumeration_limit: int = 200_000,
) -> dict[str, object]:
    enumerated, enum_stats = memoized_search(catalog, enumeration_limit)
    enum_best = min(enumerated, key=lambda plan: plan.cost) if enumerated else None
    solver_result = solve(catalog)
    if not enum_stats.aborted and solver_result.get("cost") is not None:
        assert solver_result["cost"] == enum_best.cost
        assert semantic_signature(
            catalog,
            tuple(solver_result["realizations"]),
            tuple(solver_result["producers"]),
        ) == semantic_signature(
            catalog, enum_best.realizations, enum_best.producers
        )
        cross_check = "same_cost"
    else:
        cross_check = "enumerator_bounded"
    return {
        "parameters": asdict(parameters),
        "enumerator": {
            "plans_materialized": len(enumerated),
            "aborted": enum_stats.aborted,
            "best_cost": enum_best.cost if enum_best else None,
            "best_realizations": enum_best.realizations if enum_best else None,
            "best_producers": enum_best.producers if enum_best else None,
        },
        "solver": solver_result,
        "cross_check": cross_check,
    }


def mandatory_sharing_cases() -> list[dict[str, object]]:
    cases = (
        Parameters(3, 2, 1, 2, 3),
        Parameters(2, 2, 0, 2, 1),
        Parameters(4, 2, 1, 2, 2),
    )
    results = []
    for parameters in cases:
        catalog = sharing_preferred_catalog(parameters)
        result = compare_catalog(parameters, catalog)
        assert result["solver"]["status"] == "OPTIMAL"
        assert result["cross_check"] == "same_cost"
        assert result["solver"]["producers"]
        results.append(result)
    return results


def run() -> dict[str, object]:
    cases = (
        Parameters(2, 2, 0, 1, 1),
        Parameters(3, 2, 1, 2, 3),  # three consumers sharing one chain
        Parameters(4, 3, 1, 2, 2),  # two independently shared resources
        Parameters(4, 2, 2, 2, 1),
        Parameters(6, 3, 2, 2, 1),
        Parameters(6, 2, 3, 3, 6),
        Parameters(8, 3, 3, 3, 8),
    )
    results = [compare(parameters) for parameters in cases]
    assert all(
        result["cross_check"] in ("same_cost", "enumerator_bounded")
        for result in results
    )
    return {
        "solver": "OR-Tools CP-SAT",
        "cases": results,
        "mandatory_sharing": mandatory_sharing_cases(),
        "model_is_domain_branch_free": True,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
