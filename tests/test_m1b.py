import copy
import dataclasses
import json
import sqlite3
from pathlib import Path

import pytest

from atlas import *


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def make_fixture():
    return json.loads(FIXTURE.read_text())


def make_store(tmp_path, fixture=None):
    return admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture or make_fixture())


def ground(store, candidate="realization:r1", request="request:q1", **bindings):
    values = {"candidate": DescriptionId(candidate), "request": DescriptionId(request)}
    values.update(bindings)
    return store.ground("coverage:v1", values, "snapshot:m1", "context:m1")


def test_canonical_r1_is_false_without_negative_conclusion(tmp_path):
    result = ground(make_store(tmp_path))
    assert result.truth is EvaluationTruth.FALSE
    assert result.conclusion is None
    assert result.effective_dependencies == tuple(KnowledgeId(x) for x in (
        "fact:q1-search", "fact:q1-output", "fact:r1-capabilities"))


def test_grounding_result_enforces_nominal_conclusion_and_truth_coherence(tmp_path):
    store = make_store(tmp_path)
    false_result = ground(store)
    true_result = ground(store, candidate="realization:r2")

    with pytest.raises(ValidationError):
        dataclasses.replace(true_result, conclusion=True)
    with pytest.raises(ValidationError):
        dataclasses.replace(true_result, conclusion=RelationAssertion)
    with pytest.raises(ValidationError):
        dataclasses.replace(false_result, conclusion=true_result.conclusion)
    with pytest.raises(ValidationError):
        dataclasses.replace(false_result, truth=EvaluationTruth.UNKNOWN, conclusion=true_result.conclusion)
    with pytest.raises(ValidationError):
        dataclasses.replace(true_result, conclusion=None)

    assert dataclasses.replace(true_result) == true_result
    assert dataclasses.replace(false_result) == false_result


def test_canonical_r2_is_true_with_ordered_grounded_positive_term(tmp_path):
    result = ground(make_store(tmp_path), candidate="realization:r2")
    assert result.truth is EvaluationTruth.TRUE
    assert result.conclusion is not None
    assert result.conclusion.term == RelationTerm(
        PredicateId("covers"), "1", (DescriptionId("realization:r2"), DescriptionId("request:q1")))
    assert result.conclusion.polarity == "positive"
    assert not isinstance(result.conclusion, RelationAssertion)
    assert result.conclusion.epistemic_status == "exact"
    assert result.conclusion.rule_id == RuleId("coverage:v1")
    assert result.conclusion.dependencies == result.effective_dependencies
    assert KnowledgeId("fact:r1-unused") not in result.effective_dependencies


def test_bindings_are_exact_and_rule_head_order_wins(tmp_path):
    store = make_store(tmp_path)
    result = ground(store, request="request:q1", candidate="realization:r2")
    assert result.conclusion.term.participants == (DescriptionId("realization:r2"), DescriptionId("request:q1"))
    with pytest.raises(GroundingError): ground(store, extra=DescriptionId("request:q1"))
    with pytest.raises(GroundingError):
        store.ground("coverage:v1", {"candidate": DescriptionId("realization:r1")}, "snapshot:m1", "context:m1")
    with pytest.raises(ValidationError):
        store.ground("coverage:v1", {"candidate": "realization:r1", "request": DescriptionId("request:q1")}, "snapshot:m1", "context:m1")
    with pytest.raises(ValidationError):
        store.ground("coverage:v1", {"candidate": PropertyId("realization:r1"), "request": DescriptionId("request:q1")}, "snapshot:m1", "context:m1")


def test_missing_property_is_unknown_and_structured(tmp_path):
    fixture = make_fixture()
    fixture["facts"] = [x for x in fixture["facts"] if x["id"] != "fact:r1-capabilities"]
    result = ground(make_store(tmp_path, fixture))
    assert result.truth is EvaluationTruth.UNKNOWN and result.conclusion is None
    assert len(result.missing_reads) == 1
    missing = result.missing_reads[0]
    assert (missing.participant, missing.description, missing.property, missing.version) == (
        "candidate", DescriptionId("realization:r1"), PropertyId("available-capabilities"), "1")
    assert KnowledgeId("fact:r1-unused") not in result.effective_dependencies


