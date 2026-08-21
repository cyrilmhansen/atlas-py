import json
import sqlite3
from dataclasses import replace

import pytest

from atlas import (DescriptionId, GroundingError, GroundingManifest, GroundingStatus,
                   KnowledgeId, RuleId, Snapshot, SnapshotId, ValidationError,
                   admit_fixture, open_store)
from test_m1c_scope import FIXTURE, fixture
from atlas.evidence import evidence_for


def _store(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture())


def _manifest():
    return GroundingManifest("m1-grounding/1",
                             (DescriptionId("realization:r2"),),
                             (RuleId("coverage:v1"),))


def _copy_snapshot(path, snapshot_id):
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='snapshot' AND id='snapshot:m1'").fetchone()
    payload = json.loads(row[0])
    payload["id"] = snapshot_id
    db.execute("INSERT INTO records(id,kind,payload) VALUES(?,?,?)",
               (snapshot_id, "snapshot", json.dumps(payload)))
    db.commit(); db.close()


def _corrupt_snapshot(path, snapshot_id, field):
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='snapshot' AND id=?", (snapshot_id,)).fetchone()
    payload = json.loads(row[0])
    if field == "context":
        payload["context_definitions"][0]["visible_scopes"] = ["corrupt-scope"]
    else:
        payload["rule_definitions"][0]["payload"]["when"] = {"op": "future_corruption"}
    db.execute("UPDATE records SET payload=? WHERE kind='snapshot' AND id=?",
               (json.dumps(payload), snapshot_id))
    db.commit(); db.close()


def _order_case(tmp_path, corrupt_id, field):
    store = _store(tmp_path)
    store.create_decision_scope("decision-scope:ds", "snapshot:m1", "context:m1",
                                "request:q1", _manifest())
    store.evaluate_decision_scope("decision-scope:ds")
    store.close()
    path = tmp_path / "atlas.sqlite"
    _copy_snapshot(path, corrupt_id)
    _corrupt_snapshot(path, corrupt_id, field)
    reopened = open_store(path)
    return reopened, path


@pytest.mark.parametrize("corrupt_id", ["snapshot:zz-corrupt", "snapshot:aa-corrupt"])
def test_r2_1_context_claim_corruption_is_order_independent(tmp_path, corrupt_id):
    store, _ = _order_case(tmp_path, corrupt_id, "context")
    assert "snapshot:m1" in store.snapshots
    assert "context:m1" in store.contexts
    assert "decision-scope:ds" in store.decision_scopes
    assert "decision-scope:ds" in store.decision_groundings
    assert corrupt_id not in store.snapshots
    assert ("snapshot", corrupt_id) in store.isolated


@pytest.mark.parametrize("corrupt_id", ["snapshot:zz-corrupt", "snapshot:aa-corrupt"])
def test_r2_1_rule_claim_corruption_is_order_independent(tmp_path, corrupt_id):
    store, _ = _order_case(tmp_path, corrupt_id, "rule")
    assert "snapshot:m1" in store.snapshots
    assert "coverage:v1" in store.rules
    assert "decision-scope:ds" in store.decision_scopes
    assert "decision-scope:ds" in store.decision_groundings
    assert corrupt_id not in store.snapshots


def _semantic_state(store):
    return (tuple(sorted(store.descriptions)), tuple(sorted(store.rules)),
            tuple(sorted(store.contexts)), tuple(sorted(store.snapshots)),
            tuple(sorted(store.decision_scopes)), tuple(sorted(store.decision_groundings)),
            tuple(sorted((kind, "snapshot:corrupt" if kind == "snapshot" else ident)
                         for kind, ident in store.isolated)))


def test_r2_1_context_aa_and_zz_have_identical_semantics(tmp_path):
    zz, _ = _order_case(tmp_path / "zz", "snapshot:zz-corrupt", "context")
    aa, _ = _order_case(tmp_path / "aa", "snapshot:aa-corrupt", "context")
    assert _semantic_state(zz) == _semantic_state(aa)


def test_r2_1_rule_aa_and_zz_have_identical_semantics(tmp_path):
    zz, _ = _order_case(tmp_path / "rule-zz", "snapshot:zz-corrupt", "rule")
    aa, _ = _order_case(tmp_path / "rule-aa", "snapshot:aa-corrupt", "rule")
    assert _semantic_state(zz) == _semantic_state(aa)


