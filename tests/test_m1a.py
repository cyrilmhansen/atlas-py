import json
import copy
from pathlib import Path
import pytest
from atlas import *
from atlas.values import value_from_json

FIXTURE=Path(__file__).parents[1]/"conformance/fixtures/m1-coverage.json"
def fixture(): return json.loads(FIXTURE.read_text())

def test_identity_and_values_are_explicit():
    assert DescriptionId("x") != KnowledgeId("x")
    assert FiniteSetSymbol(("a","b")) == FiniteSetSymbol(("b","a"))
    assert SequenceSymbol(("a","b")) != SequenceSymbol(("b","a"))
    with pytest.raises(ValidationError): Integer(True)
    with pytest.raises(ValidationError): FiniteSetSymbol(("a","a"))

def test_vocabulary_lookups_require_their_nominal_domain():
    vocabulary = Vocabulary(
        {("same", "1"): PredicateSpec(PredicateId("same"), "1", 0, ())},
        {("same", "1"): PropertySpec(PropertyId("same"), "1", "symbol")},
    )
    assert vocabulary.predicate(PredicateId("same"), "1") is not None
    assert vocabulary.prop(PropertyId("same"), "1") is not None
    with pytest.raises(ValidationError): vocabulary.predicate(PropertyId("same"), "1")
    with pytest.raises(ValidationError): vocabulary.prop(PredicateId("same"), "1")

def test_integer_uses_ascii_decimal_syntax():
    assert value_from_json({"kind": "integer", "value": "1"}).value == 1
    assert value_from_json({"kind": "integer", "value": "-1"}).value == -1
    assert value_from_json({"kind": "integer", "value": "-0"}).value == 0
    with pytest.raises(ValidationError): value_from_json({"kind": "integer", "value": "١"})
    with pytest.raises(ValidationError): value_from_json({"kind": "integer", "value": "-١"})

def test_fixture_admission_snapshot_restart(tmp_path):
    path=tmp_path/"atlas.sqlite"; s=admit_fixture(open_store(path), fixture())
    snap=s.open_snapshot("snapshot:m1")
    assert len(s.find(snapshot="snapshot:m1")) == 9
    assert s.read("fact:r1-cost", "snapshot:m1").id == KnowledgeId("fact:r1-cost")
    s.close(); s=open_store(path)
    assert s.open_snapshot("snapshot:m1").record_ids == snap.record_ids
    assert s.contexts["context:m1"].visible_scopes == ("catalog",)
    assert s.contexts["context:m1"].enabled_rules == (RuleId("coverage:v1"),)
    assert len(s.find(snapshot="snapshot:m1")) == 9

def test_invalid_batch_is_atomic(tmp_path):
    s=admit_fixture(open_store(tmp_path/"a.sqlite"), fixture()); before=set(s.descriptions)
    with pytest.raises((ValidationError, AdmissionError)):
        s.admit([{"kind":"description","payload":{"id":"description:new","label":"new"}}, {"kind":"property","payload":{"id":"fact:bad","description":"description:missing","property":"cost","version":"1","value":{"kind":"integer","value":"1"},"scope":"catalog","epistemic_status":"exact","provenance":["source:m1-fixture"]}}])
    assert set(s.descriptions)==before and "description:new" not in s.descriptions

def test_relation_find_is_multivalued(tmp_path):
    s=admit_fixture(open_store(tmp_path/"a.sqlite"), fixture())
    assert len(s.find(kind="relation")) == 2

def test_host_boundary_and_references(tmp_path):
    s=admit_fixture(open_store(tmp_path/"a.sqlite"), fixture())
    with pytest.raises(ValidationError): Integer(1.0)
    with pytest.raises(ValidationError): Symbol(object())
    with pytest.raises(ValidationError): SequenceSymbol(["a"])
    with pytest.raises((ValidationError, AdmissionError)):
        s.admit([{"kind":"property","payload":{"id":"fact:bad","description":"realization:r1","property":"unknown","version":"1","value":{"kind":"symbol","value":"x"},"scope":"catalog","epistemic_status":"exact","provenance":["source:m1-fixture"]}}])
    with pytest.raises((ValidationError, AdmissionError)):
        s.admit([{"kind":"relation","payload":{"id":"rel:bad","predicate":"realizes","version":"1","participants":["realization:r1"],"polarity":"positive","scope":"catalog","epistemic_status":"exact","provenance":["source:m1-fixture"]}}])

