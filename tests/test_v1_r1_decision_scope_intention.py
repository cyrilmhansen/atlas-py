import json
import sqlite3

import pytest

from atlas import (DescriptionId, GroundingManifest, RuleId, ValidationError,
                   GroundingError, admit_fixture, open_store)


FIXTURE = "conformance/fixtures/m1-coverage.json"


def _manifest():
    return GroundingManifest("m1-grounding/1",
                             (DescriptionId("realization:r1"),),
                             (RuleId("coverage:v1"),))


def _store(tmp_path):
    import pathlib
    return admit_fixture(open_store(tmp_path / "scope.sqlite"),
                         json.loads(pathlib.Path(FIXTURE).read_text()))


def _store_with_intention_a(tmp_path):
    import pathlib
    fixture = pathlib.Path(FIXTURE).read_text().replace(
        "intent:selection", "intent:A")
    return admit_fixture(open_store(tmp_path / "scope.sqlite"),
                         json.loads(fixture))


def _store_with_candidate_realizing_b(tmp_path):
    import pathlib
    fixture = json.loads(pathlib.Path(FIXTURE).read_text())
    fixture["descriptions"].append({"id": "intent:B", "label": "other intention"})
    for relation in fixture["relations"]:
        if relation["id"] == "rel:r1-realizes":
            relation["participants"] = ["realization:r1", "intent:B"]
    return admit_fixture(open_store(tmp_path / "scope.sqlite"), fixture)


def _scope(store, ident="decision-scope:r1", **kwargs):
    return store.create_decision_scope(
        ident, "snapshot:m1", "context:m1",
        intention=kwargs.get("intention", "intent:selection"),
        request=kwargs.get("request", "request:q1"), manifest=_manifest())


def _payload_row(path):
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='decision_scope'").fetchone()
    db.close()
    return json.loads(row[0])


def test_current_scope_is_closed_and_reopens_with_explicit_intention(tmp_path):
    store = _store(tmp_path)
    scope = _scope(store)
    assert scope.intention == DescriptionId("intent:selection")
    assert _payload_row(store.path).keys() == {
        "schema", "id", "snapshot", "context", "intention", "request", "manifest"}
    store.close()
    reopened = open_store(tmp_path / "scope.sqlite")
    assert reopened.decision_scope(scope.id).schema == "atlas.core-v1.decision-scope/2"
    assert reopened.decision_scope(scope.id).intention == scope.intention


def test_true_legacy_scope_with_synthetic_intention_absent_is_isolated(tmp_path):
    store = _store_with_intention_a(tmp_path)
    scope = _scope(store, intention="intent:A")
    path = store.path
    payload = _payload_row(path)
    assert scope.schema == "atlas.core-v1.decision-scope/2"
    assert scope.intention == DescriptionId("intent:A")
    assert DescriptionId("intent:A") in store.open_snapshot("snapshot:m1").description_ids
    assert DescriptionId("intent:selection") not in store.open_snapshot("snapshot:m1").description_ids
    payload.pop("schema")
    payload.pop("intention")
    assert set(payload) == {"id", "snapshot", "context", "request", "manifest"}
    db = sqlite3.connect(path)
    db.execute("UPDATE records SET payload=? WHERE kind='decision_scope'",
               (json.dumps(payload),))
    db.commit(); db.close(); store.close()
    reopened = open_store(path)
    assert ("decision_scope", scope.id.value) in reopened.isolated
    assert scope.id.value not in reopened.decision_scopes
    assert reopened.isolated[("decision_scope", scope.id.value)]["reason"] == (
        "decision scope intention is absent from snapshot")


def test_current_scope_with_legacy_schema_isolated_without_hybrid_downgrade(tmp_path):
    store = _store(tmp_path)
    scope = _scope(store, intention="intent:selection")
    store.evaluate_decision_scope(scope.id)
    path = store.path
    payload = _payload_row(path)
    assert set(payload) == {"schema", "id", "snapshot", "context", "intention", "request", "manifest"}
    payload["schema"] = "atlas.core-v1.decision-scope/1"
    db = sqlite3.connect(path)
    db.execute("UPDATE records SET payload=? WHERE kind='decision_scope'", (json.dumps(payload),))
    db.commit(); db.close(); store.close()

    reopened = open_store(path)
    assert ("decision_scope", scope.id.value) in reopened.isolated
    assert scope.id.value not in reopened.decision_scopes
    assert ("decision_grounding", scope.id.value) in reopened.isolated
    assert reopened.decision_groundings == {}


