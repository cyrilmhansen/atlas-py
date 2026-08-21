"""Narrow adversarial checks for the M1e.1 contract."""

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
import pytest
from atlas import *

FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def store_with_decision(tmp_path):
    data = json.loads(FIXTURE.read_text())
    for f in data["facts"]:
        if f["id"] == "fact:r1-capabilities": f["value"]["items"] = ["a", "b"]
        if f["id"] == "fact:r1-cost": f["value"]["value"] = "100"
        if f["id"] == "fact:r2-cost": f["value"]["value"] = "50"
    s = admit_fixture(open_store(tmp_path / "atlas.sqlite"), data)
    m = GroundingManifest("m1-grounding/1", (DescriptionId("realization:r1"), DescriptionId("realization:r2")), (RuleId("coverage:v1"),))
    scope = s.create_decision_scope("scope", "snapshot:m1", "context:m1", "request:q1", m)
    s.evaluate_decision_scope(scope.id); p = s.ground_decision_problem(scope.id)
    s.admit_grounded_decision_problem("problem", p); s.admit_m1_decision("decision", s.select_m1("problem"))
    return s


def add_property(s, ident, description, property_id="unused-property", value=None):
    s.admit([{"kind": "property", "payload": {"id": ident, "description": description,
        "property": property_id, "version": "1", "value": value or {"kind": "symbol", "value": ident},
        "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])


def revised(s, old, new):
    s.snapshot("s2", parent="snapshot:m1"); return s.supersede(old, new, "s2")


def test_reference_is_explicit_and_query_does_not_write(tmp_path):
    s = store_with_decision(tmp_path)
    with pytest.raises(ValidationError): s.status_of("decision", relative_to=None)
    before = s._db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    assert s.status_of("decision", relative_to="snapshot:m1") is ArtifactStatus.CURRENT
    after = s._db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    assert before == after


def test_self_unknown_and_incompatible_replacements_rejected(tmp_path):
    s = store_with_decision(tmp_path)
    with pytest.raises(ValidationError): s.supersede("fact:r2-cost", "fact:r2-cost", "snapshot:m1")
    with pytest.raises(ValidationError): s.supersede("missing", "fact:r2-cost", "snapshot:m1")
    add_property(s, "new-symbol", "realization:r2")
    s.snapshot("bad", parent="snapshot:m1")
    with pytest.raises(ValidationError): s.supersede("fact:r2-cost", "new-symbol", "bad")


def test_relevant_direct_and_irrelevant_dependencies(tmp_path):
    s = store_with_decision(tmp_path)
    add_property(s, "unused-v2", "realization:r1")
    add_property(s, "cost-v2", "realization:r2", "cost", {"kind": "integer", "value": "70"})
    s.snapshot("s2", parent="snapshot:m1")
    s.supersede("fact:r1-unused", "unused-v2", "s2")
    assert s.status_of("decision", relative_to="s2") is ArtifactStatus.CURRENT
    s.supersede("fact:r2-cost", "cost-v2", "s2")
    assert s.status_of("decision", relative_to="s2") is ArtifactStatus.STALE


def test_restart_exact_supersession_and_conflict_cycle_fail_closed(tmp_path):
    s = store_with_decision(tmp_path)
    add_property(s, "r2-cost-v2", "realization:r2", "cost", {"kind": "integer", "value": "70"})
    revised(s, "fact:r2-cost", "r2-cost-v2")
    s.close(); s = open_store(tmp_path / "atlas.sqlite")
    assert s.supersessions["fact:r2-cost"].new == KnowledgeId("r2-cost-v2")
    with pytest.raises(AdmissionError): s.supersede("fact:r2-cost", "r2-cost-v2", "s2")


def test_order_independence_and_corruption_are_not_stale(tmp_path):
    s = store_with_decision(tmp_path)
    add_property(s, "r2-cost-v2", "realization:r2", "cost", {"kind": "integer", "value": "70"})
    revised(s, "fact:r2-cost", "r2-cost-v2")
    rows = list(s._db.execute("SELECT id,payload FROM records WHERE kind='supersession'"))
    assert len(rows) == 1
    s.close()
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    db.execute("DELETE FROM records WHERE kind='property' AND id='fact:r2-cost'")
    db.commit(); db.close()
    restored = open_store(tmp_path / "atlas.sqlite")
    assert restored.status_of("decision", relative_to="s2") is ArtifactStatus.INVALID


def test_active_missing_gdp_is_invalid_without_restart(tmp_path):
    s = store_with_decision(tmp_path)
    s.grounded_decision_problems.pop("problem")
    assert s.status_of("decision", relative_to="snapshot:m1") is ArtifactStatus.INVALID


def test_active_missing_grounding_is_invalid_without_restart(tmp_path):
    s = store_with_decision(tmp_path)
    s.decision_groundings.pop("scope")
    assert s.status_of("decision", relative_to="snapshot:m1") is ArtifactStatus.INVALID


def test_active_missing_scope_is_invalid_without_restart(tmp_path):
    s = store_with_decision(tmp_path)
    s.decision_scopes.pop("scope")
    assert s.status_of("decision", relative_to="snapshot:m1") is ArtifactStatus.INVALID


def test_active_falsified_observation_is_invalid_without_restart(tmp_path):
    s = store_with_decision(tmp_path)
    grounding = s.decision_groundings["scope"]
    first, second = grounding.observations
    s.decision_groundings["scope"] = replace(
        grounding, observations=(replace(first, exclusion_reason="falsified"), second))
    assert s.status_of("decision", relative_to="snapshot:m1") is ArtifactStatus.INVALID


def test_active_missing_historical_dependency_is_invalid_without_restart(tmp_path):
    s = store_with_decision(tmp_path)
    s.records.pop("fact:r2-capabilities")
    assert s.status_of("decision", relative_to="snapshot:m1") is ArtifactStatus.INVALID


def test_prospective_cycle_is_rejected_atomically_and_survives_restart(tmp_path):
    s = store_with_decision(tmp_path)
    add_property(s, "r2-cost-b", "realization:r2", "cost", {"kind": "integer", "value": "60"})
    s.snapshot("s2", parent="snapshot:m1")
    s.supersede("fact:r2-cost", "r2-cost-b", "s2")
    rows_before = s._db.execute("SELECT COUNT(*) FROM records WHERE kind='supersession'").fetchone()[0]
    with pytest.raises((AdmissionError, ValidationError)):
        s.supersede("r2-cost-b", "fact:r2-cost", "s2")
    assert s._db.execute("SELECT COUNT(*) FROM records WHERE kind='supersession'").fetchone()[0] == rows_before
    assert list(s.supersessions) == ["fact:r2-cost"]
    s.close()
    restored = open_store(tmp_path / "atlas.sqlite")
    assert list(restored.supersessions) == ["fact:r2-cost"]
    assert restored.status_of("decision", relative_to="s2") is ArtifactStatus.STALE


def test_property_slot_corruption_isolated_on_reload(tmp_path):
    s = store_with_decision(tmp_path)
    add_property(s, "r2-cost-v2", "realization:r2", "cost", {"kind": "integer", "value": "70"})
    revised(s, "fact:r2-cost", "r2-cost-v2")
    row = s._db.execute("SELECT payload FROM records WHERE kind='property' AND id='r2-cost-v2'").fetchone()
    payload = json.loads(row[0]); payload["description"] = "realization:r1"
    s._db.execute("UPDATE records SET payload=? WHERE kind='property' AND id='r2-cost-v2'", (json.dumps(payload),))
    s._db.commit(); s.close()
    restored = open_store(tmp_path / "atlas.sqlite")
    assert ("supersession", "supersession:fact:r2-cost") in restored.isolated


def test_relation_polarity_is_a_slot_in_admission_and_reload(tmp_path):
    s = store_with_decision(tmp_path)
    relation = next(r for r in s.records.values() if isinstance(r, RelationAssertion))
    replacement = dict(id="relation-replacement", predicate=relation.predicate.value,
                       version=relation.version, participants=[x.value for x in relation.participants],
                       polarity="negative" if relation.polarity == "positive" else "positive",
                       scope=relation.scope, epistemic_status=relation.epistemic_status,
                       provenance=[x.value for x in relation.provenance])
    s.admit([{"kind": "relation", "payload": replacement}])
    s.snapshot("relation-bad", parent="snapshot:m1")
    with pytest.raises(ValidationError):
        s.supersede(relation.id.value, "relation-replacement", "relation-bad")
    s._persist("supersession", "supersession:relation-fake", {
        "schema": "atlas.core-v1.supersession/1", "id": "supersession:relation-fake",
        "old": relation.id.value, "new": "relation-replacement", "snapshot": "relation-bad"})
    s._db.commit(); s.close()
    restored = open_store(tmp_path / "atlas.sqlite")
    assert ("supersession", "supersession:relation-fake") in restored.isolated


@pytest.mark.parametrize("payload_change", [
    lambda payload: payload.pop("schema"),
    lambda payload: payload.__setitem__("schema", "atlas.core-v1.supersession/999"),
])
def test_supersession_schema_is_closed_on_reload(tmp_path, payload_change):
    s = store_with_decision(tmp_path)
    add_property(s, "r2-cost-v2", "realization:r2", "cost", {"kind": "integer", "value": "70"})
    revised(s, "fact:r2-cost", "r2-cost-v2")
    row = s._db.execute("SELECT payload FROM records WHERE kind='supersession'").fetchone()
    payload = json.loads(row[0]); payload_change(payload)
    s._db.execute("UPDATE records SET payload=? WHERE kind='supersession'", (json.dumps(payload),))
    s._db.commit(); s.close()
    restored = open_store(tmp_path / "atlas.sqlite")
    assert ("supersession", "supersession:fact:r2-cost") in restored.isolated