def test_r2_1_two_healthy_snapshots_share_definitions(tmp_path):
    store = _store(tmp_path)
    store.close()
    path = tmp_path / "atlas.sqlite"
    _copy_snapshot(path, "snapshot:shared")
    reopened = open_store(path)
    assert {"snapshot:m1", "snapshot:shared"} <= set(reopened.snapshots)
    assert "context:m1" in reopened.contexts and "coverage:v1" in reopened.rules


def test_r2_1_active_scopes_have_final_context_and_rules(tmp_path):
    store, _ = _order_case(tmp_path, "snapshot:zz-corrupt", "context")
    for scope in store.decision_scopes.values():
        assert scope.context.value in store.contexts
        snapshot = store.snapshots[scope.snapshot.value]
        fixed = {ident: version for ident, version, *_ in snapshot.rule_definitions}
        assert all(rule.value in store.rules and store.rules[rule.value].version == fixed[rule.value]
                   for rule in scope.manifest.prescribed_rule_ids)


def test_r2_1_double_restart_and_sqlite_unchanged(tmp_path):
    first, path = _order_case(tmp_path, "snapshot:aa-corrupt", "context")
    db = sqlite3.connect(path)
    before = db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()
    db.close()
    first.close()
    second = open_store(path)
    second.close()
    db = sqlite3.connect(path)
    after = db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()
    db.close()
    assert before == after
    third = open_store(path)
    assert "snapshot:m1" in third.snapshots
    assert "snapshot:aa-corrupt" not in third.snapshots


def _terminal_case(tmp_path, ident="derived:k"):
    store = _store(tmp_path)
    result = store.ground("coverage:v1", {
        "candidate": DescriptionId("realization:r2"),
        "request": DescriptionId("request:q1")}, "snapshot:m1", "context:m1")
    store.admit_derived(KnowledgeId(ident), result)
    store.snapshot("snapshot:with-derived")
    store.create_decision_scope("decision-scope:ds", "snapshot:with-derived",
                                "context:m1", "request:q1", _manifest())
    store.evaluate_decision_scope("decision-scope:ds")
    store.close()
    path = tmp_path / "atlas.sqlite"
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='derivation' AND id=?", (ident,)).fetchone()
    payload = json.loads(row[0])
    payload["dependencies"] = ["fact:missing"]
    db.execute("UPDATE records SET payload=? WHERE kind='derivation' AND id=?",
               (json.dumps(payload), ident))
    db.commit()
    db.close()
    return path


def test_r2_01_derived_snapshot_scope_run_close_together(tmp_path):
    path = _terminal_case(tmp_path)
    reopened = open_store(path)
    assert "derived:k" not in reopened.records and "derived:k" not in reopened.derivations
    assert "snapshot:with-derived" not in reopened.snapshots
    assert "decision-scope:ds" not in reopened.decision_scopes
    assert "decision-scope:ds" not in reopened.decision_groundings
    assert {("relation", "derived:k"), ("derivation", "derived:k"),
            ("snapshot", "snapshot:with-derived"),
            ("decision_scope", "decision-scope:ds"),
            ("decision_grounding", "decision-scope:ds")} <= set(reopened.isolated)
    for operation in (reopened.decision_scope, reopened.decision_grounding,
                      reopened.encountered_candidates):
        with pytest.raises(GroundingError):
            operation("decision-scope:ds")


def test_r2_02_closure_is_independent_of_lexical_derived_ids(tmp_path):
    first = _terminal_case(tmp_path / "z-first", "derived:z")
    second = _terminal_case(tmp_path / "a-second", "derived:a")
    one = open_store(first)
    two = open_store(second)
    assert set(one.records) == set(two.records)
    assert set(one.derivations) == set(two.derivations)
    assert set(one.snapshots) == set(two.snapshots)
    assert {kind for kind, _ in one.isolated} == {kind for kind, _ in two.isolated}


def test_r2_03_invalid_snapshot_invalidates_declared_scope_without_run(tmp_path):
    store = _store(tmp_path)
    store.create_decision_scope("decision-scope:ds", "snapshot:m1", "context:m1",
                                "request:q1", _manifest())
    store.close()
    path = tmp_path / "atlas.sqlite"
    db = sqlite3.connect(path)
    db.execute("UPDATE records SET payload=json_set(payload, '$.record_ids', json('[\"fact:missing\"]')) WHERE kind='snapshot' AND id='snapshot:m1'")
    db.commit(); db.close()
    reopened = open_store(path)
    assert not reopened.snapshots and not reopened.decision_scopes
    assert ("decision_scope", "decision-scope:ds") in reopened.isolated


