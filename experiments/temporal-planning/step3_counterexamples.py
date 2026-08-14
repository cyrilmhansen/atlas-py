"""Bounded search for counterexamples to independent selection then scheduling.

The exact oracle enumerates both alternative selections and integer start times.
CP-SAT is used only for the joint formulation and is cross-checked against it.
"""

from dataclasses import dataclass
from itertools import product
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model


@dataclass(frozen=True)
class Alternative:
    name: str
    duration: int
    scratch: int


@dataclass(frozen=True)
class Scenario:
    name: str
    alternatives: Tuple[Tuple[Alternative, ...], ...]
    before: Tuple[Tuple[int, int], ...]
    capacity: int
    deadline: Optional[int]
    width: int


@dataclass(frozen=True)
class Schedule:
    feasible: bool
    makespan: Optional[int]
    starts: Tuple[int, ...] = ()


def _horizon(scenario: Scenario, selection: Tuple[int, ...]) -> int:
    if scenario.deadline is not None:
        return scenario.deadline
    return sum(scenario.alternatives[i][choice].duration for i, choice in enumerate(selection))


def exact_schedule(scenario: Scenario, selection: Tuple[int, ...]) -> Schedule:
    """Exact integer-time scheduling oracle for one fixed selection."""
    durations = tuple(scenario.alternatives[i][choice].duration
                      for i, choice in enumerate(selection))
    scratch = tuple(scenario.alternatives[i][choice].scratch
                   for i, choice in enumerate(selection))
    horizon = _horizon(scenario, selection)
    best = None
    best_starts = None
    for starts in product(range(horizon + 1), repeat=len(selection)):
        ends = tuple(starts[i] + durations[i] for i in range(len(selection)))
        if scenario.deadline is not None and any(end > scenario.deadline for end in ends):
            continue
        if any(ends[left] > starts[right] for left, right in scenario.before):
            continue
        if any(sum(scratch[i] for i in range(len(selection))
                   if starts[i] <= time < ends[i]) > scenario.capacity
                   for time in range(horizon)):
            continue
        makespan = max(ends, default=0)
        if best is None or makespan < best:
            best, best_starts = makespan, starts
    return Schedule(best is not None, best, best_starts or ())


def enumerate_optimum(scenario: Scenario):
    best = None
    best_selection = None
    best_schedule = None
    for selection in product(*(range(len(options)) for options in scenario.alternatives)):
        schedule = exact_schedule(scenario, selection)
        if schedule.feasible and (best is None or schedule.makespan < best):
            best = schedule.makespan
            best_selection = selection
            best_schedule = schedule
    return best_selection, best_schedule


def local_selection(scenario: Scenario) -> Tuple[int, ...]:
    """The local policy uses only each intention's own duration."""
    return tuple(min(range(len(options)),
                     key=lambda index: (options[index].duration, options[index].name))
                 for options in scenario.alternatives)


def select_independently_then_schedule(scenario: Scenario):
    selection = local_selection(scenario)
    return selection, exact_schedule(scenario, selection)