@pytest.mark.parametrize("mutation", [
    lambda p: p.pop("intention"),
    lambda p: p.pop("schema"),
    lambda p: p.__setitem__("schema", "atlas.core-v1.decision-scope/999"),
    lambda p: p.__setitem__("schema", "atlas.core-v1.decision-scope/1"),
    lambda p: p.__setitem__("extra", True),
    lambda p: p.__setitem__("intention", 42),
])
def test_current_scope_format_mutations_are_isolated(tmp_path, mutation):
    store = _store(tmp_path); path = store.path
    _scope(store); payload = _payload_row(path); mutation(payload)
    db = sqlite3.connect(path)
    db.execute("UPDATE records SET payload=? WHERE kind='decision_scope'",
               (json.dumps(payload),)); db.commit(); db.close(); store.close()
    reopened = open_store(path)
    assert ("decision_scope", "decision-scope:r1") in reopened.isolated
    assert "decision-scope:r1" not in reopened.decision_scopes


def test_current_scope_requires_distinct_intention_and_request(tmp_path):
    store = _store(tmp_path)
    with pytest.raises((ValidationError, GroundingError)):
        _scope(store, intention="request:q1", request="request:q1")
    with pytest.raises((ValidationError, GroundingError)):
        _scope(store, intention="missing:intention")


def test_current_api_requires_intention_without_historical_fallback(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(TypeError):
        store.create_decision_scope("decision-scope:missing", "snapshot:m1",
                                    "context:m1", request="request:q1",
                                    manifest=_manifest())


@pytest.mark.parametrize("scope_legacy, grounding_legacy, valid", [
    (True, True, True),
    (True, False, True),
    (False, False, True),
    (False, True, False),
])
def test_scope_grounding_compatibility_matrix(tmp_path, scope_legacy, grounding_legacy, valid):
    store = _store(tmp_path)
    scope = _scope(store, ident="decision-scope:matrix")
    store.evaluate_decision_scope(scope.id)
    path = store.path
    store.close()
    db = sqlite3.connect(path)
    scope_payload_row = db.execute(
        "SELECT payload FROM records WHERE kind='decision_scope' AND id=?", (scope.id.value,)
    ).fetchone()
    scope_data = json.loads(scope_payload_row[0])
    if scope_legacy:
        scope_data.pop("schema")
        scope_data.pop("intention")
    grounding_row = db.execute(
        "SELECT payload FROM records WHERE kind='decision_grounding' AND id=?", (scope.id.value,)
    ).fetchone()
    grounding_data = json.loads(grounding_row[0])
    if grounding_legacy:
        grounding_data.pop("schema")
        for observation in grounding_data["observations"]:
            observation.pop("discovery_evidence")
    db.execute("UPDATE records SET payload=? WHERE kind='decision_scope' AND id=?",
               (json.dumps(scope_data), scope.id.value))
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding' AND id=?",
               (json.dumps(grounding_data), scope.id.value))
    db.commit(); db.close()
    reopened = open_store(path)
    if valid:
        assert reopened.decision_scope(scope.id).schema.endswith("/1" if scope_legacy else "/2")
        assert reopened.decision_grounding(scope.id).schema.endswith("/1" if grounding_legacy else "/2")
    else:
        assert ("decision_scope", scope.id.value) not in reopened.isolated
        assert ("decision_grounding", scope.id.value) in reopened.isolated
        assert reopened.decision_groundings == {}


def test_current_scope_survives_semantic_legacy_grounding_but_chain_is_unusable(tmp_path):
    store = _store_with_candidate_realizing_b(tmp_path)
    scope = _scope(store, ident="decision-scope:semantic", intention="intent:selection")
    grounding = store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    assert grounding.schema.endswith("/2")
    assert problem.scope_id == scope.id
    observation = grounding.observations[0]
    assert observation.candidate == DescriptionId("realization:r1")
    assert observation.exclusion_reason == "excluded_by_context"
    assert observation.discovery_evidence.found == ()
    assert observation.discovery_evidence.included == ()
    assert any(relation.id.value == "rel:r1-realizes" and
               relation.participants == (DescriptionId("realization:r1"), DescriptionId("intent:B"))
               for relation in store.find(kind="relation"))

    path = store.path
    store.close()
    db = sqlite3.connect(path)
    row = db.execute(
        "SELECT payload FROM records WHERE kind='decision_grounding' AND id=?",
        (scope.id.value,)).fetchone()
    grounding_data = json.loads(row[0])
    grounding_data.pop("schema")
    for observation in grounding_data["observations"]:
        observation.pop("discovery_evidence")
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding' AND id=?",
               (json.dumps(grounding_data), scope.id.value))
    db.commit(); db.close()

    reopened = open_store(path)
    assert reopened.decision_scope(scope.id).schema.endswith("/2")
    assert ("decision_grounding", scope.id.value) in reopened.isolated
    assert scope.id.value not in reopened.decision_groundings
    assert reopened.grounded_decision_problems == {}
    assert reopened.decisions == {}
    with pytest.raises(GroundingError):
        reopened.ground_decision_problem(scope.id)
    with pytest.raises(GroundingError):
        reopened.select_m1("decision-problem:semantic")
