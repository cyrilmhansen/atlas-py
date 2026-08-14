"""Semantic Kernel POC: open catalogue, local scenario facts, path search."""

from __future__ import annotations

import math
from dataclasses import dataclass

from egglog import EGraph, Expr, StringLike, i64, relation, rule, vars_


class Description(Expr):
    def __init__(self, name: StringLike): ...


# Catalogue relations: these are independent of any scenario.
realizes = relation("realizes", Description, Description)
requires = relation("requires", Description, Description)
represents = relation("represents", Description, Description)
sorted_representation = relation("sorted_representation", Description)
hash_index = relation("hash_index", Description)
dense_view = relation("dense_view", Description)
builds = relation("builds", Description, Description, Description)

# Scenario facts and derived search facts.
present = relation("present", Description, Description)
enabled = relation("enabled", Description, Description)
constructible = relation("constructible", Description, Description)
available = relation("available", Description, Description)
uses = relation("uses", Description, Description)

# Local observations used by the abstract cost comparison.
cardinality = relation("cardinality", Description, i64)
cost = relation("cost", Description, Description, i64)
memory_cost = relation("memory_cost", Description, Description, i64)
memory_budget = relation("memory_budget", Description, i64)


@dataclass(frozen=True)
class Scenario:
    name: str
    n: int
    lookups: int = 0
    operation_repetitions: int = 0
    mode: str = "auto"
    present_resources: tuple[str, ...] = ()
    enabled_builders: tuple[str, ...] = ()
    memory_budget_value: int | None = None


def descriptions(scenario_name: str) -> dict[str, Description]:
    names = (
        "lookup(collection,key)",
        "linear_lookup(collection,key)",
        "binary_lookup(sorted_representation,key)",
        "hash_lookup(hash_index,key)",
        "scan(collection)",
        "linear_scan(collection)",
        "scan_dense(dense_view)",
        "scan_sorted(sorted_representation)",
        "operation(P,x)",
        "generic_operation_P(x)",
        "specialized_operation_P(x)",
        "collection",
        "S",
        "H",
        "D",
        "P",
        "input",
        "build_sorted(collection)->S",
        "build_hash_index(collection)->H",
        "build_dense_view(collection)->D",
        "prepare_P(input)->P",
        "workload",
        "lookup_call_1",
        "lookup_call_2",
    )
    result = {name: Description(name) for name in names}
    result["scenario"] = Description(scenario_name)
    return result


def register_catalog(graph: EGraph, d: dict[str, Description]) -> None:
    """Register all generic possibilities, regardless of scenario."""
    graph.register(
        realizes(d["linear_lookup(collection,key)"], d["lookup(collection,key)"]),
        realizes(
            d["binary_lookup(sorted_representation,key)"],
            d["lookup(collection,key)"],
        ),
        realizes(
            d["hash_lookup(hash_index,key)"], d["lookup(collection,key)"]
        ),
        realizes(d["linear_scan(collection)"], d["scan(collection)"]),
        realizes(d["scan_dense(dense_view)"], d["scan(collection)"]),
        realizes(
            d["scan_sorted(sorted_representation)"], d["scan(collection)"]
        ),
        realizes(d["generic_operation_P(x)"], d["operation(P,x)"]),
        realizes(
            d["specialized_operation_P(x)"], d["operation(P,x)"]
        ),
        requires(
            d["binary_lookup(sorted_representation,key)"], d["S"]
        ),
        requires(d["hash_lookup(hash_index,key)"], d["H"]),
        requires(d["scan_dense(dense_view)"], d["D"]),
        requires(d["scan_sorted(sorted_representation)"], d["S"]),
        requires(d["specialized_operation_P(x)"], d["P"]),
        represents(d["S"], d["collection"]),
        sorted_representation(d["S"]),
        represents(d["H"], d["collection"]),
        hash_index(d["H"]),
        represents(d["D"], d["collection"]),
        dense_view(d["D"]),
        builds(d["build_sorted(collection)->S"], d["collection"], d["S"]),
        builds(d["build_hash_index(collection)->H"], d["collection"], d["H"]),
        builds(d["build_dense_view(collection)->D"], d["collection"], d["D"]),
        builds(d["prepare_P(input)->P"], d["input"], d["P"]),
    )


