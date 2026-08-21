"""Small adversarial boundaries for the pure M1d.1 explanation API."""

from dataclasses import replace

import pytest

from atlas import *
from atlas.problem import validate_persisted_grounded_decision_problem
from test_m1d_explanation_scenarios import data, decide, resolved_fixture


def test_public_candidate_explanation_rejects_false_selected(tmp_path):
    fixture = data()
    for fact in fixture["facts"]:
        if fact["id"] in {"fact:q1-search", "fact:q1-output"}:
            fact["value"]["items"] = ["not-supported"]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)
    decision = decide(store, "decision-scope:false-selected", ("realization:r1", "realization:r2"))
    explanation = store.explain_m1(decision.id)
    false_candidate = next(x for x in explanation.candidates if x.truth is EvaluationTruth.FALSE)
    with pytest.raises(ValidationError):
        replace(false_candidate, selected=True)


def test_public_candidate_explanation_rejects_unknown_objective(tmp_path):
    fixture = data()
    fixture["facts"] = [x for x in fixture["facts"]
                        if x["id"] not in {"fact:r2-capabilities", "fact:r2-cost"}]
    for fact in fixture["facts"]:
        if fact["id"] == "fact:r1-capabilities": fact["value"]["items"] = ["a", "b"]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)
    decision = decide(store, "decision-scope:unknown-objective", ("realization:r1", "realization:r2"))
    explanation = store.explain_m1(decision.id)
    unknown = next(x for x in explanation.candidates if x.truth is EvaluationTruth.UNKNOWN)
    objective_root = tmp_path / "objective-source"
    objective_root.mkdir()
    objective_store = resolved_fixture(objective_root)
    objective_decision = decide(objective_store, "decision-scope:objective-source",
                                ("realization:r1", "realization:r2"))
    objective = next(x.objective_value for x in objective_store.explain_m1(objective_decision.id).candidates
                     if x.objective_value is not None)
    with pytest.raises(ValidationError):
        replace(unknown, objective_value=objective)


def test_public_decision_explanation_rejects_higher_objective_without_certified_optimum(tmp_path):
    fixture = data()
    fixture["facts"] = [x for x in fixture["facts"]
                        if x["id"] not in {"fact:r2-capabilities", "fact:r2-cost"}]
    for fact in fixture["facts"]:
        if fact["id"] == "fact:r1-capabilities": fact["value"]["items"] = ["a", "b"]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), fixture)
    decision = decide(store, "decision-scope:higher-without-optimum", ("realization:r1", "realization:r2"))
    explanation = store.explain_m1(decision.id)
    true_candidate = next(x for x in explanation.candidates if x.truth is EvaluationTruth.TRUE)
    invalid = replace(true_candidate, reason=ExplanationReason.ADMISSIBLE_HIGHER_OBJECTIVE)
    with pytest.raises(ValidationError):
        replace(explanation, candidates=tuple(invalid if x is true_candidate else x for x in explanation.candidates))


def test_public_decision_explanation_rejects_selected_without_admissible_candidate(tmp_path):
    store = resolved_fixture(tmp_path)
    decision = decide(store, "decision-scope:selected-without-candidate", ("realization:r1", "realization:r2"))
    explanation = store.explain_m1(decision.id)
    selected = next(x for x in explanation.candidates if x.selected)
    with pytest.raises(ValidationError):
        replace(explanation, status=SelectionStatus.NO_ADMISSIBLE_CANDIDATE,
                optimum=None, candidates=(selected,))


