"""Non-normative vertical composition probes for the currently implemented M1 surface."""

import copy
import json
from pathlib import Path

from atlas import *


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def base():
    return json.loads(FIXTURE.read_text())


def manifest(*ids, rule="coverage:v1"):
    return GroundingManifest("m1-grounding/1", tuple(DescriptionId(x) for x in ids), (RuleId(rule),))


def run(store, sid, candidates, context="context:m1", request="request:q1", rule="coverage:v1"):
    scope = store.create_decision_scope(sid, "snapshot:m1", context, intention='intent:selection', request=request, manifest=manifest(*candidates, rule=rule))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    store.admit_grounded_decision_problem("decision-problem:" + sid.rsplit(":", 1)[-1], problem)
    path = store.path
    store.close()
    reopened = open_store(path)
    return problem, reopened.decision_problem("decision-problem:" + sid.rsplit(":", 1)[-1])


def test_scenario_a_two_implementations_are_true_and_fallback_false(tmp_path):
    data = base()
    for fact in data["facts"]:
        if fact["id"] == "fact:r1-capabilities":
            fact["value"]["items"] = ["a", "b"]
        if fact["id"] == "fact:r1-cost":
            fact["value"]["value"] = "100"
        if fact["id"] == "fact:r2-cost":
            fact["value"]["value"] = "50"
    data["descriptions"].append({"id": "implementation:fallback", "label": "fallback"})
    data["facts"].append({"id": "fact:fallback-capabilities", "kind": "property", "description": "implementation:fallback", "property": "available-capabilities", "value": {"kind": "finite_set<symbol>", "items": ["a"]}, "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]})
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), data)
    # r1 and r2 stand for CPU/GPU here; both cover the request and carry exact costs.
    before, after = run(store, "decision-scope:mechanisms", ("realization:r1", "realization:r2", "implementation:fallback"))
    assert [x.truth for x in after.candidates] == [EvaluationTruth.TRUE, EvaluationTruth.TRUE, EvaluationTruth.FALSE]
    assert after.candidates[1].objective_value.value == Integer(50)
    assert after == before
    assert not hasattr(after, "winner") and not hasattr(after, "selected")


def test_scenario_a_selection_returns_the_unique_optimum(tmp_path):
    data = base()
    for fact in data["facts"]:
        if fact["id"] == "fact:r1-capabilities":
            fact["value"]["items"] = ["a", "b"]
        if fact["id"] == "fact:r1-cost":
            fact["value"]["value"] = "100"
        if fact["id"] == "fact:r2-cost":
            fact["value"]["value"] = "50"
    data["descriptions"].append({"id": "implementation:fallback", "label": "fallback"})
    data["facts"].append({"id": "fact:fallback-capabilities", "kind": "property", "description": "implementation:fallback", "property": "available-capabilities", "value": {"kind": "finite_set<symbol>", "items": ["a"]}, "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]})
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), data)
    _, problem = run(store, "decision-scope:selection", ("realization:r1", "realization:r2", "implementation:fallback"))
    reopened = open_store(tmp_path / "atlas.sqlite")
    before_selection = reopened._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()
    result = reopened.select_m1("decision-problem:selection")
    assert result == M1SelectionResult(DecisionProblemId("decision-problem:selection"), SelectionStatus.RESOLVED, Integer(50), (DescriptionId("realization:r2"),))
    assert reopened._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall() == before_selection
    assert problem.scope_id == DecisionScopeId("decision-scope:selection")


def test_scenario_b_finite_inspection_can_still_produce_unknown(tmp_path):
    data = base()
    data["facts"] = [x for x in data["facts"] if x["id"] != "fact:r1-capabilities"]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), data)
    before, after = run(store, "decision-scope:incomplete-information", ("realization:r1", "realization:r2"))
    assert [x.truth for x in after.candidates] == [EvaluationTruth.UNKNOWN, EvaluationTruth.TRUE]
    assert after.candidates[0].objective_value is None
    assert after == before


def test_scenario_b_unknown_blocks_optimality_even_with_known_true(tmp_path):
    data = base()
    data["facts"] = [x for x in data["facts"] if x["id"] != "fact:r1-capabilities"]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), data)
    _, problem = run(store, "decision-scope:unknown-selection", ("realization:r1", "realization:r2"))
    reopened = open_store(tmp_path / "atlas.sqlite")
    result = reopened.select_m1("decision-problem:unknown-selection")
    assert [x.truth for x in problem.candidates] == [EvaluationTruth.UNKNOWN, EvaluationTruth.TRUE]
    assert result.status is SelectionStatus.NEEDS_INFORMATION
    assert result.optimum is None and result.co_optima == ()


def test_scenario_c_context_exclusion_is_not_absence(tmp_path):
    data = base()
    data["contexts"][0]["visible_scopes"] = []
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), data)
    before, after = run(store, "decision-scope:deployment-context", ("realization:r2",))
    assert after.candidates[0].truth is EvaluationTruth.UNKNOWN
    assert after.candidates[0].exclusion_reason == "excluded_by_context"
    assert after == before


