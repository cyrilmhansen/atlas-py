"""Pedagogical, end-to-end stories for pure M1d.1 explanations."""

import json
from pathlib import Path

from atlas import *


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def data():
    return json.loads(FIXTURE.read_text())


def manifest(*candidates):
    return GroundingManifest("m1-grounding/1", tuple(DescriptionId(x) for x in candidates),
                             (RuleId("coverage:v1"),))


def decide(store, name, candidates, *, context="context:m1", snapshot="snapshot:m1",
           problem_id=None, decision_id=None):
    scope = store.create_decision_scope(name, snapshot, context, "request:q1", manifest(*candidates))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    problem_id = problem_id or "decision-problem:" + name.rsplit(":", 1)[-1]
    store.admit_grounded_decision_problem(problem_id, problem)
    selection = store.select_m1(problem_id)
    return store.admit_m1_decision(
        decision_id or "decision:" + name.rsplit(":", 1)[-1], selection)


def resolved_fixture(tmp_path, *, cpu=100, gpu=50, cpu_capable=True, gpu_capable=True):
    fixture = data()
    for fact in fixture["facts"]:
        if fact["id"] == "fact:r1-capabilities" and cpu_capable:
            fact["value"]["items"] = ["a", "b"]
        elif fact["id"] == "fact:r2-capabilities" and not gpu_capable:
            fact["value"]["items"] = ["x"]
        elif fact["id"] == "fact:r1-cost":
            fact["value"]["value"] = str(cpu)
        elif fact["id"] == "fact:r2-cost":
            fact["value"]["value"] = str(gpu)
    return admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)


def candidate_map(explanation):
    return {item.candidate.value: item for item in explanation.candidates}


