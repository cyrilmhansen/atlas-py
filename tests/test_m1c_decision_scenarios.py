"""Executable, functional stories for durable M1 decision outcomes."""

import json
from pathlib import Path

from atlas import *


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def data():
    return json.loads(FIXTURE.read_text())


def manifest(*candidates):
    return GroundingManifest("m1-grounding/1",
                             tuple(DescriptionId(x) for x in candidates),
                             (RuleId("coverage:v1"),))


def decide(store, scope_name, candidates, *, context="context:m1", snapshot="snapshot:m1",
           problem_id=None, decision_id=None):
    scope = store.create_decision_scope(scope_name, snapshot, context, intention='intent:selection', request="request:q1", manifest=manifest(*candidates))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    problem_id = problem_id or "decision-problem:" + scope_name.rsplit(":", 1)[-1]
    store.admit_grounded_decision_problem(problem_id, problem)
    selection = store.select_m1(problem_id)
    decision = store.admit_m1_decision(decision_id or "decision:" + scope_name.rsplit(":", 1)[-1], selection)
    return problem_id, selection, decision


def reopened(store):
    path = store.path
    store.close()
    return open_store(path)


def test_scenario_a_choose_a_mechanism_and_restart(tmp_path):
    """CPU 100, GPU 50, fallback FALSE: Atlas chooses GPU and remembers it."""
    fixture = data()
    for fact in fixture["facts"]:
        if fact["id"] == "fact:r1-capabilities":
            fact["value"]["items"] = ["a", "b"]  # CPU can perform the request.
        elif fact["id"] == "fact:r1-cost":
            fact["value"]["value"] = "100"
        elif fact["id"] == "fact:r2-cost":
            fact["value"]["value"] = "50"
    fixture["descriptions"].append({"id": "implementation:fallback", "label": "fallback"})
    fixture["facts"].append({"id": "fact:fallback-capabilities", "kind": "property",
        "description": "implementation:fallback", "property": "available-capabilities",
        "value": {"kind": "finite_set<symbol>", "items": ["a"]}, "scope": "catalog",
        "epistemic_status": "exact", "provenance": ["source:m1-fixture"]})
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)
    problem_id, selection, _ = decide(store, "decision-scope:mechanism",
                                      ("realization:r1", "realization:r2", "implementation:fallback"))
    assert selection == M1SelectionResult(DecisionProblemId(problem_id), SelectionStatus.RESOLVED,
                                          Integer(50), (DescriptionId("realization:r2"),))
    assert [candidate.candidate for candidate in store.decision_problem(problem_id).candidates] == [
        DescriptionId("realization:r1"), DescriptionId("realization:r2"), DescriptionId("implementation:fallback")]

    restored = reopened(store)
    assert restored.decision("decision:mechanism").status is SelectionStatus.RESOLVED
    assert restored.decision("decision:mechanism").optimum == Integer(50)
    assert restored.decision("decision:mechanism").co_optima == (DescriptionId("realization:r2"),)


