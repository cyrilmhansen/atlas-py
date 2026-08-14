"""Step 3: synthetic plan-space growth and generic reductions.

The generator uses only anonymous intents, resources and producers.  It is
deliberately separate from the QuickDraw-shaped fixtures used by steps 1/2.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class Parameters:
    G: int
    A: int
    D: int
    P: int
    S: int


@dataclass(frozen=True)
class Alternative:
    name: str
    intent: str
    resource: str | None
    cost: int


@dataclass(frozen=True)
class Producer:
    name: str
    resource: str
    dependency: str | None
    cost: int
    properties: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyntheticCatalog:
    alternatives: tuple[Alternative, ...]
    producers: tuple[Producer, ...]
    intents: tuple[str, ...]
    descriptions: int
    relations: int


@dataclass(frozen=True)
class Plan:
    realizations: tuple[str, ...]
    producers: tuple[str, ...]
    cost: int


@dataclass
class SearchStats:
    states: int = 0
    max_frontier: int = 0
    aborted: bool = False


class ExpansionLimit(Exception):
    pass


def generate_catalog(parameters: Parameters) -> SyntheticCatalog:
    if min(parameters.G, parameters.A, parameters.P) < 1:
        raise ValueError("G, A and P must be positive")
    if parameters.D < 0:
        raise ValueError("D must be non-negative")
    sharing = max(1, min(parameters.S, parameters.G))
    group_count = (parameters.G + sharing - 1) // sharing

    intents = tuple(f"i{index}" for index in range(parameters.G))
    alternatives: list[Alternative] = []
    producers: list[Producer] = []
    for intent_index, intent in enumerate(intents):
        group = intent_index // sharing
        root = f"r{group}:{parameters.D}"
        for alternative_index in range(parameters.A):
            # Alternative zero is direct; the others use the shared resource.
            resource = None if alternative_index == 0 else root
            alternatives.append(
                Alternative(
                    f"a{intent_index}:{alternative_index}",
                    intent,
                    resource,
                    10 + alternative_index,
                )
            )
    for group in range(group_count):
        for depth in range(parameters.D + 1):
            resource = f"r{group}:{depth}"
            dependency = f"r{group}:{depth - 1}" if depth else None
            for producer_index in range(parameters.P):
                producers.append(
                    Producer(
                        f"p{group}:{depth}:{producer_index}",
                        resource,
                        dependency,
                        3 + producer_index,
                    )
                )
    # Descriptions count intents, alternatives, resources and producers.
    descriptions = (
        len(intents)
        + len(alternatives)
        + group_count * (parameters.D + 1)
        + len(producers)
    )
    relations = (
        len(alternatives)  # realizes
        + sum(alt.resource is not None for alt in alternatives)  # requires
        + len(producers)  # builds
        + sum(producer.dependency is not None for producer in producers)
    )
    return SyntheticCatalog(
        tuple(alternatives), tuple(producers), intents, descriptions, relations
    )


def _producers_for(catalog: SyntheticCatalog, resource: str) -> tuple[Producer, ...]:
    return tuple(p for p in catalog.producers if p.resource == resource)


def _naive_chain(
    catalog: SyntheticCatalog,
    resource: str,
    stats: SearchStats,
    limit: int | None,
) -> tuple[tuple[str, ...], ...]:
    stats.states += 1
    if limit is not None and stats.states > limit:
        stats.aborted = True
        raise ExpansionLimit
    chains: list[tuple[str, ...]] = []
    for producer in _producers_for(catalog, resource):
        if producer.dependency is None:
            chains.append((producer.name,))
        else:
            for chain in _naive_chain(catalog, producer.dependency, stats, limit):
                chains.append(chain + (producer.name,))
    stats.max_frontier = max(stats.max_frontier, len(chains))
    return tuple(chains)


def naive_search(
    catalog: SyntheticCatalog, limit: int | None = None
) -> tuple[tuple[Plan, ...], SearchStats]:
    stats = SearchStats()
    by_intent = [
        tuple(a for a in catalog.alternatives if a.intent == intent)
        for intent in catalog.intents
    ]
    plans: list[Plan] = []
    try:
        for selected in product(*by_intent):
            front = [((), sum(a.cost for a in selected))]
            for alternative in selected:
                if alternative.resource is None:
                    continue
                chains = _naive_chain(catalog, alternative.resource, stats, limit)
                next_front = []
                for existing, cost in front:
                    for chain in chains:
                        stats.states += 1
                        if limit is not None and stats.states > limit:
                            stats.aborted = True
                            raise ExpansionLimit
                        next_front.append((existing + chain, cost + sum(
                            next(
                                producer.cost
                                for producer in catalog.producers
                                if producer.name == name
                            )
                            for name in chain
                        )))
                front = next_front
                stats.max_frontier = max(stats.max_frontier, len(front))
            plans.extend(
                Plan(
                    tuple(a.name for a in selected),
                    producers,
                    cost,
                )
                for producers, cost in front
            )
    except ExpansionLimit:
        return tuple(plans), stats
    return tuple(plans), stats


def canonicalize(
    catalog: SyntheticCatalog, plans: tuple[Plan, ...]
) -> tuple[tuple[Plan, ...], int, int, int]:
    producer_by_name = {producer.name: producer for producer in catalog.producers}
    unique: dict[tuple[tuple[str, ...], frozenset[str]], Plan] = {}
    invalid = 0
    valid_plans: list[Plan] = []
    for plan in plans:
        producer_names = frozenset(plan.producers)
        resources = {
            producer_by_name[name].resource for name in producer_names
        }
        if len(resources) != len(producer_names):
            invalid += 1
            continue
        valid_plans.append(plan)
        key = (plan.realizations, producer_names)
        normalized = Plan(
            plan.realizations,
            tuple(sorted(producer_names)),
            sum(
                next(a.cost for a in catalog.alternatives if a.name == name)
                for name in plan.realizations
            )
            + sum(producer_by_name[name].cost for name in producer_names),
        )
        unique[key] = normalized
    exact_keys = {
        (plan.realizations, plan.producers, plan.cost)
        for plan in valid_plans
    }
    exact_duplicates = len(valid_plans) - len(exact_keys)
    canonical_equivalents = (
        len(valid_plans) - len(unique) - exact_duplicates
    )
    return (
        tuple(unique.values()),
        canonical_equivalents,
        exact_duplicates,
        invalid,
    )


def _memo_chain(
    catalog: SyntheticCatalog,
    resource: str,
    cache: dict[str, tuple[tuple[str, ...], ...]],
    stats: SearchStats,
) -> tuple[tuple[str, ...], ...]:
    if resource in cache:
        return cache[resource]
    stats.states += 1
    chains: list[tuple[str, ...]] = []
    for producer in _producers_for(catalog, resource):
        if producer.dependency is None:
            chains.append((producer.name,))
        else:
            chains.extend(
                chain + (producer.name,)
                for chain in _memo_chain(catalog, producer.dependency, cache, stats)
            )
    cache[resource] = tuple(chains)
    stats.max_frontier = max(stats.max_frontier, len(chains))
    return cache[resource]


def memoized_search(
    catalog: SyntheticCatalog,
    limit: int | None = None,
) -> tuple[tuple[Plan, ...], SearchStats]:
    stats = SearchStats()
    cache: dict[str, tuple[tuple[str, ...], ...]] = {}
    by_intent = [
        tuple(a for a in catalog.alternatives if a.intent == intent)
        for intent in catalog.intents
    ]
    producer_by_name = {producer.name: producer for producer in catalog.producers}
    plans: list[Plan] = []
    try:
        for selected in product(*by_intent):
            resource_names = tuple(sorted({
                alternative.resource
                for alternative in selected
                if alternative.resource is not None
            }))
            choices = [
                _memo_chain(catalog, resource, cache, stats)
                for resource in resource_names
            ]
            for chains in product(*choices) if choices else [()]:
                producer_names = frozenset(name for chain in chains for name in chain)
                if limit is not None and len(plans) >= limit:
                    raise ExpansionLimit
                plans.append(
                    Plan(
                        tuple(a.name for a in selected),
                        tuple(sorted(producer_names)),
                        sum(a.cost for a in selected)
                        + sum(producer_by_name[name].cost for name in producer_names),
                    )
                )
                stats.states += 1
            stats.max_frontier = max(stats.max_frontier, len(plans))
    except ExpansionLimit:
        stats.aborted = True
    return tuple(plans), stats


def prune(
    catalog: SyntheticCatalog, plans: tuple[Plan, ...]
) -> tuple[Plan, ...]:
    producer_by_name = {producer.name: producer for producer in catalog.producers}
    best: dict[tuple[tuple[str, ...], frozenset[str]], Plan] = {}
    for plan in plans:
        produced = frozenset(
            (
                producer_by_name[name].resource,
                producer_by_name[name].properties,
            )
            for name in plan.producers
        )
        key = (plan.realizations, produced)
        if key not in best or plan.cost < best[key].cost:
            best[key] = plan
    return tuple(best.values())


def measure(
    parameters: Parameters,
    naive_limit: int = 50_000,
    memo_limit: int = 200_000,
) -> dict[str, object]:
    catalog = generate_catalog(parameters)
    start = time.perf_counter()
    naive, naive_stats = naive_search(catalog, naive_limit)
    naive_time = time.perf_counter() - start

    start = time.perf_counter()
    canonical, canonical_equivalents, exact_duplicates, invalid = canonicalize(
        catalog, naive
    )
    canonical_time = time.perf_counter() - start

    start = time.perf_counter()
    memo, memo_stats = memoized_search(catalog, memo_limit)
    memo_time = time.perf_counter() - start
    pruned = prune(catalog, memo)

    return {
        "G": parameters.G,
        "A": parameters.A,
        "D": parameters.D,
        "P": parameters.P,
        "S": parameters.S,
        "descriptions": catalog.descriptions,
        "relations": catalog.relations,
        "naive": {
            "terminal_plans_observed": len(naive),
            "states": naive_stats.states,
            "max_frontier": naive_stats.max_frontier,
            "aborted": naive_stats.aborted,
            "seconds": round(naive_time, 6),
        },
        "canonical": {
            "terminal_plans": len(canonical),
            "canonical_equivalents_merged": canonical_equivalents,
            "exact_duplicates_removed": exact_duplicates,
            "invalid_expansions_filtered": invalid,
            "input_complete": not naive_stats.aborted,
            "seconds": round(canonical_time, 6),
        },
        "memo": {
            "terminal_plans": len(memo),
            "states": memo_stats.states,
            "max_frontier": memo_stats.max_frontier,
            "aborted": memo_stats.aborted,
            "seconds": round(memo_time, 6),
        },
        "pruned_terminal_plans": len(pruned),
    }


def sensitivity_results() -> list[dict[str, object]]:
    rows = []
    variations = (
        ("G", (Parameters(g, 2, 1, 2, 1) for g in range(1, 6))),
        ("A", (Parameters(3, a, 1, 2, 3) for a in range(1, 5))),
        ("D", (Parameters(3, 2, d, 2, 3) for d in range(4))),
        ("P", (Parameters(3, 2, 1, p, 3) for p in range(1, 4))),
        ("S", (Parameters(3, 2, 1, 2, s) for s in (1, 2, 3))),
    )
    for dimension, cases in variations:
        for parameters in cases:
            catalog = generate_catalog(parameters)
            start = time.perf_counter()
            plans, stats = memoized_search(catalog, 200_000)
            rows.append({
                "varied_dimension": dimension,
                "G": parameters.G,
                "A": parameters.A,
                "D": parameters.D,
                "P": parameters.P,
                "S": parameters.S,
                "memo_terminal_plans": len(plans),
                "memo_states": stats.states,
                "memo_aborted": stats.aborted,
                "seconds": round(time.perf_counter() - start, 6),
            })
    return rows


def pruning_validation() -> dict[str, object]:
    with_extra_property = SyntheticCatalog(
        (Alternative("use_R", "goal", "R", 1),),
        (
            Producer("cheap_R", "R", None, 2, ("base",)),
            Producer("rich_R", "R", None, 3, ("base", "also_Q")),
        ),
        ("goal",),
        4,
        3,
    )
    plans, _ = memoized_search(with_extra_property)
    retained = prune(with_extra_property, plans)
    assert {plan.producers for plan in retained} == {
        ("cheap_R",),
        ("rich_R",),
    }

    same_properties = SyntheticCatalog(
        (Alternative("use_R", "goal", "R", 1),),
        (
            Producer("cheap_R", "R", None, 2, ("base",)),
            Producer("expensive_R", "R", None, 9, ("base",)),
        ),
        ("goal",),
        4,
        3,
    )
    same_plans, _ = memoized_search(same_properties)
    same_retained = prune(same_properties, same_plans)
    assert {plan.producers for plan in same_retained} == {("cheap_R",)}
    return {
        "different_relevant_property": {
            "plans_before": len(plans),
            "plans_after": len(retained),
            "retained_producers": [plan.producers for plan in retained],
        },
        "same_properties_different_cost": {
            "plans_before": len(same_plans),
            "plans_after": len(same_retained),
            "retained_producers": [plan.producers for plan in same_retained],
        },
        "pruning_rule": "same realization selection, produced resource identities and producer-relevant properties; then lower cost wins",
    }


def reduction_category_validation() -> dict[str, int]:
    catalog = SyntheticCatalog(
        (Alternative("a", "goal", None, 1),),
        (
            Producer("p_R", "R", None, 2),
            Producer("p_Q", "Q", None, 3),
            Producer("p_R_alt", "R", None, 4),
        ),
        ("goal",),
        5,
        4,
    )
    base = Plan(("a",), ("p_R", "p_Q"), 6)
    reordered = Plan(("a",), ("p_Q", "p_R"), 6)
    exact = Plan(("a",), ("p_R", "p_Q"), 6)
    invalid = Plan(("a",), ("p_R", "p_R_alt"), 6)
    _, canonical_equivalents, exact_duplicates, invalid_expansions = canonicalize(
        catalog, (base, reordered, exact, invalid)
    )
    assert (canonical_equivalents, exact_duplicates, invalid_expansions) == (1, 1, 1)
    return {
        "invalid_expansions_filtered": invalid_expansions,
        "canonical_equivalents_merged": canonical_equivalents,
        "exact_duplicates_removed": exact_duplicates,
    }


def run() -> dict[str, object]:
    cases = (
        Parameters(2, 2, 0, 1, 1),
        Parameters(3, 2, 1, 2, 3),
        Parameters(4, 2, 2, 2, 1),
        Parameters(5, 2, 2, 2, 5),
        Parameters(6, 3, 2, 2, 1),
        Parameters(6, 2, 3, 3, 6),
    )
    return {
        "measurements": [measure(parameters) for parameters in cases],
        "sensitivity": sensitivity_results(),
        "pruning_validation": pruning_validation(),
        "reduction_category_validation": reduction_category_validation(),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