def test_nominal_models_and_exact_boundary_types(tmp_path):
    assert DescriptionId("a.b").value == "a.b"
    assert DescriptionId("a/b").value == "a/b"
    with pytest.raises(ValidationError): Description(KnowledgeId("x"), "label")
    assert Description(DescriptionId("x"), "a") == Description(DescriptionId("x"), "b")
    assert Description(DescriptionId("x"), "a") != Description(DescriptionId("y"), "a")
    with pytest.raises(ValidationError): PredicateSpec(PropertyId("p"), "1", 0, ())
    with pytest.raises(ValidationError): PropertySpec(PredicateId("p"), "1", "symbol")
    with pytest.raises(ValidationError): Source(KnowledgeId("source:x"))
    with pytest.raises(ValidationError): Snapshot(KnowledgeId("snapshot:x"), None, ())
    with pytest.raises(ValidationError): Snapshot(SnapshotId("snapshot:x"), KnowledgeId("snapshot:p"), ())
    with pytest.raises(ValidationError): Snapshot(SnapshotId("snapshot:x"), None, (SourceId("record:x"),))
    assert Description(DescriptionId("empty"), "").label == ""
    with pytest.raises(ValidationError): Description(DescriptionId("bad"), 1)
    with pytest.raises(ValidationError): Description(DescriptionId("bad"), "\ud800")

    s = admit_fixture(open_store(tmp_path / "a.sqlite"), fixture())
    bad = {"id": "context:bad", "visible_scopes": [True], "enabled_rules": ["coverage:v1"]}
    with pytest.raises((ValidationError, AdmissionError)): s.admit([{"kind": "context", "payload": bad}])
    bad = {"id": "context:bad", "visible_scopes": ["catalog"], "enabled_rules": [1]}
    with pytest.raises((ValidationError, AdmissionError)): s.admit([{"kind": "context", "payload": bad}])
    payload = copy.deepcopy(fixture()["facts"][0])
    payload["scope"] = True
    with pytest.raises((ValidationError, AdmissionError)): s.admit([{"kind": "property", "payload": payload}])

