import copy
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from atlas import *
from atlas.values import Symbol


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def data_fixture():
    return json.loads(FIXTURE.read_text())


def make_store(tmp_path, data=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return admit_fixture(open_store(tmp_path / "atlas.sqlite"), data_fixture() if data is None else data)


def manifest(*candidates):
    return GroundingManifest("m1-grounding/1", tuple(DescriptionId(x) for x in candidates), (RuleId("coverage:v1"),))


def declare_and_ground(store, ident="decision-scope:ds1", candidates=("realization:r1", "realization:r2")):
    scope = store.create_decision_scope(ident, "snapshot:m1", "context:m1", intention='intent:selection', request="request:q1", manifest=manifest(*candidates))
    store.evaluate_decision_scope(scope.id)
    return scope


def test_m1c21_canonical_problem_and_exact_manifest_bijection(tmp_path):
    store = make_store(tmp_path)
    scope = declare_and_ground(store)
    problem = store.ground_decision_problem(scope.id)
    assert problem.scope_id == scope.id
    assert (problem.snapshot, problem.context, problem.request) == (scope.snapshot, scope.context, scope.request)
    assert tuple(x.candidate for x in problem.candidates) == scope.manifest.candidate_description_ids
    assert problem.objective == M1Objective(PropertyId("cost"), "1", "minimize", "exact")
    assert problem.candidates[0].truth is EvaluationTruth.FALSE
    assert problem.candidates[1].truth is EvaluationTruth.TRUE
    assert problem.candidates[1].objective_value.value == Integer(2)
    assert problem.candidates[1].objective_value.knowledge_id == KnowledgeId("fact:r2-cost")


def test_m1c21_false_unknown_and_context_exclusion_are_preserved(tmp_path):
    data = data_fixture()
    data["facts"] = [x for x in data["facts"] if x["id"] != "fact:r2-capabilities"]
    store = make_store(tmp_path, data)
    scope = declare_and_ground(store)
    problem = store.ground_decision_problem(scope.id)
    assert [x.truth for x in problem.candidates] == [EvaluationTruth.FALSE, EvaluationTruth.UNKNOWN]
    assert problem.candidates[1].grounding_result.missing_reads
    assert problem.candidates[1].objective_value is None

    excluded_data = data_fixture()
    excluded_data["contexts"][0]["visible_scopes"] = []
    excluded = make_store(tmp_path / "excluded", excluded_data)
    excluded_scope = declare_and_ground(excluded, candidates=("realization:r1",))
    candidate = excluded.ground_decision_problem(excluded_scope.id).candidates[0]
    assert candidate.truth is EvaluationTruth.UNKNOWN
    assert candidate.exclusion_reason == "excluded_by_context"


def test_m1c21_true_requires_unique_historical_exact_integer_cost(tmp_path):
    missing = data_fixture()
    missing["facts"] = [x for x in missing["facts"] if x["id"] != "fact:r2-cost"]
    with pytest.raises(GroundingError, match="cost is missing"):
        store = make_store(tmp_path / "missing", missing)
        scope = declare_and_ground(store)
        store.ground_decision_problem(scope.id)

    ambiguous = data_fixture()
    ambiguous["facts"].append({
        "id": "fact:r2-cost-duplicate", "kind": "property", "description": "realization:r2",
        "property": "cost", "value": {"kind": "integer", "value": "3"}, "scope": "catalog",
        "epistemic_status": "exact", "provenance": ["source:m1-fixture"]})
    with pytest.raises(GroundingError, match="cost is ambiguous"):
        store = make_store(tmp_path / "ambiguous", ambiguous)
        scope = declare_and_ground(store)
        store.ground_decision_problem(scope.id)

    wrong = make_store(tmp_path / "wrong")
    scope = declare_and_ground(wrong)
    wrong.records["fact:r2-cost"] = replace(wrong.records["fact:r2-cost"], value=Symbol("2"))
    with pytest.raises(GroundingError, match="not an exact integer"):
        wrong.ground_decision_problem(scope.id)


def test_m1c21_non_exact_cost_fails_but_truth_is_not_rewritten(tmp_path):
    data = data_fixture()
    for fact in data["facts"]:
        if fact["id"] == "fact:r2-cost":
            fact["epistemic_status"] = "estimate"
    store = make_store(tmp_path, data)
    scope = declare_and_ground(store)
    # The source run remains TRUE; objective construction rejects its unusable cost.
    assert store.decision_grounding(scope.id).observations[1].truth is EvaluationTruth.TRUE
    with pytest.raises(GroundingError, match="not exact"):
        store.ground_decision_problem(scope.id)


def test_m1c21_incomplete_or_missing_run_cannot_build(tmp_path):
    store = make_store(tmp_path)
    scope = store.create_decision_scope("decision-scope:no-run", "snapshot:m1", "context:m1", intention='intent:selection', request="request:q1", manifest=manifest("realization:r1"))
    with pytest.raises(GroundingError):
        store.ground_decision_problem(scope.id)

    grounded = declare_and_ground(store, "decision-scope:incomplete", ("realization:r1",))
    store.decision_groundings[grounded.id.value] = replace(
        store.decision_groundings[grounded.id.value], interrupted=True)
    with pytest.raises(GroundingError, match="not complete"):
        store.ground_decision_problem(grounded.id)


def test_m1c21_does_not_discover_r3_and_does_not_reground(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    scope = declare_and_ground(store)
    before = tuple(store.decision_groundings)

    def forbidden(*args, **kwargs):
        raise AssertionError("M1c.2.1 must not re-ground")
    monkeypatch.setattr(store, "ground", forbidden)
    monkeypatch.setattr(store, "ground_decision_scope", forbidden)
    store.descriptions["realization:r3"] = Description(DescriptionId("realization:r3"), "new current candidate")
    problem = store.ground_decision_problem(scope.id)
    assert tuple(x.candidate.value for x in problem.candidates) == ("realization:r1", "realization:r2")
    assert tuple(store.decision_groundings) == before


def test_m1c21_zero_persistence_mutation_and_v1_is_historical(tmp_path):
    store = make_store(tmp_path)
    scope = declare_and_ground(store)
    path = store.path
    before_rows = store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()
    before_maps = (dict(store.records), dict(store.decision_scopes), dict(store.decision_groundings))
    first = store.ground_decision_problem(scope.id)

    store.configure_vocabulary({"properties": [{"id": "cost", "version": "2", "value": "integer"}]})
    store.admit([{"kind": "description", "payload": {"id": "realization:r3", "label": "new"}},
                 {"kind": "property", "payload": {"id": "fact:r2-cost-v2", "description": "realization:r2", "property": "cost", "version": "2", "value": {"kind": "integer", "value": "99"}, "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])
    second = store.ground_decision_problem(scope.id)
    assert second == first
    assert dict(store.records) != before_maps[0]  # only the caller's later V2 additions changed the store
    after_rows = store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()
    # Building the problem itself adds no row; the only new rows are the explicit V2 additions.
    assert len(after_rows) == len(before_rows) + 2
    assert all(x.candidate.value != "realization:r3" for x in second.candidates)
    store.close()
    reopened = open_store(path)
    assert reopened.ground_decision_problem(scope.id) == first


def test_m1c21_two_scopes_and_multiple_true_candidates_remain_independent(tmp_path):
    data = data_fixture()
    for fact in data["facts"]:
        if fact["id"] in {"fact:q1-search", "fact:q1-output"}:
            fact["value"]["items"] = []
    store = make_store(tmp_path, data)
    multi_scope = store.create_decision_scope("decision-scope:multi", "snapshot:m1", "context:m1", intention='intent:selection', request="request:q1", manifest=manifest("realization:r1", "realization:r2"))
    s1 = store.create_decision_scope("decision-scope:ds1", "snapshot:m1", "context:m1", intention='intent:selection', request="request:q1", manifest=manifest("realization:r2"))
    s2 = store.create_decision_scope("decision-scope:ds2", "snapshot:m1", "context:m1", intention='intent:selection', request="request:q1", manifest=manifest("realization:r1"))
    store.evaluate_decision_scope(multi_scope.id)
    store.evaluate_decision_scope(s1.id)
    store.evaluate_decision_scope(s2.id)
    multi = store.ground_decision_problem(multi_scope.id)
    assert [x.truth for x in multi.candidates] == [EvaluationTruth.TRUE, EvaluationTruth.TRUE]
    assert not hasattr(multi, "winner") and not hasattr(multi, "selected")
    p1, p2 = store.ground_decision_problem(s1.id), store.ground_decision_problem(s2.id)
    assert p1.scope_id != p2.scope_id
    assert p1.candidates[0].candidate != p2.candidates[0].candidate
    assert not hasattr(p1, "winner") and not hasattr(p1, "selected")


def test_m1c21_source_support_is_immutable_and_no_problem_identity_is_persisted(tmp_path):
    store = make_store(tmp_path)
    scope = declare_and_ground(store)
    problem = store.ground_decision_problem(scope.id)
    support = problem.candidates[1].objective_value
    assert support.knowledge_id == KnowledgeId("fact:r2-cost")
    with pytest.raises((AttributeError, TypeError)):
        problem.candidates += (problem.candidates[0],)
    assert not any(kind == "grounded_decision_problem" for kind, _ in store.isolated)
    assert store._db.execute("SELECT COUNT(*) FROM records WHERE kind='grounded_decision_problem'").fetchone()[0] == 0