def register_derivation_rules(graph: EGraph) -> None:
    resource, source, result, scenario = vars_(
        "resource source result scenario", Description
    )
    builder, builder_source, built, builder_scenario = vars_(
        "builder builder_source built builder_scenario", Description
    )
    graph.register(
        rule(
            builds(builder, builder_source, built),
            present(builder_source, builder_scenario),
            enabled(builder, builder_scenario),
        ).then(constructible(built, builder_scenario)),
        rule(
            requires(result, resource),
            present(resource, scenario),
        ).then(available(result, scenario)),
        rule(
            requires(result, resource),
            constructible(resource, scenario),
        ).then(available(result, scenario)),
    )


def register_local_facts(
    graph: EGraph, d: dict[str, Description], scenario: Scenario
) -> None:
    scenario_desc = d["scenario"]
    graph.register(
        present(d["collection"], scenario_desc),
        cardinality(d["collection"], i64(scenario.n)),
        available(d["linear_lookup(collection,key)"], scenario_desc),
        available(d["linear_scan(collection)"], scenario_desc),
        uses(d["lookup_call_1"], d["H"]),
        uses(d["lookup_call_2"], d["H"]),
        cost(
            d["linear_lookup(collection,key)"],
            d["workload"],
            i64(scenario.n * scenario.lookups),
        ),
        cost(d["linear_scan(collection)"], d["workload"], i64(scenario.n)),
    )
    if scenario.operation_repetitions:
        graph.register(
            present(d["input"], scenario_desc),
            available(d["generic_operation_P(x)"], scenario_desc),
        )
    for resource in scenario.present_resources:
        graph.register(present(d[resource], scenario_desc))
    for builder in scenario.enabled_builders:
        graph.register(enabled(d[builder], scenario_desc))
    if scenario.memory_budget_value is not None:
        graph.register(
            memory_budget(d["workload"], i64(scenario.memory_budget_value))
        )