def test_scenario_b_insufficient_information_is_historical(tmp_path):
    """Complete traversal is not complete knowledge; V2 supplies the missing fact."""
    fixture = data()
    fixture["facts"] = [fact for fact in fixture["facts"]
                        if fact["id"] not in {"fact:r2-capabilities", "fact:r2-cost"}]
    for fact in fixture["facts"]:
        if fact["id"] == "fact:r1-capabilities":
            fact["value"]["items"] = ["a", "b"]
        elif fact["id"] == "fact:r1-cost":
            fact["value"]["value"] = "100"
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)

    # V1: every candidate was traversed, but traversal did not create the
    # missing GPU knowledge. Complete traversal != complete knowledge.
    problem_id, selection, decision_v1 = decide(
        store, "decision-scope:unknown", ("realization:r1", "realization:r2"),
        problem_id="decision-problem:unknown", decision_id="decision:d1")
    assert store.decision_grounding("decision-scope:unknown").status is GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE
    assert all(observation.traversed for observation in
               store.decision_grounding("decision-scope:unknown").observations)
    assert store.decision_problem(problem_id).candidates[0].truth is EvaluationTruth.TRUE
    assert store.decision_problem(problem_id).candidates[1].truth is EvaluationTruth.UNKNOWN
    assert selection == M1SelectionResult(DecisionProblemId(problem_id),
                                          SelectionStatus.NEEDS_INFORMATION, None, ())
    assert decision_v1.status is SelectionStatus.NEEDS_INFORMATION

    # V2: the previously missing GPU knowledge becomes available through the
    # normal admission API, so a new historical environment can decide.
    store.admit([
        {"kind": "property", "payload": {
            "id": "fact:r2-capabilities-v2", "description": "realization:r2",
            "property": "available-capabilities", "version": "1",
            "value": {"kind": "finite_set<symbol>", "items": ["a", "b"]},
            "scope": "catalog", "epistemic_status": "exact",
            "provenance": ["source:m1-fixture"]}},
        {"kind": "property", "payload": {
            "id": "fact:r2-cost-v2", "description": "realization:r2",
            "property": "cost", "version": "1",
            "value": {"kind": "integer", "value": "50"},
            "scope": "catalog", "epistemic_status": "exact",
            "provenance": ["source:m1-fixture"]}},
    ])
    store.snapshot("snapshot:m1-revised", parent="snapshot:m1")
    _, selection_v2, decision_v2 = decide(
        store, "decision-scope:known", ("realization:r1", "realization:r2"),
        snapshot="snapshot:m1-revised", problem_id="decision-problem:known",
        decision_id="decision:d2")
    assert selection_v2 == M1SelectionResult(DecisionProblemId("decision-problem:known"),
                                              SelectionStatus.RESOLVED, Integer(50),
                                              (DescriptionId("realization:r2"),))
    assert decision_v2.status is SelectionStatus.RESOLVED

    restored = reopened(store)
    # Atlas was not wrong in V1: it did not yet have the information required.
    # The old GDP and decision remain historical; V2 is a separate decision.
    historical = restored.decision("decision:d1")
    assert (historical.status, historical.optimum, historical.co_optima) == (
        SelectionStatus.NEEDS_INFORMATION, None, ())
    assert (restored.decision("decision:d2").status,
            restored.decision("decision:d2").optimum,
            restored.decision("decision:d2").co_optima) == (
        SelectionStatus.RESOLVED, Integer(50), (DescriptionId("realization:r2"),))


def test_scenario_c_no_admissible_candidate_is_distinct(tmp_path):
    """CPU, GPU and fallback are all FALSE: this is not missing information."""
    fixture = data()
    fixture["descriptions"].append({"id": "implementation:fallback", "label": "fallback"})
    fixture["facts"].append({"id": "fact:fallback-capabilities", "kind": "property",
        "description": "implementation:fallback", "property": "available-capabilities",
        "value": {"kind": "finite_set<symbol>", "items": ["a"]}, "scope": "catalog",
        "epistemic_status": "exact", "provenance": ["source:m1-fixture"]})
    for fact in fixture["facts"]:
        if fact["id"] in {"fact:q1-search", "fact:q1-output"}:
            fact["value"]["items"] = ["not-supported"]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)
    _, selection, _ = decide(store, "decision-scope:none",
                             ("realization:r1", "realization:r2", "implementation:fallback"))
    assert selection == M1SelectionResult(DecisionProblemId("decision-problem:none"),
                                          SelectionStatus.NO_ADMISSIBLE_CANDIDATE, None, ())
    restored = reopened(store)
    decision = restored.decision("decision:none")
    assert decision.status is SelectionStatus.NO_ADMISSIBLE_CANDIDATE
    assert decision.optimum is None and decision.co_optima == ()


def test_scenario_d_both_co_optima_survive_restart(tmp_path):
    """CPU and GPU both cost 50: Atlas preserves the complete tie."""
    fixture = data()
    for fact in fixture["facts"]:
        if fact["id"] == "fact:r1-capabilities":
            fact["value"]["items"] = ["a", "b"]
        elif fact["id"] in {"fact:r1-cost", "fact:r2-cost"}:
            fact["value"]["value"] = "50"
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)
    _, selection, _ = decide(store, "decision-scope:tie", ("realization:r1", "realization:r2"))
    assert selection.status is SelectionStatus.RESOLVED
    assert set(selection.co_optima) == {DescriptionId("realization:r1"), DescriptionId("realization:r2")}
    restored = reopened(store)
    assert set(restored.decision("decision:tie").co_optima) == {
        DescriptionId("realization:r1"), DescriptionId("realization:r2")}