def test_hostile_values_are_rejected_before_semantic_operations(tmp_path):
    class HostileString(str):
        def __hash__(self): raise AssertionError("hostile hash called")
        def __eq__(self, other): raise AssertionError("hostile equality called")
    class Hostile:
        def __hash__(self): raise AssertionError("hostile hash called")
        def __eq__(self, other): raise AssertionError("hostile equality called")

    with pytest.raises(ValidationError): Symbol(HostileString("x"))
    with pytest.raises(ValidationError): FiniteSetSymbol((HostileString("x"),))
    with pytest.raises(ValidationError): SequenceSymbol(("\ud800",))
    with pytest.raises(ValidationError): Symbol("\ud800")
    with pytest.raises(ValidationError): Symbol(Hostile())
    assert value_from_json({"kind": "integer", "value": "-0"}).value == 0

    s = admit_fixture(open_store(tmp_path / "a.sqlite"), fixture())
    bad = {"id": "rel:bad", "predicate": "realizes", "version": "1", "participants": [Hostile()], "polarity": "positive", "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}
    with pytest.raises((ValidationError, AdmissionError)): s.admit([{"kind": "relation", "payload": bad}])
    with pytest.raises(ValidationError): PredicateSpec(PredicateId("p"), "1", 1, ("\ud800",))


def test_r31_vocabulary_roles_and_cardinality_are_strict():
    assert PredicateSpec(PredicateId("p"), "1", 2, ("left", "right")).roles == ("left", "right")
    with pytest.raises(ValidationError): PredicateSpec(PredicateId("p"), "1", 2, ("same", "same"))
    with pytest.raises(ValidationError): PropertySpec(PropertyId("p"), "1", "integer", True)
    assert PropertySpec(PropertyId("p"), "1", "integer", "multivalued").cardinality == "multivalued"


def test_r31_knowledge_id_collisions_are_global_and_atomic(tmp_path):
    f = fixture(); path = tmp_path / "knowledge-identity.sqlite"
    s = admit_fixture(open_store(path), f)
    relation = copy.deepcopy(f["relations"][0]); relation["id"] = "fact:r1-cost"
    before = set(s.records)
    with pytest.raises((ValidationError, AdmissionError)):
        s.admit([{"kind": "relation", "payload": relation}])
    assert set(s.records) == before and s.read("fact:r1-cost").value.value == 1
    with pytest.raises((ValidationError, AdmissionError)):
        s.admit([
            {"kind": "property", "payload": dict(f["facts"][0], id="fact:batch-duplicate", version="1")},
            {"kind": "property", "payload": dict(f["facts"][0], id="fact:batch-duplicate", version="1")},
        ])
    assert "fact:batch-duplicate" not in s.records
    relation = copy.deepcopy(f["relations"][0]); relation["id"] = "rel:batch-duplicate"
    with pytest.raises((ValidationError, AdmissionError)):
        s.admit([
            {"kind": "relation", "payload": relation},
            {"kind": "relation", "payload": dict(relation)},
        ])
    assert "rel:batch-duplicate" not in s.records


@pytest.mark.parametrize("first,second", [("property", "relation"), ("relation", "property")])
def test_r31_cross_kind_admission_rejects_second_in_either_order(tmp_path, first, second):
    f = fixture(); path = tmp_path / (first + "-then-" + second + ".sqlite")
    s = admit_fixture(open_store(path), f)
    property_payload = dict(f["facts"][0], id="fact:order-collision", version="1")
    relation_payload = dict(f["relations"][0], id="fact:order-collision")
    s.admit([{"kind": first, "payload": property_payload if first == "property" else relation_payload}])
    with pytest.raises((ValidationError, AdmissionError)):
        s.admit([{"kind": second, "payload": property_payload if second == "property" else relation_payload}])
    assert type(s.read("fact:order-collision")).__name__ == ("PropertyAssertion" if first == "property" else "RelationAssertion")


def test_r31_cross_kind_corruption_is_isolated_without_masking_or_losing_snapshot(tmp_path):
    path = tmp_path / "knowledge-corruption.sqlite"
    s = admit_fixture(open_store(path), fixture()); s.close()
    _inject_row(path, "fact:r1-cost", "relation", {
        "id": "fact:r1-cost", "predicate": "realizes", "version": "1",
        "participants": ["realization:r1", "artifact:r1"], "polarity": "positive",
        "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"],
    })
    reopened = open_store(path)
    assert reopened.read("fact:r1-cost").value.value == 1
    assert ("relation", "fact:r1-cost") in reopened.isolated
    assert reopened.read("fact:r1-cost", "snapshot:m1").value.value == 1


def _remove_identity(path, knowledge_id):
    import sqlite3
    db = sqlite3.connect(path)
    db.execute("DELETE FROM knowledge_identity WHERE knowledge_id=?", (knowledge_id,))
    db.commit(); db.close()


def _inject_valid_relation_claimant(path, row_id, knowledge_id):
    _inject_row(path, row_id, "relation", {
        "id": knowledge_id, "predicate": "realizes", "version": "1",
        "participants": ["realization:r1", "intent:selection"], "polarity": "positive",
        "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"],
    })


@pytest.mark.parametrize("claimant_kind", ["property", "relation"])
def test_r31_missing_identity_rebuilds_for_one_claimant(tmp_path, claimant_kind):
    path = tmp_path / (claimant_kind + "-migration.sqlite")
    s = admit_fixture(open_store(path), fixture()); s.close()
    knowledge_id = "fact:r1-cost" if claimant_kind == "property" else "rel:r1-realizes"
    _remove_identity(path, knowledge_id)
    reopened = open_store(path)
    owner = reopened._db.execute("SELECT kind,row_id FROM knowledge_identity WHERE knowledge_id=?", (knowledge_id,)).fetchone()
    assert owner["kind"] == claimant_kind and owner["row_id"] == knowledge_id
    assert reopened.read(knowledge_id) is not None
    assert (claimant_kind, knowledge_id) not in reopened.isolated


