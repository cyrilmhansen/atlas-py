"""Knowledge-window experiment: specialize only while a fact is valid."""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ortools.sat.python import cp_model


@dataclass(frozen=True)
class Call:
    name: str
    release: int
    deadline: int


@dataclass(frozen=True)
class KnowledgeWindow:
    known_from: int
    valid_until: int


@dataclass(frozen=True)
class SpecializationScenario:
    name: str
    calls: Tuple[Call, ...]
    knowledge: KnowledgeWindow
    preparation_duration: int
    generic_duration: int
    specialized_duration: int


@dataclass
class Result:
    status: str
    makespan: Optional[int]
    specialized: Tuple[str, ...]
    generic: Tuple[str, ...]
    preparation: Optional[Tuple[int, int]]
    starts: Dict[str, int]
    ends: Dict[str, int]
    variables: int
    constraints: int


def solve(scenario: SpecializationScenario) -> Result:
    model = cp_model.CpModel()
    horizon = max(call.deadline for call in scenario.calls)
    choices = {}
    intervals = []
    for call in scenario.calls:
        generic = model.new_bool_var(f"generic_{call.name}")
        specialized = model.new_bool_var(f"specialized_{call.name}")
        model.add_exactly_one(generic, specialized)
        call_choices = []
        for label, present, duration in (
                ("generic", generic, scenario.generic_duration),
                ("specialized", specialized, scenario.specialized_duration)):
            start = model.new_int_var(0, horizon, f"start_{label}_{call.name}")
            end = model.new_int_var(0, horizon, f"end_{label}_{call.name}")
            interval = model.new_optional_interval_var(
                start, duration, end, present, f"interval_{label}_{call.name}")
            model.add(start >= call.release).only_enforce_if(present)
            model.add(end <= call.deadline).only_enforce_if(present)
            model.add(start == 0).only_enforce_if(present.Not())
            model.add(end == 0).only_enforce_if(present.Not())
            if label == "specialized":
                model.add(end <= scenario.knowledge.valid_until).only_enforce_if(present)
            call_choices.append((label, present, start, end))
            intervals.append((interval, 1))
        choices[call.name] = call_choices

    preparation_present = model.new_bool_var("preparation_present")
    specialized_flags = [entry[1] for choices_for_call in choices.values()
                         for entry in choices_for_call if entry[0] == "specialized"]
    for flag in specialized_flags:
        model.add(preparation_present >= flag)
    model.add(preparation_present <= sum(specialized_flags))
    preparation_start = model.new_int_var(0, horizon, "preparation_start")
    preparation_end = model.new_int_var(0, horizon, "preparation_end")
    preparation_interval = model.new_optional_interval_var(
        preparation_start, scenario.preparation_duration, preparation_end,
        preparation_present, "preparation")
    model.add(preparation_start >= scenario.knowledge.known_from).only_enforce_if(
        preparation_present)
    model.add(preparation_end <= scenario.knowledge.valid_until).only_enforce_if(
        preparation_present)
    model.add(preparation_start == 0).only_enforce_if(preparation_present.Not())
    model.add(preparation_end == 0).only_enforce_if(preparation_present.Not())
    intervals.append((preparation_interval, 1))

    for choices_for_call in choices.values():
        for label, present, start, end in choices_for_call:
            if label == "specialized":
                model.add(start >= preparation_end).only_enforce_if(
                    [present, preparation_present])
    model.add_cumulative([interval for interval, _ in intervals],
                         [demand for _, demand in intervals], 1)
    makespan = model.new_int_var(0, horizon, "makespan")
    for choices_for_call in choices.values():
        for _, present, _, end in choices_for_call:
            model.add(makespan >= end).only_enforce_if(present)
    model.minimize(makespan)

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 7
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Result("infeasible", None, (), (), None, {}, {},
                      len(model.Proto().variables), len(model.Proto().constraints))

    selected_specialized = tuple(call.name for call in scenario.calls
                                 if solver.value(choices[call.name][1][1]))
    selected_generic = tuple(call.name for call in scenario.calls
                              if solver.value(choices[call.name][0][1]))
    starts, ends = {}, {}
    for call in scenario.calls:
        for label, present, start, end in choices[call.name]:
            if solver.value(present):
                starts[call.name] = solver.value(start)
                ends[call.name] = solver.value(end)
    preparation = ((solver.value(preparation_start), solver.value(preparation_end))
                   if solver.value(preparation_present) else None)
    return Result("feasible", solver.value(makespan), selected_specialized,
                  selected_generic, preparation, starts, ends,
                  len(model.Proto().variables), len(model.Proto().constraints))


def report(scenario: SpecializationScenario) -> Result:
    result = solve(scenario)
    print(f"{scenario.name}: status={result.status} makespan={result.makespan} "
          f"specialized={result.specialized} generic={result.generic} "
          f"preparation={result.preparation}")
    return result


def main() -> None:
    early = tuple(Call(f"early_{i}", 0, 13) for i in range(6))
    late = (Call("late_0", 14, 20), Call("late_1", 14, 20))
    case_a = SpecializationScenario(
        "A_many_calls_few_in_window", early + late,
        KnowledgeWindow(14, 20), preparation_duration=3,
        generic_duration=2, specialized_duration=1)
    case_b = SpecializationScenario(
        "B_many_calls_in_window",
        tuple(Call(f"window_{i}", 10, 30) for i in range(6)),
        KnowledgeWindow(10, 30), preparation_duration=3,
        generic_duration=2, specialized_duration=1)
    case_c_movable = SpecializationScenario(
        "C_calls_movable_into_window",
        tuple(Call(f"movable_{i}", 10, 20) for i in range(4)),
        KnowledgeWindow(10, 20), preparation_duration=3,
        generic_duration=2, specialized_duration=1)
    case_c_shifted = SpecializationScenario(
        "C_calls_shifted_after_window",
        tuple(Call(f"shifted_{i}", 21, 30) for i in range(4)),
        KnowledgeWindow(10, 20), preparation_duration=3,
        generic_duration=2, specialized_duration=1)

    result_a = report(case_a)
    result_b = report(case_b)
    result_c_movable = report(case_c_movable)
    result_c_shifted = report(case_c_shifted)
    assert result_a.specialized == ()
    assert result_a.preparation is None
    assert result_b.specialized == tuple(call.name for call in case_b.calls)
    assert result_b.preparation is not None
    assert result_b.preparation[0] >= case_b.knowledge.known_from
    assert result_b.preparation[1] <= case_b.knowledge.valid_until
    assert all(result_b.ends[name] <= case_b.knowledge.valid_until
               for name in result_b.specialized)
    assert result_c_movable.specialized == tuple(call.name for call in case_c_movable.calls)
    assert result_c_shifted.specialized == ()
    assert result_c_movable.makespan < result_c_shifted.makespan
    assert all(start >= case_b.knowledge.known_from
               for name, start in result_b.starts.items()
               if name in result_b.specialized)
    print("assertions: OK")
    print("knowledge-window specialization is selected and placed only when amortized")


if __name__ == "__main__":
    main()