def test_r2_04_corrupt_run_does_not_invalidate_healthy_scope(tmp_path):
    store = _store(tmp_path)
    store.create_decision_scope("decision-scope:ds", "snapshot:m1", "context:m1",
                                "request:q1", _manifest())
    store.evaluate_decision_scope("decision-scope:ds")
    store.close()
    path = tmp_path / "atlas.sqlite"
    db = sqlite3.connect(path)
    db.execute("UPDATE records SET payload=json_set(payload, '$.status', 'invalid') WHERE kind='decision_grounding'")
    db.commit(); db.close()
    reopened = open_store(path)
    assert "snapshot:m1" in reopened.snapshots
    assert "decision-scope:ds" in reopened.decision_scopes
    assert "decision-scope:ds" not in reopened.decision_groundings


def test_r2_05_invalid_scope_invalidates_run_but_not_snapshot(tmp_path):
    store = _store(tmp_path)
    store.create_decision_scope("decision-scope:ds", "snapshot:m1", "context:m1",
                                "request:q1", _manifest())
    store.evaluate_decision_scope("decision-scope:ds")
    store.close()
    path = tmp_path / "atlas.sqlite"
    db = sqlite3.connect(path)
    db.execute("UPDATE records SET payload=json_set(payload, '$.request', 'request:missing') WHERE kind='decision_scope'")
    db.commit(); db.close()
    reopened = open_store(path)
    assert "snapshot:m1" in reopened.snapshots
    assert "decision-scope:ds" not in reopened.decision_scopes
    assert "decision-scope:ds" not in reopened.decision_groundings
    assert ("decision_grounding", "decision-scope:ds") in reopened.isolated


@pytest.mark.parametrize("kind,ident,path,value", [
    ("context", "context:m1", "$.visible_scopes", json.dumps(["other"])),
    ("rule", "coverage:v1", "$.evaluation_supported", "false"),
])
def test_r2_06_r2_07_historical_context_or_rule_invalidation_closes_scope_and_run(
        tmp_path, kind, ident, path, value):
    store = _store(tmp_path)
    store.create_decision_scope("decision-scope:ds", "snapshot:m1", "context:m1",
                                "request:q1", _manifest())
    store.evaluate_decision_scope("decision-scope:ds")
    store.close()
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    if kind == "context":
        db.execute("UPDATE records SET payload=json_set(payload, ?, json(?)) WHERE kind=? AND id=?",
                   (path, value, kind, ident))
    else:
        db.execute("UPDATE records SET payload=json_set(payload, ?, ?) WHERE kind=? AND id=?",
                   (path, value, kind, ident))
    db.commit(); db.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert "snapshot:m1" not in reopened.snapshots
    assert "decision-scope:ds" not in reopened.decision_scopes
    assert "decision-scope:ds" not in reopened.decision_groundings


@pytest.mark.parametrize("field,value", [("request", "request:missing"),
                                           ("candidate_description_ids", ["realization:missing"])])