@pytest.mark.parametrize("reverse_physical_order", [False, True])
def test_r31_missing_identity_with_cross_kind_claimants_stays_ambiguous(tmp_path, reverse_physical_order):
    filename = "ambiguous-reverse-migration.sqlite" if reverse_physical_order else "ambiguous-migration.sqlite"
    path = tmp_path / filename
    s = admit_fixture(open_store(path), fixture()); s.close()
    _remove_identity(path, "fact:r1-cost")
    if reverse_physical_order:
        import sqlite3
        db = sqlite3.connect(path)
        row = db.execute("SELECT payload FROM records WHERE kind='property' AND id='fact:r1-cost'").fetchone()
        db.execute("DELETE FROM records WHERE kind='property' AND id='fact:r1-cost'")
        db.execute("INSERT INTO records(id,kind,payload) VALUES(?,?,?)", ("property-claimant", "property", row[0]))
        db.commit(); db.close()
    _inject_valid_relation_claimant(path, "relation-claimant", "fact:r1-cost")
    reopened = open_store(path)
    assert reopened._db.execute("SELECT 1 FROM knowledge_identity WHERE knowledge_id='fact:r1-cost'").fetchone() is None
    assert reopened.read("fact:r1-cost") is None
    assert ("property", "property-claimant" if reverse_physical_order else "fact:r1-cost") in reopened.isolated
    assert ("relation", "relation-claimant") in reopened.isolated
    assert ("snapshot", "snapshot:m1") in reopened.isolated
    reopened.close()
    second = open_store(path)
    assert second.read("fact:r1-cost") is None
    assert second._db.execute("SELECT 1 FROM knowledge_identity WHERE knowledge_id='fact:r1-cost'").fetchone() is None
    assert len([key for key in second.isolated if key[0] in {"property", "relation"} and key[1] in {"fact:r1-cost", "property-claimant", "relation-claimant"}]) == 2


def test_r31_nominal_id_domains_remain_independent(tmp_path):
    s = admit_fixture(open_store(tmp_path / "nominal-domains.sqlite"), fixture())
    assert DescriptionId("same") != KnowledgeId("same")
    s.admit([{"kind": "description", "payload": {"id": "same", "label": "same"}}])
    assert s.descriptions["same"].id == DescriptionId("same")


def test_r31_same_kind_physical_duplicate_cannot_overwrite_owner(tmp_path):
    path = tmp_path / "knowledge-same-kind-corruption.sqlite"
    s = admit_fixture(open_store(path), fixture()); s.close()
    _inject_row(path, "duplicate-property-row", "property", {
        "id": "fact:r1-cost", "description": "realization:r1", "property": "cost",
        "version": "1", "value": {"kind": "integer", "value": "999"},
        "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"],
    })
    reopened = open_store(path)
    assert reopened.read("fact:r1-cost").value.value == 1
    assert ("property", "duplicate-property-row") in reopened.isolated

def test_rule_coverage_boundary_and_future_operator_isolation(tmp_path):
    f = fixture()
    path = tmp_path / "a.sqlite"
    s = admit_fixture(open_store(path), f)
    assert s.rules["coverage:v1"].evaluation_supported is True
    f["rules"][0]["when"] = {"op": "future_op", "argument": {"nested": [1, "x"]}}
    s.admit([{"kind": "rule", "payload": {"id": "future:v1", "version": "1", "payload": f["rules"][0]}}])
    assert s.rules["future:v1"].evaluation_supported is False
    assert s.rules["future:v1"].payload["when"]["op"] == "future_op"
    s.close(); s = open_store(path)
    assert s.rules["coverage:v1"].evaluation_supported is True
    assert s.rules["future:v1"].evaluation_supported is False
    assert s.rules["future:v1"].payload["when"]["op"] == "future_op"

    bad = copy.deepcopy(fixture()["rules"][0])
    bad["head"]["participants"] = ["candidate"]
    with pytest.raises((ValidationError, AdmissionError)): s.admit([{"kind": "rule", "payload": {"id": bad["id"], "version": bad["version"], "payload": bad}}])
    bad = copy.deepcopy(fixture()["rules"][0])
    bad["participants"] = [True, 1]
    bad["head"]["participants"] = [True, 1]
    with pytest.raises((ValidationError, AdmissionError)): s.admit([{"kind": "rule", "payload": {"id": "coverage:bad", "version": "1", "payload": bad}}])