def test_scenario_a_why_gpu_is_selected(tmp_path):
    store = resolved_fixture(tmp_path)
    fixture = data()
    fixture["descriptions"].append({"id": "implementation:fallback", "label": "fallback"})
    fixture["facts"].append({"id": "fact:fallback-capabilities", "kind": "property",
        "description": "implementation:fallback", "property": "available-capabilities",
        "value": {"kind": "finite_set<symbol>", "items": ["a"]}, "scope": "catalog",
        "epistemic_status": "exact", "provenance": ["source:m1-fixture"]})
    store.admit([{"kind": "description", "payload": {"id": "implementation:fallback", "label": "fallback"}},
                 {"kind": "property", "payload": {"id": "fact:fallback-capabilities",
                    "description": "implementation:fallback", "property": "available-capabilities",
                    "version": "1", "value": {"kind": "finite_set<symbol>", "items": ["a"]},
                        "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])
    store.snapshot("snapshot:a")
    decision = decide(store, "decision-scope:a",
                      ("realization:r1", "realization:r2", "implementation:fallback"), snapshot="snapshot:a")
    explanation = store.explain_m1(decision.id)
    items = candidate_map(explanation)
    assert (explanation.status, explanation.optimum) == (SelectionStatus.RESOLVED, Integer(50))
    assert (items["realization:r2"].truth, items["realization:r2"].selected,
            items["realization:r2"].objective_value.value, items["realization:r2"].reason) == (
            EvaluationTruth.TRUE, True, Integer(50), ExplanationReason.SELECTED_CO_OPTIMUM)
    assert items["realization:r1"].reason is ExplanationReason.ADMISSIBLE_HIGHER_OBJECTIVE
    assert items["implementation:fallback"].reason is ExplanationReason.NOT_ADMISSIBLE
    assert items["realization:r2"].effective_dependencies
    assert items["realization:r2"].provenance == (SourceId("source:m1-fixture"),)


def test_scenario_b_why_atlas_refuses_to_choose(tmp_path):
    fixture = data()
    fixture["facts"] = [x for x in fixture["facts"]
                        if x["id"] not in {"fact:r2-capabilities", "fact:r2-cost"}]
    for fact in fixture["facts"]:
        if fact["id"] == "fact:r1-capabilities": fact["value"]["items"] = ["a", "b"]
        if fact["id"] == "fact:r1-cost": fact["value"]["value"] = "100"
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)
    decision = decide(store, "decision-scope:b", ("realization:r1", "realization:r2"),
                      problem_id="decision-problem:b", decision_id="decision:b")
    explanation = store.explain_m1(decision.id)
    items = candidate_map(explanation)
    assert explanation.optimum is None
    assert items["realization:r1"].reason is ExplanationReason.ADMISSIBLE_BUT_OPTIMALITY_UNCERTIFIED
    gpu = items["realization:r2"]
    assert gpu.reason is ExplanationReason.INSUFFICIENT_INFORMATION
    assert gpu.truth is EvaluationTruth.UNKNOWN
    assert any(read.description == DescriptionId("realization:r2") for read in gpu.missing_reads)


def test_scenario_c_no_solution_means_false_not_unknown(tmp_path):
    fixture = data()
    for fact in fixture["facts"]:
        if fact["id"] in {"fact:q1-search", "fact:q1-output"}:
            fact["value"]["items"] = ["not-supported"]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)
    decision = decide(store, "decision-scope:c", ("realization:r1", "realization:r2"))
    explanation = store.explain_m1(decision.id)
    assert explanation.status is SelectionStatus.NO_ADMISSIBLE_CANDIDATE
    assert all(x.truth is EvaluationTruth.FALSE and x.reason is ExplanationReason.NOT_ADMISSIBLE
               for x in explanation.candidates)


def test_scenario_d_two_winners_are_both_co_optimal(tmp_path):
    store = resolved_fixture(tmp_path, cpu=50, gpu=50)
    decision = decide(store, "decision-scope:d", ("realization:r1", "realization:r2"))
    explanation = store.explain_m1(decision.id)
    assert {x.candidate for x in explanation.candidates if x.selected} == {
        DescriptionId("realization:r1"), DescriptionId("realization:r2")}
    assert all(x.reason is ExplanationReason.SELECTED_CO_OPTIMUM for x in explanation.candidates)


def test_scenario_e_historical_explanations_remain_different_after_restart(tmp_path):
    store = resolved_fixture(tmp_path, cpu=100, gpu=50)
    d1 = decide(store, "decision-scope:e1", ("realization:r1", "realization:r2"), decision_id="decision:d1")
    store.configure_vocabulary({"properties": [{"id": "cost", "version": "2", "value": "integer"}]})
    store.admit([{"kind": "property", "payload": {"id": "fact:r1-cost-v2", "description": "realization:r1",
        "property": "cost", "version": "2", "value": {"kind": "integer", "value": "30"},
        "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}},
        {"kind": "property", "payload": {"id": "fact:r2-cost-v2", "description": "realization:r2",
        "property": "cost", "version": "2", "value": {"kind": "integer", "value": "80"},
        "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])
    store.snapshot("snapshot:e2")
    d2 = decide(store, "decision-scope:e2", ("realization:r1", "realization:r2"),
                snapshot="snapshot:e2", problem_id="decision-problem:e2", decision_id="decision:d2")
    store.close()
    store = open_store(tmp_path / "atlas.sqlite")
    e1, e2 = store.explain_m1(d1.id), store.explain_m1(d2.id)
    assert (e1.optimum, e1.candidates[0].objective_value.value, e1.candidates[1].selected) == (Integer(50), Integer(100), True)
    assert (e2.optimum, e2.candidates[0].selected, e2.candidates[0].objective_value.value) == (Integer(30), True, Integer(30))


def test_scenario_f_contexts_have_separate_explanations(tmp_path):
    fixture = data()
    for fact in fixture["facts"]:
        if fact["id"] == "fact:r1-capabilities": fact["value"]["items"] = ["a", "b"]
        if fact["id"] == "fact:r2-capabilities": fact["scope"] = "gpu-only"
        if fact["id"] == "fact:r1-cost": fact["value"]["value"] = "100"
        if fact["id"] == "fact:r2-cost": fact["value"]["value"] = "50"
    fixture["contexts"] = [
        {"id": "context:desktop", "visible_scopes": ["catalog", "gpu-only"], "enabled_rules": ["coverage:v1"]},
        {"id": "context:embedded", "visible_scopes": ["catalog"], "enabled_rules": ["coverage:v1"]}]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)
    store.snapshot("snapshot:contexts")
    d1 = decide(store, "decision-scope:desktop", ("realization:r1", "realization:r2"),
                context="context:desktop", snapshot="snapshot:contexts", decision_id="decision:desktop")
    d2 = decide(store, "decision-scope:embedded", ("realization:r1", "realization:r2"),
                context="context:embedded", snapshot="snapshot:contexts", decision_id="decision:embedded")
    desktop, embedded = store.explain_m1(d1.id), store.explain_m1(d2.id)
    assert candidate_map(desktop)["realization:r2"].reason is ExplanationReason.SELECTED_CO_OPTIMUM
    gpu = candidate_map(embedded)["realization:r2"]
    assert embedded.status is SelectionStatus.NEEDS_INFORMATION
    assert gpu.reason is ExplanationReason.INSUFFICIENT_INFORMATION
    # The relation remains included in the embedded context; only the
    # grounding truth is UNKNOWN because the required property is hidden.
    assert gpu.exclusion_reason is None
