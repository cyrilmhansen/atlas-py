"""Minimal experiment: selection before scheduling versus joint optimization."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model


@dataclass(frozen=True)
class Realization:
    name: str
    duration: int
    scratch: int
    produces: Tuple[str, ...] = ()
    consumes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Intent:
    name: str
    realizations: Tuple[Realization, ...]


@dataclass(frozen=True)
class Scenario:
    name: str
    intents: Tuple[Intent, ...]
    scratch_capacity: int
    deadline: int
    before: Tuple[Tuple[str, str], ...] = ()


@dataclass
class Result:
    status: str
    objective: Optional[int]
    selection: Dict[str, str]
    starts: Dict[str, int]
    ends: Dict[str, int]
    note: str = ""


@dataclass(frozen=True)
class ResourceSpec:
    name: str
    size: int
    producer: str
    consumers: Tuple[str, ...]


@dataclass(frozen=True)
class LifecycleScenario:
    name: str
    intents: Tuple[Intent, ...]
    resources: Tuple[ResourceSpec, ...]
    scratch_capacity: int
    memory_capacity: int
    deadline: int
    before: Tuple[Tuple[str, str], ...] = ()


@dataclass
class LifecycleResult:
    status: str
    objective: Optional[int]
    selection: Dict[str, str]
    starts: Dict[str, int]
    ends: Dict[str, int]
    lifetimes: Dict[str, Tuple[int, int]]
    peak_memory: int
    note: str = ""


@dataclass(frozen=True)
class CompositeOperation:
    name: str
    duration: int
    scratch: int = 0
    produces: Tuple[str, ...] = ()
    consumes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CompositeRealization:
    name: str
    operations: Tuple[CompositeOperation, ...]
    before: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CompositeScenario:
    name: str
    realizations: Tuple[CompositeRealization, ...]
    resources: Tuple["CompositeResourceSpec", ...]
    scratch_capacity: int
    memory_capacity: int
    deadline: int


@dataclass
class CompositeResult:
    status: str
    makespan: Optional[int]
    selected: Optional[str]
    starts: Dict[str, int]
    ends: Dict[str, int]
    lifetimes: Dict[str, Tuple[int, int]]
    peak_memory: int
    note: str = ""


@dataclass(frozen=True)
class CompositeResourceSpec:
    name: str
    size: int
    producers: Tuple[str, ...]
    consumers: Tuple[str, ...]


@dataclass(frozen=True)
class MultiCompositeScenario:
    name: str
    intentions: Tuple[Tuple[str, Tuple[CompositeRealization, ...]], ...]
    resources: Tuple[CompositeResourceSpec, ...]
    scratch_capacity: int
    memory_capacity: int
    deadline: Optional[int]


@dataclass
class MultiCompositeResult:
    status: str
    makespan: Optional[int]
    selected: Dict[str, str]
    starts: Dict[str, int]
    ends: Dict[str, int]
    lifetimes: Dict[str, Tuple[int, int]]
    peak_memory: int
    note: str = ""


def _solver() -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 7
    return solver


def select_then_schedule(scenario: Scenario) -> Result:
    """Select minimum duration without using temporal constraints, then fix it."""
    selection = {
        intent.name: min(intent.realizations, key=lambda r: (r.duration, r.name)).name
        for intent in scenario.intents
    }

    model = cp_model.CpModel()
    horizon = scenario.deadline
    starts = {name: model.new_int_var(0, horizon, f"start_{name}")
              for name in selection}
    ends = {name: model.new_int_var(0, horizon, f"end_{name}")
            for name in selection}
    intervals = []
    selected = {}
    for intent in scenario.intents:
        realization = next(r for r in intent.realizations
                           if r.name == selection[intent.name])
        model.add(ends[intent.name] == starts[intent.name] + realization.duration)
        intervals.append(model.new_interval_var(
            starts[intent.name], realization.duration, ends[intent.name],
            f"interval_{intent.name}"))
        selected[intent.name] = realization
    model.add_cumulative(intervals, [r.scratch for r in selected.values()],
                         scenario.scratch_capacity)
    for left, right in scenario.before:
        model.add(ends[left] <= starts[right])
    makespan = model.new_int_var(0, horizon, "makespan")
    model.add_max_equality(makespan, list(ends.values()))
    model.minimize(makespan)
    solver = _solver()
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Result("infeasible", None, selection, {}, {},
                      "static selection cannot be scheduled")
    return Result("feasible", solver.objective_value, selection,
                  {n: solver.value(v) for n, v in starts.items()},
                  {n: solver.value(v) for n, v in ends.items()})


def joint_select_and_schedule(scenario: Scenario) -> Result:
    """Select one optional interval per intent while scheduling it."""
    model = cp_model.CpModel()
    horizon = scenario.deadline
    starts, ends, choices, intervals = {}, {}, {}, []
    for intent in scenario.intents:
        choices[intent.name] = []
        for realization in intent.realizations:
            key = (intent.name, realization.name)
            present = model.new_bool_var(f"use_{intent.name}_{realization.name}")
            start = model.new_int_var(0, horizon, f"start_{intent.name}_{realization.name}")
            end = model.new_int_var(0, horizon, f"end_{intent.name}_{realization.name}")
            interval = model.new_optional_interval_var(
                start, realization.duration, end, present,
                f"interval_{intent.name}_{realization.name}")
            model.add(start == 0).only_enforce_if(present.Not())
            model.add(end == 0).only_enforce_if(present.Not())
            choices[intent.name].append((realization, present, start, end))
            intervals.append((interval, realization.scratch))
            starts[key], ends[key] = start, end
        model.add_exactly_one(present for _, present, _, _ in choices[intent.name])

    model.add_cumulative([i for i, _ in intervals], [s for _, s in intervals],
                         scenario.scratch_capacity)
    for left, right in scenario.before:
        for left_r, left_p, _, left_end in choices[left]:
            for right_r, right_p, right_start, _ in choices[right]:
                # If both alternatives are selected, enforce the dependency.
                model.add(left_end <= right_start).only_enforce_if([left_p, right_p])

    makespan = model.new_int_var(0, horizon, "makespan")
    for intent in scenario.intents:
        for _, present, _, end in choices[intent.name]:
            model.add(makespan >= end).only_enforce_if(present)
    model.minimize(makespan * 100 + sum(
        realization.duration * present
        for entries in choices.values()
        for realization, present, _, _ in entries))

    solver = _solver()
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Result("infeasible", None, {}, {}, {}, "no joint plan")
    selection, result_starts, result_ends = {}, {}, {}
    for intent in scenario.intents:
        for realization, present, start, end in choices[intent.name]:
            if solver.value(present):
                selection[intent.name] = realization.name
                result_starts[intent.name] = solver.value(start)
                result_ends[intent.name] = solver.value(end)
    return Result("feasible", solver.objective_value, selection,
                  result_starts, result_ends)


def run_case(scenario: Scenario) -> Tuple[Result, Result]:
    static = select_then_schedule(scenario)
    joint = joint_select_and_schedule(scenario)
    print(f"{scenario.name}: static={static.status} {static.selection}; "
          f"joint={joint.status} {joint.selection}")
    return static, joint


def _lifecycle_model(scenario: LifecycleScenario,
                     fixed_selection: Optional[Dict[str, str]] = None):
    """Build one joint model; resource intervals are derived from operation choices."""
    model = cp_model.CpModel()
    horizon = scenario.deadline
    choices = {}
    operation_intervals = []
    for intent in scenario.intents:
        choices[intent.name] = []
        for realization in intent.realizations:
            present = model.new_bool_var(f"use_{intent.name}_{realization.name}")
            start = model.new_int_var(0, horizon, f"start_{intent.name}_{realization.name}")
            end = model.new_int_var(0, horizon, f"end_{intent.name}_{realization.name}")
            interval = model.new_optional_interval_var(
                start, realization.duration, end, present,
                f"interval_{intent.name}_{realization.name}")
            model.add(start == 0).only_enforce_if(present.Not())
            model.add(end == 0).only_enforce_if(present.Not())
            choices[intent.name].append((realization, present, start, end))
            operation_intervals.append((interval, realization.scratch))
        if fixed_selection is None:
            model.add_exactly_one(p for _, p, _, _ in choices[intent.name])
        else:
            for realization, present, _, _ in choices[intent.name]:
                model.add(present == (realization.name == fixed_selection[intent.name]))

    model.add_cumulative([i for i, _ in operation_intervals],
                         [s for _, s in operation_intervals],
                         scenario.scratch_capacity)
    for left, right in scenario.before:
        for _, left_p, _, left_end in choices[left]:
            for _, right_p, right_start, _ in choices[right]:
                model.add(left_end <= right_start).only_enforce_if([left_p, right_p])

    resource_intervals = []
    resource_meta = {}
    for resource in scenario.resources:
        producer_choices = [entry for entry in choices[resource.producer]
                            if resource.name in entry[0].produces]
        if not producer_choices:
            raise ValueError(f"no realization produces {resource.name}")
        model.add_exactly_one(p for _, p, _, _ in producer_choices)
        consumer_ends = []
        for consumer in resource.consumers:
            consumer_choices = choices[consumer]
            for realization, present, start, end in consumer_choices:
                if resource.name not in realization.consumes:
                    raise ValueError(f"{consumer} does not consume {resource.name}")
                consumer_ends.append(end)
                for _, producer_p, _, producer_end in producer_choices:
                    model.add(producer_end <= start).only_enforce_if([producer_p, present])

        # The resource is live from production completion through its last use.
        for producer_realization, producer_p, _, producer_end in producer_choices:
            resource_end = model.new_int_var(0, horizon, f"end_resource_{resource.name}_{producer_realization.name}")
            resource_duration = model.new_int_var(0, horizon, f"duration_resource_{resource.name}_{producer_realization.name}")
            if consumer_ends:
                model.add_max_equality(resource_end, consumer_ends)
            else:
                model.add(resource_end == producer_end)
            model.add(resource_duration == resource_end - producer_end)
            interval = model.new_optional_interval_var(
                producer_end, resource_duration, resource_end,
                producer_p, f"life_{resource.name}_{producer_realization.name}")
            resource_intervals.append((interval, resource.size))
            resource_meta[(resource.name, producer_realization.name)] = (producer_end, resource_end, producer_p)

    model.add_cumulative([i for i, _ in resource_intervals],
                         [s for _, s in resource_intervals],
                         scenario.memory_capacity)
    makespan = model.new_int_var(0, horizon, "makespan")
    for intent in scenario.intents:
        for _, present, _, end in choices[intent.name]:
            model.add(makespan >= end).only_enforce_if(present)
    model.minimize(makespan)
    return model, choices, resource_meta, makespan


def _lifecycle_result(solver, choices, resource_meta, resources,
                      objective=None) -> LifecycleResult:
    chosen = {}
    starts, ends = {}, {}
    for intent, entries in choices.items():
        for realization, present, start, end in entries:
            if solver.value(present):
                chosen[intent] = realization.name
                starts[intent] = solver.value(start)
                ends[intent] = solver.value(end)
    lifetimes = {}
    for (name, realization), (start, end, present) in resource_meta.items():
        if solver.value(present):
            lifetimes[name] = (solver.value(start), solver.value(end))
    sizes = {resource.name: resource.size for resource in resources}
    peak = 0
    points = sorted({point for lifetime in lifetimes.values() for point in lifetime})
    for point in points:
        peak = max(peak, sum(
            sizes[name]
            for name, (start, end) in lifetimes.items() if start <= point < end
        ))
    return LifecycleResult("feasible", objective, chosen, starts, ends,
                           lifetimes, peak)


def schedule_lifetimes(scenario: LifecycleScenario,
                       fixed_selection: Optional[Dict[str, str]] = None) -> LifecycleResult:
    model, choices, resource_meta, makespan = _lifecycle_model(scenario, fixed_selection)
    solver = _solver()
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        selection = fixed_selection or {}
        return LifecycleResult("infeasible", None, selection, {}, {}, {}, 0,
                               "lifetime plan violates capacity/deadline")
    return _lifecycle_result(solver, choices, resource_meta, scenario.resources,
                             solver.value(makespan))


def lifecycle_case(scenario: LifecycleScenario) -> LifecycleResult:
    result = schedule_lifetimes(scenario)
    print(f"{scenario.name}: status={result.status} selection={result.selection} "
          f"makespan={result.objective} peak={result.peak_memory} "
          f"lifetimes={result.lifetimes}")
    return result


def solve_composite(scenario: CompositeScenario) -> CompositeResult:
    """Select one composite realization and schedule its internal graph jointly."""
    model = cp_model.CpModel()
    horizon = scenario.deadline
    selected = [model.new_bool_var(f"use_{r.name}") for r in scenario.realizations]
    model.add_exactly_one(selected)
    operations = {}
    operation_intervals = []
    for realization, realization_present in zip(scenario.realizations, selected):
        for operation in realization.operations:
            present = realization_present
            start = model.new_int_var(0, horizon, f"start_{operation.name}")
            end = model.new_int_var(0, horizon, f"end_{operation.name}")
            interval = model.new_optional_interval_var(
                start, operation.duration, end, present, f"interval_{operation.name}")
            model.add(start == 0).only_enforce_if(present.Not())
            model.add(end == 0).only_enforce_if(present.Not())
            operations[operation.name] = (operation, present, start, end)
            operation_intervals.append((interval, operation.scratch))
        for left, right in realization.before:
            left_end = operations[left][3]
            right_start = operations[right][2]
            model.add(left_end <= right_start).only_enforce_if(realization_present)

    model.add_cumulative([interval for interval, _ in operation_intervals],
                         [scratch for _, scratch in operation_intervals],
                         scenario.scratch_capacity)

    resource_intervals = []
    resource_meta = {}
    for resource in scenario.resources:
        producer_entries = []
        for producer_name in resource.producers:
            if producer_name not in operations:
                raise ValueError(f"unknown producer operation {producer_name}")
            producer_operation, producer_present, _, producer_end = operations[producer_name]
            if resource.name not in producer_operation.produces:
                raise ValueError(f"{producer_name} does not produce {resource.name}")
            producer_entries.append((producer_name, producer_operation,
                                     producer_present, producer_end))
        consumer_ends = []
        for consumer_name in resource.consumers:
            if consumer_name not in operations:
                raise ValueError(f"unknown consumer operation {consumer_name}")
            consumer_operation, consumer_present, consumer_start, consumer_end = operations[consumer_name]
            if resource.name not in consumer_operation.consumes:
                raise ValueError(f"{consumer_name} does not consume {resource.name}")
            consumer_ends.append(consumer_end)
            for _, _, producer_present, producer_end in producer_entries:
                model.add(producer_end <= consumer_start).only_enforce_if(
                    [producer_present, consumer_present])

        resource_end = model.new_int_var(0, horizon, f"end_resource_{resource.name}")
        model.add_max_equality(resource_end, consumer_ends)
        resource_meta[resource.name] = []
        for producer_name, _, producer_present, producer_end in producer_entries:
            resource_duration = model.new_int_var(
                0, horizon, f"duration_resource_{resource.name}_{producer_name}")
            model.add(resource_duration == resource_end - producer_end)
            interval = model.new_optional_interval_var(
                producer_end, resource_duration, resource_end, producer_present,
                f"life_{resource.name}_{producer_name}")
            resource_intervals.append((interval, resource.size))
            resource_meta[resource.name].append((producer_name, producer_end,
                                                 resource_end, producer_present))

    model.add_cumulative([interval for interval, _ in resource_intervals],
                         [size for _, size in resource_intervals],
                         scenario.memory_capacity)
    makespan = model.new_int_var(0, horizon, "makespan")
    for _, present, _, end in operations.values():
        model.add(makespan >= end).only_enforce_if(present)
    model.minimize(makespan)
    solver = _solver()
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return CompositeResult("infeasible", None, None, {}, {}, {}, 0,
                               "no realization and schedule satisfy constraints")

    selected_name = next(r.name for r, present in zip(scenario.realizations, selected)
                         if solver.value(present))
    starts = {name: solver.value(start) for name, (_, present, start, _) in operations.items()
              if solver.value(present)}
    ends = {name: solver.value(end) for name, (_, present, _, end) in operations.items()
            if solver.value(present)}
    lifetimes = {}
    for name, entries in resource_meta.items():
        for _, start, end, present in entries:
            if solver.value(present):
                lifetimes[name] = (solver.value(start), solver.value(end))
    sizes = {resource.name: resource.size for resource in scenario.resources}
    points = sorted({point for lifetime in lifetimes.values() for point in lifetime})
    peak = max((sum(sizes[name] for name, (start, end) in lifetimes.items()
                    if start <= point < end) for point in points), default=0)
    return CompositeResult("feasible", solver.value(makespan), selected_name,
                           starts, ends, lifetimes, peak)


def composite_case(scenario: CompositeScenario) -> CompositeResult:
    result = solve_composite(scenario)
    print(f"{scenario.name}: status={result.status} selected={result.selected} "
          f"makespan={result.makespan} peak={result.peak_memory} "
          f"lifetimes={result.lifetimes}")
    return result


def solve_multi_composite(
    scenario: MultiCompositeScenario,
    fixed_selection: Optional[Dict[str, str]] = None,
) -> MultiCompositeResult:
    """Jointly select one graph per intention and schedule all selected graphs."""
    model = cp_model.CpModel()
    # None means no effective deadline; 20 is only a finite CP-SAT domain bound
    # above every schedule in this small experiment.
    horizon = scenario.deadline if scenario.deadline is not None else 20
    choices = {}
    operations = {}
    operation_intervals = []
    for intent_name, realizations in scenario.intentions:
        selected = []
        for realization in realizations:
            present = model.new_bool_var(f"use_{intent_name}_{realization.name}")
            selected.append(present)
            if fixed_selection is not None:
                model.add(present == (fixed_selection[intent_name] == realization.name))
            for operation in realization.operations:
                start = model.new_int_var(0, horizon, f"start_{operation.name}")
                end = model.new_int_var(0, horizon, f"end_{operation.name}")
                interval = model.new_optional_interval_var(
                    start, operation.duration, end, present, f"interval_{operation.name}")
                model.add(start == 0).only_enforce_if(present.Not())
                model.add(end == 0).only_enforce_if(present.Not())
                operations[operation.name] = (operation, present, start, end)
                operation_intervals.append((interval, operation.scratch))
            for left, right in realization.before:
                model.add(operations[left][3] <= operations[right][2]).only_enforce_if(present)
        model.add_exactly_one(selected)
        choices[intent_name] = selected

    model.add_cumulative([interval for interval, _ in operation_intervals],
                         [scratch for _, scratch in operation_intervals],
                         scenario.scratch_capacity)

    resource_intervals = []
    resource_meta = {}
    for resource in scenario.resources:
        producer_entries = []
        for producer_name in resource.producers:
            if producer_name not in operations:
                raise ValueError(f"unknown producer operation {producer_name}")
            operation, present, _, end = operations[producer_name]
            if resource.name not in operation.produces:
                raise ValueError(f"{producer_name} does not produce {resource.name}")
            producer_entries.append((producer_name, present, end))
        model.add_bool_or([present for _, present, _ in producer_entries])
        consumer_ends = []
        for consumer_name in resource.consumers:
            if consumer_name not in operations:
                raise ValueError(f"unknown consumer operation {consumer_name}")
            operation, consumer_present, start, end = operations[consumer_name]
            if resource.name not in operation.consumes:
                raise ValueError(f"{consumer_name} does not consume {resource.name}")
            consumer_ends.append(end)
            for _, producer_present, producer_end in producer_entries:
                model.add(producer_end <= start).only_enforce_if(
                    [producer_present, consumer_present])

        resource_end = model.new_int_var(0, horizon, f"end_resource_{resource.name}")
        model.add_max_equality(resource_end, consumer_ends)
        resource_meta[resource.name] = []
        for producer_name, producer_present, producer_end in producer_entries:
            resource_duration = model.new_int_var(
                0, horizon, f"duration_resource_{resource.name}_{producer_name}")
            model.add(resource_duration == resource_end - producer_end)
            interval = model.new_optional_interval_var(
                producer_end, resource_duration, resource_end, producer_present,
                f"life_{resource.name}_{producer_name}")
            resource_intervals.append((interval, resource.size))
            resource_meta[resource.name].append((producer_name, producer_end,
                                                 resource_end, producer_present))

    model.add_cumulative([interval for interval, _ in resource_intervals],
                         [size for _, size in resource_intervals],
                         scenario.memory_capacity)
    makespan = model.new_int_var(0, horizon, "makespan")
    for _, present, _, end in operations.values():
        model.add(makespan >= end).only_enforce_if(present)
    model.minimize(makespan)

    solver = _solver()
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return MultiCompositeResult("infeasible", None, {}, {}, {}, {}, 0,
                                    "no joint selection and schedule satisfy constraints")

    selected = {}
    for intent_name, realizations in scenario.intentions:
        selected[intent_name] = next(
            realization.name for realization, present in zip(realizations, choices[intent_name])
            if solver.value(present))
    starts = {name: solver.value(start) for name, (_, present, start, _) in operations.items()
              if solver.value(present)}
    ends = {name: solver.value(end) for name, (_, present, _, end) in operations.items()
            if solver.value(present)}
    lifetimes = {}
    for name, entries in resource_meta.items():
        for _, start, end, present in entries:
            if solver.value(present):
                lifetimes[name] = (solver.value(start), solver.value(end))
    sizes = {resource.name: resource.size for resource in scenario.resources}
    points = sorted({point for lifetime in lifetimes.values() for point in lifetime})
    peak = max((sum(sizes[name] for name, (start, end) in lifetimes.items()
                    if start <= point < end) for point in points), default=0)
    return MultiCompositeResult("feasible", solver.value(makespan), selected,
                                starts, ends, lifetimes, peak)


def multi_composite_case(scenario: MultiCompositeScenario,
                         fixed_selection: Optional[Dict[str, str]] = None):
    result = solve_multi_composite(scenario, fixed_selection)
    print(f"{scenario.name}: status={result.status} selected={result.selected} "
          f"makespan={result.makespan} peak={result.peak_memory} "
          f"lifetimes={result.lifetimes}")
    return result


def main() -> None:
    divergence = Scenario(
        "counterexample_fast_overlap", (
            Intent("A", (Realization("Fast", 2, 5), Realization("Compact", 3, 1))),
            Intent("B", (Realization("Fast", 2, 5), Realization("Compact", 3, 1))),
        ), scratch_capacity=5, deadline=3)
    witness = Scenario(
        "separation_safe", (
            Intent("A", (Realization("Fast", 2, 5), Realization("Compact", 3, 1))),
            Intent("B", (Realization("Fast", 2, 5), Realization("Compact", 3, 1))),
        ), scratch_capacity=10, deadline=2)

    static_bad, joint_good = run_case(divergence)
    assert static_bad.status == "infeasible"
    assert joint_good.status == "feasible"
    assert joint_good.selection == {"A": "Compact", "B": "Compact"}
    assert max(joint_good.ends.values()) <= divergence.deadline

    static_same, joint_same = run_case(witness)
    assert static_same.status == joint_same.status == "feasible"
    assert static_same.selection == joint_same.selection == {"A": "Fast", "B": "Fast"}
    assert max(static_same.ends.values()) <= witness.deadline

    producer_a = Intent("produce_A", (Realization("produce", 1, 1, ("A",)),))
    consumer_a = Intent("consume_A", (Realization("consume", 1, 1, (), ("A",)),))
    producer_b = Intent("produce_B", (Realization("produce", 1, 1, ("B",)),))
    consumer_b = Intent("consume_B", (Realization("consume", 1, 1, (), ("B",)),))
    branches = (producer_a, consumer_a, producer_b, consumer_b)
    resources = (ResourceSpec("A", 5, "produce_A", ("consume_A",)),
                 ResourceSpec("B", 7, "produce_B", ("consume_B",)))
    sequential = LifecycleScenario(
        "lifetimes_sequential_reuse", branches, resources, 4, 7, 4,
        (("consume_A", "produce_B"),))
    sequential_result = lifecycle_case(sequential)
    assert sequential_result.status == "feasible"
    assert sequential_result.peak_memory == 7
    assert sequential_result.lifetimes["A"][1] <= sequential_result.lifetimes["B"][0]

    concurrent = LifecycleScenario(
        "lifetimes_concurrent_required", branches, resources, 4, 12, 2)
    concurrent_result = lifecycle_case(concurrent)
    assert concurrent_result.status == "feasible"
    assert concurrent_result.peak_memory == 12
    assert concurrent_result.lifetimes["A"][0] < concurrent_result.lifetimes["B"][1]

    fast_memory = tuple(
        Intent(name, (Realization("same", 1, 1, (resource,)),))
        for name, resource in (("produce_A", "A"), ("produce_B", "B")))
    same_consumers = (consumer_a, consumer_b)
    planning_ops = fast_memory + same_consumers
    fast_resources = (ResourceSpec("A", 6, "produce_A", ("consume_A",)),
                      ResourceSpec("B", 6, "produce_B", ("consume_B",)))
    rapid = LifecycleScenario("planning_fast_overlap", planning_ops, fast_resources,
                              4, 12, 2)
    compact = LifecycleScenario("planning_compact_reuse", planning_ops, fast_resources,
                                4, 6, 4)
    rapid_result = lifecycle_case(rapid)
    compact_result = lifecycle_case(compact)
    assert rapid_result.status == compact_result.status == "feasible"
    assert rapid_result.objective < compact_result.objective
    assert rapid_result.peak_memory > compact_result.peak_memory

    wide = CompositeRealization(
        "wide",
        (CompositeOperation("wide.produce_A", 1, produces=("A",)),
         CompositeOperation("wide.produce_B", 1, produces=("B",)),
         CompositeOperation("wide.combine", 1, consumes=("A", "B"))),
        (("wide.produce_A", "wide.combine"),
         ("wide.produce_B", "wide.combine")))
    streamed = CompositeRealization(
        "streamed",
        (CompositeOperation("streamed.produce_A", 1, produces=("A",)),
         CompositeOperation("streamed.consume_A_produce_B", 1,
                            produces=("B",), consumes=("A",)),
         CompositeOperation("streamed.consume_B", 1, consumes=("B",))),
        (("streamed.produce_A", "streamed.consume_A_produce_B"),
         ("streamed.consume_A_produce_B", "streamed.consume_B")))
    composite_resources = (
        CompositeResourceSpec("A", 6,
                              ("wide.produce_A", "streamed.produce_A"),
                              ("wide.combine", "streamed.consume_A_produce_B")),
        CompositeResourceSpec("B", 6,
                              ("wide.produce_B", "streamed.consume_A_produce_B"),
                              ("wide.combine", "streamed.consume_B")),
    )
    abundant = CompositeScenario("compute_result_memory_abundant", (wide, streamed),
                                 composite_resources, 10, 12, 2)
    constrained = CompositeScenario("compute_result_memory_constrained", (wide, streamed),
                                    composite_resources, 10, 6, 10)
    conflict = CompositeScenario("compute_result_time_memory_conflict", (wide, streamed),
                                 composite_resources, 10, 6, 2)
    abundant_result = composite_case(abundant)
    constrained_result = composite_case(constrained)
    conflict_result = composite_case(conflict)
    assert abundant_result.status == "feasible"
    assert abundant_result.selected == "wide"
    assert abundant_result.makespan == 2
    assert abundant_result.peak_memory == 12
    assert constrained_result.status == "feasible"
    assert constrained_result.selected == "streamed"
    assert constrained_result.makespan == 3
    assert constrained_result.peak_memory == 6
    assert conflict_result.status == "infeasible"
    assert constrained_result.lifetimes["A"][1] <= constrained_result.lifetimes["B"][0]

    print("choice assertions: OK")
    print("selection and internal dependency graph jointly determine lifetimes and peak")

    def local_realizations(prefix, resource):
        fast = CompositeRealization(
            "fast",
            (CompositeOperation(f"{prefix}.fast.produce", 1,
                                produces=(resource,)),
             CompositeOperation(f"{prefix}.fast.consume", 2,
                                consumes=(resource,))),
            ((f"{prefix}.fast.produce", f"{prefix}.fast.consume"),))
        compact = CompositeRealization(
            "compact",
            (CompositeOperation(f"{prefix}.compact.prepare", 2),
             CompositeOperation(f"{prefix}.compact.produce", 1,
                                produces=(resource,)),
             CompositeOperation(f"{prefix}.compact.consume", 1,
                                consumes=(resource,))),
            ((f"{prefix}.compact.prepare", f"{prefix}.compact.produce"),
             (f"{prefix}.compact.produce", f"{prefix}.compact.consume")))
        return fast, compact

    x_fast, x_compact = local_realizations("X", "X")
    y_fast, y_compact = local_realizations("Y", "Y")
    multi_resources = (
        CompositeResourceSpec("X", 6,
                              ("X.fast.produce", "X.compact.produce"),
                              ("X.fast.consume", "X.compact.consume")),
        CompositeResourceSpec("Y", 6,
                              ("Y.fast.produce", "Y.compact.produce"),
                              ("Y.fast.consume", "Y.compact.consume")),
    )
    global_intentions = (("compute_x", (x_fast, x_compact)),
                         ("compute_y", (y_fast, y_compact)))
    local_x = MultiCompositeScenario("local_compute_x", (("compute_x", (x_fast, x_compact)),),
                                     (multi_resources[0],), 10, 12, 10)
    local_y = MultiCompositeScenario("local_compute_y", (("compute_y", (y_fast, y_compact)),),
                                     (multi_resources[1],), 10, 12, 10)
    local_x_result = multi_composite_case(local_x)
    local_y_result = multi_composite_case(local_y)
    local_x_compact_result = multi_composite_case(local_x, {"compute_x": "compact"})
    local_y_compact_result = multi_composite_case(local_y, {"compute_y": "compact"})
    assert local_x_result.status == local_y_result.status == "feasible"
    assert local_x_result.selected == {"compute_x": "fast"}
    assert local_y_result.selected == {"compute_y": "fast"}
    assert local_x_compact_result.status == local_y_compact_result.status == "feasible"
    assert local_x_result.makespan == local_y_result.makespan == 3
    assert local_x_compact_result.makespan == local_y_compact_result.makespan == 4
    assert local_x_result.makespan < local_x_compact_result.makespan

    constrained_global = MultiCompositeScenario(
        "independent_local_choice_fails", global_intentions, multi_resources,
        10, 8, 4)
    abundant_global = MultiCompositeScenario(
        "independent_local_choice_restored", global_intentions, multi_resources,
        10, 12, 3)
    baseline = multi_composite_case(
        constrained_global, {"compute_x": "fast", "compute_y": "fast"})
    constrained_global_result = multi_composite_case(constrained_global)
    abundant_global_result = multi_composite_case(abundant_global)
    assert baseline.status == "infeasible"
    assert constrained_global_result.status == "feasible"
    assert sorted(constrained_global_result.selected.values()) == ["compact", "fast"]
    assert constrained_global_result.makespan == 4
    assert constrained_global_result.peak_memory == 6
    assert constrained_global_result.peak_memory <= constrained_global.memory_capacity
    assert abundant_global_result.status == "feasible"
    assert abundant_global_result.selected == {"compute_x": "fast", "compute_y": "fast"}
    assert abundant_global_result.makespan == 3
    assert abundant_global_result.peak_memory == 12
    assert abundant_global_result.makespan < constrained_global_result.makespan
    assert abundant_global_result.peak_memory > constrained_global_result.peak_memory
    print("multi-intention assertions: OK")
    print("independent fast choices fail globally; joint selection finds a mixed plan")

    local_selection = {
        "compute_x": local_x_result.selected["compute_x"],
        "compute_y": local_y_result.selected["compute_y"],
    }
    grid = []
    print("memory deadline | local selected/status ms peak | joint selected/status ms peak | class")
    print("---------------------------------------------------------------------------------------")
    for memory in range(6, 13):
        for deadline in (None, 3, 4, 5):
            grid_scenario = MultiCompositeScenario(
                f"grid_m{memory}_d{deadline}", global_intentions, multi_resources,
                10, memory, deadline)
            local = solve_multi_composite(grid_scenario, local_selection)
            joint = solve_multi_composite(grid_scenario)
            same_selection = local.selected == joint.selected
            same_feasibility = local.status == joint.status
            if local.status == "infeasible" and joint.status == "feasible":
                category = "Local infeasible, joint feasible"
            elif local.status == joint.status == "infeasible":
                category = "Both infeasible"
            elif (local.status == joint.status == "feasible" and same_selection
                  and local.makespan == joint.makespan
                  and local.peak_memory == joint.peak_memory):
                category = "Equivalent"
            elif (local.status == joint.status == "feasible" and same_selection):
                category = "Selection-equivalent, schedule-different"
            elif (local.status == joint.status == "feasible"
                  and joint.makespan < local.makespan):
                category = "Local feasible but globally suboptimal"
            else:
                category = "Unclassified"
            row = {
                "memory": memory,
                "deadline": deadline,
                "local_selected": local.selected,
                "local_schedule_status": local.status,
                "local_makespan": local.makespan,
                "local_peak": local.peak_memory if local.status == "feasible" else None,
                "joint_selected": joint.selected,
                "joint_status": joint.status,
                "joint_makespan": joint.makespan,
                "joint_peak": joint.peak_memory if joint.status == "feasible" else None,
                "same_selection": same_selection,
                "same_feasibility": same_feasibility,
                "class": category,
            }
            grid.append(row)
            local_label = "".join(local.selected.get(name, "-")[0].upper()
                                 for name in ("compute_x", "compute_y"))
            joint_label = "".join(joint.selected.get(name, "-")[0].upper()
                                 for name in ("compute_x", "compute_y"))
            print(f"{memory:>6} {str(deadline):>8} | {local_label:>5} "
                  f"{local.status:>10} {str(local.makespan):>2} {str(row['local_peak']):>4} | "
                  f"{joint_label:>5} {joint.status:>10} {str(joint.makespan):>2} "
                  f"{str(row['joint_peak']):>4} | {category}")

    def grid_point(memory, deadline):
        return next(row for row in grid
                    if row["memory"] == memory and row["deadline"] == deadline)

    abundant_point = grid_point(12, None)
    memory_only_point = grid_point(8, None)
    deadline_only_point = grid_point(12, 3)
    combined_point = grid_point(8, 4)
    both_infeasible_point = grid_point(8, 3)
    assert abundant_point["class"] == "Equivalent"
    assert memory_only_point["class"] == "Local feasible but globally suboptimal"
    assert memory_only_point["same_selection"] is False
    assert deadline_only_point["class"] == "Equivalent"
    assert combined_point["class"] == "Local infeasible, joint feasible"
    assert both_infeasible_point["class"] == "Both infeasible"
    print("grid assertions: OK")

    print("lifetime assertions: OK")
    print("peak live memory depends on the schedule; non-overlapping resources reuse capacity")

    print("assertions: OK")
    print("temporal primitives: duration, optional interval, cumulative scratch, deadline")
    print("validated: static selection can fail after scheduling; joint selection avoids it")


if __name__ == "__main__":
    main()