def test_rule_payload_is_independent_before_and_after_restart(tmp_path):
    f = fixture(); original = copy.deepcopy(f["rules"][0])
    path = tmp_path / "a.sqlite"
    s = admit_fixture(open_store(path), f)
    before = s.rules["coverage:v1"].payload
    f["rules"][0]["head"]["participants"].append("mutated")
    f["rules"][0]["when"]["left"]["property"] = "changed"
    assert s.rules["coverage:v1"].payload == before
    s.close(); reopened = open_store(path)
    assert reopened.rules["coverage:v1"].payload == before
    assert original["head"]["participants"] == ["candidate", "request"]

def test_r2_fixture_failure_rolls_back_vocabulary_sqlite_and_reopen(tmp_path):
    f=fixture(); f["contexts"][0]["enabled_rules"]=["missing-rule"]
    path=tmp_path/"r2.sqlite"; s=open_store(path)
    with pytest.raises((ValidationError, AdmissionError)): admit_fixture(s,f)
    assert s.vocabulary.properties == {} and s.records == {} and s.descriptions == {}
    s.close(); reopened=open_store(path)
    assert reopened.vocabulary.properties == {} and reopened.records == {} and reopened.isolated == {}

def test_r2_configure_vocabulary_failure_does_not_publish_memory(monkeypatch,tmp_path):
    s=admit_fixture(open_store(tmp_path/"r2.sqlite"),fixture()); before=s.vocabulary
    def fail(_): raise OSError("late serialization failure")
    monkeypatch.setattr(s,"_vocabulary_payload",fail)
    with pytest.raises(OSError): s.configure_vocabulary({"properties":[{"id":"cost","version":"2","value":"integer"}]})
    assert s.vocabulary == before
    s.close(); reopened=open_store(tmp_path/"r2.sqlite")
    assert ("cost","2") not in reopened.vocabulary.properties

def test_r2_vocabulary_versions_are_append_only_and_order_independent(tmp_path):
    def make(order,path):
        s=open_store(path); s.configure_vocabulary({"properties":[{"id":"cost","version":v,"value":"integer"} for v in order]})
        assert {x[1] for x in s.vocabulary.properties}=={"1","2"}
        with pytest.raises((ValidationError,AdmissionError)):
            s.admit([{"kind":"description","payload":{"id":"d","label":"d"}},{"kind":"source","payload":{"id":"src"}},{"kind":"property","payload":{"id":"k","description":"d","property":"cost","version":"1","value":{"kind":"integer","value":"1"},"scope":"catalog","epistemic_status":"exact","provenance":["src"]}},{"kind":"rule","payload":{"id":"r","version":"1","payload":{"participants":["x"],"when":{"op":"property","participant":"x","property":"cost"},"head":{"predicate":"p","version":"1","participants":["x"],"polarity":"positive"}}}}])
        return tuple(sorted(s.vocabulary.properties))
    assert make(["1","2"],tmp_path/"one.sqlite")==make(["2","1"],tmp_path/"two.sqlite")

def test_r2_snapshot_freezes_environment_and_active_all(tmp_path):
    path=tmp_path/"history.sqlite"; s=admit_fixture(open_store(path),fixture()); s.snapshot("s1")
    before=s.open_snapshot("s1"); old_ids=before.record_ids
    s.configure_vocabulary({"properties":[{"id":"cost","version":"2","value":"integer"}]})
    s.admit([{"kind":"property","payload":{"id":"fact:r1-cost-v2","description":"realization:r1","property":"cost","version":"2","value":{"kind":"integer","value":"9"},"scope":"catalog","epistemic_status":"exact","provenance":["source:m1-fixture"]}}])
    s.snapshot("s2")
    assert s.open_snapshot("s1").record_ids == old_ids and ("cost","1") in s.open_snapshot("s1").property_versions and ("cost","2") not in s.open_snapshot("s1").property_versions
    assert KnowledgeId("fact:r1-cost-v2") not in s.open_snapshot("s1").record_ids and KnowledgeId("fact:r1-cost-v2") in s.open_snapshot("s2").record_ids
    s.close(); s=open_store(path)
    assert s.open_snapshot("s1").property_versions == before.property_versions
    assert s.open_snapshot("s2").property_versions != s.open_snapshot("s1").property_versions

