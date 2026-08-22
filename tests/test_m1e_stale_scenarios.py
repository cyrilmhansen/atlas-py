"""Pedagogical M1e.1 stories: historical decisions versus explicit S2."""

import json
from pathlib import Path

from atlas import *

FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def fixture():
    value = json.loads(FIXTURE.read_text())
    value = json.loads(json.dumps(value).replace("realization:r1", "EASY_SHORTCUT")
                       .replace("realization:r2", "DEEP_THOUGHT")
                       .replace("fact:r1", "fact:EASY_SHORTCUT")
                       .replace("fact:r2", "fact:DEEP_THOUGHT"))
    value["descriptions"].append({"id": "LAST_HOPE", "label": "LAST_HOPE"})
    return value


def manifest(*candidates):
    return GroundingManifest("m1-grounding/1", tuple(DescriptionId(x) for x in candidates),
                             (RuleId("coverage:v1"),))


def decide(store, decision_id="decision:old", scope_id="decision-scope:old",
           snapshot="snapshot:m1", candidates=("EASY_SHORTCUT", "DEEP_THOUGHT")):
    scope = store.create_decision_scope(scope_id, snapshot, "context:m1", intention='intent:selection', request="request:q1", manifest=manifest(*candidates))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    problem_id = "decision-problem:" + scope_id.rsplit(":", 1)[-1]
    store.admit_grounded_decision_problem(problem_id, problem)
    return store.admit_m1_decision(decision_id, store.select_m1(problem_id))


