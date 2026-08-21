"""Adversarial boundaries for the explicit M1 decision persistence API."""

import json
import sqlite3
from pathlib import Path

import pytest

from atlas import *


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def prepared(tmp_path, *, costs=(100, 50), unknown_gpu=False, all_false=False, problem_id="decision-problem:p"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw = json.loads(FIXTURE.read_text())
    for fact in raw["facts"]:
        if fact["id"] == "fact:r1-capabilities":
            fact["value"]["items"] = ["a", "b"] if not all_false else ["x"]
        elif fact["id"] == "fact:r2-capabilities" and unknown_gpu:
            raw["facts"].remove(fact)
            break
        elif fact["id"] == "fact:r1-cost":
            fact["value"]["value"] = str(costs[0])
        elif fact["id"] == "fact:r2-cost":
            fact["value"]["value"] = str(costs[1])
    if all_false:
        for fact in raw["facts"]:
            if fact["id"] in {"fact:q1-search", "fact:q1-output"}:
                fact["value"]["items"] = ["z"]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), raw)
    scope = store.create_decision_scope("decision-scope:p", "snapshot:m1", "context:m1", "request:q1",
        GroundingManifest("m1-grounding/1", (DescriptionId("realization:r1"), DescriptionId("realization:r2")), (RuleId("coverage:v1"),)))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    store.admit_grounded_decision_problem(problem_id, problem)
    selection = store.select_m1(problem_id)
    store.admit_m1_decision("decision:d", selection)
    return store


def payload_row(path, kind="decision", ident="decision:d"):
    conn = sqlite3.connect(path)
    row = conn.execute("SELECT payload FROM records WHERE kind=? AND id=?", (kind, ident)).fetchone()
    return conn, json.loads(row[0])


def test_canonical_admission_restart_and_pure_select(tmp_path):
    store = prepared(tmp_path)
    before = store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()
    result = store.select_m1("decision-problem:p")
    assert result.status is SelectionStatus.RESOLVED
    assert store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall() == before
    path = store.path
    store.close()
    reopened = open_store(path)
    assert reopened.decision("decision:d").optimum == Integer(50)
    assert reopened.decision("decision:d").source == DecisionProblemId("decision-problem:p")


def test_explicit_admission_only_and_atomic_rollback(tmp_path, monkeypatch):
    raw = json.loads(FIXTURE.read_text())
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), raw)
    scope = store.create_decision_scope("decision-scope:p", "snapshot:m1", "context:m1", "request:q1",
        GroundingManifest("m1-grounding/1", (DescriptionId("realization:r2"),), (RuleId("coverage:v1"),)))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    store.admit_grounded_decision_problem("decision-problem:p", problem)
    selection = store.select_m1("decision-problem:p")
    assert not store.decisions
    original = store._persist
    def fail(*args):
        original(*args)
        raise RuntimeError("injected")
    monkeypatch.setattr(store, "_persist", fail)
    with pytest.raises(RuntimeError):
        store.admit_m1_decision("decision:d", selection)
    assert not store.decisions
    assert store._db.execute("SELECT COUNT(*) FROM records WHERE kind='decision'").fetchone()[0] == 0
    monkeypatch.setattr(store, "_persist", original)
    store.admit_m1_decision("decision:d", selection)
    assert store.decision("decision:d").status is SelectionStatus.RESOLVED


@pytest.mark.parametrize("bad", [None, [], {"schema": "wrong"}, {"schema": "atlas.core-v1.m1-decision/1"}])
def test_malformed_root_or_closed_schema_isolated(tmp_path, bad):
    store = prepared(tmp_path)
    path = store.path
    store.close()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE records SET payload=? WHERE kind='decision' AND id='decision:d'", (json.dumps(bad),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "decision:d" in reopened.isolated
    assert not reopened.decisions