def test_public_decision_explanation_accepts_the_three_closed_statuses(tmp_path):
    resolved_root = tmp_path / "resolved"
    resolved_root.mkdir()
    resolved = store = resolved_fixture(resolved_root)
    resolved_decision = decide(store, "decision-scope:valid-resolved", ("realization:r1", "realization:r2"))
    assert store.explain_m1(resolved_decision.id).status is SelectionStatus.RESOLVED

    fixture = data()
    fixture["facts"] = [x for x in fixture["facts"]
                        if x["id"] not in {"fact:r2-capabilities", "fact:r2-cost"}]
    for fact in fixture["facts"]:
        if fact["id"] == "fact:r1-capabilities": fact["value"]["items"] = ["a", "b"]
    needs_store = admit_fixture(open_store(tmp_path / "needs.sqlite"), fixture)
    needs_decision = decide(needs_store, "decision-scope:valid-needs", ("realization:r1", "realization:r2"))
    assert needs_store.explain_m1(needs_decision.id).status is SelectionStatus.NEEDS_INFORMATION

    fixture = data()
    for fact in fixture["facts"]:
        if fact["id"] in {"fact:q1-search", "fact:q1-output"}:
            fact["value"]["items"] = ["not-supported"]
    none_store = admit_fixture(open_store(tmp_path / "none.sqlite"), fixture)
    none_decision = decide(none_store, "decision-scope:valid-none", ("realization:r1", "realization:r2"))
    assert none_store.explain_m1(none_decision.id).status is SelectionStatus.NO_ADMISSIBLE_CANDIDATE


def test_explain_m1_is_not_a_package_level_public_helper():
    import atlas

    assert hasattr(atlas, "explain_m1") is False
    with pytest.raises(ImportError):
        exec("from atlas import explain_m1", {})


def test_explain_requires_a_persisted_decision_id(tmp_path):
    store = resolved_fixture(tmp_path)
    with pytest.raises(GroundingError):
        store.explain_m1(DecisionId("decision:absent"))


def test_explain_fails_closed_when_active_decision_grounding_is_missing(tmp_path):
    store = resolved_fixture(tmp_path)
    decision = decide(store, "decision-scope:missing-grounding", ("realization:r1", "realization:r2"))
    del store.decision_groundings[store.grounded_decision_problems[decision.source.value].scope_id.value]

    with pytest.raises(GroundingError):
        store.explain_m1(decision.id)


def test_explain_fails_closed_when_active_grounding_observation_is_missing(tmp_path):
    store = resolved_fixture(tmp_path)
    decision = decide(store, "decision-scope:missing-observation", ("realization:r1", "realization:r2"))
    problem = store.grounded_decision_problems[decision.source.value]
    grounding = store.decision_groundings[problem.scope_id.value]
    store.decision_groundings[problem.scope_id.value] = replace(
        grounding, observations=grounding.observations[:-1])

    with pytest.raises(GroundingError):
        store.explain_m1(decision.id)


def test_explain_fails_closed_when_active_observations_are_permuted(tmp_path):
    store = resolved_fixture(tmp_path)
    decision = decide(store, "decision-scope:permuted-observations", ("realization:r1", "realization:r2"))
    problem = store.grounded_decision_problems[decision.source.value]
    grounding = store.decision_groundings[problem.scope_id.value]
    store.decision_groundings[problem.scope_id.value] = replace(
        grounding, observations=tuple(reversed(grounding.observations)))

    with pytest.raises(GroundingError):
        store.explain_m1(decision.id)


def test_explain_rejects_asymmetric_candidate_to_grounding_result_binding(tmp_path):
    store = resolved_fixture(tmp_path)
    decision = decide(store, "decision-scope:asymmetric-binding", ("realization:r1", "realization:r2"))
    problem = store.grounded_decision_problems[decision.source.value]
    cpu, gpu = problem.candidates
    gpu_result = gpu.grounding_result
    assert gpu_result.bindings == {"candidate": DescriptionId("realization:r2"),
                                   "request": DescriptionId("request:q1")}
    assert KnowledgeId("fact:r2-capabilities") in gpu_result.effective_dependencies

    forged = replace(problem, candidates=(replace(cpu, grounding_result=gpu_result), gpu))
    store.grounded_decision_problems[decision.source.value] = forged
    with pytest.raises(GroundingError):
        validate_persisted_grounded_decision_problem(store, forged)
    with pytest.raises(GroundingError):
        store.explain_m1(decision.id)