def joint_cp_sat(scenario: Scenario):
    model = cp_model.CpModel()
    horizon = _horizon(scenario, tuple(0 for _ in scenario.alternatives))
    choices = []
    intervals = []
    for intent, options in enumerate(scenario.alternatives):
        intent_choices = []
        for alternative in options:
            present = model.new_bool_var(f"use_{intent}_{alternative.name}")
            start = model.new_int_var(0, horizon, f"start_{intent}_{alternative.name}")
            end = model.new_int_var(0, horizon, f"end_{intent}_{alternative.name}")
            interval = model.new_optional_interval_var(
                start, alternative.duration, end, present,
                f"interval_{intent}_{alternative.name}")
            model.add(start == 0).only_enforce_if(present.Not())
            model.add(end == 0).only_enforce_if(present.Not())
            intent_choices.append((alternative, present, start, end))
            intervals.append((interval, alternative.scratch))
        model.add_exactly_one(present for _, present, _, _ in intent_choices)
        choices.append(intent_choices)
    model.add_cumulative([interval for interval, _ in intervals],
                         [scratch for _, scratch in intervals], scenario.capacity)
    for left, right in scenario.before:
        for _, left_present, _, left_end in choices[left]:
            for _, right_present, right_start, _ in choices[right]:
                model.add(left_end <= right_start).only_enforce_if(
                    [left_present, right_present])
    makespan = model.new_int_var(0, horizon, "makespan")
    for intent_choices in choices:
        for _, present, _, end in intent_choices:
            model.add(makespan >= end).only_enforce_if(present)
    model.minimize(makespan)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 7
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result = Schedule(False, None)
        selected = None
    else:
        selected = tuple(next(index for index, (_, present, _, _) in enumerate(intent_choices)
                             if solver.value(present)) for intent_choices in choices)
        result = Schedule(True, solver.value(makespan), tuple(
            next(solver.value(start) for _, present, start, _ in intent_choices
                 if solver.value(present)) for intent_choices in choices))
    return selected, result, len(model.Proto().variables), len(model.Proto().constraints)


def static_cp_sat_counts(scenario: Scenario, selection: Tuple[int, ...]):
    """Count the analogous fixed-selection CP-SAT model for growth reporting."""
    model = cp_model.CpModel()
    horizon = _horizon(scenario, selection)
    intervals = []
    ends = []
    for intent, choice in enumerate(selection):
        alternative = scenario.alternatives[intent][choice]
        start = model.new_int_var(0, horizon, f"start_{intent}")
        end = model.new_int_var(0, horizon, f"end_{intent}")
        intervals.append((model.new_interval_var(
            start, alternative.duration, end, f"interval_{intent}"),
            alternative.scratch))
        ends.append((start, end))
    model.add_cumulative([interval for interval, _ in intervals],
                         [scratch for _, scratch in intervals], scenario.capacity)
    for left, right in scenario.before:
        model.add(ends[left][1] <= ends[right][0])
    makespan = model.new_int_var(0, horizon, "makespan")
    model.add_max_equality(makespan, [end for _, end in ends])
    model.minimize(makespan)
    return len(model.Proto().variables), len(model.Proto().constraints)


def _scenario(name, pair, capacity, deadline, before=()):
    return Scenario(name, (pair, pair), before, capacity, deadline, width=2)


def _selection_label(scenario, selection):
    if selection is None:
        return "--"
    return "/".join(scenario.alternatives[i][choice].name[0].upper()
                     for i, choice in enumerate(selection))


def classify(local, joint):
    local_selection, local_schedule = local
    joint_selection, joint_schedule, _, _ = joint
    if not local_schedule.feasible and not joint_schedule.feasible:
        return "Both infeasible"
    if not local_schedule.feasible and joint_schedule.feasible:
        return "Local infeasible, joint feasible"
    if (local_schedule.feasible and joint_schedule.feasible
            and local_selection == joint_selection
            and local_schedule.makespan == joint_schedule.makespan):
        return "Equivalent"
    if (local_schedule.feasible and joint_schedule.feasible
            and local_selection == joint_selection):
        return "Selection-equivalent, schedule-different"
    if (local_schedule.feasible and joint_schedule.feasible
            and joint_schedule.makespan < local_schedule.makespan):
        return "Local feasible but globally suboptimal"
    return "Unclassified"