def register_local_cost_facts(
    graph: EGraph, d: dict[str, Description], scenario: Scenario
) -> None:
    if (
        "S" in scenario.present_resources
        or "build_sorted(collection)->S" in scenario.enabled_builders
    ):
        build = (
            0
            if "S" in scenario.present_resources
            else math.ceil(scenario.n * math.log2(scenario.n))
        )
        graph.register(
            cost(
                d["binary_lookup(sorted_representation,key)"],
                d["workload"],
                i64(build + math.ceil(math.log2(scenario.n)) * scenario.lookups),
            )
        )
        graph.register(
            cost(
                d["scan_sorted(sorted_representation)"],
                d["workload"],
                i64(build + scenario.n),
            )
        )
    if (
        "H" in scenario.present_resources
        or "build_hash_index(collection)->H" in scenario.enabled_builders
    ):
        build = (
            0
            if "H" in scenario.present_resources
            else 2 * scenario.n
        )
        graph.register(
            cost(
                d["hash_lookup(hash_index,key)"],
                d["workload"],
                i64(build + 3 * scenario.lookups),
            )
        )
        if "build_hash_index(collection)->H" in scenario.enabled_builders:
            graph.register(
                cost(
                    d["build_hash_index(collection)->H"],
                    d["workload"],
                    i64(2 * scenario.n),
                )
            )
    if (
        "D" in scenario.present_resources
        or "build_dense_view(collection)->D" in scenario.enabled_builders
    ):
        build = (
            0
            if "D" in scenario.present_resources
            else scenario.n
        )
        graph.register(
            cost(
                d["scan_dense(dense_view)"],
                d["workload"],
                i64(build + scenario.n // 2),
            ),
            memory_cost(d["D"], d["workload"], i64(2 * scenario.n)),
        )
        if "build_dense_view(collection)->D" in scenario.enabled_builders:
            graph.register(
                cost(
                    d["build_dense_view(collection)->D"],
                    d["workload"],
                    i64(scenario.n),
                )
            )
    if scenario.operation_repetitions:
        graph.register(
            cost(
                d["generic_operation_P(x)"],
                d["workload"],
                i64(10 * scenario.operation_repetitions),
            ),
            cost(
                d["specialized_operation_P(x)"],
                d["workload"],
                i64(100 + 2 * scenario.operation_repetitions),
            ),
            cost(d["prepare_P(input)->P"], d["workload"], i64(100)),
        )


def build_graph(scenario: Scenario) -> tuple[EGraph, dict[str, Description]]:
    d = descriptions(scenario.name)
    graph = EGraph()
    register_catalog(graph, d)
    register_local_facts(graph, d, scenario)
    register_local_cost_facts(graph, d, scenario)
    register_derivation_rules(graph)
    graph.run(10)
    return graph, d


def provable(graph: EGraph, fact: object) -> bool:
    try:
        graph.check(fact)
    except Exception:
        return False
    return True


def choose_best(paths: list[dict[str, object]]) -> dict[str, object]:
    admissible = [path for path in paths if path["admissible"]]
    if not admissible:
        raise AssertionError("every fixed scenario must retain a linear path")
    return min(admissible, key=lambda path: path["cost"])


def lookup_paths(
    graph: EGraph, d: dict[str, Description], scenario: Scenario
) -> dict[str, object]:
    w = d["scenario"]
    linear_available = provable(
        graph, available(d["linear_lookup(collection,key)"], w)
    )
    binary_available = provable(
        graph, available(d["binary_lookup(sorted_representation,key)"], w)
    )
    hash_available = provable(
        graph, available(d["hash_lookup(hash_index,key)"], w)
    )
    binary_constructible = provable(
        graph, constructible(d["S"], w)
    )
    hash_constructible = provable(graph, constructible(d["H"], w))
    paths = [
        {
            "name": "linear_lookup",
            "admissible": linear_available,
            "cost": scenario.n * scenario.lookups,
        },
        {
            "name": "binary_lookup",
            "admissible": binary_available,
            "cost": (
                (0 if "S" in scenario.present_resources
                 else math.ceil(scenario.n * math.log2(scenario.n)))
                + math.ceil(math.log2(scenario.n)) * scenario.lookups
            )
            if binary_available
            else None,
        },
        {
            "name": "hash_lookup",
            "admissible": hash_available,
            "cost": (
                (0 if "H" in scenario.present_resources else 2 * scenario.n)
                + 3 * scenario.lookups
            )
            if hash_available
            else None,
        },
    ]
    for path in paths:
        if not path["admissible"]:
            path["cost"] = None
    selected = choose_best(paths)
    return {
        "intent": "lookup(collection,key)",
        "paths": paths,
        "selected": selected["name"],
        "constructible": {
            "S": binary_constructible,
            "H": hash_constructible,
        },
        "hash_status": (
            "existing"
            if "H" in scenario.present_resources
            else "constructible"
            if hash_constructible
            else "no_known_admissible_producer"
        ),
        "shared_by": ["lookup_call_1", "lookup_call_2"],
    }


def scan_paths(
    graph: EGraph, d: dict[str, Description], scenario: Scenario
) -> dict[str, object]:
    w = d["scenario"]
    dense_available = provable(
        graph, available(d["scan_dense(dense_view)"], w)
    )
    dense_constructible = provable(graph, constructible(d["D"], w))
    dense_memory = 2 * scenario.n
    budget_ok = (
        scenario.memory_budget_value is None
        or dense_memory <= scenario.memory_budget_value
    )
    paths = [
        {
            "name": "linear_scan",
            "admissible": provable(
                graph, available(d["linear_scan(collection)"], w)
            ),
            "cost": scenario.n,
        },
        {
            "name": "scan_dense",
            "admissible": dense_available and budget_ok,
            "cost": (
                (0 if "D" in scenario.present_resources else scenario.n)
                + scenario.n // 2
            )
            if dense_available and budget_ok
            else None,
        },
    ]
    selected = choose_best(paths)
    return {
        "intent": "scan(collection)",
        "paths": paths,
        "selected": selected["name"],
        "constructible": {"D": dense_constructible},
        "dense_status": (
            "existing"
            if "D" in scenario.present_resources
            else "constructible"
            if dense_constructible
            else "no_known_admissible_producer"
        ),
        "memory_cost": dense_memory,
        "memory_budget": scenario.memory_budget_value,
        "memory_admissible": budget_ok,
    }


def composition_paths(
    graph: EGraph, d: dict[str, Description], scenario: Scenario
) -> dict[str, object]:
    w = d["scenario"]
    separate_available = (
        provable(graph, available(d["linear_lookup(collection,key)"], w))
        and provable(graph, available(d["linear_scan(collection)"], w))
    )
    shared_available = (
        provable(
            graph,
            available(d["binary_lookup(sorted_representation,key)"], w),
        )
        and provable(
            graph, available(d["scan_sorted(sorted_representation)"], w)
        )
    )
    build = (
        0
        if "S" in scenario.present_resources
        else math.ceil(scenario.n * math.log2(scenario.n))
    )
    paths = [
        {
            "name": "separate_linear_realizations",
            "admissible": separate_available,
            "cost": scenario.n * scenario.lookups + scenario.n,
        },
        {
            "name": "shared_sorted_preparation",
            "admissible": shared_available,
            "cost": build
            + math.ceil(math.log2(scenario.n)) * scenario.lookups
            + scenario.n,
        },
    ]
    selected = choose_best(paths)
    return {
        "intentions": ["lookup(collection,key)", "scan(collection)"],
        "paths": paths,
        "selected": selected["name"],
        "shared_resource": {
            "resource": "S",
            "producer": "build_sorted(collection)->S",
            "consumers": [
                "binary_lookup(sorted_representation,key)",
                "scan_sorted(sorted_representation)",
            ],
            "build_count": (
                0
                if "S" in scenario.present_resources
                else 1
                if shared_available
                else 0
            ),
        },
    }


def specialization_paths(
    graph: EGraph, d: dict[str, Description], scenario: Scenario
) -> dict[str, object]:
    w = d["scenario"]
    generic_available = provable(
        graph, available(d["generic_operation_P(x)"], w)
    )
    specialized_available = provable(
        graph, available(d["specialized_operation_P(x)"], w)
    )
    repetitions = scenario.operation_repetitions
    paths = [
        {
            "name": "generic_operation",
            "admissible": generic_available,
            "cost": 10 * repetitions,
        },
        {
            "name": "prepare_then_specialize",
            "admissible": specialized_available,
            "cost": 100 + 2 * repetitions,
        },
    ]
    selected = choose_best(paths)
    return {
        "intent": "operation(P,x)",
        "repetitions": repetitions,
        "paths": paths,
        "selected": selected["name"],
        "parameter": "P",
    }


def scenario_result(scenario: Scenario) -> dict[str, object]:
    graph, d = build_graph(scenario)
    result: dict[str, object] = {
        "scenario": scenario.name,
        "n": scenario.n,
        "lookups": scenario.lookups,
    }
    if scenario.mode == "composition":
        result["composition"] = composition_paths(graph, d, scenario)
    elif scenario.mode == "specialization":
        result["specialization"] = specialization_paths(graph, d, scenario)
    elif scenario.lookups:
        result["lookup"] = lookup_paths(graph, d, scenario)
    else:
        result["scan"] = scan_paths(graph, d, scenario)
    return result


def architecture_assertions() -> None:
    no_producer = Scenario("no-producer", 64, lookups=20)
    constructible_hash = Scenario(
        "constructible-hash",
        64,
        lookups=20,
        enabled_builders=("build_hash_index(collection)->H",),
    )
    graph_catalog, d_catalog = build_graph(no_producer)
    graph_constructible, d_constructible = build_graph(constructible_hash)
    builder = d_catalog["build_hash_index(collection)->H"]
    collection = d_catalog["collection"]
    resource = d_catalog["H"]
    scenario = d_constructible["scenario"]

    # 1. The generic catalogue rule exists even where the scenario has no
    # producer fact.
    graph_catalog.check(builds(builder, collection, resource))
    # Constructibility is not intrinsic to the catalogue: without local
    # present/enabled facts, the generic build rule does not derive it.
    assert not provable(
        graph_catalog, constructible(resource, d_catalog["scenario"])
    )
    # 2. Constructibility comes from the catalogue rule plus local facts.
    graph_constructible.check(constructible(resource, scenario))
    # 3. The intention remains present without an admissible hash realization.
    graph_catalog.check(
        realizes(
            d_catalog["hash_lookup(hash_index,key)"],
            d_catalog["lookup(collection,key)"],
        )
    )
    no_producer_result = scenario_result(no_producer)["lookup"]
    assert no_producer_result["selected"] == "linear_lookup"
    assert [p["name"] for p in no_producer_result["paths"]] == [
        "linear_lookup",
        "binary_lookup",
        "hash_lookup",
    ]
    assert no_producer_result["paths"][2]["admissible"] is False
    # 4. Linear wins only because choose_best sees it as the remaining path.
    assert no_producer_result["selected"] == choose_best(
        no_producer_result["paths"]
    )["name"]

    # Admissibility is not an egglog/catalogue property. It is computed only
    # by search from derived availability plus the local memory constraint.
    tight_dense = Scenario(
        "tight-dense",
        100,
        enabled_builders=("build_dense_view(collection)->D",),
        memory_budget_value=100,
    )
    tight_result = scenario_result(tight_dense)["scan"]
    tight_graph, tight_d = build_graph(tight_dense)
    assert provable(tight_graph, constructible(tight_d["D"], tight_d["scenario"]))
    assert tight_result["memory_admissible"] is False
    dense_path = next(
        path for path in tight_result["paths"] if path["name"] == "scan_dense"
    )
    assert dense_path["admissible"] is False

    small_composition = Scenario(
        "shared-preparation-not-worthwhile",
        16,
        lookups=1,
        mode="composition",
        enabled_builders=("build_sorted(collection)->S",),
    )
    large_composition = Scenario(
        "shared-preparation-worthwhile",
        64,
        lookups=20,
        mode="composition",
        enabled_builders=("build_sorted(collection)->S",),
    )
    small_result = scenario_result(small_composition)["composition"]
    large_result = scenario_result(large_composition)["composition"]
    assert small_result["selected"] == "separate_linear_realizations"
    assert large_result["selected"] == "shared_sorted_preparation"
    assert large_result["shared_resource"]["build_count"] == 1
    assert large_result["shared_resource"]["consumers"] == [
        "binary_lookup(sorted_representation,key)",
        "scan_sorted(sorted_representation)",
    ]

    existing_shared = scenario_result(
        Scenario(
            "shared-existing-sorted",
            64,
            lookups=20,
            mode="composition",
            present_resources=("S",),
        )
    )["composition"]
    assert existing_shared["shared_resource"]["build_count"] == 0

    low_reuse = Scenario(
        "specialization-not-worthwhile",
        1,
        operation_repetitions=5,
        mode="specialization",
        present_resources=("P",),
    )
    high_reuse = Scenario(
        "specialization-worthwhile",
        1,
        operation_repetitions=20,
        mode="specialization",
        present_resources=("P",),
    )
    assert (
        scenario_result(low_reuse)["specialization"]["selected"]
        == "generic_operation"
    )
    assert (
        scenario_result(high_reuse)["specialization"]["selected"]
        == "prepare_then_specialize"
    )


def run() -> list[dict[str, object]]:
    scenarios = [
        Scenario(
            "shared_preparation_not_worthwhile",
            n=16,
            lookups=1,
            mode="composition",
            enabled_builders=("build_sorted(collection)->S",),
        ),
        Scenario(
            "shared_preparation_worthwhile",
            n=64,
            lookups=20,
            mode="composition",
            enabled_builders=("build_sorted(collection)->S",),
        ),
        Scenario(
            "sorted_representation_exists",
            n=64,
            lookups=20,
            present_resources=("S",),
        ),
        Scenario(
            "sorted_representation_constructed_once",
            n=64,
            lookups=20,
            enabled_builders=("build_sorted(collection)->S",),
        ),
        Scenario(
            "hash_exists_and_is_shared",
            n=64,
            lookups=20,
            present_resources=("H",),
        ),
        Scenario(
            "hash_constructed_once_for_many_lookups",
            n=64,
            lookups=20,
            enabled_builders=("build_hash_index(collection)->H",),
        ),
        Scenario(
            "hash_no_known_producer_falls_back_to_linear",
            n=64,
            lookups=20,
        ),
        Scenario(
            "scan_with_existing_dense_view",
            n=100,
            present_resources=("D",),
            memory_budget_value=250,
        ),
        Scenario(
            "scan_dense_view_constructible",
            n=100,
            enabled_builders=("build_dense_view(collection)->D",),
            memory_budget_value=250,
        ),
        Scenario(
            "scan_dense_view_exceeds_memory_budget",
            n=100,
            enabled_builders=("build_dense_view(collection)->D",),
            memory_budget_value=100,
        ),
        Scenario(
            "specialization_not_worthwhile",
            n=1,
            operation_repetitions=5,
            mode="specialization",
            present_resources=("P",),
        ),
        Scenario(
            "specialization_worthwhile",
            n=1,
            operation_repetitions=20,
            mode="specialization",
            present_resources=("P",),
        ),
    ]
    architecture_assertions()
    return [scenario_result(scenario) for scenario in scenarios]


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2))
