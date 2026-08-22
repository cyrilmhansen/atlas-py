"""V1-R1.1: FIND_RELEVANT_MAIL, end-to-end through Core V1."""

import json
import sqlite3

from atlas import (
    ArtifactStatus,
    DescriptionId,
    EvaluationTruth,
    GroundingManifest,
    KnowledgeId,
    RuleId,
    open_store,
    admit_fixture,
)
from atlas.scope import scope_payload


def _mail_search_knowledge():
    """The small, readable business description used by this proof."""
    return {
        "schema": "atlas.conformance.core-v1/1",
        "fixture_id": "v1-r1-mail-search",
        "description": "local mail archive search",
        "vocabulary": {
            "predicates": [
                {"id": "realizes", "version": "1", "arity": 2,
                 "roles": ["realization", "intention"]},
                {"id": "covers", "version": "1", "arity": 2,
                 "roles": ["candidate", "request"]},
            ],
            "properties": [
                {"id": "search-requirements", "version": "1",
                 "value": "finite_set<symbol>"},
                {"id": "available-capabilities", "version": "1",
                 "value": "finite_set<symbol>"},
                {"id": "cost", "version": "1", "value": "integer"},
            ],
        },
        "descriptions": [
            {"id": "FIND_RELEVANT_MAIL", "label": "find relevant mail"},
            {"id": "MAIL_SEARCH_REQUEST", "label": "mail search request"},
            {"id": "SIMPLE_SCAN", "label": "simple scan"},
            {"id": "FULL_TEXT_INDEX", "label": "full text index"},
        ],
        "sources": [
            {"id": "source:mail-search-benchmark-v1"},
            {"id": "source:mail-search-benchmark-v2"},
        ],
        "facts": [
            {"id": "knowledge:request-capabilities", "kind": "property",
             "description": "MAIL_SEARCH_REQUEST", "property": "search-requirements",
             "value": {"kind": "finite_set<symbol>",
                       "items": ["SEARCH_SUBJECT", "SEARCH_BODY"]},
             "scope": "mail-archive", "epistemic_status": "exact",
             "provenance": ["source:mail-search-benchmark-v1"]},
            {"id": "knowledge:simple-scan-capabilities", "kind": "property",
             "description": "SIMPLE_SCAN", "property": "available-capabilities",
             "value": {"kind": "finite_set<symbol>",
                       "items": ["SEARCH_SUBJECT", "SEARCH_BODY"]},
             "scope": "mail-archive", "epistemic_status": "exact",
             "provenance": ["source:mail-search-benchmark-v1"]},
            {"id": "knowledge:full-text-index-capabilities", "kind": "property",
             "description": "FULL_TEXT_INDEX", "property": "available-capabilities",
             "value": {"kind": "finite_set<symbol>",
                       "items": ["SEARCH_SUBJECT", "SEARCH_BODY", "RANK_RESULTS"]},
             "scope": "mail-archive", "epistemic_status": "exact",
             "provenance": ["source:mail-search-benchmark-v1"]},
            {"id": "knowledge:simple-scan-cost-s1", "kind": "property",
             "description": "SIMPLE_SCAN", "property": "cost",
             "value": {"kind": "integer", "value": "100"},
             "scope": "mail-archive", "epistemic_status": "exact",
             "provenance": ["source:mail-search-benchmark-v1"]},
            {"id": "knowledge:full-text-index-cost-s1", "kind": "property",
             "description": "FULL_TEXT_INDEX", "property": "cost",
             "value": {"kind": "integer", "value": "40"},
             "scope": "mail-archive", "epistemic_status": "exact",
             "provenance": ["source:mail-search-benchmark-v1"]},
        ],
        "relations": [
            {"id": "knowledge:simple-scan-realizes", "predicate": "realizes",
             "version": "1", "participants": ["SIMPLE_SCAN", "FIND_RELEVANT_MAIL"],
             "polarity": "positive", "scope": "mail-archive",
             "epistemic_status": "exact", "provenance": ["source:mail-search-benchmark-v1"]},
            {"id": "knowledge:full-text-index-realizes", "predicate": "realizes",
             "version": "1", "participants": ["FULL_TEXT_INDEX", "FIND_RELEVANT_MAIL"],
             "polarity": "positive", "scope": "mail-archive",
             "epistemic_status": "exact", "provenance": ["source:mail-search-benchmark-v1"]},
            {"id": "knowledge:simple-scan-realizes-request", "predicate": "realizes",
             "version": "1", "participants": ["SIMPLE_SCAN", "MAIL_SEARCH_REQUEST"],
             "polarity": "positive", "scope": "mail-archive",
             "epistemic_status": "exact", "provenance": ["source:mail-search-benchmark-v1"]},
        ],
        "rules": [{
            "id": "mail-search:capability-coverage", "version": "1",
            "participants": ["candidate", "request"],
            "when": {"op": "set_subset",
                     "left": {"op": "property", "participant": "request",
                              "property": "search-requirements"},
                     "right": {"op": "property", "participant": "candidate",
                               "property": "available-capabilities"}},
            "head": {"predicate": "covers", "version": "1",
                     "participants": ["candidate", "request"], "polarity": "positive"},
        }],
        "contexts": [{"id": "context:mail-search", "visible_scopes": ["mail-archive"],
                       "enabled_rules": ["mail-search:capability-coverage"]}],
        "snapshots": [{"id": "snapshot:S1", "parent": None, "active_records": "all"}],
    }


