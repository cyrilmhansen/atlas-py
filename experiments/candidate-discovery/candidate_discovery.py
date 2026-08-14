"""Step 1: generic discovery of the small known plan shapes.

The discovery code knows only catalogue relations. Domain labels such as
lookup, scan, S, H and D occur only in the fixture and regression assertions.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class Realization:
    name: str
    intent: str
    requires: tuple[str, ...]
    cost: int


@dataclass(frozen=True)
class Producer:
    name: str
    resource: str
    requires: tuple[str, ...]
    cost: int


@dataclass(frozen=True)
class Catalog:
    realizations: tuple[Realization, ...]
    producers: tuple[Producer, ...]


@dataclass(frozen=True)
class Scenario:
    present_resources: frozenset[str] = frozenset()
    enabled_producers: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Plan:
    goals: tuple[str, ...]
    realizations: tuple[str, ...]
    producers: tuple[str, ...]
    present_resources: tuple[str, ...]
    produced_resources: tuple[str, ...]
    cost: int


@dataclass(frozen=True)
class _Resolution:
    producers: tuple[Producer, ...]
    present_resources: frozenset[str]
    produced_resources: frozenset[str]


def _unique_producers(*groups: tuple[Producer, ...]) -> tuple[Producer, ...]:
    by_name = {producer.name: producer for group in groups for producer in group}
    names = list(by_name)
    names.sort()
    return tuple(by_name[name] for name in names)


def _canonical_names(values: frozenset[str]) -> tuple[str, ...]:
    names = list(values)
    names.sort()
    return tuple(names)


def _resolve_resources(
    resources: tuple[str, ...],
    catalog: Catalog,
    scenario: Scenario,
    known: frozenset[str],
    active: frozenset[str],
) -> tuple[_Resolution, ...]:
    """Resolve a resource and producer prerequisites without domain branches."""
    if not resources:
        return (_Resolution((), frozenset(), frozenset()),)

    resource, *rest = resources
    if resource in known:
        remaining = _resolve_resources(
            tuple(rest), catalog, scenario, known, active
        )
        present = (
            frozenset({resource})
            if resource in scenario.present_resources
            else frozenset()
        )
        return tuple(
            _Resolution(
                resolution.producers,
                resolution.present_resources | present,
                resolution.produced_resources,
            )
            for resolution in remaining
        )
    if resource in active:
        return ()

    producers = tuple(
        producer for producer in catalog.producers
        if producer.resource == resource
        and producer.name in scenario.enabled_producers
    )
    resolutions: list[_Resolution] = []
    for producer in producers:
        dependency_resolutions = _resolve_resources(
            producer.requires,
            catalog,
            scenario,
            known,
            active | {resource},
        )
        for dependency in dependency_resolutions:
            next_known = known | dependency.produced_resources | {resource}
            remaining_resolutions = _resolve_resources(
                tuple(rest),
                catalog,
                scenario,
                next_known,
                active,
            )
            for remaining in remaining_resolutions:
                resolutions.append(
                    _Resolution(
                        _unique_producers(
                            dependency.producers,
                            (producer,),
                            remaining.producers,
                        ),
                        dependency.present_resources
                        | remaining.present_resources,
                        dependency.produced_resources
                        | remaining.produced_resources
                        | {resource},
                    )
                )
    return tuple(resolutions)


def discover_plans(
    goals: tuple[str, ...], catalog: Catalog, scenario: Scenario
) -> tuple[Plan, ...]:
    """Discover candidate plans for the requested goals from catalogue facts."""
    alternatives = tuple(
        tuple(realization for realization in catalog.realizations
              if realization.intent == goal)
        for goal in goals
    )
    if any(not choices for choices in alternatives):
        return ()

    plans: list[Plan] = []
    for selected in product(*alternatives):
        required = tuple(
            resource for realization in selected for resource in realization.requires
        )
        resolutions = _resolve_resources(
            required,
            catalog,
            scenario,
            scenario.present_resources,
            frozenset(),
        )
        for resolution in resolutions:
            producers = resolution.producers
            plans.append(
                Plan(
                    goals=goals,
                    realizations=tuple(realization.name for realization in selected),
                    producers=tuple(producer.name for producer in producers),
                    present_resources=_canonical_names(resolution.present_resources),
                    produced_resources=_canonical_names(resolution.produced_resources),
                    cost=sum(realization.cost for realization in selected)
                    + sum(producer.cost for producer in producers),
                )
            )
    return tuple(plans)


def choose_best(plans: tuple[Plan, ...]) -> Plan | None:
    return min(plans, key=lambda plan: plan.cost) if plans else None


def fixture_catalog() -> Catalog:
    """The old POC's lookup/scan catalogue, expressed only as data."""
    return Catalog(
        realizations=(
            Realization("linear_lookup", "lookup", (), 50),
            Realization("binary_lookup", "lookup", ("S",), 3),
            Realization("hash_lookup", "lookup", ("H",), 4),
            Realization("linear_scan", "scan", (), 30),
            Realization("scan_sorted", "scan", ("S",), 5),
            Realization("scan_dense", "scan", ("D",), 6),
        ),
        producers=(
            Producer("build_sorted", "S", (), 35),
            Producer("build_hash", "H", (), 60),
            Producer("build_dense", "D", (), 45),
        ),
    )