def test_r2_08_unresolved_scope_request_or_candidate_is_not_unknown(tmp_path, field, value):
    store = _store(tmp_path)
    store.create_decision_scope("decision-scope:ds", "snapshot:m1", "context:m1",
                                "request:q1", _manifest())
    store.close()
    path = tmp_path / "atlas.sqlite"
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='decision_scope'").fetchone()
    payload = json.loads(row[0])
    if field == "request": payload[field] = value
    else: payload["manifest"][field] = value
    db.execute("UPDATE records SET payload=? WHERE kind='decision_scope'", (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(path)
    assert "snapshot:m1" in reopened.snapshots
    assert "decision-scope:ds" not in reopened.decision_scopes
    assert ("decision_scope", "decision-scope:ds") in reopened.isolated


def test_r2_09_and_r2_10_double_restart_and_sqlite_unchanged(tmp_path):
    path = _terminal_case(tmp_path)
    db = sqlite3.connect(path)
    before = db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()
    db.close()
    first = open_store(path)
    first.close()
    db = sqlite3.connect(path)
    after = db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()
    db.close()
    assert before == after
    second = open_store(path)
    assert set(first.isolated) == set(second.isolated)
    assert set(first.records) == set(second.records)
    assert set(first.snapshots) == set(second.snapshots)


def test_r2_2_invalid_definition_is_absent_from_active_maps_and_cannot_self_legitimize(tmp_path):
    store = _store(tmp_path)
    store.close()
    path = tmp_path / "atlas.sqlite"
    db = sqlite3.connect(path)
    # This remains a structurally valid Rule, but disagrees with every
    # historical rule claim (the snapshot claims evaluation_supported=true).
    db.execute("UPDATE records SET payload=json_set(payload, '$.evaluation_supported', 0) WHERE kind='rule' AND id='coverage:v1'")
    db.commit(); db.close()
    first = open_store(path)
    assert "coverage:v1" not in first.rules
    assert ("rule", "coverage:v1") in first.isolated
    first.snapshot("snapshot:after-invalid-rule")
    first.close()
    second = open_store(path)
    assert "coverage:v1" not in second.rules
    assert "coverage:v1" not in {
        rule_id for snapshot in second.snapshots.values()
        for rule_id, _ in snapshot.rule_versions
    }
    second.close()
    third = open_store(path)
    assert "coverage:v1" not in third.rules


def test_r2_2_invalid_context_is_absent_from_active_map(tmp_path):
    store = _store(tmp_path)
    store.close()
    path = tmp_path / "atlas.sqlite"
    db = sqlite3.connect(path)
    db.execute("UPDATE records SET payload=json_set(payload, '$.visible_scopes', json('[\"other\"]')) WHERE kind='context' AND id='context:m1'")
    db.commit(); db.close()
    reopened = open_store(path)
    assert "context:m1" not in reopened.contexts
    assert ("context", "context:m1") in reopened.isolated
    assert "snapshot:m1" not in reopened.snapshots


@pytest.mark.parametrize("raw", ["[]", "null", '"string"', "123", "true", "{}"])
def test_r2_2_hostile_snapshot_roots_are_isolated_without_breaking_restore(tmp_path, raw):
    store = _store(tmp_path)
    store.close()
    path = tmp_path / "atlas.sqlite"
    db = sqlite3.connect(path)
    ident = "snapshot:hostile-" + str(len(raw))
    db.execute("INSERT INTO records(id,kind,payload) VALUES(?,?,?)", (ident, "snapshot", raw))
    db.commit(); db.close()
    reopened = open_store(path)
    assert "snapshot:m1" in reopened.snapshots
    assert ident not in reopened.snapshots
    assert ("snapshot", ident) in reopened.isolated


def test_r2_2_conclusion_dependencies_are_closed_over_effective_dependencies(tmp_path):
    store = _store(tmp_path)
    store.create_decision_scope("decision-scope:ds", "snapshot:m1", "context:m1",
                                "request:q1", _manifest())
    store.evaluate_decision_scope("decision-scope:ds")
    store.close()
    path = tmp_path / "atlas.sqlite"
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='decision_grounding'").fetchone()
    payload = json.loads(row[0])
    result_payload = payload["observations"][0]["grounding_result"]
    result = open_store(path)
    original = result.decision_grounding("decision-scope:ds").observations[0].grounding_result
    result.close()
    bad_conclusion = replace(original.conclusion, dependencies=(KnowledgeId("fact:not-in-store"),))
    bad_result = replace(original, conclusion=bad_conclusion,
                        grounding_evidence=evidence_for(replace(original, conclusion=bad_conclusion)))
    result_payload["conclusion"]["dependencies"] = [x.value for x in bad_result.conclusion.dependencies]
    result_payload["grounding_evidence"] = bad_result.grounding_evidence
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding'", (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(path)
    assert ("decision_grounding", "decision-scope:ds") in reopened.isolated
    assert "decision-scope:ds" not in reopened.decision_groundings


def _inject_snapshot_row(path, ident, payload):
    db = sqlite3.connect(path)
    db.execute("INSERT INTO records(id,kind,payload) VALUES(?,?,?)",
               (ident, "snapshot", json.dumps(payload)))
    db.commit(); db.close()


def _fake_rule_claim():
    return {
        "id": "snapshot:fake-rule-claim",
        "rule_versions": [["coverage:v1", "1"]],
        "rule_definitions": [{
            "id": "coverage:v1", "version": "1", "payload": {},
            "evaluation_supported": False,
        }],
    }


def _fake_context_claim():
    return {
        "id": "snapshot:fake-context-claim",
        "context_ids": ["context:m1"],
        "context_definitions": [{
            "id": "context:m1", "visible_scopes": ["catalog"],
            "enabled_rules": ["coverage:v1"],
        }],
    }


def _corrupt_global_definition(path, kind):
    db = sqlite3.connect(path)
    if kind == "rule":
        row = db.execute("SELECT payload FROM records WHERE kind='rule' AND id='coverage:v1'").fetchone()
        payload = json.loads(row[0]); payload["evaluation_supported"] = False
        db.execute("UPDATE records SET payload=? WHERE kind='rule' AND id='coverage:v1'", (json.dumps(payload),))
    else:
        db.execute("UPDATE records SET payload=json_set(payload, '$.visible_scopes', json('[\"corrupt\"]')) WHERE kind='context' AND id='context:m1'")
    db.commit(); db.close()


def test_r2_3_01_fake_incomplete_rule_claim_contributes_zero_claims(tmp_path):
    store = _store(tmp_path); store.close()
    path = tmp_path / "atlas.sqlite"
    _corrupt_global_definition(path, "rule")
    _inject_snapshot_row(path, "snapshot:fake-rule-claim", _fake_rule_claim())
    reopened = open_store(path)
    assert "coverage:v1" not in reopened.rules
    assert ("rule", "coverage:v1") in reopened.isolated
    assert ("snapshot", "snapshot:fake-rule-claim") in reopened.isolated


def test_r2_3_02_fake_incomplete_context_claim_contributes_zero_claims(tmp_path):
    store = _store(tmp_path); store.close()
    path = tmp_path / "atlas.sqlite"
    _corrupt_global_definition(path, "context")
    _inject_snapshot_row(path, "snapshot:fake-context-claim", _fake_context_claim())
    reopened = open_store(path)
    assert "context:m1" not in reopened.contexts
    assert ("context", "context:m1") in reopened.isolated
    assert ("snapshot", "snapshot:fake-context-claim") in reopened.isolated


def test_r2_3_03_multiple_fake_claimants_still_have_zero_authority(tmp_path):
    store = _store(tmp_path); store.close()
    path = tmp_path / "atlas.sqlite"
    _corrupt_global_definition(path, "rule")
    for suffix in ("a", "b", "c"):
        payload = _fake_rule_claim()
        payload["id"] = "snapshot:fake-rule-claim-" + suffix
        _inject_snapshot_row(path, payload["id"], payload)
    reopened = open_store(path)
    assert "coverage:v1" not in reopened.rules
    assert all(("snapshot", "snapshot:fake-rule-claim-" + suffix) in reopened.isolated
               for suffix in ("a", "b", "c"))


def test_r2_3_04_structurally_valid_snapshot_claimant_still_counts(tmp_path):
    store = _store(tmp_path); store.close()
    path = tmp_path / "atlas.sqlite"
    _corrupt_global_definition(path, "rule")
    db = sqlite3.connect(path)
    payload = json.loads(db.execute("SELECT payload FROM records WHERE kind='snapshot' AND id='snapshot:m1'").fetchone()[0])
    payload["id"] = "snapshot:valid-false-claim"
    payload["rule_definitions"][0]["evaluation_supported"] = False
    db.close()
    _inject_snapshot_row(path, payload["id"], payload)
    reopened = open_store(path)
    assert "coverage:v1" in reopened.rules
    assert "snapshot:valid-false-claim" in reopened.snapshots


@pytest.mark.parametrize("mutation", ["missing_id", "missing_definitions", "duplicate_rule",
                                       "malformed_context", "bad_context_id", "unknown_field"])
def test_r2_3_05_malformed_snapshot_variants_do_not_claim(tmp_path, mutation):
    store = _store(tmp_path); store.close()
    path = tmp_path / "atlas.sqlite"
    _corrupt_global_definition(path, "rule")
    db = sqlite3.connect(path)
    payload = json.loads(db.execute("SELECT payload FROM records WHERE kind='snapshot' AND id='snapshot:m1'").fetchone()[0])
    ident = "snapshot:malformed-" + mutation
    payload["id"] = ident
    if mutation == "missing_id": payload.pop("id")
    elif mutation == "missing_definitions": payload.pop("rule_definitions")
    elif mutation == "duplicate_rule": payload["rule_definitions"].append(payload["rule_definitions"][0])
    elif mutation == "malformed_context": payload["context_definitions"][0]["visible_scopes"] = "catalog"
    elif mutation == "bad_context_id": payload["context_definitions"][0]["id"] = "context:other"
    else: payload["unexpected"] = True
    db.close()
    _inject_snapshot_row(path, ident, payload)
    reopened = open_store(path)
    assert "coverage:v1" not in reopened.rules
    assert ("snapshot", ident) in reopened.isolated


def test_r2_3_06_rule_stays_inactive_after_second_reopen(tmp_path):
    store = _store(tmp_path); store.close()
    path = tmp_path / "atlas.sqlite"
    _corrupt_global_definition(path, "rule")
    _inject_snapshot_row(path, "snapshot:fake-rule-claim", _fake_rule_claim())
    first = open_store(path); first.close()
    second = open_store(path)
    assert "coverage:v1" not in second.rules
    assert ("rule", "coverage:v1") in second.isolated


def test_r2_3_07_snapshot_cannot_self_legitimize_invalid_rule(tmp_path):
    store = _store(tmp_path); store.close()
    path = tmp_path / "atlas.sqlite"
    _corrupt_global_definition(path, "rule")
    _inject_snapshot_row(path, "snapshot:fake-rule-claim", _fake_rule_claim())
    reopened = open_store(path)
    reopened.close()
    reopened = open_store(path)
    assert "coverage:v1" not in reopened.rules
    assert all("coverage:v1" not in snapshot.rule_versions for snapshot in reopened.snapshots.values())


def test_r2_3_08_branch_dependent_on_invalid_definition_closes(tmp_path):
    store = _store(tmp_path)
    store.create_decision_scope("decision-scope:ds", "snapshot:m1", "context:m1",
                                "request:q1", _manifest())
    store.evaluate_decision_scope("decision-scope:ds")
    store.close()
    path = tmp_path / "atlas.sqlite"
    _corrupt_global_definition(path, "rule")
    _inject_snapshot_row(path, "snapshot:fake-rule-claim", _fake_rule_claim())
    reopened = open_store(path)
    assert "coverage:v1" not in reopened.rules
    assert "snapshot:m1" not in reopened.snapshots
    assert "decision-scope:ds" not in reopened.decision_scopes
    assert "decision-scope:ds" not in reopened.decision_groundings


def test_r2_3_09_independent_healthy_scope_branch_survives(tmp_path):
    store = _store(tmp_path)
    for ident in ("decision-scope:bad", "decision-scope:healthy"):
        store.create_decision_scope(ident, "snapshot:m1", "context:m1",
                                    "request:q1", _manifest())
        store.evaluate_decision_scope(ident)
    store.close()
    path = tmp_path / "atlas.sqlite"
    db = sqlite3.connect(path)
    db.execute("UPDATE records SET payload=json_set(payload, '$.request', 'request:missing') WHERE kind='decision_scope' AND id='decision-scope:bad'")
    db.commit(); db.close()
    reopened = open_store(path)
    assert "snapshot:m1" in reopened.snapshots
    assert "decision-scope:bad" not in reopened.decision_scopes
    assert "decision-scope:healthy" in reopened.decision_scopes
    assert "decision-scope:healthy" in reopened.decision_groundings


def _r24_clone(path, ident):
    db = sqlite3.connect(path)
    payload = json.loads(db.execute(
        "SELECT payload FROM records WHERE kind='snapshot' AND id='snapshot:m1'"
    ).fetchone()[0])
    payload["id"] = ident
    db.close()
    _inject_snapshot_row(path, ident, payload)
    return payload


def _r24_reopen_with_mutation(tmp_path, mutate):
    store = _store(tmp_path)
    store.close()
    path = tmp_path / "atlas.sqlite"
    payload = _r24_clone(path, "snapshot:r2-4-fake")
    mutate(payload)
    db = sqlite3.connect(path)
    db.execute("UPDATE records SET payload=? WHERE kind='snapshot' AND id=?",
               (json.dumps(payload), "snapshot:r2-4-fake"))
    db.commit(); db.close()
    return open_store(path)


def test_r2_4_01_duplicate_record_ids_is_rejected_and_has_zero_claims(tmp_path):
    reopened = _r24_reopen_with_mutation(tmp_path,
        lambda p: p["record_ids"].append(p["record_ids"][0]))
    assert "snapshot:r2-4-fake" not in reopened.snapshots
    assert ("snapshot", "snapshot:r2-4-fake") in reopened.isolated


@pytest.mark.parametrize("field", ["predicate_versions", "property_versions"])
@pytest.mark.parametrize("versions", [("same", "same"), ("1", "2")])
def test_r2_4_02_and_03_duplicate_vocabulary_identity_is_rejected(tmp_path, field, versions):
    def mutate(payload):
        original = payload[field][0]
        payload[field].append([original[0], original[1] if versions[0] == "same" else versions[1]])
    reopened = _r24_reopen_with_mutation(tmp_path, mutate)
    assert "snapshot:r2-4-fake" not in reopened.snapshots
    assert ("snapshot", "snapshot:r2-4-fake") in reopened.isolated


def test_r2_4_06_unexpected_rule_definition_field_is_rejected(tmp_path):
    reopened = _r24_reopen_with_mutation(tmp_path,
        lambda p: p["rule_definitions"][0].update(unexpected=42))
    assert "snapshot:r2-4-fake" not in reopened.snapshots
    assert ("snapshot", "snapshot:r2-4-fake") in reopened.isolated


def test_r2_4_07_unexpected_context_definition_field_is_rejected(tmp_path):
    reopened = _r24_reopen_with_mutation(tmp_path,
        lambda p: p["context_definitions"][0].update(unexpected=42))
    assert "snapshot:r2-4-fake" not in reopened.snapshots
    assert ("snapshot", "snapshot:r2-4-fake") in reopened.isolated


def test_r2_4_08_duplicate_record_fake_cannot_save_corrupt_rule(tmp_path):
    store = _store(tmp_path); store.close()
    path = tmp_path / "atlas.sqlite"
    _r24_clone(path, "snapshot:r2-4-fake")
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='snapshot' AND id=?",
                     ("snapshot:r2-4-fake",)).fetchone()
    fake = json.loads(row[0]); fake["record_ids"].append(fake["record_ids"][0])
    db.execute("UPDATE records SET payload=json_set(payload, '$.evaluation_supported', 0) "
               "WHERE kind='rule' AND id='coverage:v1'")
    db.execute("UPDATE records SET payload=? WHERE kind='snapshot' AND id=?",
               (json.dumps(fake), "snapshot:r2-4-fake"))
    db.commit(); db.close()
    reopened = open_store(path)
    assert "coverage:v1" not in reopened.rules
    assert ("rule", "coverage:v1") in reopened.isolated
    assert ("snapshot", "snapshot:r2-4-fake") in reopened.isolated


def test_r2_4_09_duplicate_record_fake_cannot_save_corrupt_context(tmp_path):
    store = _store(tmp_path); store.close()
    path = tmp_path / "atlas.sqlite"
    _r24_clone(path, "snapshot:r2-4-fake")
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='snapshot' AND id=?",
                     ("snapshot:r2-4-fake",)).fetchone()
    fake = json.loads(row[0]); fake["record_ids"].append(fake["record_ids"][0])
    db.execute("UPDATE records SET payload=json_set(payload, '$.visible_scopes', json('[\"corrupt\"]')) "
               "WHERE kind='context' AND id='context:m1'")
    db.execute("UPDATE records SET payload=? WHERE kind='snapshot' AND id=?",
               (json.dumps(fake), "snapshot:r2-4-fake"))
    db.commit(); db.close()
    reopened = open_store(path)
    assert "context:m1" not in reopened.contexts
    assert ("context", "context:m1") in reopened.isolated
    assert ("snapshot", "snapshot:r2-4-fake") in reopened.isolated


