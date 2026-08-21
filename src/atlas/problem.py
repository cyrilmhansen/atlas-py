"""Pure construction of the finite M1 grounded decision problem.

This module deliberately consumes an already published M1c.1 grounding run.
It does not evaluate rules, discover descriptions, or write store state.
"""

from dataclasses import dataclass

from .errors import GroundingError, ValidationError
from .identity import (ContextId, DecisionScopeId, DescriptionId, KnowledgeId,
                       PropertyId, RuleId, SnapshotId)
from .model import (DecisionGrounding, DecisionScope, EvaluationTruth,
                    GroundingResult, GroundingStatus, PropertyAssertion)
from .scope import compute_declared_scope_completeness, validate_scope_environment
from .values import Integer


@dataclass(frozen=True, slots=True)
class ObjectiveValue:
    """An exact historical objective value and the Knowledge that supports it."""

    value: Integer
    knowledge_id: KnowledgeId
    property: PropertyId
    version: str
    epistemic_status: str

    def __post_init__(self):
        if type(self.value) is not Integer or type(self.knowledge_id) is not KnowledgeId:
            raise ValidationError("objective value requires exact integer and knowledge identities")
        if type(self.property) is not PropertyId or type(self.version) is not str or not self.version:
            raise ValidationError("objective value requires an exact property reference")
        if self.epistemic_status != "exact":
            raise ValidationError("M1 objective values require exact epistemic status")


@dataclass(frozen=True, slots=True)
class M1Objective:
    property: PropertyId
    version: str
    direction: str
    epistemic_status: str

    def __post_init__(self):
        if type(self.property) is not PropertyId or self.property != PropertyId("cost"):
            raise ValidationError("M1 objective must use the profile cost property")
        if type(self.version) is not str or not self.version or self.direction != "minimize":
            raise ValidationError("invalid M1 objective definition")
        if self.epistemic_status != "exact":
            raise ValidationError("M1 objective requires exact epistemic status")


@dataclass(frozen=True, slots=True)
class GroundedCandidate:
    candidate: DescriptionId
    truth: EvaluationTruth
    grounding_result: GroundingResult
    exclusion_reason: str | None
    objective_value: ObjectiveValue | None

    def __post_init__(self):
        if type(self.candidate) is not DescriptionId or type(self.truth) is not EvaluationTruth:
            raise ValidationError("invalid grounded candidate identity or truth")
        if type(self.grounding_result) is not GroundingResult or self.truth is not self.grounding_result.truth:
            raise ValidationError("grounded candidate disagrees with its grounding result")
        if self.exclusion_reason is not None and (type(self.exclusion_reason) is not str or not self.exclusion_reason):
            raise ValidationError("invalid candidate exclusion reason")
        if self.objective_value is not None and type(self.objective_value) is not ObjectiveValue:
            raise ValidationError("invalid candidate objective value")
        if self.truth is not EvaluationTruth.TRUE and self.objective_value is not None:
            raise ValidationError("non-TRUE candidate must not require an objective value")


@dataclass(frozen=True, slots=True)
class GroundedDecisionProblem:
    scope_id: DecisionScopeId
    snapshot: SnapshotId
    context: ContextId
    request: DescriptionId
    manifest_version: str
    rule_id: RuleId
    objective: M1Objective
    candidates: tuple[GroundedCandidate, ...]
    grounding_status: GroundingStatus

    def __post_init__(self):
        if type(self.scope_id) is not DecisionScopeId or type(self.snapshot) is not SnapshotId or type(self.context) is not ContextId or type(self.request) is not DescriptionId:
            raise ValidationError("invalid grounded decision problem environment")
        if type(self.manifest_version) is not str or not self.manifest_version or type(self.rule_id) is not RuleId:
            raise ValidationError("invalid grounded decision problem manifest")
        if type(self.objective) is not M1Objective or type(self.candidates) is not tuple or any(type(x) is not GroundedCandidate for x in self.candidates):
            raise ValidationError("invalid grounded decision problem contents")
        if self.grounding_status is not GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE:
            raise ValidationError("grounded decision problem requires complete declared-scope grounding")
        if len({x.candidate for x in self.candidates}) != len(self.candidates):
            raise ValidationError("grounded decision problem contains duplicate candidates")


def _historical_context(store, scope):
    snapshot = store.open_snapshot(scope.snapshot.value)
    matches = [x for x in snapshot.context_definitions if x[0] == scope.context.value]
    if len(matches) != 1:
        raise GroundingError("context is not uniquely fixed by the scope snapshot")
    return snapshot, tuple(matches[0][1])


def _objective_version(snapshot):
    versions = [version for property_id, version in snapshot.property_versions if property_id == "cost"]
    if len(versions) != 1:
        raise GroundingError("M1 cost property version is absent or ambiguous in the scope snapshot")
    return versions[0]


def _objective_for_true(store, candidate, snapshot, visible_scopes, version):
    records = [record for record in store.records.values()
               if isinstance(record, PropertyAssertion)
               and record.id in snapshot.record_ids
               and ("property", record.id.value) not in store.isolated
               and record.description == candidate
               and record.property == PropertyId("cost")
               and record.version == version
               and record.scope in visible_scopes]
    if not records:
        raise GroundingError(f"required historical M1 cost is missing for {candidate.value}")
    if len(records) != 1:
        raise GroundingError(f"required historical M1 cost is ambiguous for {candidate.value}")
    record = records[0]
    if type(record.value) is not Integer:
        raise GroundingError(f"historical M1 cost is not an exact integer for {candidate.value}")
    if record.epistemic_status != "exact":
        raise GroundingError(f"historical M1 cost is not exact for {candidate.value}")
    return ObjectiveValue(record.value, record.id, record.property, record.version, record.epistemic_status)


def build_grounded_decision_problem(store, decision_scope_id):
    """Construct a problem from the persisted complete grounding run only."""
    store._check()
    scope = store.decision_scope(decision_scope_id)
    grounding = store.decision_grounding(scope.id)
    if type(scope) is not DecisionScope or type(grounding) is not DecisionGrounding or grounding.scope_id != scope.id:
        raise GroundingError("scope and grounding identities do not match")
    validate_scope_environment(store, scope)
    if grounding.status is not GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE:
        raise GroundingError("decision grounding is not complete for its declared scope")
    if compute_declared_scope_completeness(store, scope, grounding) is not GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE:
        raise GroundingError("decision grounding is not complete for its declared scope")
    snapshot, visible_scopes = _historical_context(store, scope)
    if len(scope.manifest.prescribed_rule_ids) != 1:
        raise GroundingError("M1 requires exactly one prescribed historical rule")
    rule_id = scope.manifest.prescribed_rule_ids[0]
    cost_version = _objective_version(snapshot)
    observations = {observation.candidate: observation for observation in grounding.observations}
    candidates = []
    for candidate in scope.manifest.candidate_description_ids:
        observation = observations.get(candidate)
        if observation is None or not observation.traversed or observation.grounding_result is None:
            raise GroundingError("grounding does not contain the complete manifest candidate")
        objective = (_objective_for_true(store, candidate, snapshot, visible_scopes, cost_version)
                     if observation.truth is EvaluationTruth.TRUE else None)
        candidates.append(GroundedCandidate(candidate, observation.truth, observation.grounding_result,
                                            observation.exclusion_reason, objective))
    return GroundedDecisionProblem(scope.id, scope.snapshot, scope.context, scope.request,
                                   scope.manifest.manifest_version, rule_id,
                                   M1Objective(PropertyId("cost"), cost_version, "minimize", "exact"),
                                   tuple(candidates), GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE)