def test_scenario_e_v1_and_v2_decisions_remain_separate(tmp_path):
    """A later world creates D2; it does not rewrite D1's historical GDP."""
    fixture = data()
    for fact in fixture["facts"]:
        if fact["id"] == "fact:r1-capabilities":
            fact["value"]["items"] = ["a", "b"]
        elif fact["id"] == "fact:r1-cost":
            fact["value"]["value"] = "100"
        elif fact["id"] == "fact:r2-cost":
            fact["value"]["value"] = "50"
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)
    decide(store, "decision-scope:v1", ("realization:r1", "realization:r2"), decision_id="decision:d1")
    store.configure_vocabulary({"properties": [{"id": "cost", "version": "2", "value": "integer"}]})
    store.admit([{"kind": "property", "payload": {"id": "fact:r1-cost-v2", "description": "realization:r1", "property": "cost", "version": "2", "value": {"kind": "integer", "value": "30"}, "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}},
                 {"kind": "property", "payload": {"id": "fact:r2-cost-v2", "description": "realization:r2", "property": "cost", "version": "2", "value": {"kind": "integer", "value": "80"}, "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])
    store.snapshot("snapshot:v2")
    scope = store.create_decision_scope("decision-scope:v2", "snapshot:v2", "context:m1", intention='intent:selection', request="request:q1", manifest=manifest("realization:r1", "realization:r2"))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    store.admit_grounded_decision_problem("decision-problem:v2", problem)
    store.admit_m1_decision("decision:d2", store.select_m1("decision-problem:v2"))
    restored = reopened(store)
    assert (restored.decision("decision:d1").optimum, restored.decision("decision:d1").co_optima) == (Integer(50), (DescriptionId("realization:r2"),))
    assert (restored.decision("decision:d2").optimum, restored.decision("decision:d2").co_optima) == (Integer(30), (DescriptionId("realization:r1"),))


def test_scenario_f_independent_contexts_have_independent_outcomes(tmp_path):
    """The same GPU is known in desktop and UNKNOWN in embedded."""
    fixture = data()
    for fact in fixture["facts"]:
        if fact["id"] == "fact:r1-capabilities":
            fact["value"]["items"] = ["a", "b"]
        elif fact["id"] == "fact:r2-capabilities":
            fact["scope"] = "gpu-only"
        elif fact["id"] == "fact:r1-cost":
            fact["value"]["value"] = "100"
        elif fact["id"] == "fact:r2-cost":
            fact["value"]["value"] = "50"
    fixture["contexts"] = [
        {"id": "context:desktop", "visible_scopes": ["catalog", "gpu-only"], "enabled_rules": ["coverage:v1"]},
        {"id": "context:embedded", "visible_scopes": ["catalog"], "enabled_rules": ["coverage:v1"]},
    ]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)
    store.snapshot("snapshot:contexts")
    def make(context, decision_id):
        scope = store.create_decision_scope("decision-scope:" + context.rsplit(":", 1)[-1], "snapshot:contexts", context, intention='intent:selection', request="request:q1", manifest=manifest("realization:r1", "realization:r2"))
        store.evaluate_decision_scope(scope.id)
        problem = store.ground_decision_problem(scope.id)
        problem_id = "decision-problem:" + context.rsplit(":", 1)[-1]
        store.admit_grounded_decision_problem(problem_id, problem)
        return store.admit_m1_decision(decision_id, store.select_m1(problem_id))
    make("context:desktop", "decision:desktop")
    make("context:embedded", "decision:embedded")
    restored = reopened(store)
    assert restored.decision("decision:desktop").co_optima == (DescriptionId("realization:r2"),)
    assert restored.decision("decision:embedded").status is SelectionStatus.NEEDS_INFORMATION