def test_r2_4_10_canonical_snapshot_and_duplicate_valid_claims_remain_admissible(tmp_path):
    store = _store(tmp_path)
    store.snapshot("snapshot:r2-4-canonical")
    store.close()
    path = tmp_path / "atlas.sqlite"
    _r24_clone(path, "snapshot:r2-4-second-valid")
    reopened = open_store(path)
    assert {"snapshot:m1", "snapshot:r2-4-canonical", "snapshot:r2-4-second-valid"} <= set(reopened.snapshots)


def test_r2_4_admission_snapshot_model_rejects_noncanonical_collections():
    with pytest.raises(ValidationError):
        Snapshot(SnapshotId("snapshot:bad"), None,
                 (KnowledgeId("fact:a"), KnowledgeId("fact:a")))


@pytest.mark.parametrize("raw_parent", [False, True, 0, 1, [], {}])
def test_r2_5_non_exact_snapshot_parent_has_zero_claim_authority(tmp_path, raw_parent):
    store = _store(tmp_path); store.close()
    path = tmp_path / "atlas.sqlite"
    _corrupt_global_definition(path, "rule")
    payload = _r24_clone(path, "snapshot:r2-5-bad-parent")
    payload["parent"] = raw_parent
    _rewrite_snapshot(path, "snapshot:r2-5-bad-parent", payload)
    reopened = open_store(path)
    assert "snapshot:r2-5-bad-parent" not in reopened.snapshots
    assert ("snapshot", "snapshot:r2-5-bad-parent") in reopened.isolated
    assert "coverage:v1" not in reopened.rules
    assert ("rule", "coverage:v1") in reopened.isolated


