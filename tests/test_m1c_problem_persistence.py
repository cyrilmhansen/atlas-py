import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from atlas import *


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def fixture():
    return json.loads(FIXTURE.read_text())


def manifest(*candidates):
    return GroundingManifest("m1-grounding/1", tuple(DescriptionId(x) for x in candidates), (RuleId("coverage:v1"),))


def prepared(tmp_path, candidates=("realization:r1", "realization:r2")):
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture())
    scope = store.create_decision_scope("decision-scope:problem", "snapshot:m1", "context:m1", "request:q1", manifest(*candidates))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    return store, scope, problem


def test_m1c22_01_admit_and_02_restart_are_exact(tmp_path):
    store, scope, problem = prepared(tmp_path)
    assert store.grounded_decision_problems == {}
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    assert store.decision_problem("decision-problem:p1") == problem
    assert store._db.execute("SELECT kind FROM records WHERE kind='grounded_decision_problem'").fetchall()
    path = store.path
    store.close()
    reopened = open_store(path)
    assert reopened.decision_problem("decision-problem:p1") == problem


def test_m1c22_03_pure_construction_does_not_persist(tmp_path):
    store, scope, problem = prepared(tmp_path)
    before = store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()
    assert store.ground_decision_problem(scope.id) == problem
    assert store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall() == before


def test_m1c22_04_admission_is_atomic(tmp_path, monkeypatch):
    store, scope, problem = prepared(tmp_path)
    original = store._persist

    def fail(kind, ident, payload):
        original(kind, ident, payload)
        raise RuntimeError("injected admission failure")

    monkeypatch.setattr(store, "_persist", fail)
    with pytest.raises(RuntimeError):
        store.admit_grounded_decision_problem("decision-problem:atomic", problem)
    assert store._db.execute("SELECT COUNT(*) FROM records WHERE kind='grounded_decision_problem'").fetchone()[0] == 0
    assert "decision-problem:atomic" not in store.grounded_decision_problems


def test_m1c22_05_restore_does_not_ground(tmp_path, monkeypatch):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    path = store.path
    store.close()
    def forbidden(*args, **kwargs):
        raise AssertionError("restore must not ground")
    monkeypatch.setattr(Store, "ground", forbidden)
    monkeypatch.setattr(Store, "ground_decision_scope", forbidden)
    monkeypatch.setattr(Store, "ground_decision_problem", forbidden)
    import atlas.problem as problem_module
    monkeypatch.setattr(problem_module, "build_grounded_decision_problem", forbidden)
    import atlas.store as store_module
    assert not hasattr(store_module, "build_grounded_decision_problem")
    reopened = open_store(path)
    assert reopened.decision_problem("decision-problem:p1") == problem


