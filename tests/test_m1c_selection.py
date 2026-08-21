import json
from dataclasses import replace
from pathlib import Path

import pytest

from atlas import *


FIXTURE = Path(__file__).parents[1] / "conformance/fixtures/m1-coverage.json"


def prepared(tmp_path, candidates, *, costs=None, unknown=(), make_r1_true=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    data = json.loads(FIXTURE.read_text())
    costs = costs or {}
    for fact in data["facts"]:
        if fact["id"] == "fact:r1-capabilities" and "realization:r1" in unknown:
            data["facts"].remove(fact)
            break
        if fact["id"] == "fact:r2-capabilities" and "realization:r2" in unknown:
            data["facts"].remove(fact)
            break
        if fact["id"] == "fact:r1-cost" and "realization:r1" in costs:
            fact["value"]["value"] = str(costs["realization:r1"])
        if fact["id"] == "fact:r2-cost" and "realization:r2" in costs:
            fact["value"]["value"] = str(costs["realization:r2"])
    # Make r1 admissible when requested; r2 is admissible in the fixture.
    if make_r1_true:
        for fact in data["facts"]:
            if fact["id"] == "fact:r1-capabilities":
                fact["value"]["items"] = ["a", "b"]
    store = admit_fixture(open_store(tmp_path / "atlas.sqlite"), data)
    scope = store.create_decision_scope("decision-scope:test", "snapshot:m1", "context:m1", "request:q1",
                                        GroundingManifest("m1-grounding/1", tuple(DescriptionId(x) for x in candidates), (RuleId("coverage:v1"),)))
    store.evaluate_decision_scope(scope.id)
    problem = store.ground_decision_problem(scope.id)
    store.admit_grounded_decision_problem("decision-problem:test", problem)
    return store


def test_selection_all_statuses_and_exact_boundaries(tmp_path):
    store = prepared(tmp_path / "unique", ("realization:r1", "realization:r2"), costs={"realization:r1": 100, "realization:r2": 50})
    assert store.select_m1("decision-problem:test") == M1SelectionResult(DecisionProblemId("decision-problem:test"), SelectionStatus.RESOLVED, Integer(50), (DescriptionId("realization:r2"),))

    tie = prepared(tmp_path / "tie", ("realization:r1", "realization:r2"), costs={"realization:r1": 50, "realization:r2": 50})
    assert set(tie.select_m1("decision-problem:test").co_optima) == {DescriptionId("realization:r1"), DescriptionId("realization:r2")}
    permuted = prepared(tmp_path / "permuted", ("realization:r2", "realization:r1"), costs={"realization:r1": 50, "realization:r2": 50})
    assert permuted.select_m1("decision-problem:test").status is SelectionStatus.RESOLVED
    assert permuted.select_m1("decision-problem:test").optimum == tie.select_m1("decision-problem:test").optimum
    assert set(permuted.select_m1("decision-problem:test").co_optima) == set(tie.select_m1("decision-problem:test").co_optima)

    one = prepared(tmp_path / "one", ("realization:r2",))
    assert one.select_m1("decision-problem:test").co_optima == (DescriptionId("realization:r2"),)

    # The base fixture leaves r1 non-admissible.
    data = json.loads(FIXTURE.read_text())
    (tmp_path / "all-false").mkdir(parents=True, exist_ok=True)
    false = admit_fixture(open_store(tmp_path / "all-false" / "atlas.sqlite"), data)
    scope = false.create_decision_scope("decision-scope:test", "snapshot:m1", "context:m1", "request:q1",
                                        GroundingManifest("m1-grounding/1", (DescriptionId("realization:r1"),), (RuleId("coverage:v1"),)))
    false.evaluate_decision_scope(scope.id)
    problem = false.ground_decision_problem(scope.id)
    false.admit_grounded_decision_problem("decision-problem:test", problem)
    assert false.select_m1("decision-problem:test").status is SelectionStatus.NO_ADMISSIBLE_CANDIDATE

    unknown_cases = (
        ("true-unknown", ("realization:r1",), ("realization:r1", "realization:r2"), True),
        ("false-unknown", ("realization:r2",), ("realization:r1", "realization:r2"), False),
        ("only-unknown", ("realization:r2",), ("realization:r2",), False),
    )
    for label, unknown, candidates, make_r1_true in unknown_cases:
        unknown_store = prepared(tmp_path / label, candidates, unknown=unknown, make_r1_true=make_r1_true)
        assert unknown_store.select_m1("decision-problem:test").status is SelectionStatus.NEEDS_INFORMATION

    boundary = prepared(tmp_path / "boundary", ("realization:r1", "realization:r2"), costs={"realization:r1": -(10**100), "realization:r2": 0})
    assert boundary.select_m1("decision-problem:test").optimum == Integer(-(10**100))


def test_selection_is_order_independent_and_does_not_persist_or_reground(tmp_path, monkeypatch):
    store = prepared(tmp_path, ("realization:r1", "realization:r2"), costs={"realization:r1": 50, "realization:r2": 50})
    before = store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall()
    from atlas import problem as problem_module
    monkeypatch.setattr(problem_module, "build_grounded_decision_problem", lambda *args: (_ for _ in ()).throw(AssertionError("must not rebuild GDP")))
    result = store.select_m1(DecisionProblemId("decision-problem:test"))
    assert result.source == DecisionProblemId("decision-problem:test")
    assert set(result.co_optima) == {DescriptionId("realization:r1"), DescriptionId("realization:r2")}
    assert store._db.execute("SELECT kind,id,payload FROM records ORDER BY kind,id").fetchall() == before


def test_selection_is_not_a_public_free_function_and_store_anchors_source(tmp_path):
    store = prepared(tmp_path, ("realization:r2",), costs={"realization:r2": 50}, make_r1_true=False)
    result = store.select_m1("decision-problem:test")
    assert result.source == DecisionProblemId("decision-problem:test")
    import atlas
    assert not hasattr(atlas, "select_m1")
    with pytest.raises(ImportError):
        exec("from atlas import select_m1", {})


def test_invalid_true_without_objective_is_rejected_before_unknown(tmp_path):
    from atlas import problem as problem_module

    valid = prepared(tmp_path, ("realization:r1", "realization:r2"), costs={"realization:r1": 100, "realization:r2": 50})
    original = valid.decision_problem("decision-problem:test")
    true_without_objective = GroundedCandidate(
        original.candidates[0].candidate, EvaluationTruth.TRUE,
        original.candidates[0].grounding_result, None, None)
    unknown = replace(original.candidates[1],
                     truth=EvaluationTruth.UNKNOWN,
                     grounding_result=replace(original.candidates[1].grounding_result,
                                               truth=EvaluationTruth.UNKNOWN,
                                               conclusion=None),
                     objective_value=None)
    invalid = GroundedDecisionProblem(
        original.scope_id, original.snapshot, original.context, original.request,
        original.manifest_version, original.rule_id, original.objective,
        (true_without_objective, unknown), original.grounding_status)
    with pytest.raises(ValidationError, match="TRUE candidate has no exact M1 objective value"):
        problem_module._select_m1(DecisionProblemId("decision-problem:not-persisted"), invalid)


def test_invalid_true_estimated_objective_is_rejected_before_unknown(tmp_path):
    from atlas import problem as problem_module

    valid = prepared(tmp_path, ("realization:r1", "realization:r2"),
                     costs={"realization:r1": 100, "realization:r2": 50})
    original = valid.decision_problem("decision-problem:test")
    objective = original.candidates[0].objective_value
    estimated = object.__new__(ObjectiveValue)
    for field in ("value", "knowledge_id", "property", "version"):
        object.__setattr__(estimated, field, getattr(objective, field))
    object.__setattr__(estimated, "epistemic_status", "estimated")
    true_estimated = replace(original.candidates[0], objective_value=estimated)
    unknown = replace(original.candidates[1],
                     truth=EvaluationTruth.UNKNOWN,
                     grounding_result=replace(original.candidates[1].grounding_result,
                                               truth=EvaluationTruth.UNKNOWN,
                                               conclusion=None),
                     objective_value=None)
    invalid = replace(original, candidates=(true_estimated, unknown))
    with pytest.raises(ValidationError, match="TRUE candidate objective value disagrees with problem objective"):
        problem_module._select_m1(DecisionProblemId("decision-problem:not-persisted"), invalid)


@pytest.mark.parametrize("field,value", [
    ("property", PropertyId("other-cost")),
    ("version", "2"),
])
def test_invalid_true_objective_reference_is_rejected_before_unknown(tmp_path, field, value):
    from atlas import problem as problem_module

    valid = prepared(tmp_path, ("realization:r1", "realization:r2"),
                     costs={"realization:r1": 100, "realization:r2": 50})
    original = valid.decision_problem("decision-problem:test")
    objective = original.candidates[0].objective_value
    forged = object.__new__(ObjectiveValue)
    for name in ("value", "knowledge_id", "property", "version", "epistemic_status"):
        object.__setattr__(forged, name, getattr(objective, name))
    object.__setattr__(forged, field, value)
    true_invalid = replace(original.candidates[0], objective_value=forged)
    unknown = replace(original.candidates[1],
                     truth=EvaluationTruth.UNKNOWN,
                     grounding_result=replace(original.candidates[1].grounding_result,
                                               truth=EvaluationTruth.UNKNOWN,
                                               conclusion=None),
                     objective_value=None)
    invalid = replace(original, candidates=(true_invalid, unknown))
    with pytest.raises(ValidationError, match="TRUE candidate objective value disagrees with problem objective"):
        problem_module._select_m1(DecisionProblemId("decision-problem:not-persisted"), invalid)
