"""M1e.2.2: two explicit, immutable decision histories across snapshots."""

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
import pytest

from atlas import *
from atlas.evidence import evidence_for
from atlas.scope import grounding_payload


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def _fixture():
    value = json.loads(FIXTURE.read_text())
    value = json.loads(json.dumps(value).replace("realization:r1", "EASY_SHORTCUT")
                       .replace("realization:r2", "DEEP_THOUGHT")
                       .replace("fact:r1", "fact:EASY_SHORTCUT")
                       .replace("fact:r2", "fact:DEEP_THOUGHT"))
    for fact in value["facts"]:
        if fact["id"] == "fact:EASY_SHORTCUT-capabilities":
            fact["value"]["items"] = ["a", "b"]
        if fact["id"] == "fact:EASY_SHORTCUT-cost": fact["value"]["value"] = "100"
        if fact["id"] == "fact:DEEP_THOUGHT-cost": fact["value"]["value"] = "50"
    return value


def _manifest():
    return GroundingManifest(
        "m1-grounding/1",
        (DescriptionId("EASY_SHORTCUT"), DescriptionId("DEEP_THOUGHT")),
        (RuleId("coverage:v1"),),
    )


def _new_cost(store, ident, candidate, value):
    store.admit([{"kind": "property", "payload": {
        "id": ident, "description": candidate, "property": "cost", "version": "1",
        "value": {"kind": "integer", "value": str(value)}, "scope": "catalog",
        "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])


def _base(tmp_path):
    return admit_fixture(open_store(tmp_path / "atlas.sqlite"), _fixture())


def _resolve(store, prefix, snapshot, *, decision_id=None, problem_id=None):
    scope = store.create_decision_scope(
        f"decision-scope:{prefix}", snapshot, "context:m1", "request:q1", _manifest())
    store.evaluate_decision_scope(scope.id)
    grounded = store.ground_decision_problem(scope.id)
    pid = problem_id or f"decision-problem:{prefix}"
    store.admit_grounded_decision_problem(pid, grounded)
    selection = store.select_m1(pid)
    return store.admit_m1_decision(decision_id or f"decision:{prefix}", selection)


def _candidate(explanation, name):
    return next(x for x in explanation.candidates if x.candidate == DescriptionId(name))


def test_explicit_new_decision_preserves_two_historical_histories(tmp_path):
    store = _base(tmp_path)

    # DEEP_THOUGHT WAS CHEAP: explicit S1 chain and D1.
    d1 = _resolve(store, "S1", "snapshot:m1", decision_id="decision:D1",
                  problem_id="decision-problem:D1")
    scope1 = store.decision_scope("decision-scope:S1")
    grounding1 = store.decision_grounding("decision-scope:S1")
    gdp1 = store.decision_problem("decision-problem:D1")
    explanation1 = store.explain_m1(d1.id)
    assert scope1.snapshot == SnapshotId("snapshot:m1")
    assert grounding1.scope_id == scope1.id

    # DEEP_THOUGHT BECOMES EXPENSIVE. Supersession is the only mutation of
    # the effective view; it does not create any decision artifacts.
    _new_cost(store, "fact:DEEP_THOUGHT-cost-v2", "DEEP_THOUGHT", 120)
    store.snapshot("S2", parent="snapshot:m1")
    store.supersede("fact:DEEP_THOUGHT-cost", "fact:DEEP_THOUGHT-cost-v2", "S2")
    assert set(store.decision_scopes) == {"decision-scope:S1"}
    assert set(store.decision_groundings) == {"decision-scope:S1"}
    assert set(store.grounded_decision_problems) == {"decision-problem:D1"}
    assert set(store.decisions) == {"decision:D1"}
    assert store.status_of("decision:D1", relative_to="snapshot:m1") is ArtifactStatus.CURRENT
    assert store.status_of("decision:D1", relative_to="S2") is ArtifactStatus.STALE
    assert store.decision("decision:D1").co_optima == (DescriptionId("DEEP_THOUGHT"),)
    assert _candidate(store.explain_m1("decision:D1"), "DEEP_THOUGHT").objective_value.value == Integer(50)

    # ASK AGAIN: D2 is a wholly new Scope -> Grounding -> GDP -> Selection
    # -> Decision chain, with no latest/current lookup involved.
    d2 = _resolve(store, "S2", "S2", decision_id="decision:D2",
                  problem_id="decision-problem:D2")
    gdp2 = store.decision_problem("decision-problem:D2")
    assert d2.source == DecisionProblemId("decision-problem:D2")
    assert store.decision_scope("decision-scope:S2").snapshot == SnapshotId("S2")
    assert store.decision_grounding("decision-scope:S2").scope_id == DecisionScopeId("decision-scope:S2")
    assert store.decision_grounding("decision-scope:S2").schema.endswith("/2")
    assert d2.co_optima == (DescriptionId("EASY_SHORTCUT"),)
    assert store.status_of("decision:D2", relative_to="S2") is ArtifactStatus.CURRENT

    old_deep = _candidate(store.explain_m1("decision:D1"), "DEEP_THOUGHT")
    new_deep = next(x for x in gdp2.candidates if x.candidate == DescriptionId("DEEP_THOUGHT"))
    new_easy = next(x for x in gdp2.candidates if x.candidate == DescriptionId("EASY_SHORTCUT"))
    assert old_deep.objective_value.knowledge_id == KnowledgeId("fact:DEEP_THOUGHT-cost")
    assert old_deep.objective_value.value == Integer(50)
    assert new_deep.objective_value.knowledge_id == KnowledgeId("fact:DEEP_THOUGHT-cost-v2")
    assert new_deep.objective_value.value == Integer(120)
    assert new_easy.objective_value.value == Integer(100)

    # Both explanations are reconstructed from their own persisted GDP.
    e1, e2 = store.explain_m1("decision:D1"), store.explain_m1("decision:D2")
    assert _candidate(e1, "DEEP_THOUGHT").selected
    assert _candidate(e1, "DEEP_THOUGHT").objective_value.value == Integer(50)
    assert _candidate(e2, "EASY_SHORTCUT").selected
    assert _candidate(e2, "EASY_SHORTCUT").objective_value.value == Integer(100)
    assert _candidate(e2, "DEEP_THOUGHT").reason is ExplanationReason.ADMISSIBLE_HIGHER_OBJECTIVE
    assert _candidate(e2, "DEEP_THOUGHT").objective_value.value == Integer(120)

    # Historical reproduction is restore/validation only, never a new solve.
    store.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert reopened.decision("decision:D1") == d1
    assert reopened.decision_problem("decision-problem:D1") == gdp1
    assert reopened.explain_m1("decision:D1") == explanation1
    assert reopened.decision("decision:D2") == d2
    assert reopened.decision_problem("decision-problem:D2") == gdp2
    assert reopened.explain_m1("decision:D2") == e2
    assert reopened.status_of("decision:D1", relative_to="snapshot:m1") is ArtifactStatus.CURRENT
    assert reopened.status_of("decision:D1", relative_to="S2") is ArtifactStatus.STALE
    assert reopened.status_of("decision:D2", relative_to="S2") is ArtifactStatus.CURRENT


def test_sibling_snapshots_require_independent_explicit_decisions(tmp_path):
    store = _base(tmp_path)
    _new_cost(store, "fact:DEEP_THOUGHT-cost-v2", "DEEP_THOUGHT", 120)
    store.snapshot("S2A", parent="snapshot:m1")
    store.snapshot("S2B", parent="snapshot:m1")
    store.supersede("fact:DEEP_THOUGHT-cost", "fact:DEEP_THOUGHT-cost-v2", "S2A")
    d2a = _resolve(store, "S2A", "S2A", decision_id="decision:D2A", problem_id="decision-problem:D2A")
    d2b = _resolve(store, "S2B", "S2B", decision_id="decision:D2B", problem_id="decision-problem:D2B")
    gdp2a = store.decision_problem("decision-problem:D2A")
    explanation2a = store.explain_m1(d2a.id)
    gdp2b = store.decision_problem("decision-problem:D2B")
    explanation2b = store.explain_m1(d2b.id)
    assert d2a.co_optima == (DescriptionId("EASY_SHORTCUT"),)
    assert d2b.co_optima == (DescriptionId("DEEP_THOUGHT"),)
    assert next(x for x in gdp2a.candidates if x.candidate == DescriptionId("EASY_SHORTCUT")).objective_value.value == Integer(100)
    assert next(x for x in gdp2b.candidates if x.candidate == DescriptionId("DEEP_THOUGHT")).objective_value.value == Integer(50)
    assert gdp2a.candidates[1].objective_value.value == Integer(120)
    assert gdp2b.candidates[1].objective_value.value == Integer(50)
    store.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert reopened.decision("decision:D2A") == d2a
    assert reopened.decision_problem("decision-problem:D2A") == gdp2a
    assert reopened.explain_m1("decision:D2A") == explanation2a
    assert reopened.decision("decision:D2B") == d2b
    assert reopened.decision_problem("decision-problem:D2B") == gdp2b
    assert reopened.explain_m1("decision:D2B") == explanation2b
    assert reopened.decision("decision:D2A") != reopened.decision("decision:D2B")
    assert reopened.decision("decision:D2A").co_optima != reopened.decision("decision:D2B").co_optima
    assert reopened.status_of("decision:D2A", relative_to="S2A") is ArtifactStatus.CURRENT
    assert reopened.status_of("decision:D2B", relative_to="S2B") is ArtifactStatus.CURRENT


def test_corrupting_d2_isolated_without_poisoning_d1(tmp_path):
    store = _base(tmp_path)
    d1 = _resolve(store, "S1", "snapshot:m1", decision_id="decision:D1", problem_id="decision-problem:D1")
    _new_cost(store, "fact:DEEP_THOUGHT-cost-v2", "DEEP_THOUGHT", 120)
    store.snapshot("S2", parent="snapshot:m1")
    store.supersede("fact:DEEP_THOUGHT-cost", "fact:DEEP_THOUGHT-cost-v2", "S2")
    d2 = _resolve(store, "S2", "S2", decision_id="decision:D2", problem_id="decision-problem:D2")
    gdp2 = store.decision_problem("decision-problem:D2")
    explanation2 = store.explain_m1(d2.id)
    assert store.decision("decision:D2") == d2
    assert store.decision_problem("decision-problem:D2") == gdp2
    assert d2.co_optima == (DescriptionId("EASY_SHORTCUT"),)
    assert _candidate(explanation2, "EASY_SHORTCUT").selected
    assert _candidate(explanation2, "EASY_SHORTCUT").objective_value.value == Integer(100)
    assert _candidate(explanation2, "DEEP_THOUGHT").objective_value.value == Integer(120)
    assert store.status_of("decision:D2", relative_to="S2") is ArtifactStatus.CURRENT
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    payload = json.loads(db.execute(
        "SELECT payload FROM records WHERE kind='grounded_decision_problem' AND id='decision-problem:D2'"
    ).fetchone()[0])
    payload["candidates"][1]["objective_value"]["knowledge_id"] = "fact:DEEP_THOUGHT-cost"
    db.execute("UPDATE records SET payload=? WHERE kind='grounded_decision_problem' AND id='decision-problem:D2'",
               (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert "decision-problem:D2" not in reopened.grounded_decision_problems
    assert "decision:D2" not in reopened.decisions
    assert reopened.decision("decision:D1") == d1
    assert reopened.status_of("decision:D1", relative_to="snapshot:m1") is ArtifactStatus.CURRENT


def test_corrupt_d2_source_cannot_reuse_gdp1(tmp_path):
    store = _base(tmp_path)
    d1 = _resolve(store, "S1", "snapshot:m1", decision_id="decision:D1", problem_id="decision-problem:D1")
    _new_cost(store, "fact:DEEP_THOUGHT-cost-v2", "DEEP_THOUGHT", 120)
    store.snapshot("S2", parent="snapshot:m1")
    store.supersede("fact:DEEP_THOUGHT-cost", "fact:DEEP_THOUGHT-cost-v2", "S2")
    d2 = _resolve(store, "S2", "S2", decision_id="decision:D2", problem_id="decision-problem:D2")
    gdp2 = store.decision_problem("decision-problem:D2")
    explanation2 = store.explain_m1(d2.id)
    assert store.decision("decision:D2") == d2
    assert store.decision_problem("decision-problem:D2") == gdp2
    assert d2.co_optima == (DescriptionId("EASY_SHORTCUT"),)
    assert _candidate(explanation2, "EASY_SHORTCUT").selected
    assert _candidate(explanation2, "EASY_SHORTCUT").objective_value.value == Integer(100)
    assert _candidate(explanation2, "DEEP_THOUGHT").objective_value.value == Integer(120)
    assert store.status_of("decision:D2", relative_to="S2") is ArtifactStatus.CURRENT
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    payload = json.loads(db.execute(
        "SELECT payload FROM records WHERE kind='decision' AND id='decision:D2'"
    ).fetchone()[0])
    payload["source_decision_problem_id"] = "decision-problem:D1"
    db.execute("UPDATE records SET payload=? WHERE kind='decision' AND id='decision:D2'",
               (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert "decision:D2" not in reopened.decisions
    # records has no checksum/hash derived from payload: the schema-valid row
    # reaches validate_persisted_decision and is rejected against GDP1.
    assert reopened.isolated[("decision", "decision:D2")]["reason"] == (
        "persisted decision optimum disagrees with historical GDP"
    )
    assert reopened.decision("decision:D1") == d1
    assert reopened.explain_m1("decision:D1").candidates[1].objective_value.value == Integer(50)


def test_corrupt_current_grounding_old_support_isolated_before_gdp(tmp_path):
    store = _base(tmp_path)
    d1 = _resolve(store, "S1", "snapshot:m1", decision_id="decision:D1",
                  problem_id="decision-problem:D1")

    store.admit([{"kind": "property", "payload": {
        "id": "fact:DEEP_THOUGHT-capabilities-v2", "description": "DEEP_THOUGHT",
        "property": "available-capabilities", "version": "1",
        "value": {"kind": "finite_set<symbol>", "items": ["a"]}, "scope": "catalog",
        "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])
    store.snapshot("S2", parent="snapshot:m1")
    store.supersede("fact:DEEP_THOUGHT-capabilities",
                    "fact:DEEP_THOUGHT-capabilities-v2", "S2")
    scope2 = store.create_decision_scope(
        "decision-scope:S2", "S2", "context:m1", "request:q1", _manifest())
    store.evaluate_decision_scope(scope2.id)
    assert next(x for x in store.decision_grounding(scope2.id).observations
                if x.candidate == DescriptionId("DEEP_THOUGHT")).truth is EvaluationTruth.FALSE

    # Forge only the persisted S2 grounding: reuse S1's TRUE result, retag its
    # explicit snapshot as S2, and retain the physically present but masked ID.
    s1_result = next(x for x in store.decision_grounding("decision-scope:S1").observations
                     if x.candidate == DescriptionId("DEEP_THOUGHT")).grounding_result
    forged_result = replace(s1_result, snapshot=SnapshotId("S2"))
    forged_result = replace(forged_result,
                            grounding_evidence=evidence_for(forged_result, ("candidate", "request")))
    current = store.decision_grounding(scope2.id)
    observations = tuple(
        replace(observation, truth=EvaluationTruth.TRUE, grounding_result=forged_result)
        if observation.candidate == DescriptionId("DEEP_THOUGHT") else observation
        for observation in current.observations)
    forged_payload = grounding_payload(replace(current, observations=observations))
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding' AND id=?",
               (json.dumps(forged_payload), scope2.id.value))
    db.commit(); db.close()
    store.close()

    reopened = open_store(tmp_path / "atlas.sqlite")
    assert "decision-scope:S2" not in reopened.decision_groundings
    assert ("decision_grounding", "decision-scope:S2") in reopened.isolated
    with pytest.raises(GroundingError):
        reopened.ground_decision_problem("decision-scope:S2")

    assert reopened.decision("decision:D1") == d1
    assert reopened.explain_m1("decision:D1")
    assert reopened.status_of("decision:D1", relative_to="snapshot:m1") is ArtifactStatus.CURRENT
    assert reopened.status_of("decision:D1", relative_to="S2") is ArtifactStatus.STALE


def test_missing_d2_gdp_isolated_without_invalidating_d1(tmp_path):
    store = _base(tmp_path)
    d1 = _resolve(store, "S1", "snapshot:m1", decision_id="decision:D1", problem_id="decision-problem:D1")
    _new_cost(store, "fact:DEEP_THOUGHT-cost-v2", "DEEP_THOUGHT", 120)
    store.snapshot("S2", parent="snapshot:m1")
    store.supersede("fact:DEEP_THOUGHT-cost", "fact:DEEP_THOUGHT-cost-v2", "S2")
    d2 = _resolve(store, "S2", "S2", decision_id="decision:D2", problem_id="decision-problem:D2")
    gdp2 = store.decision_problem("decision-problem:D2")
    explanation2 = store.explain_m1(d2.id)
    assert store.decision("decision:D2") == d2
    assert store.decision_problem("decision-problem:D2") == gdp2
    assert d2.co_optima == (DescriptionId("EASY_SHORTCUT"),)
    assert _candidate(explanation2, "EASY_SHORTCUT").selected
    assert _candidate(explanation2, "EASY_SHORTCUT").objective_value.value == Integer(100)
    assert _candidate(explanation2, "DEEP_THOUGHT").objective_value.value == Integer(120)
    assert store.status_of("decision:D2", relative_to="S2") is ArtifactStatus.CURRENT
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    db.execute("DELETE FROM records WHERE kind='grounded_decision_problem' AND id='decision-problem:D2'")
    db.commit(); db.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert "decision-problem:D2" not in reopened.grounded_decision_problems
    assert "decision:D2" not in reopened.decisions
    assert reopened.isolated[("decision", "decision:D2")]["reason"] == (
        "decision references an invalid source grounded decision problem"
    )
    assert "decision-scope:S1" in reopened.decision_scopes
    assert "decision-scope:S1" in reopened.decision_groundings
    assert "decision-problem:D1" in reopened.grounded_decision_problems
    assert reopened.decision("decision:D1") == d1