def _manifest():
    return GroundingManifest(
        "m1-grounding/1",
        (DescriptionId("SIMPLE_SCAN"), DescriptionId("FULL_TEXT_INDEX")),
        (RuleId("mail-search:capability-coverage"),),
    )


def _resolve(store, snapshot, suffix):
    scope = store.create_decision_scope(f"decision-scope:{suffix}", snapshot, "context:mail-search", intention='FIND_RELEVANT_MAIL', request="MAIL_SEARCH_REQUEST", manifest=_manifest())
    grounding = store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    store.admit_grounded_decision_problem(f"decision-problem:{suffix}", problem)
    selection = store.select_m1(f"decision-problem:{suffix}")
    decision = store.admit_m1_decision(f"decision:{suffix}", selection)
    return scope, grounding, problem, decision


def _candidate(explanation, name):
    return next(item for item in explanation.candidates
                if item.candidate == DescriptionId(name))


def _objective_knowledge_id(explanation, name):
    return _candidate(explanation, name).objective_value.knowledge_id.value


def test_v1_r1_mail_search_end_to_end_and_restart(tmp_path):
    store = admit_fixture(open_store(tmp_path / "mail-search.sqlite"),
                          _mail_search_knowledge())

    scope1, grounding1, problem1, decision1 = _resolve(store, "snapshot:S1", "S1")
    explanation1 = store.explain_m1(decision1.id)
    assert scope1.intention == DescriptionId("FIND_RELEVANT_MAIL")
    assert scope1.request == DescriptionId("MAIL_SEARCH_REQUEST")
    assert all(item.truth is EvaluationTruth.TRUE for item in grounding1.observations)
    assert all(item.discovery_evidence.query.participants ==
               (item.candidate, DescriptionId("FIND_RELEVANT_MAIL"))
               for item in grounding1.observations)
    full_text_observation = next(item for item in grounding1.observations
                                 if item.candidate == DescriptionId("FULL_TEXT_INDEX"))
    assert full_text_observation.discovery_evidence.included == (
        KnowledgeId("knowledge:full-text-index-realizes"),)
    assert decision1.optimum.value == 40
    assert decision1.co_optima == (DescriptionId("FULL_TEXT_INDEX"),)
    assert _objective_knowledge_id(explanation1, "SIMPLE_SCAN") == "knowledge:simple-scan-cost-s1"
    assert _objective_knowledge_id(explanation1, "FULL_TEXT_INDEX") == "knowledge:full-text-index-cost-s1"

    store.admit([{"kind": "property", "payload": {
        "id": "knowledge:full-text-index-cost-s2",
        "description": "FULL_TEXT_INDEX", "property": "cost", "version": "1",
        "value": {"kind": "integer", "value": "160"},
        "scope": "mail-archive", "epistemic_status": "exact",
        "provenance": ["source:mail-search-benchmark-v1"]}}])
    store.snapshot("snapshot:S2", parent="snapshot:S1")
    store.supersede("knowledge:full-text-index-cost-s1",
                    "knowledge:full-text-index-cost-s2", "snapshot:S2")
    assert store.status_of("decision:S1", relative_to="snapshot:S1") is ArtifactStatus.CURRENT
    assert store.status_of("decision:S1", relative_to="snapshot:S2") is ArtifactStatus.STALE
    assert full_text_observation.discovery_evidence.included == (
        KnowledgeId("knowledge:full-text-index-realizes"),)
    assert store.explain_m1("decision:S1") == explanation1
    assert set(store.decisions) == {"decision:S1"}

    scope2, grounding2, problem2, decision2 = _resolve(store, "snapshot:S2", "S2")
    explanation2 = store.explain_m1(decision2.id)
    assert scope2.intention == DescriptionId("FIND_RELEVANT_MAIL")
    assert decision2.co_optima == (DescriptionId("SIMPLE_SCAN"),)
    assert decision2.optimum.value == 100
    assert _objective_knowledge_id(explanation2, "SIMPLE_SCAN") == "knowledge:simple-scan-cost-s1"
    assert _objective_knowledge_id(explanation2, "FULL_TEXT_INDEX") == "knowledge:full-text-index-cost-s2"
    assert store.status_of("decision:S2", relative_to="snapshot:S2") is ArtifactStatus.CURRENT
    # Capture the complete persisted scope shape before close(); this is
    # intentionally stronger than DecisionScope's nominal-id equality.
    scope1_payload = scope_payload(scope1)
    scope2_payload = scope_payload(scope2)
    store.close()

    reopened = open_store(tmp_path / "mail-search.sqlite")
    assert reopened.decision_scope("decision-scope:S1").intention == DescriptionId("FIND_RELEVANT_MAIL")
    assert reopened.decision_scope("decision-scope:S2").intention == DescriptionId("FIND_RELEVANT_MAIL")
    assert scope_payload(reopened.decision_scope("decision-scope:S1")) == scope1_payload
    assert reopened.decision_grounding("decision-scope:S1") == grounding1
    assert reopened.decision_grounding("decision-scope:S1").observations[
        1].discovery_evidence.included == (
            KnowledgeId("knowledge:full-text-index-realizes"),)
    assert reopened.decision_problem("decision-problem:S1") == problem1
    assert reopened.decision("decision:S1") == decision1
    assert reopened.explain_m1("decision:S1") == explanation1
    assert scope_payload(reopened.decision_scope("decision-scope:S2")) == scope2_payload
    assert reopened.decision_grounding("decision-scope:S2") == grounding2
    assert reopened.decision_problem("decision-problem:S2") == problem2
    assert reopened.decision("decision:S2") == decision2
    assert reopened.explain_m1("decision:S2") == explanation2
    assert reopened.status_of("decision:S1", relative_to="snapshot:S2") is ArtifactStatus.STALE
    assert reopened.status_of("decision:S2", relative_to="snapshot:S2") is ArtifactStatus.CURRENT