def test_m1c22_r1_wrong_persisted_support_identity_is_rejected(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    path = store.path; store.close()
    conn, payload = _payload(path)
    # Make Fact A a second valid cost of 2, then point the persisted r2 GDP at
    # it.  Numeric equality must not replace the historical support identity.
    fact = json.loads(conn.execute("SELECT payload FROM records WHERE kind='property' AND id='fact:r1-cost'").fetchone()[0])
    fact["value"]["value"] = "2"
    conn.execute("UPDATE records SET payload=? WHERE kind='property' AND id='fact:r1-cost'", (json.dumps(fact),))
    payload["candidates"][1]["objective_value"]["knowledge_id"] = "fact:r1-cost"
    conn.execute("UPDATE records SET payload=? WHERE kind='grounded_decision_problem'", (json.dumps(payload),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "decision-problem:p1" in reopened.isolated
    assert not reopened.grounded_decision_problems
    assert ("snapshot", "snapshot:m1") not in reopened.isolated
    assert ("decision_scope", scope.id.value) not in reopened.isolated
    assert ("decision_grounding", scope.id.value) not in reopened.isolated


def test_m1c22_r1_forged_payload_is_not_repaired_by_a_successful_builder(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    path = store.path; store.close()
    conn, payload = _payload(path)
    payload["candidates"][1]["objective_value"]["value"]["value"] = "50"
    conn.execute("UPDATE records SET payload=? WHERE kind='grounded_decision_problem'", (json.dumps(payload),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "decision-problem:p1" in reopened.isolated
    assert not reopened.grounded_decision_problems
    from atlas.problem import build_grounded_decision_problem
    assert build_grounded_decision_problem(reopened, scope.id) == problem


def _add_cost_and_make_historical(store, scope, *, ident="fact:r2-cost-equivalent",
                                  version="1", scope_name="catalog", status="exact",
                                  value="2", include_snapshot=True):
    store.admit([{"kind": "property", "payload": {
        "id": ident, "description": "realization:r2", "property": "cost",
        "version": version, "value": {"kind": "integer", "value": value},
        "scope": scope_name, "epistemic_status": status,
        "provenance": ["source:m1-fixture"]}}])
    snapshot = store.open_snapshot(scope.snapshot)
    if include_snapshot and ident not in {record.value for record in snapshot.record_ids}:
        updated = replace(snapshot, record_ids=snapshot.record_ids + (KnowledgeId(ident),))
        store.snapshots[scope.snapshot.value] = updated
        raw = json.loads(store._db.execute(
            "SELECT payload FROM records WHERE kind='snapshot' AND id=?",
            (scope.snapshot.value,)).fetchone()[0])
        raw["record_ids"].append(ident)
        store._db.execute("UPDATE records SET payload=? WHERE kind='snapshot' AND id=?",
                          (json.dumps(raw), scope.snapshot.value))
        store._db.commit()


def test_m1c22_r2_01_and_02_exact_equivalent_supports_invalidate_both_ids(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    _add_cost_and_make_historical(store, scope)
    path = store.path
    store.close()

    reopened = open_store(path)
    assert "decision-problem:p1" in reopened.isolated
    assert not reopened.grounded_decision_problems
    assert ("snapshot", "snapshot:m1") not in reopened.isolated
    assert ("decision_scope", scope.id.value) not in reopened.isolated
    assert ("decision_grounding", scope.id.value) not in reopened.isolated

    conn, payload = _payload(path)
    payload["candidates"][1]["objective_value"]["knowledge_id"] = "fact:r2-cost-equivalent"
    conn.execute("UPDATE records SET payload=? WHERE kind='grounded_decision_problem'",
                 (json.dumps(payload),))
    conn.commit(); conn.close()
    forged = open_store(path)
    assert "decision-problem:p1" in forged.isolated
    assert not forged.grounded_decision_problems


def test_m1c22_r2_03_equivalent_support_outside_historical_snapshot_is_ignored(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    _add_cost_and_make_historical(store, scope, ident="fact:r2-cost-current",
                                  include_snapshot=False)
    path = store.path; store.close()
    reopened = open_store(path)
    assert reopened.decision_problem("decision-problem:p1") == problem


@pytest.mark.parametrize("kwargs", [
    {"ident": "fact:r2-cost-outside-context", "scope_name": "private"},
    {"ident": "fact:r2-cost-v2", "version": "2"},
    {"ident": "fact:r2-cost-estimate", "status": "estimate"},
])
def test_m1c22_r2_03_to_06_non_admissible_equivalents_do_not_invalidate(tmp_path, kwargs):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    if kwargs.get("version") == "2":
        store.configure_vocabulary({"properties": [{"id": "cost", "version": "2", "value": "integer"}]})
    _add_cost_and_make_historical(store, scope, **kwargs)
    path = store.path
    store.close()
    reopened = open_store(path)
    assert reopened.decision_problem("decision-problem:p1") == problem


def test_m1c22_r2_07_unique_support_does_not_repair_forged_identity(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    path = store.path; store.close()
    conn, payload = _payload(path)
    payload["candidates"][1]["objective_value"]["knowledge_id"] = "fact:r2-cost-equivalent"
    conn.execute("UPDATE records SET payload=? WHERE kind='grounded_decision_problem'",
                 (json.dumps(payload),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "decision-problem:p1" in reopened.isolated
    assert not reopened.grounded_decision_problems


def test_m1c22_r2_08_restore_with_all_semantic_builders_forbidden(tmp_path, monkeypatch):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    path = store.path; store.close()

    def forbidden(*args, **kwargs):
        raise AssertionError("restore must validate locally, not reconstruct")
    monkeypatch.setattr(Store, "ground", forbidden)
    monkeypatch.setattr(Store, "ground_decision_scope", forbidden)
    monkeypatch.setattr(Store, "ground_decision_problem", forbidden)
    import atlas.problem as problem_module
    monkeypatch.setattr(problem_module, "build_grounded_decision_problem", forbidden)
    reopened = open_store(path)
    assert reopened.decision_problem("decision-problem:p1") == problem


def test_m1c22_r3_01_objective_value_v2_cannot_redefine_global_v1(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    store.configure_vocabulary({"properties": [{"id": "cost", "version": "2", "value": "integer"}]})
    _add_cost_and_make_historical(store, scope, ident="fact:r2-cost-v2-audit", version="2")
    path = store.path; store.close()
    conn, payload = _payload(path)
    objective_value = payload["candidates"][1]["objective_value"]
    objective_value.update({"knowledge_id": "fact:r2-cost-v2-audit", "version": "2"})
    conn.execute("UPDATE records SET payload=? WHERE kind='grounded_decision_problem'",
                 (json.dumps(payload),))
    conn.commit(); conn.close()

    reopened = open_store(path)
    assert "decision-problem:p1" in reopened.isolated
    assert not reopened.grounded_decision_problems
    assert ("snapshot", "snapshot:m1") not in reopened.isolated
    assert ("decision_scope", "decision-scope:problem") not in reopened.isolated
    assert ("decision_grounding", "decision-scope:problem") not in reopened.isolated


def test_m1c22_r3_02_v2_support_does_not_affect_persisted_v1_payload(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    store.configure_vocabulary({"properties": [{"id": "cost", "version": "2", "value": "integer"}]})
    _add_cost_and_make_historical(store, scope, ident="fact:r2-cost-v2-audit", version="2")
    path = store.path; store.close()

    reopened = open_store(path)
    assert reopened.decision_problem("decision-problem:p1") == problem


def _payload(path):
    conn = sqlite3.connect(path)
    raw = conn.execute("SELECT payload FROM records WHERE kind='grounded_decision_problem'").fetchone()[0]
    return conn, json.loads(raw)


def test_m1c22_06_corrupt_problem_is_local(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    path = store.path
    store.close()
    conn, payload = _payload(path)
    payload["candidates"][0]["candidate"] = "realization:r2"
    conn.execute("UPDATE records SET payload=? WHERE kind='grounded_decision_problem'", (json.dumps(payload),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "decision-problem:p1" in reopened.isolated
    assert reopened.decision_scope(scope.id).id == scope.id
    assert reopened.decision_grounding(scope.id).status is GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE
    assert reopened.open_snapshot("snapshot:m1").id == SnapshotId("snapshot:m1")


def test_m1c22_07_prerequisite_corruption_closes_dependent_problem(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    path = store.path; store.close()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE records SET payload=? WHERE kind='property' AND id='fact:r2-cost'", ("{}",))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "fact:r2-cost" in reopened.isolated
    assert "decision-problem:p1" in reopened.isolated
    # The objective support and GDP are isolated; no healthy upstream object
    # is repaired or replaced from another cost assertion.


def test_m1c22_08_healthy_sibling_survives_and_16_nominal_ids_are_independent(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:z", problem)
    store.admit_grounded_decision_problem("decision-problem:a", problem)
    assert store.decision_problem("decision-problem:z") == store.decision_problem("decision-problem:a")
    with pytest.raises(AdmissionError):
        store.admit_grounded_decision_problem("decision-problem:z", problem)
    assert set(store.grounded_decision_problems) == {"decision-problem:a", "decision-problem:z"}


def test_m1c22_09_to_11_objective_support_is_semantically_exact(tmp_path):
    store, scope, problem = prepared(tmp_path)
    bad_participant = problem.candidates[1].objective_value
    forged = ObjectiveValue(bad_participant.value, KnowledgeId("fact:r1-cost"), bad_participant.property, bad_participant.version, bad_participant.epistemic_status)
    with pytest.raises((ValidationError, GroundingError)):
        store.admit_grounded_decision_problem("decision-problem:bad-participant", replace_candidate(problem, 1, objective_value=forged))
    forged_value = ObjectiveValue(Integer(99), bad_participant.knowledge_id, bad_participant.property, bad_participant.version, bad_participant.epistemic_status)
    with pytest.raises((ValidationError, GroundingError)):
        store.admit_grounded_decision_problem("decision-problem:bad-value", replace_candidate(problem, 1, objective_value=forged_value))
    forged_property = ObjectiveValue(bad_participant.value, bad_participant.knowledge_id, PropertyId("other-cost"), bad_participant.version, bad_participant.epistemic_status)
    with pytest.raises((ValidationError, GroundingError)):
        store.admit_grounded_decision_problem("decision-problem:bad-property", replace_candidate(problem, 1, objective_value=forged_property))
    forged_version = ObjectiveValue(bad_participant.value, bad_participant.knowledge_id, bad_participant.property, "2", bad_participant.epistemic_status)
    with pytest.raises((ValidationError, GroundingError)):
        store.admit_grounded_decision_problem("decision-problem:bad-version", replace_candidate(problem, 1, objective_value=forged_version))


def replace_candidate(problem, index, **changes):
    from dataclasses import replace
    candidates = list(problem.candidates)
    candidates[index] = replace(candidates[index], **changes)
    return replace(problem, candidates=tuple(candidates))


def test_m1c22_12_malformed_payload_fails_closed(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    path = store.path; store.close()
    conn, payload = _payload(path)
    payload["candidates"] = {"not": "a list"}
    conn.execute("UPDATE records SET payload=? WHERE kind='grounded_decision_problem'", (json.dumps(payload),))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert "decision-problem:p1" in reopened.isolated
    assert not reopened.grounded_decision_problems


def test_m1c22_13_duplicate_candidates_and_conflicting_duplicate_identity_fail_closed(tmp_path):
    store, scope, problem = prepared(tmp_path)
    with pytest.raises(ValidationError):
        duplicate = replace(problem, candidates=problem.candidates + (problem.candidates[0],))
    store.admit_grounded_decision_problem("decision-problem:p1", problem)
    with pytest.raises(AdmissionError):
        store.admit_grounded_decision_problem("decision-problem:p1", problem)


def test_m1c22_14_restore_order_is_not_semantic(tmp_path):
    store, scope, problem = prepared(tmp_path)
    store.admit_grounded_decision_problem("decision-problem:z", problem)
    store.admit_grounded_decision_problem("decision-problem:a", problem)
    path = store.path; store.close()
    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT id,payload FROM records WHERE kind='grounded_decision_problem' ORDER BY id").fetchall()
    conn.execute("DELETE FROM records WHERE kind='grounded_decision_problem'")
    for ident, payload in reversed(rows):
        conn.execute("INSERT INTO records(id,kind,payload) VALUES(?,?,?)", (ident, "grounded_decision_problem", payload))
    conn.commit(); conn.close()
    reopened = open_store(path)
    assert set(reopened.grounded_decision_problems) == {"decision-problem:a", "decision-problem:z"}


def test_m1c22_17_unknown_survives_restart_and_18_no_selection(tmp_path):
    data = fixture()
    data["facts"] = [x for x in data["facts"] if x["id"] != "fact:r2-capabilities"]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), data)
    scope = store.create_decision_scope("decision-scope:unknown", "snapshot:m1", "context:m1", "request:q1", manifest("realization:r2"))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    assert problem.candidates[0].truth is EvaluationTruth.UNKNOWN
    assert not hasattr(problem, "winner") and not hasattr(problem, "selected")
    store.admit_grounded_decision_problem("decision-problem:unknown", problem)
    path = store.path; store.close()
    reopened = open_store(path)
    restored = reopened.decision_problem("decision-problem:unknown")
    assert restored == problem and restored.candidates[0].truth is EvaluationTruth.UNKNOWN