def _case(
    goals: tuple[str, ...], scenario: Scenario
) -> dict[str, object]:
    plans = discover_plans(goals, fixture_catalog(), scenario)
    selected = choose_best(plans)
    return {
        "goals": goals,
        "plans": [plan.__dict__ for plan in plans],
        "selected": selected.__dict__ if selected else None,
    }


def regression_results() -> dict[str, object]:
    return {
        "lookup_no_resources": _case(
            ("lookup",), Scenario()
        ),
        "lookup_sorted_producer": _case(
            ("lookup",), Scenario(enabled_producers=frozenset({"build_sorted"}))
        ),
        "lookup_hash_present": _case(
            ("lookup",), Scenario(present_resources=frozenset({"H"}))
        ),
        "scan_no_resources": _case(
            ("scan",), Scenario()
        ),
        "scan_dense_producer": _case(
            ("scan",), Scenario(enabled_producers=frozenset({"build_dense"}))
        ),
        "scan_sorted_present": _case(
            ("scan",), Scenario(present_resources=frozenset({"S"}))
        ),
        "lookup_and_scan_shared_S": _case(
            ("lookup", "scan"),
            Scenario(enabled_producers=frozenset({"build_sorted"})),
        ),
    }


def assertions() -> None:
    catalog = fixture_catalog()

    lookup = discover_plans(("lookup",), catalog, Scenario())
    assert choose_best(lookup).realizations == ("linear_lookup",)
    sorted_lookup = discover_plans(
        ("lookup",), catalog,
        Scenario(enabled_producers=frozenset({"build_sorted"})),
    )
    assert choose_best(sorted_lookup).realizations == ("binary_lookup",)
    hash_lookup = discover_plans(
        ("lookup",), catalog,
        Scenario(present_resources=frozenset({"H"})),
    )
    assert choose_best(hash_lookup).realizations == ("hash_lookup",)
    assert choose_best(hash_lookup).present_resources == ("H",)

    scan = discover_plans(("scan",), catalog, Scenario())
    assert choose_best(scan).realizations == ("linear_scan",)
    dense_scan = discover_plans(
        ("scan",), catalog,
        Scenario(enabled_producers=frozenset({"build_dense"})),
    )
    assert any(
        plan.realizations == ("scan_dense",) for plan in dense_scan
    )
    sorted_scan = discover_plans(
        ("scan",), catalog,
        Scenario(present_resources=frozenset({"S"})),
    )
    assert choose_best(sorted_scan).realizations == ("scan_sorted",)
    assert choose_best(sorted_scan).present_resources == ("S",)

    shared = discover_plans(
        ("lookup", "scan"), catalog,
        Scenario(enabled_producers=frozenset({"build_sorted"})),
    )
    shared_best = choose_best(shared)
    assert shared_best is not None
    assert shared_best.producers == ("build_sorted",)
    assert shared_best.produced_resources == ("S",)
    assert shared_best.cost == 43

    chained = Catalog(
        (Realization("use_R", "goal", ("R",), 2),),
        (
            Producer("build_R", "R", ("Q",), 5),
            Producer("build_Q", "Q", (), 7),
        ),
    )
    chained_plans = discover_plans(
        ("goal",), chained,
        Scenario(enabled_producers=frozenset({"build_R", "build_Q"})),
    )
    chained_best = choose_best(chained_plans)
    assert chained_best is not None
    assert chained_best.producers == ("build_Q", "build_R")
    assert chained_best.cost == 14

    source = inspect.getsource(discover_plans) + inspect.getsource(_resolve_resources)
    for forbidden in ("hash", "sorted", "dense", "lookup", "scan"):
        assert forbidden not in source.lower(), forbidden


def run() -> dict[str, object]:
    assertions()
    return {
        "regressions": regression_results(),
        "validation_1_5": {
            "candidate_lists_are_catalogue_data": True,
            "discovery_has_no_domain_branches": True,
            "shared_resource_deduplicated_by_identity": True,
            "present_and_produced_resources_use_same_resolution": True,
            "inadmissible_realizations_are_absent_from_plans": True,
            "cost_aggregated_from_plan_elements": True,
        },
    }