def test_v1_r1_included_realizes_identity_alone_stales_historical_decision(tmp_path):
    """A superseded included realizes assertion is the sole S2 staleness cause."""
    knowledge = {
        "schema": "atlas.conformance.core-v1/1",
        "fixture_id": "v1-r1-included-realizes-staleness",
        "description": "isolated included realizes staleness proof",
        "vocabulary": {
            "predicates": [
                {"id": "realizes", "version": "1", "arity": 2,
                 "roles": ["candidate", "intention"]},
                {"id": "covers", "version": "1", "arity": 2,
                 "roles": ["candidate", "request"]},
            ],
            "properties": [
                {"id": "search-requirements", "version": "1",
                 "value": "finite_set<symbol>"},
                {"id": "available-capabilities", "version": "1",
                 "value": "finite_set<symbol>"},
                {"id": "cost", "version": "1", "value": "integer"},
            ],
        },
        "descriptions": [
            {"id": "A", "label": "intention A"},
            {"id": "RA", "label": "request RA"},
            {"id": "C", "label": "candidate C"},
        ],
        "sources": [{"id": "source:v1-r1-included"}],
        "facts": [
            {"id": "knowledge:ra-requirements", "kind": "property",
             "description": "RA", "property": "search-requirements",
             "value": {"kind": "finite_set<symbol>", "items": ["SEARCH"]},
             "scope": "isolated", "epistemic_status": "exact",
             "provenance": ["source:v1-r1-included"]},
            {"id": "knowledge:c-capabilities", "kind": "property",
             "description": "C", "property": "available-capabilities",
             "value": {"kind": "finite_set<symbol>", "items": ["SEARCH"]},
             "scope": "isolated", "epistemic_status": "exact",
             "provenance": ["source:v1-r1-included"]},
            {"id": "knowledge:c-cost", "kind": "property",
             "description": "C", "property": "cost",
             "value": {"kind": "integer", "value": "7"},
             "scope": "isolated", "epistemic_status": "exact",
             "provenance": ["source:v1-r1-included"]},
        ],
        "relations": [{
            "id": "knowledge:c-realizes-a-v1", "predicate": "realizes",
            "version": "1", "participants": ["C", "A"],
            "polarity": "positive", "scope": "isolated",
            "epistemic_status": "exact", "provenance": ["source:v1-r1-included"],
        }],
        "rules": [{
            "id": "v1-r1-included:coverage", "version": "1",
            "participants": ["candidate", "request"],
            "when": {"op": "set_subset",
                     "left": {"op": "property", "participant": "request",
                              "property": "search-requirements"},
                     "right": {"op": "property", "participant": "candidate",
                               "property": "available-capabilities"}},
            "head": {"predicate": "covers", "version": "1",
                     "participants": ["candidate", "request"], "polarity": "positive"},
        }],
        "contexts": [{"id": "context:v1-r1-included", "visible_scopes": ["isolated"],
                       "enabled_rules": ["v1-r1-included:coverage"]}],
        "snapshots": [{"id": "snapshot:S1", "parent": None, "active_records": "all"}],
    }
    manifest = GroundingManifest(
        "m1-grounding/1", (DescriptionId("C"),),
        (RuleId("v1-r1-included:coverage"),),
    )
    store = admit_fixture(open_store(tmp_path / "included.sqlite"), knowledge)
    scope = store.create_decision_scope(
        "decision-scope:D1", "snapshot:S1", "context:v1-r1-included",
        intention="A", request="RA", manifest=manifest,
    )
    grounding1 = store.evaluate_decision_scope(scope.id)
    store.admit_grounded_decision_problem("decision-problem:D1",
                                          store.ground_decision_problem(scope.id))
    d1 = store.admit_m1_decision("decision:D1",
                                  store.select_m1("decision-problem:D1"))
    explanation1 = store.explain_m1(d1.id)
    observation1 = grounding1.observations[0]
    discovery_evidence1 = observation1.discovery_evidence

    assert scope.intention == DescriptionId("A")
    assert scope.request == DescriptionId("RA")
    assert observation1.candidate == DescriptionId("C")
    assert discovery_evidence1.included == (
        KnowledgeId("knowledge:c-realizes-a-v1"),)
    assert store.status_of(d1.id, relative_to="snapshot:S1") is ArtifactStatus.CURRENT

    store.admit([{"kind": "relation", "payload": {
        "id": "knowledge:c-realizes-a-v2", "predicate": "realizes",
        "version": "1", "participants": ["C", "A"], "polarity": "positive",
        "scope": "isolated", "epistemic_status": "exact",
        "provenance": ["source:v1-r1-included"]}}])
    store.snapshot("snapshot:S2", parent="snapshot:S1")
    store.supersede("knowledge:c-realizes-a-v1", "knowledge:c-realizes-a-v2", "snapshot:S2")

    assert store.status_of(d1.id, relative_to="snapshot:S1") is ArtifactStatus.CURRENT
    assert store.status_of(d1.id, relative_to="snapshot:S2") is ArtifactStatus.STALE
    assert store.decision_grounding(scope.id) == grounding1
    assert store.decision_grounding(scope.id).observations[0].discovery_evidence.included == (
        KnowledgeId("knowledge:c-realizes-a-v1"),)
    assert store.explain_m1(d1.id) == explanation1

    store.close()
    reopened = open_store(tmp_path / "included.sqlite")
    assert reopened.status_of(d1.id, relative_to="snapshot:S1") is ArtifactStatus.CURRENT
    assert reopened.status_of(d1.id, relative_to="snapshot:S2") is ArtifactStatus.STALE
    assert reopened.decision_grounding(scope.id) == grounding1
    assert reopened.decision_grounding(scope.id).observations[0].discovery_evidence.included == (
        KnowledgeId("knowledge:c-realizes-a-v1"),)
    assert reopened.explain_m1(d1.id) == explanation1


def test_discovery_evidence_intention_participant_forgery_is_isolated(tmp_path):
    store = admit_fixture(open_store(tmp_path / "mail-search.sqlite"),
                          _mail_search_knowledge())
    scope, grounding, _, _ = _resolve(store, "snapshot:S1", "AB")
    assert grounding.observations[0].discovery_evidence.query.participants == (
        grounding.observations[0].candidate, DescriptionId("FIND_RELEVANT_MAIL"))
    path = store.path
    store.close()
    db = sqlite3.connect(path)
    row = db.execute(
        "SELECT payload FROM records WHERE kind='decision_grounding' AND id=?",
        (scope.id.value,)).fetchone()
    payload = json.loads(row[0])
    payload["observations"][0]["discovery_evidence"]["query"]["participants"][1] = "MAIL_SEARCH_REQUEST"
    db.execute("UPDATE records SET payload=? WHERE kind='decision_grounding' AND id=?",
               (json.dumps(payload), scope.id.value))
    db.commit(); db.close()

    reopened = open_store(path)
    assert ("decision_grounding", scope.id.value) in reopened.isolated
    assert scope.id.value not in reopened.decision_groundings
