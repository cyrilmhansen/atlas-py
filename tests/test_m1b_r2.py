import json
import sqlite3
from pathlib import Path

from atlas import DescriptionId, KnowledgeId, admit_fixture, open_store


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def _store(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return admit_fixture(open_store(tmp_path / "atlas.sqlite"), json.loads(FIXTURE.read_text()))


def _derived(store, ident, snapshot="snapshot:m1"):
    result = store.ground(
        "coverage:v1",
        {"candidate": DescriptionId("realization:r2"), "request": DescriptionId("request:q1")},
        snapshot,
        "context:m1",
    )
    return store.admit_derived(KnowledgeId(ident), result)


def _replace_dependencies(path, changes):
    db = sqlite3.connect(path)
    for ident, dependencies in changes.items():
        row = db.execute(
            "SELECT payload FROM records WHERE kind='derivation' AND id=?", (ident,)
        ).fetchone()
        payload = json.loads(row[0])
        payload["dependencies"] = list(dependencies)
        db.execute(
            "UPDATE records SET payload=? WHERE kind='derivation' AND id=?",
            (json.dumps(payload), ident),
        )
    db.commit()
    db.close()


def _reopen_cycle(tmp_path, first, second):
    store = _store(tmp_path)
    _derived(store, first)
    store.snapshot("snapshot:m2", parent="snapshot:m1")
    _derived(store, second, "snapshot:m2")
    path = store.path
    store.close()
    _replace_dependencies(path, {first: [second], second: [first]})
    return open_store(path)


def test_r2_sol_counterexample_closes_cycle_and_is_restart_invariant(tmp_path):
    reopened = _reopen_cycle(tmp_path, "derived:z-old", "derived:a-new")
    assert not {"derived:z-old", "derived:a-new"} & set(reopened.records)
    assert not {"derived:z-old", "derived:a-new"} & set(reopened.derivations)
    assert {("relation", "derived:z-old"), ("derivation", "derived:z-old"),
            ("relation", "derived:a-new"), ("derivation", "derived:a-new")} <= set(reopened.isolated)
    before = (set(reopened.records), set(reopened.derivations), set(reopened.isolated))
    reopened.close()
    again = open_store(tmp_path / "atlas.sqlite")
    assert (set(again.records), set(again.derivations), set(again.isolated)) == before


def test_r2_sol_counterexample_is_independent_of_lexical_names(tmp_path):
    first = _reopen_cycle(tmp_path / "forward", "derived:z-old", "derived:a-new")
    second = _reopen_cycle(tmp_path / "reverse", "derived:a-old", "derived:z-new")
    assert set(first.records) == set(second.records)
    assert set(first.derivations) == set(second.derivations)
    assert sorted(kind for kind, ident in first.isolated if kind in {"relation", "derivation"}) == [
        "derivation", "derivation", "relation", "relation"]
    assert sorted(kind for kind, ident in second.isolated if kind in {"relation", "derivation"}) == [
        "derivation", "derivation", "relation", "relation"]


def test_r2_self_cycle_and_external_dependent_are_all_closed(tmp_path):
    store = _store(tmp_path)
    _derived(store, "derived:A")
    _derived(store, "derived:B")
    _derived(store, "derived:C")
    path = store.path
    store.close()
    _replace_dependencies(path, {
        "derived:A": ["derived:A"],
        "derived:B": ["derived:A"],
        "derived:C": ["derived:B"],
    })
    reopened = open_store(path)
    assert not {"derived:A", "derived:B", "derived:C"} & set(reopened.records)
    assert not {"derived:A", "derived:B", "derived:C"} & set(reopened.derivations)


def test_r2_invalid_dependency_does_not_invalidate_healthy_dependency(tmp_path):
    store = _store(tmp_path)
    _derived(store, "derived:bad")
    _derived(store, "derived:healthy")
    path = store.path
    store.close()
    _replace_dependencies(path, {"derived:bad": ["fact:missing"]})
    reopened = open_store(path)
    assert "derived:bad" not in reopened.records
    assert "derived:healthy" in reopened.records
    assert "fact:r2-cost" in reopened.records