def _rewrite_snapshot(path, ident, payload):
    db = sqlite3.connect(path)
    db.execute("UPDATE records SET payload=? WHERE kind='snapshot' AND id=?",
               (json.dumps(payload), ident))
    db.commit(); db.close()


def test_r2_5_null_parent_and_exact_version_pairs_remain_canonical(tmp_path):
    reopened = _r24_reopen_with_mutation(tmp_path, lambda p: None)
    assert "snapshot:r2-4-fake" in reopened.snapshots
    assert reopened.snapshots["snapshot:r2-4-fake"].parent is None


def test_r2_5_valid_parent_string_remains_canonical(tmp_path):
    store = _store(tmp_path)
    store.snapshot("snapshot:r2-5-parent", parent="snapshot:m1")
    store.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert reopened.snapshots["snapshot:r2-5-parent"].parent == SnapshotId("snapshot:m1")


@pytest.mark.parametrize("field,bad_value", [
    ("rule_versions", ["r1"]),
    ("rule_versions", [["r"]]),
    ("rule_versions", [["r", "1", "extra"]]),
    ("rule_versions", [[1, "1"]]),
    ("rule_versions", [["r", 1]]),
    ("predicate_versions", ["p1"]),
    ("property_versions", ["p1"]),
])
def test_r2_5_non_exact_version_pairs_have_zero_claim_authority(tmp_path, field, bad_value):
    store = _store(tmp_path); store.close()
    path = tmp_path / "atlas.sqlite"
    _corrupt_global_definition(path, "rule")
    payload = _r24_clone(path, "snapshot:r2-5-bad-pair")
    payload[field] = bad_value
    _rewrite_snapshot(path, "snapshot:r2-5-bad-pair", payload)
    reopened = open_store(path)
    assert "snapshot:r2-5-bad-pair" not in reopened.snapshots
    assert ("snapshot", "snapshot:r2-5-bad-pair") in reopened.isolated
    assert "coverage:v1" not in reopened.rules
    assert ("rule", "coverage:v1") in reopened.isolated


@pytest.mark.parametrize("field", ["description_ids", "context_ids", "rule_versions"])
def test_r2_5_duplicate_snapshot_identity_lists_remain_isolated(tmp_path, field):
    reopened = _r24_reopen_with_mutation(
        tmp_path, lambda p: p[field].append(p[field][0]))
    assert "snapshot:r2-4-fake" not in reopened.snapshots
    assert ("snapshot", "snapshot:r2-4-fake") in reopened.isolated


@pytest.mark.parametrize("field", ["context_definitions", "rule_definitions"])
def test_r2_5_duplicate_snapshot_definitions_remain_isolated(tmp_path, field):
    reopened = _r24_reopen_with_mutation(
        tmp_path, lambda p: p[field].append(dict(p[field][0])))
    assert "snapshot:r2-4-fake" not in reopened.snapshots
    assert ("snapshot", "snapshot:r2-4-fake") in reopened.isolated