def test_scenario_d_v1_and_v2_are_historical_and_separate(tmp_path):
    data = base()
    for fact in data["facts"]:
        if fact["id"] == "fact:r1-capabilities":
            fact["value"]["items"] = ["a", "b"]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), data)
    scope1 = store.create_decision_scope("decision-scope:v1", "snapshot:m1", "context:m1", intention='intent:selection', request="request:q1", manifest=manifest("realization:r1", "realization:r2"))
    store.evaluate_decision_scope(scope1.id)
    problem1 = store.ground_decision_problem(scope1.id)
    store.admit_grounded_decision_problem("decision-problem:v1", problem1)

    store.configure_vocabulary({"properties": [{"id": "cost", "version": "2", "value": "integer"}]})
    rule = next(x for x in base()["rules"] if x["id"] == "coverage:v1")
    store.admit([
        {"kind": "description", "payload": {"id": "implementation:npu", "label": "NPU"}},
        {"kind": "rule", "payload": {"id": "coverage:v2", "version": "2", "payload": dict(rule, version="2")}},
        {"kind": "context", "payload": {"id": "context:v2", "visible_scopes": ["catalog"], "enabled_rules": ["coverage:v2"]}},
        {"kind": "property", "payload": {"id": "fact:r1-cost-v2", "description": "realization:r1", "property": "cost", "version": "2", "value": {"kind": "integer", "value": "30"}, "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}},
        {"kind": "property", "payload": {"id": "fact:r2-cost-v2", "description": "realization:r2", "property": "cost", "version": "2", "value": {"kind": "integer", "value": "80"}, "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}},
    ])
    store.snapshot("snapshot:v2")
    scope2 = store.create_decision_scope("decision-scope:v2", "snapshot:v2", "context:v2", intention='intent:selection', request="request:q1", manifest=manifest("realization:r1", "realization:r2", "implementation:npu", rule="coverage:v2"))
    store.evaluate_decision_scope(scope2.id)
    problem2 = store.ground_decision_problem(scope2.id)
    store.admit_grounded_decision_problem("decision-problem:v2", problem2)
    path = store.path; store.close()
    reopened = open_store(path)
    restored1 = reopened.decision_problem("decision-problem:v1")
    restored2 = reopened.decision_problem("decision-problem:v2")
    assert [x.objective_value.value for x in restored1.candidates if x.objective_value] == [Integer(1), Integer(2)]
    assert [x.objective_value.value for x in restored2.candidates if x.objective_value] == [Integer(30), Integer(80)]
    assert all(x.candidate != DescriptionId("implementation:npu") for x in restored1.candidates)
    assert any(x.candidate == DescriptionId("implementation:npu") for x in restored2.candidates)
    assert reopened.select_m1("decision-problem:v1").co_optima == (DescriptionId("realization:r1"),)
    # The added candidate has no included realizes support, so its UNKNOWN
    # truth is removed before decision evaluation.
    assert reopened.select_m1("decision-problem:v2").status is SelectionStatus.RESOLVED


def test_scenario_e_independent_context_scopes_do_not_leak(tmp_path):
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), base())
    store.admit([
        {"kind": "context", "payload": {"id": "context:desktop", "visible_scopes": ["catalog"], "enabled_rules": ["coverage:v1"]}},
        {"kind": "context", "payload": {"id": "context:embedded", "visible_scopes": [], "enabled_rules": ["coverage:v1"]}},
    ])
    store.snapshot("snapshot:contexts")
    def make(sid, context):
        scope = store.create_decision_scope(sid, "snapshot:contexts", context, intention='intent:selection', request="request:q1", manifest=manifest("realization:r2"))
        store.evaluate_decision_scope(scope.id)
        problem = store.ground_decision_problem(scope.id)
        store.admit_grounded_decision_problem("decision-problem:" + context.rsplit(":", 1)[-1], problem)
        return problem
    desktop = make("decision-scope:desktop", "context:desktop")
    embedded = make("decision-scope:embedded", "context:embedded")
    assert desktop.context != embedded.context
    assert desktop.candidates[0].truth is EvaluationTruth.TRUE
    assert embedded.candidates[0].truth is EvaluationTruth.UNKNOWN
    path = store.path; store.close()
    reopened = open_store(path)
    assert reopened.decision_problem("decision-problem:desktop").context == ContextId("context:desktop")
    assert reopened.decision_problem("decision-problem:embedded").candidates[0].exclusion_reason == "excluded_by_context"
    assert reopened.select_m1("decision-problem:desktop").status is SelectionStatus.RESOLVED
    assert reopened.select_m1("decision-problem:embedded").status is SelectionStatus.NO_ADMISSIBLE_CANDIDATE