def replacement(store, old, new, property_id, value):
    store.admit([{"kind": "property", "payload": {
        "id": new, "description": old.split("-", 2)[1] if old.startswith("fact:") else "DEEP_THOUGHT",
        "property": property_id, "version": "1", "value": value, "scope": "catalog",
        "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])


def base_store(tmp_path):
    data = fixture()
    for fact in data["facts"]:
        if fact["id"] == "fact:EASY_SHORTCUT-capabilities": fact["value"]["items"] = ["a", "b"]
        if fact["id"] == "fact:EASY_SHORTCUT-cost": fact["value"]["value"] = "100"
        if fact["id"] == "fact:DEEP_THOUGHT-cost": fact["value"]["value"] = "50"
    return admit_fixture(open_store(tmp_path / "atlas.sqlite"), data)


def test_a_deep_thought_changed_stales_but_keeps_history(tmp_path):
    store = base_store(tmp_path)
    d1 = decide(store)
    before = store.explain_m1(d1.id)
    store.admit([{"kind": "property", "payload": {
        "id": "fact:DEEP_THOUGHT-capabilities-v2", "description": "DEEP_THOUGHT",
        "property": "available-capabilities", "version": "1",
        "value": {"kind": "finite_set<symbol>", "items": ["a"]}, "scope": "catalog",
        "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])
    store.snapshot("snapshot:m1-revised", parent="snapshot:m1")
    store.supersede("fact:DEEP_THOUGHT-capabilities", "fact:DEEP_THOUGHT-capabilities-v2",
                    "snapshot:m1-revised")
    assert store.status_of(d1.id, relative_to="snapshot:m1") is ArtifactStatus.CURRENT
    assert store.status_of(d1.id, relative_to="snapshot:m1-revised") is ArtifactStatus.STALE
    assert store.explain_m1(d1.id) == before
    assert store.decision(d1.id).co_optima == (DescriptionId("DEEP_THOUGHT"),)


def test_b_irrelevant_quick_overview_change_does_not_stale(tmp_path):
    store = base_store(tmp_path)
    d1 = decide(store)
    store.admit([{"kind": "property", "payload": {
        "id": "fact:unused-v2", "description": "EASY_SHORTCUT", "property": "unused-property",
        "version": "1", "value": {"kind": "symbol", "value": "QUICK_OVERVIEW"},
        "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])
    store.snapshot("snapshot:unused", parent="snapshot:m1")
    store.supersede("fact:EASY_SHORTCUT-unused", "fact:unused-v2", "snapshot:unused")
    assert store.status_of(d1.id, relative_to="snapshot:unused") is ArtifactStatus.CURRENT


def test_c_prices_changed_stale_without_automatic_replacement(tmp_path):
    store = base_store(tmp_path)
    d1 = decide(store)
    for candidate, old, cost in (("EASY_SHORTCUT", "fact:EASY_SHORTCUT-cost", "30"),
                                 ("DEEP_THOUGHT", "fact:DEEP_THOUGHT-cost", "80")):
        store.admit([{"kind": "property", "payload": {
            "id": old + "-v2", "description": candidate, "property": "cost", "version": "1",
            "value": {"kind": "integer", "value": cost}, "scope": "catalog",
            "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])
    store.snapshot("snapshot:prices", parent="snapshot:m1")
    store.supersede("fact:EASY_SHORTCUT-cost", "fact:EASY_SHORTCUT-cost-v2", "snapshot:prices")
    store.supersede("fact:DEEP_THOUGHT-cost", "fact:DEEP_THOUGHT-cost-v2", "snapshot:prices")
    assert store.status_of(d1.id, relative_to="snapshot:prices") is ArtifactStatus.STALE
    assert store.decision("decision:old").co_optima == (DescriptionId("DEEP_THOUGHT"),)
    assert store.decision("decision:old").id.value == "decision:old"


def test_d_stale_is_not_corrupt_and_f_restart_preserves_classification(tmp_path):
    store = base_store(tmp_path)
    d1 = decide(store)
    before = store.explain_m1(d1.id)
    store.admit([{"kind": "property", "payload": {
        "id": "fact:DEEP_THOUGHT-capabilities-v2", "description": "DEEP_THOUGHT",
        "property": "available-capabilities", "version": "1",
        "value": {"kind": "finite_set<symbol>", "items": ["a"]}, "scope": "catalog",
        "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])
    store.snapshot("snapshot:restart", parent="snapshot:m1")
    store.supersede("fact:DEEP_THOUGHT-capabilities", "fact:DEEP_THOUGHT-capabilities-v2", "snapshot:restart")
    store.close()
    restored = open_store(tmp_path / "atlas.sqlite")
    assert restored.status_of("decision:old", relative_to="snapshot:m1") is ArtifactStatus.CURRENT
    assert restored.status_of("decision:old", relative_to="snapshot:restart") is ArtifactStatus.STALE
    assert restored.explain_m1("decision:old") == before


def test_e_corruption_is_invalid_not_stale(tmp_path):
    store = base_store(tmp_path)
    decide(store)
    store.close()
    import sqlite3
    db = sqlite3.connect(tmp_path / "atlas.sqlite")
    db.execute("DELETE FROM records WHERE kind='property' AND id='fact:DEEP_THOUGHT-capabilities'")
    db.commit(); db.close()
    restored = open_store(tmp_path / "atlas.sqlite")
    assert restored.status_of("decision:old", relative_to="snapshot:m1") is ArtifactStatus.INVALID


def test_included_discovery_identity_stales_only_the_superseding_branch(tmp_path):
    store = base_store(tmp_path)
    d1 = decide(store)
    before = store.explain_m1(d1.id)
    store.admit([{"kind": "relation", "payload": {
        "id": "rel:r2-realizes-v2", "predicate": "realizes", "version": "1",
        "participants": ["DEEP_THOUGHT", "intent:selection"], "polarity": "positive",
        "scope": "catalog", "epistemic_status": "exact", "provenance": ["source:m1-fixture"]}}])
    store.snapshot("snapshot:branch-a", parent="snapshot:m1")
    store.snapshot("snapshot:branch-b", parent="snapshot:m1")
    store.supersede("rel:r2-realizes", "rel:r2-realizes-v2", "snapshot:branch-a")
    assert store.status_of(d1.id, relative_to="snapshot:branch-a") is ArtifactStatus.STALE
    assert store.status_of(d1.id, relative_to="snapshot:branch-b") is ArtifactStatus.CURRENT
    assert store.explain_m1(d1.id) == before
