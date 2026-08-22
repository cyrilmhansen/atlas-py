import copy, json
from dataclasses import replace
from pathlib import Path

import pytest

from atlas import *


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def fixture():
    return json.loads(FIXTURE.read_text())


def make_store(tmp_path, data=None):
    return admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture() if data is None else data)


def manifest(*candidates):
    return GroundingManifest("m1-grounding/1", tuple(DescriptionId(x) for x in candidates), (RuleId("coverage:v1"),))


def declare(store, ident="decision-scope:ds1", m=None):
    return store.create_decision_scope(ident, "snapshot:m1", "context:m1", intention='intent:selection', request="request:q1", manifest=m or manifest("realization:r1", "realization:r2"))


def test_scope_is_nominal_finite_and_persistent(tmp_path):
    store = make_store(tmp_path)
    scope = declare(store)
    assert scope.id == DecisionScopeId("decision-scope:ds1")
    assert scope.request == DescriptionId("request:q1")
    assert scope.manifest.candidate_description_ids == (DescriptionId("realization:r1"), DescriptionId("realization:r2"))
    with pytest.raises((AttributeError, TypeError)):
        scope.manifest.candidate_description_ids += (DescriptionId("realization:r3"),)
    store.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert reopened.decision_scope(scope.id) == scope


