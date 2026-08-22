"""Adversarial certificate for the pure M1e.2.1 effective snapshot view."""

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
import pytest
from atlas.evidence import evidence_for
from atlas.problem import decision_payload, validate_persisted_decision
from atlas.scope import grounding_payload

from atlas import *


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def base(tmp_path):
    data = json.loads(FIXTURE.read_text())
    # Discovery regressions below add their own relations; keep the fixture's
    # baseline relations out of those isolated effective-view scenarios.
    data["relations"] = []
    for fact in data["facts"]:
        if fact["id"] == "fact:r1-cost": fact["value"]["value"] = "100"
        if fact["id"] == "fact:r2-cost": fact["value"]["value"] = "50"
    return admit_fixture(open_store(tmp_path / "atlas.sqlite"), data)


def property_payload(ident, description, value, property_id="cost"):
    if property_id == "cost":
        encoded = {"kind": "integer", "value": str(value)}
    elif property_id == "available-capabilities":
        encoded = {"kind": "finite_set<symbol>", "items": str(value).split(",")}
    else:
        encoded = {"kind": "symbol", "value": str(value)}
    return {"kind": "property", "payload": {
        "id": ident, "description": description, "property": property_id,
        "version": "1", "value": encoded, "scope": "catalog",
        "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}


def add_property(store, ident, description, value, property_id="cost"):
    store.admit([property_payload(ident, description, value, property_id)])


def relation_payload(ident, candidate, request="intent:selection", scope="catalog"):
    return {"kind": "relation", "payload": {
        "id": ident, "predicate": "realizes", "version": "1",
        "participants": [candidate, request], "polarity": "positive",
        "scope": scope, "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}


def add_scan_relation(store, ident, candidate="realization:r2", scope="catalog"):
    store.admit([relation_payload(ident, candidate, scope=scope)])


def relation_scope(store, scope_id, snapshot, candidates=("realization:r2",), context="context:m1"):
    manifest = GroundingManifest("m1-grounding/1", tuple(DescriptionId(x) for x in candidates),
                                 (RuleId("coverage:v1"),))
    scope = store.create_decision_scope(scope_id, snapshot, context, "request:q1", manifest)
    return store.evaluate_decision_scope(scope.id)


def costs(store, snapshot):
    return {record.description.value: record.value.value
            for record in store.find(kind="property", snapshot=snapshot)
            if record.property == PropertyId("cost")}


def test_scenario_a_effective_view_and_historical_identity(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    add_property(store, "DEEP_THOUGHT-cost-v2", "realization:r2", 120)
    store.snapshot("S2", parent="S1")
    store.supersede("fact:r2-cost", "DEEP_THOUGHT-cost-v2", "S2")

    assert costs(store, "S1")["realization:r2"] == 50
    assert costs(store, "S2")["realization:r1"] == 100
    assert costs(store, "S2")["realization:r2"] == 120
    assert "fact:r2-cost" in store.records
    assert store.read("fact:r2-cost", "S1").value.value == 50


def test_chain_resolves_only_the_terminal_record(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    add_property(store, "deep-cost-80", "realization:r2", 80)
    store.snapshot("S2", parent="S1")
    store.supersede("fact:r2-cost", "deep-cost-80", "S2")
    add_property(store, "deep-cost-120", "realization:r2", 120)
    store.snapshot("S3", parent="S2")
    store.supersede("deep-cost-80", "deep-cost-120", "S3")

    assert costs(store, "S1")["realization:r2"] == 50
    assert costs(store, "S2")["realization:r2"] == 80
    assert costs(store, "S3")["realization:r2"] == 120
    assert len([x for x in store.find(kind="property", snapshot="S3")
                if x.description == DescriptionId("realization:r2")
                and x.property == PropertyId("cost")]) == 1


def test_sibling_does_not_inherit_supersession_branch(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    add_property(store, "deep-cost-120", "realization:r2", 120)
    store.snapshot("S2A", parent="S1")
    store.snapshot("S2B", parent="S1")
    store.supersede("fact:r2-cost", "deep-cost-120", "S2A")

    assert costs(store, "S2A")["realization:r2"] == 120
    assert costs(store, "S2B")["realization:r2"] == 50


def test_unrelated_supersession_and_ordinary_new_fact(tmp_path):
    store = base(tmp_path)
    add_property(store, "quick-overview-v2", "realization:r1", "v2", "unused-property")
    add_property(store, "mystery-box-answer", "realization:r1", "available", "unused-property")
    store.snapshot("S2", parent="snapshot:m1")
    store.supersede("fact:r1-unused", "quick-overview-v2", "S2")

    assert costs(store, "S2")["realization:r2"] == 50
    effective = {record.id.value for record in store.find(snapshot="S2")}
    assert "mystery-box-answer" in effective


def test_ground_uses_effective_view_without_ambiguous_read(tmp_path):
    store = base(tmp_path)
    add_property(store, "deep-capabilities-v2", "realization:r2", "a,b", "available-capabilities")
    store.snapshot("S2", parent="snapshot:m1")
    store.supersede("fact:r2-capabilities", "deep-capabilities-v2", "S2")
    before = (store.decision_scopes.copy(), store.decision_groundings.copy(),
              store.grounded_decision_problems.copy(), store.decisions.copy())

    result = store.ground("coverage:v1", {"candidate": DescriptionId("realization:r2"),
                                          "request": DescriptionId("request:q1")},
                          "S2", "context:m1")
    assert result.truth is EvaluationTruth.TRUE
    assert result.ambiguous_reads == ()
    assert KnowledgeId("deep-capabilities-v2") in result.effective_dependencies
    assert (store.decision_scopes, store.decision_groundings,
            store.grounded_decision_problems, store.decisions) == before


def test_real_ambiguity_is_not_hidden_by_effective_view(tmp_path):
    store = base(tmp_path)
    add_property(store, "second-r2-capabilities", "realization:r2", "other", "available-capabilities")
    store.snapshot("S2", parent="snapshot:m1")
    result = store.ground("coverage:v1", {"candidate": DescriptionId("realization:r2"),
                                          "request": DescriptionId("request:q1")},
                          "S2", "context:m1")
    assert result.truth is EvaluationTruth.UNKNOWN
    assert len(result.ambiguous_reads) == 1


def test_invalid_isolated_supersession_is_ignored(tmp_path):
    store = base(tmp_path)
    store.snapshot("S2", parent="snapshot:m1")
    store._persist("supersession", "supersession:isolated", {
        "schema": "atlas.core-v1.supersession/1", "id": "supersession:isolated",
        "old": "fact:r2-cost", "new": "missing-new", "snapshot": "S2"})
    store._db.commit()
    store.close()
    restored = open_store(tmp_path / "atlas.sqlite")
    assert costs(restored, "S2")["realization:r2"] == 50


def test_restart_order_independence_and_purity(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    add_property(store, "deep-cost-120", "realization:r2", 120)
    store.snapshot("S2", parent="S1")
    store.supersede("fact:r2-cost", "deep-cost-120", "S2")
    records_before = store.records.copy()
    snapshots_before = store.snapshots.copy()
    edges_before = store.supersessions.copy()
    first = tuple(record.id.value for record in store.find(snapshot="S2"))
    second = tuple(record.id.value for record in reversed(store.records.values())
                   if record.id in set(store._effective_record_ids("S2")))
    assert set(first) == set(second)
    assert store.records == records_before
    assert store.snapshots == snapshots_before
    assert store.supersessions == edges_before
    store.close()
    restored = open_store(tmp_path / "atlas.sqlite")
    assert {record.id.value for record in restored.find(snapshot="S2")} == set(first)


def test_exact_historical_read_remains_physical(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    add_property(store, "deep-cost-120", "realization:r2", 120)
    store.snapshot("S2", parent="S1")
    store.supersede("fact:r2-cost", "deep-cost-120", "S2")
    assert store.read("fact:r2-cost", "S2").value.value == 50
    assert store.read("deep-cost-120", "S2").value.value == 120


def test_stale_derived_relation_is_hidden_but_exact_history_remains(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    result = store.ground("coverage:v1", {"candidate": DescriptionId("realization:r2"),
                                           "request": DescriptionId("request:q1")},
                          "S1", "context:m1")
    store.admit_derived("derived:R1", result)
    store.snapshot("S1-derived", parent="S1")
    add_property(store, "r2-capabilities-v2", "realization:r2", "a", "available-capabilities")
    store.snapshot("S2", parent="S1-derived")
    store.supersede("fact:r2-capabilities", "r2-capabilities-v2", "S2")

    assert "derived:R1" not in {x.id.value for x in store.find(kind="relation", snapshot="S2")}
    assert store.read("derived:R1", "S1-derived") is not None
    assert store.read("derived:R1", "S2") is not None


def test_stale_derivation_closure_is_transitive_and_historical(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    first = store.ground("coverage:v1", {"candidate": DescriptionId("realization:r2"),
                                         "request": DescriptionId("request:q1")},
                        "S1", "context:m1")
    store.admit_derived("derived:R1", first)
    store.snapshot("S1-derived", parent="S1")
    second = replace(first,
                     effective_dependencies=(KnowledgeId("derived:R1"),),
                     conclusion=replace(first.conclusion,
                                        dependencies=(KnowledgeId("derived:R1"),)),
                     snapshot=SnapshotId("S1-derived"))
    second = replace(second, grounding_evidence=evidence_for(second, ("candidate", "request")))
    store.admit_derived("derived:R2", second)
    store.snapshot("S1-derived2", parent="S1-derived")
    add_property(store, "r2-capabilities-v2", "realization:r2", "a", "available-capabilities")
    store.snapshot("S2", parent="S1-derived2")
    store.supersede("fact:r2-capabilities", "r2-capabilities-v2", "S2")

    effective = {x.id.value for x in store.find(kind="relation", snapshot="S2")}
    assert not {"derived:R1", "derived:R2"} & effective
    historical = {x.id.value for x in store.find(kind="relation", snapshot="S1-derived2")}
    assert {"derived:R1", "derived:R2"} <= historical
    store.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert {x.id.value for x in reopened.find(kind="relation", snapshot="S2")} == effective
    assert {"derived:R1", "derived:R2"} <= {
        x.id.value for x in reopened.find(kind="relation", snapshot="S1-derived2")}


def test_new_gdp_uses_effective_objective_but_old_gdp_stays_historical(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:r2-selection")
    store.snapshot("S1")
    manifest = GroundingManifest("m1-grounding/1",
                                 (DescriptionId("realization:r1"), DescriptionId("realization:r2")),
                                 (RuleId("coverage:v1"),))
    old_scope = store.create_decision_scope("scope:S1", "S1", "context:m1", "request:q1", manifest)
    store.evaluate_decision_scope(old_scope.id)
    old_problem = store.ground_decision_problem(old_scope.id)
    store.admit_grounded_decision_problem("problem:S1", old_problem)
    store.admit_m1_decision("decision:S1", store.select_m1("problem:S1"))

    add_property(store, "r2-cost-v2", "realization:r2", 120)
    store.snapshot("S2", parent="S1")
    store.supersede("fact:r2-cost", "r2-cost-v2", "S2")
    new_scope = store.create_decision_scope("scope:S2", "S2", "context:m1", "request:q1", manifest)
    store.evaluate_decision_scope(new_scope.id)
    new_problem = store.ground_decision_problem(new_scope.id)
    objective = next(x.objective_value for x in new_problem.candidates
                     if x.candidate == DescriptionId("realization:r2"))
    assert objective.knowledge_id == KnowledgeId("r2-cost-v2")
    assert objective.value.value == 120
    validate_persisted_decision(store, store.decision("decision:S1"))
    assert store.explain_m1("decision:S1").candidates[1].objective_value.value.value == 50


def test_new_gdp_keeps_real_objective_ambiguity(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:r2-selection")
    store.snapshot("S1")
    add_property(store, "r2-cost-X", "realization:r2", 80)
    store.snapshot("S2", parent="S1")
    manifest = GroundingManifest("m1-grounding/1",
                                 (DescriptionId("realization:r2"),),
                                 (RuleId("coverage:v1"),))
    scope = store.create_decision_scope("scope:ambiguous", "S2", "context:m1", "request:q1", manifest)
    store.evaluate_decision_scope(scope.id)
    with pytest.raises(GroundingError, match="ambiguous"):
        store.ground_decision_problem(scope.id)


def test_g_ghost_does_not_appear_in_effective_discovery_evidence(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:deep-v1")
    store.snapshot("S1", parent="snapshot:m1")
    s1 = relation_scope(store, "scope:S1", "S1")
    assert s1.observations[0].discovery_evidence.found == (KnowledgeId("rel:deep-v1"),)
    add_scan_relation(store, "rel:deep-v2")
    store.snapshot("S2", parent="S1")
    store.supersede("rel:deep-v1", "rel:deep-v2", "S2")
    grounding = relation_scope(store, "scope:S2", "S2")
    evidence = grounding.observations[0].discovery_evidence
    assert evidence.found == (KnowledgeId("rel:deep-v2"),)
    assert evidence.included == evidence.found
    assert evidence.excluded == ()
    assert KnowledgeId("rel:deep-v1") not in evidence.found


def test_h_wrong_door_records_found_and_structured_context_exclusion(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:hidden", scope="private")
    store.snapshot("S2", parent="snapshot:m1")
    grounding = relation_scope(store, "scope:H", "S2")
    evidence = grounding.observations[0].discovery_evidence
    assert evidence.found == (KnowledgeId("rel:hidden"),)
    assert evidence.included == ()
    assert evidence.excluded == (DiscoveryExclusion(KnowledgeId("rel:hidden"),
                                                     DiscoveryExclusionReason.OUTSIDE_CONTEXT),)


def test_h_exclusion_is_not_an_admissible_gdp_candidate_or_false(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:hidden", scope="private")
    store.snapshot("S2", parent="snapshot:m1")
    scope = store.create_decision_scope(
        "scope:H-gdp", "S2", "context:m1", "request:q1",
        GroundingManifest("m1-grounding/1", (DescriptionId("realization:r2"),),
                          (RuleId("coverage:v1"),)))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    candidate = problem.candidates[0]
    assert candidate.truth is EvaluationTruth.TRUE
    assert candidate.exclusion_reason == "excluded_by_context"
    assert candidate.objective_value is None
    store.admit_grounded_decision_problem("problem:H-gdp", problem)
    assert store.select_m1("problem:H-gdp").status is SelectionStatus.NO_ADMISSIBLE_CANDIDATE


def test_empty_found_true_is_no_admissible_candidate(tmp_path):
    store = base(tmp_path)
    store.snapshot("S2", parent="snapshot:m1")
    scope = store.create_decision_scope(
        "scope:empty-gdp", "S2", "context:m1", "request:q1",
        GroundingManifest("m1-grounding/1", (DescriptionId("realization:r2"),),
                          (RuleId("coverage:v1"),)))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    assert problem.candidates[0].truth is EvaluationTruth.TRUE
    assert problem.candidates[0].exclusion_reason == "excluded_by_context"
    store.admit_grounded_decision_problem("problem:empty-gdp", problem)
    assert store.select_m1("problem:empty-gdp").status is SelectionStatus.NO_ADMISSIBLE_CANDIDATE


def test_mixed_relation_support_keeps_candidate_in_scope(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:hidden", scope="private")
    add_scan_relation(store, "rel:visible", scope="catalog")
    store.snapshot("S2", parent="snapshot:m1")
    scope = store.create_decision_scope(
        "scope:mixed", "S2", "context:m1", "request:q1",
        GroundingManifest("m1-grounding/1", (DescriptionId("realization:r2"),),
                          (RuleId("coverage:v1"),)))
    store.evaluate_decision_scope(scope.id)
    evidence = store.decision_grounding(scope.id).observations[0].discovery_evidence
    assert evidence.found == (KnowledgeId("rel:hidden"), KnowledgeId("rel:visible"))
    assert evidence.included == (KnowledgeId("rel:visible"),)
    assert evidence.excluded == (DiscoveryExclusion(KnowledgeId("rel:hidden"),
                                                    DiscoveryExclusionReason.OUTSIDE_CONTEXT),)
    problem = store.ground_decision_problem(scope.id)
    assert problem.candidates[0].exclusion_reason is None
    store.admit_grounded_decision_problem("problem:mixed", problem)
    assert store.select_m1("problem:mixed").status is SelectionStatus.RESOLVED


def test_excluded_unknown_does_not_block_included_true(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:r2-hidden", candidate="realization:r2", scope="private")
    add_scan_relation(store, "rel:r1-visible", candidate="realization:r1")
    add_property(store, "r2-capabilities-extra", "realization:r2", "other", "available-capabilities")
    add_property(store, "r1-capabilities-v2", "realization:r1", "a,b", "available-capabilities")
    store.snapshot("S2", parent="snapshot:m1")
    store.supersede("fact:r1-capabilities", "r1-capabilities-v2", "S2")
    scope = store.create_decision_scope(
        "scope:excluded-unknown", "S2", "context:m1", "request:q1",
        GroundingManifest("m1-grounding/1", (DescriptionId("realization:r2"), DescriptionId("realization:r1")),
                          (RuleId("coverage:v1"),)))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    assert problem.candidates[0].truth is EvaluationTruth.UNKNOWN
    assert problem.candidates[0].exclusion_reason == "excluded_by_context"
    assert problem.candidates[1].truth is EvaluationTruth.TRUE
    store.admit_grounded_decision_problem("problem:excluded-unknown", problem)
    assert store.select_m1("problem:excluded-unknown").status is SelectionStatus.RESOLVED


def test_included_unknown_still_needs_information(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:r2-visible", candidate="realization:r2")
    add_property(store, "r2-capabilities-extra", "realization:r2", "other", "available-capabilities")
    store.snapshot("S2", parent="snapshot:m1")
    scope = store.create_decision_scope(
        "scope:included-unknown", "S2", "context:m1", "request:q1",
        GroundingManifest("m1-grounding/1", (DescriptionId("realization:r2"),),
                          (RuleId("coverage:v1"),)))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    store.admit_grounded_decision_problem("problem:included-unknown", problem)
    assert store.select_m1("problem:included-unknown").status is SelectionStatus.NEEDS_INFORMATION


def test_discovery_is_not_rerun_as_post_hoc_evidence_scan(tmp_path, monkeypatch):
    store = base(tmp_path)
    add_scan_relation(store, "rel:causal")
    store.snapshot("S2", parent="snapshot:m1")
    import atlas.scope as scope_module
    calls = 0
    original = scope_module.discover_relation

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(scope_module, "discover_relation", counted)
    grounding = relation_scope(store, "scope:causal", "S2")
    assert grounding.observations[0].discovery_evidence is not None
    # Evaluation discovers once; completeness validation recomputes the
    # certificate as an exact pure equality check.
    assert calls == 2


def test_discovery_query_uses_core_intention_not_request(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:core")
    store.snapshot("S2", parent="snapshot:m1")
    evidence = relation_scope(store, "scope:query", "S2").observations[0].discovery_evidence
    assert evidence.query.participants == (DescriptionId("realization:r2"),
                                           DescriptionId("intent:selection"))


def test_empty_scope_discovery_does_not_claim_to_certify_grounding_truth(tmp_path):
    store = base(tmp_path)
    store.snapshot("S2", parent="snapshot:m1")
    grounding = relation_scope(store, "scope:empty-discovery", "S2")
    observation = grounding.observations[0]
    assert observation.discovery_evidence.found == ()
    assert observation.truth is EvaluationTruth.TRUE
    assert observation.exclusion_reason == "excluded_by_context"


def test_unknown_discovery_exclusion_key_isolated_on_reload(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:hidden", scope="private")
    store.snapshot("S2", parent="snapshot:m1")
    relation_scope(store, "scope:closed-exclusion", "S2")
    store.close()
    import sqlite3
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    row = db.execute("SELECT payload FROM records WHERE kind='decision_grounding' AND id='scope:closed-exclusion'").fetchone()
    payload = json.loads(row[0])
    payload["observations"][0]["discovery_evidence"]["excluded"][0]["extra"] = "unknown"
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding' AND id='scope:closed-exclusion'",
               (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert ("decision_grounding", "scope:closed-exclusion") in reopened.isolated
    assert reopened.decision_groundings == {}


def test_sibling_snapshots_have_independent_discovery_certificates(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:old")
    store.snapshot("S1", parent="snapshot:m1")
    add_scan_relation(store, "rel:new")
    store.snapshot("S2A", parent="S1")
    store.snapshot("S2B", parent="S1")
    store.supersede("rel:old", "rel:new", "S2A")
    a = relation_scope(store, "scope:A", "S2A").observations[0].discovery_evidence
    b = relation_scope(store, "scope:B", "S2B").observations[0].discovery_evidence
    assert a.found == (KnowledgeId("rel:new"),)
    assert b.found == (KnowledgeId("rel:old"),)


def test_new_ordinary_relation_and_stale_derived_relation_follow_effective_view(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1", parent="snapshot:m1")
    first = store.ground("coverage:v1", {"candidate": DescriptionId("realization:r2"),
                                         "request": DescriptionId("request:q1")}, "S1", "context:m1")
    store.admit_derived("derived:scan", first)
    add_scan_relation(store, "rel:ordinary")
    add_property(store, "r2-capabilities-v2", "realization:r2", "a", "available-capabilities")
    store.snapshot("S2", parent="S1")
    store.supersede("fact:r2-capabilities", "r2-capabilities-v2", "S2")
    grounding = relation_scope(store, "scope:ordinary", "S2").observations[0].discovery_evidence
    assert grounding.found == (KnowledgeId("rel:ordinary"),)
    assert KnowledgeId("derived:scan") not in grounding.found


@pytest.mark.parametrize("mutation", ["found", "included", "excluded", "overlap", "reason", "query"])
def test_persisted_discovery_falsification_isolated_on_reload(tmp_path, mutation):
    store = base(tmp_path)
    add_scan_relation(store, "rel:valid")
    store.snapshot("S2", parent="snapshot:m1")
    scope = relation_scope(store, "scope:falsified", "S2")
    store.close()
    import sqlite3
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    row = db.execute("SELECT payload FROM records WHERE kind='decision_grounding' AND id='scope:falsified'").fetchone()
    payload = json.loads(row[0]); evidence = payload["observations"][0]["discovery_evidence"]
    if mutation == "found": evidence["found"] = ["rel:valid", "rel:ghost"]
    elif mutation == "included": evidence["included"] = ["rel:old"]
    elif mutation == "excluded": evidence["excluded"] = [{"knowledge_id": "rel:old", "reason": "outside_context"}]
    elif mutation == "overlap": evidence["excluded"] = [{"knowledge_id": "rel:valid", "reason": "outside_context"}]
    elif mutation == "reason": evidence["excluded"] = [{"knowledge_id": "rel:valid", "reason": "not-a-reason"}]
    elif mutation == "query": evidence["query"]["version"] = "999"
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding' AND id='scope:falsified'", (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert ("decision_grounding", "scope:falsified") in reopened.isolated
    assert reopened.decision_groundings == {}


@pytest.mark.parametrize("mutation", ["omission", "reclassification"])
def test_semantically_well_formed_discovery_falsifications_are_isolated(tmp_path, mutation):
    store = base(tmp_path)
    add_scan_relation(store, "rel:visible")
    store.snapshot("S2", parent="snapshot:m1")
    relation_scope(store, "scope:semantic-falsification", "S2")
    store.close()
    import sqlite3
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    row = db.execute("SELECT payload FROM records WHERE kind='decision_grounding' AND id='scope:semantic-falsification'").fetchone()
    payload = json.loads(row[0])
    evidence = payload["observations"][0]["discovery_evidence"]
    if mutation == "omission":
        evidence["found"] = []
        evidence["included"] = []
    else:
        evidence["included"] = []
        evidence["excluded"] = [{"knowledge_id": "rel:visible", "reason": "outside_context"}]
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding' AND id='scope:semantic-falsification'",
               (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(tmp_path / "atlas.sqlite")
    assert ("decision_grounding", "scope:semantic-falsification") in reopened.isolated
    assert reopened.decision_groundings == {}


def test_current_grounding_is_explicitly_versioned_and_survives_restart(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:versioned")
    store.snapshot("S2", parent="snapshot:m1")
    relation_scope(store, "scope:versioned", "S2")
    path = store.path
    assert json.loads(store._db.execute(
        "SELECT payload FROM records WHERE kind='decision_grounding' AND id='scope:versioned'"
    ).fetchone()[0])["schema"] == "atlas.core-v1.decision-grounding/2"
    store.close()
    reopened = open_store(path)
    assert reopened.decision_grounding("scope:versioned").schema == "atlas.core-v1.decision-grounding/2"
    assert reopened.decision_grounding("scope:versioned").observations[0].discovery_evidence is not None


def test_v2_admission_matches_restore_for_forged_legacy_outcome(tmp_path):
    """A v2 GDP rejects legacy NEEDS_INFORMATION at admission and restore."""
    store = base(tmp_path)
    store.snapshot("S2", parent="snapshot:m1")
    scope = store.create_decision_scope(
        "scope:admission-parity", "S2", "context:m1", "request:q1",
        GroundingManifest("m1-grounding/1", (DescriptionId("realization:r2"),),
                          (RuleId("coverage:v1"),)))
    store.evaluate_decision_scope(scope.id)
    assert store.decision_grounding(scope.id).schema == "atlas.core-v1.decision-grounding/2"
    problem = store.ground_decision_problem(scope.id)
    store.admit_grounded_decision_problem("problem:admission-parity", problem)
    valid = store.select_m1("problem:admission-parity")
    assert valid.status is SelectionStatus.NO_ADMISSIBLE_CANDIDATE
    forged = replace(valid, status=SelectionStatus.NEEDS_INFORMATION)

    with pytest.raises(GroundingError):
        store.admit_m1_decision("decision:forged", forged)
    assert "decision:forged" not in store.decisions
    assert store._db.execute(
        "SELECT COUNT(*) FROM records WHERE kind='decision' AND id='decision:forged'"
    ).fetchone()[0] == 0

    path = store.path
    store.close()
    db = sqlite3.connect(path)
    db.execute("INSERT INTO records(id,kind,payload) VALUES(?,?,?)", (
        "decision:forged", "decision", json.dumps(decision_payload(
            Decision(DecisionId("decision:forged"), DecisionProblemId("problem:admission-parity"),
                     SelectionStatus.NEEDS_INFORMATION, None, ())))))
    db.commit()
    db.close()
    reopened = open_store(path)
    assert ("decision", "decision:forged") in reopened.isolated
    assert "decision:forged" not in reopened.decisions


def test_current_grounding_without_evidence_is_not_legacy(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:versioned")
    store.snapshot("S2", parent="snapshot:m1")
    relation_scope(store, "scope:versioned", "S2")
    path = store.path
    store.close()
    db = sqlite3.connect(path)
    payload = json.loads(db.execute(
        "SELECT payload FROM records WHERE kind='decision_grounding' AND id='scope:versioned'"
    ).fetchone()[0])
    payload["observations"][0].pop("discovery_evidence")
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding' AND id='scope:versioned'", (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(path)
    assert ("decision_grounding", "scope:versioned") in reopened.isolated
    assert not reopened.decision_groundings


def test_legacy_grounding_shape_is_closed_and_skips_current_discovery_semantics(tmp_path):
    store = base(tmp_path)
    add_scan_relation(store, "rel:hidden", scope="private")
    store.snapshot("S2", parent="snapshot:m1")
    scope = store.create_decision_scope(
        "scope:legacy", "S2", "context:m1", "request:q1",
        GroundingManifest("m1-grounding/1", (DescriptionId("realization:r2"),), (RuleId("coverage:v1"),)))
    store.evaluate_decision_scope(scope.id)
    path = store.path
    store.close()
    db = sqlite3.connect(path)
    row = db.execute("SELECT payload FROM records WHERE kind='decision_grounding' AND id='scope:legacy'").fetchone()
    payload = json.loads(row[0]); payload.pop("schema")
    for observation in payload["observations"]:
        observation.pop("discovery_evidence")
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding' AND id='scope:legacy'", (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(path)
    assert reopened.decision_grounding("scope:legacy").schema == "atlas.core-v1.decision-grounding/1"


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema="atlas.core-v1.decision-grounding/999"),
    lambda p: p.update(legacy_key=True),
])
def test_unknown_or_incoherent_grounding_schema_isolated(tmp_path, mutation):
    store = base(tmp_path)
    add_scan_relation(store, "rel:versioned")
    store.snapshot("S2", parent="snapshot:m1")
    relation_scope(store, "scope:versioned", "S2")
    path = store.path
    store.close()
    db = sqlite3.connect(path)
    payload = json.loads(db.execute("SELECT payload FROM records WHERE kind='decision_grounding' AND id='scope:versioned'").fetchone()[0])
    mutation(payload)
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding' AND id='scope:versioned'", (json.dumps(payload),))
    db.commit(); db.close()
    reopened = open_store(path)
    assert ("decision_grounding", "scope:versioned") in reopened.isolated