def test_r2_corrupt_persisted_relation_is_isolated_at_reopen(tmp_path):
    path=tmp_path/"corrupt.sqlite"; s=admit_fixture(open_store(path),fixture()); s.close()
    import sqlite3
    db=sqlite3.connect(path)
    db.execute("UPDATE records SET payload=json_set(payload,'$.polarity','not-a-polarity') WHERE id='rel:r1-realizes' AND kind='relation'")
    db.commit(); db.close()
    reopened=open_store(path)
    assert all(r.id != KnowledgeId("rel:r1-realizes") for r in reopened.find())
    assert "rel:r1-realizes" in reopened.isolated
    assert reopened.read("rel:r1-realizes") is None
    assert "snapshot:m1" in reopened.isolated
    assert "snapshot:m1" not in reopened.snapshots


def _late_snapshot_fixture():
    f = fixture()
    f["snapshots"] = [
        {"id": "snapshot:first", "parent": None, "active_records": "all"},
        {"id": "snapshot:second", "parent": "snapshot:missing", "active_records": "all"},
    ]
    return f


def test_r21_late_snapshot_failure_is_atomic_from_empty_store(tmp_path):
    path = tmp_path / "late-empty.sqlite"
    s = open_store(path)
    with pytest.raises((ValidationError, AdmissionError)):
        admit_fixture(s, _late_snapshot_fixture())
    assert s.vocabulary.properties == {} and s.descriptions == {} and s.records == {}
    assert s.rules == {} and s.contexts == {} and s.snapshots == {}
    s.close()
    reopened = open_store(path)
    assert reopened.vocabulary.properties == {} and reopened.descriptions == {}
    assert reopened.records == {} and reopened.rules == {} and reopened.contexts == {}
    assert reopened.snapshots == {} and reopened.isolated == {}


def test_r21_late_snapshot_failure_preserves_nonempty_state(tmp_path):
    path = tmp_path / "late-nonempty.sqlite"
    s = admit_fixture(open_store(path), fixture())
    before = {name: getattr(s, name) for name in ("vocabulary", "descriptions", "sources", "records", "rules", "contexts", "snapshots")}
    with pytest.raises((ValidationError, AdmissionError)):
        admit_fixture(s, _late_snapshot_fixture())
    assert all(getattr(s, name) is value for name, value in before.items())
    s.close()
    reopened = open_store(path)
    assert all(getattr(reopened, name) == value for name, value in before.items())


def _cost_fixture(version=None, vocabulary_versions=("2",), fact_id="fact:cost"):
    fact = {
        "id": fact_id, "kind": "property", "description": "d", "property": "cost",
        "value": {"kind": "integer", "value": "2"}, "scope": "catalog",
        "epistemic_status": "exact", "provenance": ["src"],
    }
    if version is not None:
        fact["version"] = version
    return {
        "vocabulary": {"predicates": [], "properties": [{"id": "cost", "version": v, "value": "integer"} for v in vocabulary_versions]},
        "descriptions": [{"id": "d", "label": "d"}], "facts": [fact], "relations": [],
        "rules": [], "contexts": [], "snapshots": [],
    }


def test_r21_unversioned_reference_sees_existing_and_batch_versions(tmp_path):
    path = tmp_path / "versions.sqlite"
    s = open_store(path)
    s.configure_vocabulary({"properties": [{"id": "cost", "version": "1", "value": "integer"}]})
    with pytest.raises((ValidationError, AdmissionError)):
        admit_fixture(s, _cost_fixture(vocabulary_versions=("2",)))
    assert set(s.vocabulary.properties) == {("cost", "1")}
    s.close(); reopened = open_store(path)
    assert set(reopened.vocabulary.properties) == {("cost", "1")} and reopened.records == {}


def test_r21_unversioned_resolution_is_order_independent(tmp_path):
    outcomes = []
    for order in (("1", "2"), ("2", "1")):
        s = open_store(tmp_path / ("order-" + "-".join(order) + ".sqlite"))
        s.configure_vocabulary({"properties": [{"id": "cost", "version": v, "value": "integer"} for v in order]})
        with pytest.raises((ValidationError, AdmissionError)):
            admit_fixture(s, _cost_fixture(vocabulary_versions=()))
        outcomes.append((set(s.vocabulary.properties), s.records))
    assert outcomes[0] == outcomes[1]


