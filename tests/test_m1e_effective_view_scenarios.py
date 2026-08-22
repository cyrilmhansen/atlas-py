"""Pedagogical M1e.2.1 stories with deliberately caricatural names."""

from test_m1e_effective_view import base, add_property, costs


def test_a_deep_thought_becomes_too_expensive(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    add_property(store, "DEEP_THOUGHT-cost-120", "realization:r2", 120)
    store.snapshot("S2", parent="S1")
    store.supersede("fact:r2-cost", "DEEP_THOUGHT-cost-120", "S2")
    assert costs(store, "S2") == {"realization:r1": 100, "realization:r2": 120}


def test_b_chain_is_50_then_80_then_120(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    add_property(store, "DEEP_THOUGHT-cost-80", "realization:r2", 80)
    store.snapshot("S2", parent="S1")
    store.supersede("fact:r2-cost", "DEEP_THOUGHT-cost-80", "S2")
    add_property(store, "DEEP_THOUGHT-cost-120", "realization:r2", 120)
    store.snapshot("S3", parent="S2")
    store.supersede("DEEP_THOUGHT-cost-80", "DEEP_THOUGHT-cost-120", "S3")
    assert costs(store, "S1")["realization:r2"] == 50
    assert costs(store, "S2")["realization:r2"] == 80
    assert costs(store, "S3")["realization:r2"] == 120


def test_c_sibling_keeps_old_price(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    add_property(store, "DEEP_THOUGHT-cost-120", "realization:r2", 120)
    store.snapshot("S2A", parent="S1")
    store.snapshot("S2B", parent="S1")
    store.supersede("fact:r2-cost", "DEEP_THOUGHT-cost-120", "S2A")
    assert costs(store, "S2A")["realization:r2"] == 120
    assert costs(store, "S2B")["realization:r2"] == 50


def test_d_unrelated_quick_overview_does_not_change_cost(tmp_path):
    store = base(tmp_path)
    add_property(store, "QUICK_OVERVIEW-v2", "realization:r1", "v2", "unused-property")
    store.snapshot("S2", parent="snapshot:m1")
    store.supersede("fact:r1-unused", "QUICK_OVERVIEW-v2", "S2")
    assert costs(store, "S2")["realization:r2"] == 50


def test_e_mystery_box_gets_an_ordinary_new_fact(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    add_property(store, "MYSTERY_BOX-new-property", "realization:r1", "available", "unused-property")
    store.snapshot("S2", parent="S1")
    assert "MYSTERY_BOX-new-property" not in {x.id.value for x in store.find(snapshot="S1")}
    assert "MYSTERY_BOX-new-property" in {x.id.value for x in store.find(snapshot="S2")}


def test_f_restart_preserves_the_effective_view(tmp_path):
    store = base(tmp_path)
    store.snapshot("S1")
    add_property(store, "DEEP_THOUGHT-cost-120", "realization:r2", 120)
    store.snapshot("S2", parent="S1")
    store.supersede("fact:r2-cost", "DEEP_THOUGHT-cost-120", "S2")
    expected = costs(store, "S2")
    store.close()
    reopened = type(store)(tmp_path / "atlas.sqlite")
    assert costs(reopened, "S2") == expected