def test_duplicate_co_optima_is_rejected_without_repair(tmp_path):
    store = prepared(tmp_path)
    path = store.path
    store.close()
    conn, payload = payload_row(path)
    payload["co_optima"] = ["realization:r2", "realization:r2"]
    conn.execute("UPDATE records SET payload=? WHERE kind='decision'", (json.dumps(payload),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "decision:d" in reopened.isolated
    assert not reopened.decisions


def test_added_non_optimal_co_optimum_is_rejected(tmp_path):
    store = prepared(tmp_path)
    path = store.path; store.close()
    conn, payload = payload_row(path)
    payload["co_optima"] = ["realization:r2", "realization:r1"]
    # r1 is TRUE at cost 100; it is not a minimizer of the historical GDP.
    conn.execute("UPDATE records SET payload=? WHERE kind='decision'", (json.dumps(payload),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "decision:d" in reopened.isolated
    assert reopened.decision_problem("decision-problem:p").candidates


def test_unknown_source_gdp_is_isolated_and_does_not_contaminate_other_gdp(tmp_path):
    store = prepared(tmp_path / "one")
    # A second nominal decision outcome remains independent on another store
    # artifact; corruption of the source is local to its dependency chain.
    store.admit_m1_decision("decision:sibling", store.select_m1("decision-problem:p"))
    path = store.path; store.close()
    conn, payload = payload_row(path, "grounded_decision_problem", "decision-problem:p")
    payload["id"] = "decision-problem:missing-source"
    conn.execute("UPDATE records SET payload=? WHERE kind='grounded_decision_problem' AND id='decision-problem:p'", (json.dumps(payload),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "decision-problem:p" in reopened.isolated
    assert "decision:d" in reopened.isolated and "decision:sibling" in reopened.isolated


def test_corrupt_decision_does_not_close_gdp_and_healthy_sibling_survives(tmp_path):
    store = prepared(tmp_path)
    store.admit_m1_decision("decision:sibling", store.select_m1("decision-problem:p"))
    path = store.path; store.close()
    conn, payload = payload_row(path)
    payload["optimum"] = {"kind": "integer", "value": "100"}
    payload["co_optima"] = ["realization:r1"]
    conn.execute("UPDATE records SET payload=? WHERE kind='decision' AND id='decision:d'", (json.dumps(payload),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "decision:d" in reopened.isolated
    assert reopened.decision_problem("decision-problem:p").candidates
    assert reopened.decision("decision:sibling").optimum == Integer(50)


@pytest.mark.parametrize("change", [
    lambda p: p.update(status="needs_information"),
    lambda p: p.update(optimum={"kind": "integer", "value": "100"}),
    lambda p: p.update(co_optima=["realization:r1"]),
    lambda p: p.update(source_decision_problem_id="decision-problem:other"),
])
def test_wrong_status_forged_optimum_omitted_co_optimum_and_source_are_rejected(tmp_path, change):
    store = prepared(tmp_path)
    path = store.path; store.close()
    conn, payload = payload_row(path)
    change(payload)
    conn.execute("UPDATE records SET payload=? WHERE kind='decision'", (json.dumps(payload),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "decision:d" in reopened.isolated
    assert reopened.decision_problem("decision-problem:p").scope_id == DecisionScopeId("decision-scope:p")


def test_restore_never_recomputes_or_repairs(tmp_path, monkeypatch):
    store = prepared(tmp_path)
    path = store.path; store.close()
    def forbidden(*args, **kwargs):
        raise AssertionError("restore must use the persisted outcome directly")
    monkeypatch.setattr(Store, "select_m1", forbidden)
    monkeypatch.setattr(Store, "ground", forbidden)
    monkeypatch.setattr(Store, "ground_decision_scope", forbidden)
    monkeypatch.setattr(Store, "ground_decision_problem", forbidden)
    import atlas.problem as problem_module
    monkeypatch.setattr(problem_module, "_select_m1", forbidden)
    monkeypatch.setattr(problem_module, "build_grounded_decision_problem", forbidden)
    reopened = open_store(path)
    assert reopened.decision("decision:d").optimum == Integer(50)


def test_two_decision_ids_are_nominally_distinct(tmp_path):
    store = prepared(tmp_path)
    first = store.decision("decision:d")
    second = store.admit_m1_decision("decision:other", store.select_m1(first.source))
    assert first.id != second.id
    path = store.path; store.close()
    reopened = open_store(path)
    assert set(reopened.decisions) == {"decision:d", "decision:other"}


def test_persisted_order_does_not_choose_first_co_optimum(tmp_path):
    store = prepared(tmp_path, costs=(50, 50))
    path = store.path; store.close()
    conn, payload = payload_row(path)
    payload["co_optima"] = ["realization:r2", "realization:r1"]
    conn.execute("UPDATE records SET payload=? WHERE kind='decision'", (json.dumps(payload),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert set(reopened.decision("decision:d").co_optima) == {DescriptionId("realization:r1"), DescriptionId("realization:r2")}


def test_all_three_statuses_can_be_admitted_and_restored(tmp_path):
    resolved = prepared(tmp_path / "resolved")
    assert resolved.decision("decision:d").status is SelectionStatus.RESOLVED
    needs = prepared(tmp_path / "needs", unknown_gpu=True)
    assert needs.decision("decision:d").status is SelectionStatus.NEEDS_INFORMATION
    none = prepared(tmp_path / "none", all_false=True)
    assert none.decision("decision:d").status is SelectionStatus.NO_ADMISSIBLE_CANDIDATE


def test_no_m1d_or_m1e_artifacts_leak_into_decision(tmp_path):
    store = prepared(tmp_path)
    decision = store.decision("decision:d")
    assert not hasattr(decision, "explanation")
    assert not hasattr(decision, "stale")
    assert not hasattr(decision, "superseded")