def test_r21_unversioned_reference_with_one_candidate_version_resolves(tmp_path):
    s = admit_fixture(open_store(tmp_path / "one-version.sqlite"), _cost_fixture())
    assert s.records["fact:cost"].version == "2"


def test_r21_explicit_version_resolves_exactly(tmp_path):
    for order in (("1", "2"), ("2", "1")):
        s = open_store(tmp_path / ("explicit-" + "-".join(order) + ".sqlite"))
        s.configure_vocabulary({"properties": [{"id": "cost", "version": v, "value": "integer"} for v in order]})
        f = _cost_fixture(version="2", vocabulary_versions=(), fact_id="fact:cost-v2")
        s = admit_fixture(s, f)
        assert s.records["fact:cost-v2"].version == "2"


def test_r21_ambiguous_resolution_rolls_back_all_candidate_categories(tmp_path):
    path = tmp_path / "ambiguous.sqlite"
    s = open_store(path)
    s.configure_vocabulary({"properties": [{"id": "cost", "version": "1", "value": "integer"}]})
    bad = _cost_fixture(vocabulary_versions=("2",))
    bad["rules"] = [{"id": "r", "version": "1", "participants": [], "when": {"op": "future_op"}, "head": {"predicate": "missing", "version": "1", "participants": [], "polarity": "positive"}}]
    with pytest.raises((ValidationError, AdmissionError)):
        admit_fixture(s, bad)
    assert set(s.vocabulary.properties) == {("cost", "1")} and s.descriptions == {} and s.records == {}
    s.close(); reopened = open_store(path)
    assert set(reopened.vocabulary.properties) == {("cost", "1")} and reopened.descriptions == {} and reopened.records == {}


def _inject_row(path, row_id, kind, payload):
    import sqlite3
    db = sqlite3.connect(path)
    db.execute("INSERT INTO records(id,kind,payload) VALUES(?,?,?)", (row_id, kind, json.dumps(payload)))
    db.commit(); db.close()


@pytest.mark.parametrize("kind,payload", [
    ("relation", {"id":"bad:polarity", "predicate":"realizes", "version":"1", "participants":["realization:r1","artifact:r1"], "polarity":"sideways", "scope":"catalog", "epistemic_status":"exact", "provenance":["source:m1-fixture"]}),
    ("relation", {"id":"bad:participant", "predicate":"realizes", "version":"1", "participants":["missing","artifact:r1"], "polarity":"positive", "scope":"catalog", "epistemic_status":"exact", "provenance":["source:m1-fixture"]}),
    ("property", {"id":"bad:property", "description":"realization:r1", "property":"cost", "version":"missing", "value":{"kind":"integer","value":"1"}, "scope":"catalog", "epistemic_status":"exact", "provenance":["source:m1-fixture"]}),
    ("relation", {"id":"bad:scope", "predicate":"realizes", "version":"1", "participants":["realization:r1","artifact:r1"], "polarity":"positive", "scope":[], "epistemic_status":"not-a-status", "provenance":["source:m1-fixture"]}),
    ("rule", {"id":"bad:rule", "version":"1", "payload":{"participants":[], "when":{"op":"property", "participant":"missing", "property":"cost", "version":"1"}, "head":{"predicate":"realizes", "version":"1", "participants":[], "polarity":"positive"}}, "evaluation_supported":True}),
    ("context", {"id":"bad:context", "visible_scopes":"catalog", "enabled_rules":["coverage:v1"]}),
])
def test_r22_corrupt_parseable_rows_are_isolated(tmp_path, kind, payload):
    path = tmp_path / (kind + ".sqlite")
    s = admit_fixture(open_store(path), fixture()); s.close()
    _inject_row(path, payload["id"], kind, payload)
    reopened = open_store(path)
    assert (kind, payload["id"]) in reopened.isolated
    assert reopened.find(snapshot=None) and payload["id"] not in [str(r.id) for r in reopened.find()]
    reopened.snapshot("after-corruption")
    assert payload["id"] not in [str(x) for x in reopened.open_snapshot("after-corruption").record_ids]