def test_explain_healthy_control_still_returns_the_historical_outcome(tmp_path):
    store = resolved_fixture(tmp_path, cpu=100, gpu=50)
    decision = decide(store, "decision-scope:healthy-control", ("realization:r1", "realization:r2"))
    explanation = store.explain_m1(decision.id)

    assert explanation.status is SelectionStatus.RESOLVED
    assert explanation.optimum == Integer(50)
    assert [(item.candidate, item.reason, item.objective_value.value if item.objective_value else None)
            for item in explanation.candidates] == [
                (DescriptionId("realization:r1"), ExplanationReason.ADMISSIBLE_HIGHER_OBJECTIVE, Integer(100)),
                (DescriptionId("realization:r2"), ExplanationReason.SELECTED_CO_OPTIMUM, Integer(50)),
            ]


def test_explain_preserves_nominal_source_identity_for_equal_decisions(tmp_path):
    store = resolved_fixture(tmp_path)
    first = decide(store, "decision-scope:one", ("realization:r1", "realization:r2"),
                   decision_id="decision:one")
    second = decide(store, "decision-scope:two", ("realization:r1", "realization:r2"),
                    problem_id="decision-problem:two", decision_id="decision:two")
    one, two = store.explain_m1(first.id), store.explain_m1(second.id)
    assert one.source == DecisionId("decision:one")
    assert two.source == DecisionId("decision:two")
    assert one.decision_problem == DecisionProblemId("decision-problem:one")
    assert two.decision_problem == DecisionProblemId("decision-problem:two")
    assert one.candidates == two.candidates


def test_explain_does_not_reground_reselect_or_persist(tmp_path, monkeypatch):
    store = resolved_fixture(tmp_path)
    decision = decide(store, "decision-scope:pure", ("realization:r1", "realization:r2"))
    before = store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()

    def forbidden(*args, **kwargs):
        raise AssertionError("M1d.1 must not recompute historical artifacts")

    monkeypatch.setattr(Store, "ground", forbidden)
    monkeypatch.setattr(Store, "ground_decision_scope", forbidden)
    monkeypatch.setattr(Store, "ground_decision_problem", forbidden)
    monkeypatch.setattr(Store, "select_m1", forbidden)
    explanation = store.explain_m1(decision.id)
    after = store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()
    assert explanation.source == decision.id
    assert after == before
    assert not any(kind == "explanation" for kind, _, _ in after)


def test_explain_keeps_effective_evidence_separate_from_coverage(tmp_path):
    store = resolved_fixture(tmp_path)
    decision = decide(store, "decision-scope:evidence", ("realization:r1", "realization:r2"))
    explanation = store.explain_m1(decision.id)
    cpu = explanation.candidates[0]
    assert cpu.effective_dependencies
    assert cpu.dependency_closure[:len(cpu.effective_dependencies)] == cpu.effective_dependencies
    assert cpu.grounding_evidence
    assert cpu.provenance
    # The unused historical fact is not evidence merely because it is in the snapshot.
    assert KnowledgeId("fact:r1-unused") not in cpu.effective_dependencies
    assert KnowledgeId("fact:r1-unused") not in cpu.dependency_closure


def test_explain_has_complete_co_optima_and_no_winner_tiebreak(tmp_path):
    store = resolved_fixture(tmp_path, cpu=50, gpu=50)
    decision = decide(store, "decision-scope:tie-adversarial",
                      ("realization:r2", "realization:r1"), decision_id="decision:tie")
    explanation = store.explain_m1(decision.id)
    assert set(x.candidate for x in explanation.candidates if x.selected) == {
        DescriptionId("realization:r1"), DescriptionId("realization:r2")}
    assert all(x.reason is ExplanationReason.SELECTED_CO_OPTIMUM for x in explanation.candidates)
