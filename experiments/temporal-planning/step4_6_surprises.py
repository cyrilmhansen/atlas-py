"""Closing surprise tests for the temporal-planning POC.

The tests use the same CP-SAT primitives as the earlier experiments.  The
two-fact and memory-aware cases expose only the smallest local structures
needed to test dimensions that step4_specialization.py cannot represent.
"""

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Dict, Optional, Tuple

from ortools.sat.python import cp_model

sys.path.insert(0, str(Path(__file__).parent))
import step4_specialization as single_fact  # noqa: E402


def solver():
    result = cp_model.CpSolver()
    result.parameters.num_search_workers = 1
    result.parameters.random_seed = 7
    return result


@dataclass(frozen=True)
class FactWindow:
    name: str
    known_from: int
    valid_until: int


@dataclass(frozen=True)
class FactCall:
    name: str
    release: int
    deadline: int
    required_facts: Tuple[str, ...]


@dataclass(frozen=True)
class TwoFactScenario:
    facts: Tuple[FactWindow, ...]
    calls: Tuple[FactCall, ...]
    preparation_duration: int
    generic_duration: int
    specialized_duration: int


def solve_two_facts(scenario: TwoFactScenario):
    """Solve calls requiring a conjunction of independently timed facts."""
    model = cp_model.CpModel()
    horizon = max(call.deadline for call in scenario.calls)
    facts = {fact.name: fact for fact in scenario.facts}
    choices: Dict[str, Tuple] = {}
    intervals = []
    for call in scenario.calls:
        generic = model.new_bool_var(f"generic_{call.name}")
        specialized = model.new_bool_var(f"specialized_{call.name}")
        model.add_exactly_one(generic, specialized)
        entries = []
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
                for fact_name in call.required_facts:
                    fact = facts[fact_name]
                    model.add(start >= fact.known_from).only_enforce_if(present)
                    model.add(end <= fact.valid_until).only_enforce_if(present)
            entries.append((label, present, start, end))
            intervals.append((interval, 1))
        choices[call.name] = tuple(entries)

    preparations = {}
    for fact in scenario.facts:
        needed = [
            present for call in scenario.calls
            for label, present, _, _ in choices[call.name]
            if label == "specialized" and fact.name in call.required_facts
        ]
        preparation_present = model.new_bool_var(f"prepare_{fact.name}")
        for flag in needed:
            model.add(preparation_present >= flag)
        model.add(preparation_present <= sum(needed))
        start = model.new_int_var(0, horizon, f"prepare_start_{fact.name}")
        end = model.new_int_var(0, horizon, f"prepare_end_{fact.name}")
        interval = model.new_optional_interval_var(
            start, scenario.preparation_duration, end,
            preparation_present, f"prepare_interval_{fact.name}")
        model.add(start >= fact.known_from).only_enforce_if(preparation_present)
        model.add(end <= fact.valid_until).only_enforce_if(preparation_present)
        model.add(start == 0).only_enforce_if(preparation_present.Not())
        model.add(end == 0).only_enforce_if(preparation_present.Not())
        intervals.append((interval, 1))
        preparations[fact.name] = (preparation_present, start, end)

    for call in scenario.calls:
        for label, present, start, _ in choices[call.name]:
            if label == "specialized":
                for fact_name in call.required_facts:
                    model.add(start >= preparations[fact_name][2]).only_enforce_if(
                        [present, preparations[fact_name][0]])

    model.add_cumulative([interval for interval, _ in intervals],
                         [demand for _, demand in intervals], 1)
    makespan = model.new_int_var(0, horizon, "makespan")
    for entries in choices.values():
        for _, present, _, end in entries:
            model.add(makespan >= end).only_enforce_if(present)
    model.minimize(makespan)
    result = solver()
    status = result.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    specialized = tuple(call.name for call in scenario.calls
                        if result.value(choices[call.name][1][1]))
    preparation = {
        name: (result.value(start), result.value(end))
        for name, (_, start, end) in preparations.items()
        if result.value(preparations[name][0])
    }
    return result.value(makespan), specialized, preparation


@dataclass(frozen=True)
class MemoryVariant:
    name: str
    duration: int
    peak_memory: int


def choose_memory_variant(variants: Tuple[MemoryVariant, ...], capacity: int):
    """Choose one timed variant under a cumulative peak-memory capacity."""
    model = cp_model.CpModel()
    horizon = max(variant.duration for variant in variants)
    intervals, choices = [], []
    for variant in variants:
        present = model.new_bool_var(f"use_{variant.name}")
        start = model.new_int_var(0, horizon, f"start_{variant.name}")
        end = model.new_int_var(0, horizon, f"end_{variant.name}")
        interval = model.new_optional_interval_var(
            start, variant.duration, end, present, f"interval_{variant.name}")
        model.add(start == 0).only_enforce_if(present.Not())
        model.add(end == 0).only_enforce_if(present.Not())
        intervals.append((interval, variant.peak_memory))
        choices.append((variant, present))
    model.add_exactly_one(present for _, present in choices)
    model.add_cumulative([interval for interval, _ in intervals],
                         [memory for _, memory in intervals], capacity)
    makespan = model.new_int_var(0, horizon, "makespan")
    for variant, present in choices:
        model.add(makespan >= variant.duration).only_enforce_if(present)
    model.minimize(makespan)
    result = solver()
    status = result.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    selected = next(variant.name for variant, present in choices
                    if result.value(present))
    return selected, result.value(makespan)


def main():
    # Surprise 1: the existing single-window model handles a long, expensive
    # preparation when the resulting specialization is reused sufficiently.
    long_window = single_fact.SpecializationScenario(
        "surprise_long_preparation",
        tuple(single_fact.Call(f"call_{i}", 10, 100) for i in range(12)),
        single_fact.KnowledgeWindow(10, 100), preparation_duration=25,
        generic_duration=10, specialized_duration=1)
    long_result = single_fact.solve(long_window)
    assert long_result.status == "feasible"
    assert len(long_result.specialized) == 12
    assert long_result.preparation == (10, 35)
    print(f"long_preparation: makespan={long_result.makespan} "
          f"specialized={len(long_result.specialized)} "
          f"preparation={long_result.preparation}")

    # Surprise 2: two partially overlapping facts require two preparations.
    two_facts = TwoFactScenario(
        facts=(FactWindow("P", 4, 18), FactWindow("Q", 10, 24)),
        calls=(FactCall("joint_call", 10, 18, ("P", "Q")),),
        preparation_duration=3, generic_duration=8, specialized_duration=1)
    two_fact_result = solve_two_facts(two_facts)
    assert two_fact_result is not None
    makespan, specialized, preparations = two_fact_result
    assert specialized == ("joint_call",)
    assert set(preparations) == {"P", "Q"}
    assert makespan <= 18
    print(f"two_facts_partial_overlap: makespan={makespan} "
          f"specialized={specialized} preparations={preparations}")

    # Surprise 3: a faster variant is selected only when its higher peak fits.
    variants = (
        MemoryVariant("specialized_fast", duration=1, peak_memory=6),
        MemoryVariant("generic_slow", duration=4, peak_memory=1),
    )
    ample = choose_memory_variant(variants, capacity=6)
    tight = choose_memory_variant(variants, capacity=5)
    assert ample == ("specialized_fast", 1)
    assert tight == ("generic_slow", 4)
    print(f"speed_memory_tradeoff: capacity6={ample} capacity5={tight}")
    print("surprise assertions: OK")


if __name__ == "__main__":
    main()