@pytest.mark.parametrize("mutate_rule", [
    lambda rule: rule["when"]["left"].update(
        left={"op": "property", "participant": "candidate", "property": "unused-property"}),
    lambda rule: rule["when"]["left"].update(
        right={"op": "property", "participant": "request", "property": "sequence-property"}),
    lambda rule: rule["when"].update(
        left={"op": "property", "participant": "candidate", "property": "cost"}),
    lambda rule: rule["when"].update(
        right={"op": "property", "participant": "candidate", "property": "unused-property"}),
])
def test_known_rule_type_errors_are_rejected_without_reading_facts(tmp_path, mutate_rule):
    fixture = make_fixture()
    fixture["vocabulary"]["properties"].append(
        {"id": "sequence-property", "version": "1", "value": "sequence<symbol>"})
    mutate_rule(fixture["rules"][0])
    with pytest.raises(ValidationError):
        make_store(tmp_path, fixture)


def test_valid_rule_without_facts_is_unknown_but_still_admitted(tmp_path):
    fixture = make_fixture()
    fixture["facts"] = []
    store = make_store(tmp_path, fixture)
    result = ground(store)
    assert result.truth is EvaluationTruth.UNKNOWN
    assert result.conclusion is None


def test_wrong_participant_does_not_fallback(tmp_path):
    fixture = make_fixture()
    fixture["facts"] = [x for x in fixture["facts"] if x["id"] != "fact:r1-capabilities"]
    fixture["facts"].append({
        "id": "fact:q1-capabilities", "kind": "property", "description": "request:q1",
        "property": "available-capabilities", "value": {"kind": "finite_set<symbol>", "items": ["a", "b"]},
        "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]})
    result = ground(make_store(tmp_path, fixture))
    assert result.truth is EvaluationTruth.UNKNOWN
    assert result.missing_reads[0].participant == "candidate"


def test_ambiguous_property_is_unknown_and_exposes_all_ids(tmp_path):
    fixture = make_fixture()
    duplicate = copy.deepcopy(next(x for x in fixture["facts"] if x["id"] == "fact:r2-capabilities"))
    duplicate["id"] = "fact:r2-capabilities-duplicate"
    fixture["facts"].append(duplicate)
    result = ground(make_store(tmp_path, fixture), candidate="realization:r2")
    assert result.truth is EvaluationTruth.UNKNOWN and result.conclusion is None
    ambiguous = next(x for x in result.ambiguous_reads if x.participant == "candidate")
    assert ambiguous.knowledge_ids == (KnowledgeId("fact:r2-capabilities"), KnowledgeId("fact:r2-capabilities-duplicate"))
    assert set(ambiguous.knowledge_ids) <= set(result.effective_dependencies)


@pytest.mark.parametrize("status", ["bound", "estimate", "unknown"])
def test_non_exact_property_status_is_explicitly_unsupported(tmp_path, status):
    fixture = make_fixture()
    next(fact for fact in fixture["facts"] if fact["id"] == "fact:r2-capabilities")["epistemic_status"] = status
    store = make_store(tmp_path, fixture)
    before = tuple(store.records)
    with pytest.raises(GroundingError, match="epistemic status"):
        ground(store, candidate="realization:r2")
    assert tuple(store.records) == before


def test_ambiguous_statuses_do_not_create_an_epistemic_preference(tmp_path):
    fixture = make_fixture()
    duplicate = copy.deepcopy(next(x for x in fixture["facts"] if x["id"] == "fact:r2-capabilities"))
    duplicate["id"] = "fact:r2-capabilities-bound"
    duplicate["epistemic_status"] = "bound"
    fixture["facts"].append(duplicate)
    result = ground(make_store(tmp_path, fixture), candidate="realization:r2")
    assert result.truth is EvaluationTruth.UNKNOWN
    assert result.conclusion is None


def test_future_operator_is_explicitly_unsupported(tmp_path):
    fixture = make_fixture()
    future = copy.deepcopy(fixture["rules"][0])
    future["id"] = "future:v1"
    future["when"] = {"op": "future_op"}
    fixture["rules"].append(future)
    fixture["contexts"][0]["enabled_rules"].append("future:v1")
    store = make_store(tmp_path, fixture)
    with pytest.raises(UnsupportedRuleError):
        store.ground("future:v1", {"candidate": DescriptionId("realization:r1"), "request": DescriptionId("request:q1")}, "snapshot:m1", "context:m1")


def test_restart_and_snapshot_bound_records_are_reproducible(tmp_path):
    path = tmp_path / "atlas.sqlite"
    store = admit_fixture(open_store(path), make_fixture())
    before = store.ground("coverage:v1", {"candidate": DescriptionId("realization:r2"), "request": DescriptionId("request:q1")}, "snapshot:m1", "context:m1")
    store.close()
    reopened = open_store(path)
    after = reopened.ground("coverage:v1", {"request": DescriptionId("request:q1"), "candidate": DescriptionId("realization:r2")}, "snapshot:m1", "context:m1")
    assert after.truth is before.truth
    assert after.effective_dependencies == before.effective_dependencies
    assert after.conclusion.term == before.conclusion.term


def test_current_records_outside_requested_snapshot_are_not_read(tmp_path):
    store = make_store(tmp_path)
    fact = copy.deepcopy(make_fixture()["facts"][2])
    fact["id"] = "fact:r1-capabilities-new"
    fact["version"] = "1"
    fact["value"] = {"kind": "finite_set<symbol>", "items": ["a", "b"]}
    store.admit([{"kind": "property", "payload": fact}])
    result = ground(store)
    assert result.truth is EvaluationTruth.FALSE


def _add_capabilities_v2(store):
    store.configure_vocabulary({"properties": [
        {"id": "available-capabilities", "version": "2", "value": "finite_set<symbol>"},
    ]})


def test_h1_historical_rule_keeps_exact_property_version_after_vocabulary_extension(tmp_path):
    path = tmp_path / "atlas.sqlite"
    store = make_store(tmp_path)
    payload = json.loads(store._db.execute(
        "SELECT payload FROM records WHERE kind='rule' AND id='coverage:v1'"
    ).fetchone()[0])
    assert payload["payload"]["when"]["left"]["left"]["version"] == "1"
    _add_capabilities_v2(store)
    before = ground(store)
    store.close()
    reopened = open_store(path)
    after = ground(reopened)
    assert before.truth is after.truth is EvaluationTruth.FALSE
    assert after.effective_dependencies == before.effective_dependencies
    assert reopened.open_snapshot("snapshot:m1").description_ids == tuple(
        DescriptionId(x) for x in sorted(make_fixture()["descriptions"][i]["id"] for i in range(len(make_fixture()["descriptions"])))
    )


def test_h2_unversioned_rule_is_rejected_when_property_versions_are_ambiguous(tmp_path):
    store = make_store(tmp_path)
    _add_capabilities_v2(store)
    rule = copy.deepcopy(make_fixture()["rules"][0])
    rule["id"] = "coverage:new"
    with pytest.raises((ValidationError, AdmissionError)):
        store.admit([{"kind": "rule", "payload": {
            "id": rule["id"], "version": rule["version"], "payload": rule
        }}])
    explicit = copy.deepcopy(rule)
    def version(expr):
        if expr["op"] == "property":
            expr["version"] = "2" if expr["property"] == "available-capabilities" else "1"
        else:
            version(expr["left"]); version(expr["right"])
    version(explicit["when"])
    explicit["id"] = "coverage:v2"
    store.admit([{"kind": "rule", "payload": {
        "id": explicit["id"], "version": explicit["version"], "payload": explicit
    }}])
    row = store._db.execute("SELECT payload FROM records WHERE kind='rule' AND id='coverage:v2'").fetchone()
    assert '"version":"2"' in row[0]
    store.close()
    reopened = open_store(store.path)
    assert reopened.rules["coverage:v2"].payload["when"]["right"]["version"] == "2"


def test_h3_description_added_after_snapshot_is_structural_error_until_new_snapshot(tmp_path):
    store = make_store(tmp_path)
    store.admit([{"kind": "description", "payload": {"id": "realization:new", "label": "future"}}])
    with pytest.raises(GroundingError):
        ground(store, candidate="realization:new")
    store.snapshot("snapshot:m2")
    result = store.ground("coverage:v1", {
        "candidate": DescriptionId("realization:new"), "request": DescriptionId("request:q1")
    }, "snapshot:m2", "context:m1")
    assert result.truth is EvaluationTruth.UNKNOWN


def test_h4_description_without_fact_is_historically_valid_binding(tmp_path):
    store = make_store(tmp_path)
    store.admit([{"kind": "description", "payload": {"id": "realization:empty", "label": "empty"}}])
    store.snapshot("snapshot:m2")
    result = store.ground("coverage:v1", {
        "candidate": DescriptionId("realization:empty"), "request": DescriptionId("request:q1")
    }, "snapshot:m2", "context:m1")
    assert result.truth is EvaluationTruth.UNKNOWN
    assert result.missing_reads[0].description == DescriptionId("realization:empty")


def test_h5_historical_description_behaviour_survives_restart(tmp_path):
    path = tmp_path / "atlas.sqlite"
    store = make_store(tmp_path)
    store.admit([{"kind": "description", "payload": {"id": "realization:new", "label": "future"}}])
    with pytest.raises(GroundingError):
        ground(store, candidate="realization:new")
    store.close()
    reopened = open_store(path)
    with pytest.raises(GroundingError):
        ground(reopened, candidate="realization:new")


def test_h6_corrupt_description_ids_isolates_snapshot(tmp_path):
    path = tmp_path / "atlas.sqlite"
    store = make_store(tmp_path)
    store.close()
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='snapshot' AND id='snapshot:m1'").fetchone()
    payload = json.loads(row[0]); del payload["description_ids"]
    db.execute("UPDATE records SET payload=? WHERE kind='snapshot' AND id='snapshot:m1'", (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(path)
    assert ("snapshot", "snapshot:m1") in reopened.isolated


def _derived(store, knowledge_id="derived:covers:r2:q1"):
    result = ground(store, candidate="realization:r2")
    return result, store.admit_derived(KnowledgeId(knowledge_id), result)


def test_m1b2_true_persists_relation_derivation_dependencies_and_provenance(tmp_path):
    store = make_store(tmp_path)
    result, relation = _derived(store)
    kid = KnowledgeId("derived:covers:r2:q1")
    assert relation.id == kid
    assert relation.predicate == PredicateId("covers")
    assert relation.version == "1"
    assert relation.participants == (DescriptionId("realization:r2"), DescriptionId("request:q1"))
    assert relation.polarity == "positive" and relation.epistemic_status == "exact"
    assert store.derivations[kid.value].rule_id == RuleId("coverage:v1")
    assert store.derivations[kid.value].rule_version == "1"
    assert store.derivations[kid.value].bindings == (
        ("candidate", DescriptionId("realization:r2")), ("request", DescriptionId("request:q1")))
    expected = tuple(KnowledgeId(x) for x in (
        "fact:q1-search", "fact:q1-output", "fact:r2-capabilities"))
    assert store.dependencies(kid, transitive=False) == expected
    assert KnowledgeId("fact:r1-unused") not in store.dependencies(kid, transitive=True)
    assert store.provenance(kid, transitive=False) == (SourceId("source:m1-fixture"),)
    assert store.provenance(kid, transitive=True) == (SourceId("source:m1-fixture"),)
    assert relation.derivation_id == kid
    assert result.conclusion is not relation


def test_m1b2_false_and_unknown_are_not_admitted(tmp_path):
    store = make_store(tmp_path)
    false = ground(store, candidate="realization:r1")
    missing_fixture = make_fixture()
    missing_fixture["facts"] = [x for x in missing_fixture["facts"] if x["id"] != "fact:r2-capabilities"]
    missing_dir = tmp_path / "missing"
    missing_dir.mkdir()
    unknown = ground(make_store(missing_dir, missing_fixture), candidate="realization:r2")
    for result in (false, unknown):
        with pytest.raises(ValidationError):
            store.admit_derived(KnowledgeId("derived:rejected"), result)
    assert "derived:rejected" not in store.records


def test_m1b2_duplicate_nominal_id_is_not_structurally_idempotent(tmp_path):
    store = make_store(tmp_path)
    result, _ = _derived(store)
    before = tuple(store.records)
    with pytest.raises(AdmissionError):
        store.admit_derived(KnowledgeId("derived:covers:r2:q1"), result)
    assert tuple(store.records) == before
    result2 = ground(store, candidate="realization:r2")
    store.admit_derived(KnowledgeId("derived:another:covers:r2:q1"), result2)
    assert len([x for x in store.records if x.startswith("derived:")]) == 2


def test_m1b2_restart_and_historical_extension_preserve_derivation(tmp_path):
    path = tmp_path / "derived.sqlite"
    store = admit_fixture(open_store(path), make_fixture())
    result, _ = _derived(store)
    before = (store.read("derived:covers:r2:q1"), store.derivations["derived:covers:r2:q1"],
              store.dependencies("derived:covers:r2:q1", True),
              store.provenance("derived:covers:r2:q1", True))
    store.configure_vocabulary({"properties":[
        {"id":"available-capabilities", "version":"2", "value":"finite_set<symbol>"}]})
    store.admit([{"kind":"description", "payload":{"id":"realization:new", "label":"new"}}])
    store.snapshot("snapshot:m2", parent="snapshot:m1")
    store.close()
    reopened = open_store(path)
    assert (reopened.read("derived:covers:r2:q1"), reopened.derivations["derived:covers:r2:q1"],
            reopened.dependencies("derived:covers:r2:q1", True),
            reopened.provenance("derived:covers:r2:q1", True)) == before
    assert result.rule_version == reopened.derivations["derived:covers:r2:q1"].rule_version == "1"


def test_m1b2_admission_is_atomic_on_late_sql_failure(monkeypatch, tmp_path):
    store = make_store(tmp_path)
    result = ground(store, candidate="realization:r2")
    before_records = dict(store.records); before_derivations = dict(store.derivations)
    original = store._persist
    calls = []
    def fail(kind, ident, payload):
        calls.append(kind)
        original(kind, ident, payload)
        if kind == "derivation":
            raise OSError("late derivation write failure")
    monkeypatch.setattr(store, "_persist", fail)
    with pytest.raises(OSError):
        store.admit_derived(KnowledgeId("derived:atomic"), result)
    assert store.records == before_records and store.derivations == before_derivations
    assert calls == ["relation", "derivation"]
    store.close(); reopened = open_store(store.path)
    assert "derived:atomic" not in reopened.records and "derived:atomic" not in reopened.derivations


@pytest.mark.parametrize("mutation", ["rule", "snapshot", "context", "dependency", "binding", "duplicate", "relation"])
def test_m1b2_corrupt_relation_or_derivation_is_isolated(tmp_path, mutation):
    store_dir = tmp_path / mutation
    store_dir.mkdir()
    path = store_dir / "atlas.sqlite"
    store = make_store(store_dir)
    _derived(store); store.close()
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='derivation' AND id=?", ("derived:covers:r2:q1",)).fetchone()
    payload = json.loads(row[0])
    if mutation == "rule": payload["rule_version"] = "missing"
    elif mutation == "snapshot": payload["snapshot"] = "snapshot:missing"
    elif mutation == "context": payload["context"] = "context:missing"
    elif mutation == "dependency": payload["dependencies"] = ["fact:missing"]
    elif mutation == "binding": payload["bindings"][0]["description"] = "not-a-description"
    elif mutation == "duplicate": payload["dependencies"].append(payload["dependencies"][0])
    else:
        db.execute("UPDATE records SET payload=json_set(payload,'$.predicate','realizes') WHERE kind='relation' AND id='derived:covers:r2:q1'")
    if mutation != "relation":
        db.execute("UPDATE records SET payload=? WHERE kind='derivation' AND id='derived:covers:r2:q1'", (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(path)
    assert "derived:covers:r2:q1" not in reopened.records
    assert "derived:covers:r2:q1" not in reopened.derivations
    assert ("relation", "derived:covers:r2:q1") in reopened.isolated
    assert ("derivation", "derived:covers:r2:q1") in reopened.isolated


def test_m1b2_nested_dependencies_and_transitive_provenance(tmp_path):
    path = tmp_path / "nested.sqlite"
    store = admit_fixture(open_store(path), make_fixture())
    first, _ = _derived(store, "derived:first")
    store.snapshot("snapshot:m2", parent="snapshot:m1")
    second = store.ground("coverage:v1", {
        "candidate": DescriptionId("realization:r2"), "request": DescriptionId("request:q1")},
        "snapshot:m2", "context:m1")
    store.admit_derived(KnowledgeId("derived:second"), second)
    direct = store.dependencies("derived:second", False)
    transitive = store.dependencies("derived:second", True)
    assert direct == (KnowledgeId("fact:q1-search"), KnowledgeId("fact:q1-output"), KnowledgeId("fact:r2-capabilities"))
    assert set(transitive) == set(direct)
    assert store.provenance("derived:second", True) == (SourceId("source:m1-fixture"),)
    store.close(); reopened = open_store(path)
    assert set(reopened.dependencies("derived:second", True)) == set(transitive)


def test_m1b2_corrupt_indirect_cycle_is_isolated(tmp_path):
    path = tmp_path / "cycle.sqlite"
    store = admit_fixture(open_store(path), make_fixture())
    first, _ = _derived(store, "derived:first")
    store.snapshot("snapshot:m2", parent="snapshot:m1")
    second = store.ground("coverage:v1", {
        "candidate": DescriptionId("realization:r2"), "request": DescriptionId("request:q1")},
        "snapshot:m2", "context:m1")
    store.admit_derived(KnowledgeId("derived:second"), second); store.close()
    db = sqlite3.connect(path)
    for ident, dep in [("derived:first", "derived:second"), ("derived:second", "derived:first")]:
        row = db.execute("SELECT payload FROM records WHERE kind='derivation' AND id=?", (ident,)).fetchone()
        payload = json.loads(row[0]); payload["dependencies"] = [dep]
        db.execute("UPDATE records SET payload=? WHERE kind='derivation' AND id=?", (json.dumps(payload), ident))
    db.commit(); db.close()
    reopened = open_store(path)
    assert not ({"derived:first", "derived:second"} & set(reopened.records))
    assert ("derivation", "derived:first") in reopened.isolated
    assert ("derivation", "derived:second") in reopened.isolated


def test_m1b2_ground_remains_pure_after_persistence_api(tmp_path):
    store = make_store(tmp_path)
    before = tuple(store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall())
    result = ground(store, candidate="realization:r2")
    after_ground = tuple(store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall())
    assert before == after_ground and "derived:covers:r2:q1" not in store.records
    store.admit_derived(KnowledgeId("derived:covers:r2:q1"), result)
    after_admit = tuple(store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall())
    assert after_admit != before


def _m2_with_context(store):
    store.admit([{"kind": "context", "payload": {
        "id": "context:m2", "visible_scopes": ["catalog", "other"],
        "enabled_rules": ["coverage:v1"]}}])
    store.snapshot("snapshot:m2", parent="snapshot:m1")
    return store


def test_r1_01_true_grounding_is_admitted_and_has_evidence(tmp_path):
    store = make_store(tmp_path)
    result = ground(store, candidate="realization:r2")
    relation = store.admit_derived(KnowledgeId("derived:r1-01"), result)
    assert relation.id.value == "derived:r1-01"
    assert result.grounding_evidence == store.derivations["derived:r1-01"].grounding_evidence


@pytest.mark.parametrize("mutation", ["snapshot", "context"])
def test_r1_02_03_environment_substitution_is_rejected(tmp_path, mutation):
    store = _m2_with_context(make_store(tmp_path))
    result = ground(store, candidate="realization:r2")
    forged = dataclasses.replace(result, **{mutation: SnapshotId("snapshot:m2") if mutation == "snapshot" else ContextId("context:m2")})
    before = dict(store.records)
    with pytest.raises((ValidationError, GroundingError)):
        store.admit_derived(KnowledgeId("derived:environment-forged"), forged)
    assert store.records == before


def test_r1_04_05_scope_substitutions_are_rejected(tmp_path):
    store = _m2_with_context(make_store(tmp_path))
    result = ground(store, candidate="realization:r2")
    for scope in ("forged-scope", "other"):
        forged = dataclasses.replace(result, conclusion=dataclasses.replace(result.conclusion, scope=scope))
        with pytest.raises(ValidationError):
            store.admit_derived(KnowledgeId("derived:scope-forged"), forged)
    assert "derived:scope-forged" not in store.records


def test_r1_06_provenance_substitution_is_rejected_even_for_existing_source(tmp_path):
    store = make_store(tmp_path)
    store.admit([{"kind": "source", "payload": {"id": "source:other"}}])
    result = ground(store, candidate="realization:r2")
    forged = dataclasses.replace(result, conclusion=dataclasses.replace(
        result.conclusion, provenance=(SourceId("source:other"),)))
    with pytest.raises(ValidationError):
        store.admit_derived(KnowledgeId("derived:provenance-forged"), forged)
    assert "derived:provenance-forged" not in store.records


@pytest.mark.parametrize("field,value", [
    ("scope", "forged-scope"),
    ("provenance", ["source:other"]),
])
def test_r1_07_08_relation_metadata_corruption_is_isolated(tmp_path, field, value):
    store_dir = tmp_path / field
    store_dir.mkdir()
    path = store_dir / "atlas.sqlite"
    store = make_store(store_dir)
    store.admit([{"kind": "source", "payload": {"id": "source:other"}}])
    _derived(store); store.close()
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='relation' AND id=?",
                     ("derived:covers:r2:q1",)).fetchone()
    payload = json.loads(row[0]); payload[field] = value
    db.execute("UPDATE records SET payload=? WHERE kind='relation' AND id=?", (json.dumps(payload), "derived:covers:r2:q1"))
    db.commit(); db.close()
    reopened = open_store(path)
    assert "derived:covers:r2:q1" not in reopened.records
    assert ("relation", "derived:covers:r2:q1") in reopened.isolated


def test_r1_09_evidence_corruption_is_isolated(tmp_path):
    store_dir = tmp_path / "evidence"
    store_dir.mkdir()
    path = store_dir / "atlas.sqlite"
    store = make_store(store_dir); _derived(store); store.close()
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='derivation' AND id=?",
                     ("derived:covers:r2:q1",)).fetchone()
    payload = json.loads(row[0]); payload["grounding_evidence"] = "0" * 64
    db.execute("UPDATE records SET payload=? WHERE kind='derivation' AND id=?", (json.dumps(payload), "derived:covers:r2:q1"))
    db.commit(); db.close()
    reopened = open_store(path)
    assert "derived:covers:r2:q1" not in reopened.records
    assert ("derivation", "derived:covers:r2:q1") in reopened.isolated


def test_r1_10_restart_preserves_exact_evidence(tmp_path):
    path = tmp_path / "restart.sqlite"
    store = admit_fixture(open_store(path), make_fixture()); result, _ = _derived(store)
    evidence = result.grounding_evidence; store.close()
    reopened = open_store(path)
    assert reopened.derivations["derived:covers:r2:q1"].grounding_evidence == evidence


def test_r1_11_historical_s1_remains_valid_after_v2_extension(tmp_path):
    path = tmp_path / "history.sqlite"
    store = admit_fixture(open_store(path), make_fixture()); result, _ = _derived(store)
    store.configure_vocabulary({"properties": [{"id": "available-capabilities", "version": "2", "value": "finite_set<symbol>"}]})
    store.snapshot("snapshot:m2", parent="snapshot:m1"); store.close()
    reopened = open_store(path)
    assert reopened.read("derived:covers:r2:q1") is not None
    assert reopened.derivations["derived:covers:r2:q1"].grounding_evidence == result.grounding_evidence


def test_r1_12_admission_never_calls_ground(monkeypatch, tmp_path):
    store = make_store(tmp_path); result = ground(store, candidate="realization:r2")
    def forbidden(*args, **kwargs):
        raise AssertionError("admit_derived must not reground")
    monkeypatch.setattr(store, "ground", forbidden)
    store.admit_derived(KnowledgeId("derived:no-reground"), result)