def test_r22_incomplete_parseable_snapshot_isolated(tmp_path):
    path = tmp_path / "incomplete-snapshot.sqlite"
    s = admit_fixture(open_store(path), fixture()); s.close()
    _inject_row(path, "snapshot:incomplete", "snapshot", {"id":"snapshot:incomplete", "parent":None, "record_ids":[]})
    reopened = open_store(path)
    assert ("snapshot", "snapshot:incomplete") in reopened.isolated
    assert "snapshot:incomplete" not in reopened.snapshots


def test_r22_context_definition_is_frozen_and_corruption_is_detected(tmp_path):
    path = tmp_path / "context-history.sqlite"
    s = admit_fixture(open_store(path), fixture()); s.snapshot("s1")
    s.admit([{"kind":"context", "payload":{"id":"context:c2", "visible_scopes":["other"], "enabled_rules":["coverage:v1"]}}])
    assert s.open_snapshot("s1").context_definitions[0][1] == ("catalog",)
    s.close(); reopened = open_store(path)
    assert reopened.open_snapshot("s1").context_definitions[0][1] == ("catalog",)
    import sqlite3
    db = sqlite3.connect(path)
    db.execute("UPDATE records SET payload=json_set(payload,'$.visible_scopes',json(?)) WHERE kind='context' AND id='context:m1'", (json.dumps(["tampered"]),))
    db.commit(); db.close()
    corrupted = open_store(path)
    assert ("context", "context:m1") in corrupted.isolated
    assert ("snapshot", "s1") in corrupted.isolated
    assert "s1" not in corrupted.snapshots


@pytest.mark.parametrize("mutation", ["missing", "additional", "duplicate", "wrong-version"])
def test_r221_snapshot_environment_definition_sets_are_exact(tmp_path, mutation):
    path = tmp_path / ("strict-snapshot-" + mutation + ".sqlite")
    s = admit_fixture(open_store(path), fixture())
    s.close()
    import sqlite3
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='snapshot' AND id='snapshot:m1'").fetchone()
    payload = json.loads(row[0])
    if mutation == "missing":
        payload["context_definitions"] = []
    elif mutation == "additional":
        payload["context_definitions"].append({"id":"context:extra", "visible_scopes":[], "enabled_rules":[]})
    elif mutation == "duplicate":
        payload["context_definitions"].append(copy.deepcopy(payload["context_definitions"][0]))
    else:
        payload["rule_definitions"][0]["version"] = "wrong-version"
    db.execute("UPDATE records SET payload=? WHERE kind='snapshot' AND id='snapshot:m1'", (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(path)
    assert ("snapshot", "snapshot:m1") in reopened.isolated
    assert "snapshot:m1" not in reopened.snapshots
    assert "context:m1" in reopened.contexts and "coverage:v1" in reopened.rules


def test_r22_physical_row_identity_cannot_mask_valid_record(tmp_path):
    path = tmp_path / "row-identity.sqlite"
    s = admit_fixture(open_store(path), fixture()); s.close()
    _inject_row(path, "zzzz-mask", "property", {"id":"fact:r1-cost", "description":"realization:r1", "property":"cost", "version":"1", "value":{"kind":"integer","value":"999"}, "scope":"catalog", "epistemic_status":"exact", "provenance":["source:m1-fixture"]})
    reopened = open_store(path)
    assert reopened.read("fact:r1-cost").value.value == 1
    assert ("property", "zzzz-mask") in reopened.isolated
    reopened.snapshot("after-mask")
    assert reopened.read("fact:r1-cost", "after-mask").value.value == 1


def test_r22_isolation_keeps_same_id_different_kinds_distinct(tmp_path):
    path = tmp_path / "isolation-identity.sqlite"
    s = admit_fixture(open_store(path), fixture()); s.close()
    _inject_row(path, "same-row-id", "context", {"id":"other", "visible_scopes":"catalog", "enabled_rules":[]})
    _inject_row(path, "same-row-id", "rule", {"id":"other", "version":"1", "payload":{}, "evaluation_supported":False})
    reopened = open_store(path)
    assert ("context", "same-row-id") in reopened.isolated
    assert ("rule", "same-row-id") in reopened.isolated
    assert len(reopened.isolated) == 2