def test_scope_admission_rejects_duplicates_missing_candidates_and_wrong_context(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises((ValidationError, AdmissionError)):
        declare(store, m=manifest("realization:r1", "realization:r1"))
    with pytest.raises((ValidationError, GroundingError)):
        declare(store, m=manifest("realization:r3"))
    with pytest.raises((ValidationError, GroundingError)):
        store.create_decision_scope("decision-scope:bad", "snapshot:m1", "context:missing", intention='intent:selection', request="request:q1", manifest=manifest("realization:r1"))
    assert store.decision_scopes == {}


def test_unknown_manifest_version_is_rejected_at_admission(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(ValidationError):
        declare(store, m=GroundingManifest("totally-unknown/999", (DescriptionId("realization:r1"),), (RuleId("coverage:v1"),)))
    assert store.decision_scopes == {}


def test_scope_traverses_exact_manifest_without_selection_or_cost(tmp_path):
    store = make_store(tmp_path)
    declare(store)
    result = store.evaluate_decision_scope("decision-scope:ds1")
    assert result.status is GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE
    assert set(store.encountered_candidates("decision-scope:ds1")) == {DescriptionId("realization:r1"), DescriptionId("realization:r2")}
    assert {x.candidate for x in result.observations} == set(result.observations[i].candidate for i in range(2))
    assert [x.truth for x in result.observations] == [EvaluationTruth.FALSE, EvaluationTruth.TRUE]
    assert not hasattr(result, "selected") and not hasattr(result, "winner")


def test_unknown_is_observed_and_does_not_break_completeness(tmp_path):
    data = fixture()
    data["facts"] = [x for x in data["facts"] if x["id"] != "fact:r2-capabilities"]
    store = make_store(tmp_path, data)
    declare(store)
    result = store.evaluate_decision_scope("decision-scope:ds1")
    by_id = {x.candidate.value: x for x in result.observations}
    assert by_id["realization:r1"].truth is EvaluationTruth.FALSE
    assert by_id["realization:r2"].truth is EvaluationTruth.UNKNOWN
    assert by_id["realization:r2"].grounding_result.missing_reads
    assert result.status is GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE


def test_context_exclusion_is_observable(tmp_path):
    data = fixture()
    data["contexts"][0]["visible_scopes"] = []
    store = make_store(tmp_path, data)
    declare(store, m=manifest("realization:r1"))
    result = store.evaluate_decision_scope("decision-scope:ds1")
    assert result.observations[0].traversed
    assert result.observations[0].exclusion_reason == "excluded_by_context"


def test_structural_failure_is_not_complete_and_is_not_published(tmp_path):
    store = make_store(tmp_path)
    declare(store, m=manifest("realization:r1"))
    scope = store.decision_scope("decision-scope:ds1")
    broken = copy.copy(store)
    broken.snapshots = dict(store.snapshots)
    broken.snapshots["snapshot:m1"] = replace(store.snapshots["snapshot:m1"], rule_definitions=())
    with pytest.raises(GroundingError):
        broken.ground_decision_scope(scope.id)


def test_restart_keeps_historical_scope_and_result_independent_of_new_descriptions(tmp_path):
    store = make_store(tmp_path)
    declare(store)
    store.evaluate_decision_scope("decision-scope:ds1")
    store.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert reopened.decision_scope("decision-scope:ds1").manifest == manifest("realization:r1", "realization:r2")
    assert reopened.decision_grounding("decision-scope:ds1").status is GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE
    assert reopened.decision_scope("decision-scope:ds1").snapshot == SnapshotId("snapshot:m1")


def test_multiple_scopes_have_independent_manifests(tmp_path):
    store = make_store(tmp_path)
    declare(store, "decision-scope:ds1", manifest("realization:r1", "realization:r2"))
    declare(store, "decision-scope:ds2", manifest("realization:r1"))
    store.evaluate_decision_scope("decision-scope:ds1")
    store.evaluate_decision_scope("decision-scope:ds2")
    assert len(store.decision_observations("decision-scope:ds1")) == 2
    assert len(store.decision_observations("decision-scope:ds2")) == 1


def test_incomplete_and_duplicate_or_extra_observations_are_rejected_on_restore(tmp_path):
    store = make_store(tmp_path)
    declare(store)
    store.evaluate_decision_scope("decision-scope:ds1")
    store.close()
    import sqlite3
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    row = db.execute("SELECT payload FROM records WHERE kind='decision_grounding'").fetchone()
    payload = json.loads(row[0]); payload["observations"] = payload["observations"][:1]
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding'", (json.dumps(payload),)); db.commit(); db.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert ("decision_grounding", "decision-scope:ds1") in reopened.isolated
    assert "decision-scope:ds1" not in reopened.decision_groundings


@pytest.mark.parametrize("mutation", [
    "not_traversed", "interrupted", "pruned", "dependency", "rule_version",
    "snapshot", "context", "binding", "truth",
])
def test_complete_grounding_counterexamples_are_isolated_on_restore(tmp_path, mutation):
    store = make_store(tmp_path)
    declare(store)
    store.evaluate_decision_scope("decision-scope:ds1")
    store.close()
    import sqlite3
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    row = db.execute("SELECT payload FROM records WHERE kind='decision_grounding'").fetchone()
    payload = json.loads(row[0])
    if mutation == "not_traversed":
        payload["observations"][0]["traversed"] = False
    elif mutation == "interrupted":
        payload["interrupted"] = True
    elif mutation == "pruned":
        payload["pruned"] = True
    elif mutation == "dependency":
        payload["observations"][0]["grounding_result"]["effective_dependencies"].append("fact:not-in-store")
    elif mutation == "rule_version":
        payload["observations"][0]["grounding_result"]["rule_version"] = "999"
    elif mutation == "snapshot":
        payload["observations"][0]["grounding_result"]["snapshot"] = "snapshot:other"
    elif mutation == "context":
        payload["observations"][0]["grounding_result"]["context"] = "context:other"
    elif mutation == "binding":
        payload["observations"][0]["grounding_result"]["bindings"][0]["description"] = "realization:r2"
    else:
        payload["observations"][0]["grounding_result"]["truth"] = "UNKNOWN"
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding'", (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert ("decision_grounding", "decision-scope:ds1") in reopened.isolated
    assert "decision-scope:ds1" not in reopened.decision_groundings


def test_successful_result_with_structural_error_is_rejected_at_construction(tmp_path):
    store = make_store(tmp_path)
    declare(store, m=manifest("realization:r1"))
    result = store.ground("coverage:v1", {"candidate": DescriptionId("realization:r1"), "request": DescriptionId("request:q1")}, "snapshot:m1", "context:m1")
    with pytest.raises(ValidationError):
        GroundingObservation(DescriptionId("realization:r1"), True, result.truth, result, structural_error="forged")


def test_corrupted_manifest_isolates_scope_and_orphaned_run(tmp_path):
    store = make_store(tmp_path)
    declare(store)
    store.evaluate_decision_scope("decision-scope:ds1")
    store.close()
    import sqlite3
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    row = db.execute("SELECT payload FROM records WHERE kind='decision_scope'").fetchone()
    payload = json.loads(row[0]); payload["manifest"]["manifest_version"] = "totally-unknown/999"
    db.execute("UPDATE records SET payload=? WHERE kind='decision_scope'", (json.dumps(payload),)); db.commit(); db.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert ("decision_scope", "decision-scope:ds1") in reopened.isolated
    assert "decision-scope:ds1" not in reopened.decision_scopes
    assert ("decision_grounding", "decision-scope:ds1") in reopened.isolated