def find_smallest_counterexample():
    pairs = (
        (Alternative("fast", 1, 2), Alternative("compact", 2, 1)),
        (Alternative("fast", 2, 2), Alternative("compact", 3, 1)),
        (Alternative("fast", 1, 3), Alternative("compact", 2, 1)),
        (Alternative("fast", 2, 3), Alternative("compact", 3, 1)),
    )
    checked = 0
    for intentions in (1, 2, 3):
        for pair_choices in product(pairs, repeat=intentions):
            for depth in (0, 1):
                before = tuple((index, index + 1) for index in range(intentions - 1)) if depth else ()
                for capacity in range(1, 7):
                    for deadline in range(1, 7):
                        scenario = Scenario(
                            f"search_g{intentions}_a2_d{depth}_c{capacity}_w{intentions}",
                            pair_choices, before, capacity, deadline, width=intentions)
                        local = select_independently_then_schedule(scenario)
                        # Require each locally selected task to be individually feasible.
                        individual_ok = all(exact_schedule(
                            Scenario(scenario.name, (scenario.alternatives[i],), (), capacity,
                                     deadline, 1), (0,)).feasible
                            for i in range(intentions))
                        if not individual_ok:
                            continue
                        joint = joint_cp_sat(scenario)
                        oracle_selection, oracle_schedule = enumerate_optimum(scenario)
                        assert (joint[1].feasible == (oracle_schedule is not None))
                        if joint[1].feasible:
                            assert joint[1].makespan == oracle_schedule.makespan
                        checked += 1
                        if classify(local, joint) in (
                                "Local infeasible, joint feasible",
                                "Local feasible but globally suboptimal"):
                            return scenario, local, joint, (oracle_selection, oracle_schedule), checked
    raise AssertionError("bounded generator found no counterexample")


def main():
    scenario, local, joint, oracle, checked = find_smallest_counterexample()
    oracle_selection, oracle_schedule = oracle
    print("smallest counterexample:")
    print(f"  name={scenario.name} G={len(scenario.alternatives)} A=2 "
          f"D={len(scenario.before)} C={scenario.capacity} deadline={scenario.deadline}")
    print(f"  local={_selection_label(scenario, local[0])} status={local[1].feasible} "
          f"makespan={local[1].makespan}")
    print(f"  joint={_selection_label(scenario, joint[0])} status={joint[1].feasible} "
          f"makespan={joint[1].makespan} vars={joint[2]} constraints={joint[3]}")
    print(f"  oracle={_selection_label(scenario, oracle_selection)} "
          f"makespan={oracle_schedule.makespan} checked={checked}")
    static_vars, static_constraints = static_cp_sat_counts(scenario, local[0])
    print(f"  model_growth static_vars={static_vars} static_constraints={static_constraints} "
          f"joint_vars={joint[2]} joint_constraints={joint[3]}")

    pair = (Alternative("fast", 2, 2), Alternative("compact", 3, 1))
    print("regime matrix (same two-intention structure):")
    print("capacity deadline | local | joint | class")
    for capacity, deadline in ((3, None), (4, None), (3, 3), (4, 3), (3, 4), (4, 4)):
        matrix_scenario = _scenario("matrix", pair, capacity, deadline)
        local_result = select_independently_then_schedule(matrix_scenario)
        joint_result = joint_cp_sat(matrix_scenario)
        oracle_selection, oracle_schedule = enumerate_optimum(matrix_scenario)
        assert joint_result[1].feasible == (oracle_schedule is not None)
        if joint_result[1].feasible:
            assert joint_result[1].makespan == oracle_schedule.makespan
        print(f"{capacity:>8} {str(deadline):>8} | "
              f"{_selection_label(matrix_scenario, local_result[0])}/"
              f"{local_result[1].makespan} | "
              f"{_selection_label(matrix_scenario, joint_result[0])}/"
              f"{joint_result[1].makespan} | {classify(local_result, joint_result)}")

    safe = _scenario("safe_two_intentions", pair, 4, None)
    safe_local = select_independently_then_schedule(safe)
    safe_joint = joint_cp_sat(safe)
    assert classify(safe_local, safe_joint) == "Equivalent"
    print("assertions: OK")
    print("oracle cross-checks: OK")
    print("risk conclusion: conditional; divergence depends on global capacity/deadline structure")


if __name__ == "__main__":
    main()
