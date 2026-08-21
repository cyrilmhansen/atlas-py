"""Pure construction of the finite M1 grounded decision problem.

This module deliberately consumes an already published M1c.1 grounding run.
It does not evaluate rules, discover descriptions, or write store state.
"""

from dataclasses import dataclass

from .errors import GroundingError, ValidationError
from .identity import (ContextId, DecisionProblemId, DecisionScopeId, DescriptionId,
                       KnowledgeId, PropertyId, RuleId, SnapshotId)
from .model import (DecisionGrounding, DecisionScope, EvaluationTruth,
                    GroundingResult, GroundingStatus, PropertyAssertion)
from .scope import (_result_from_payload, _result_payload,
                    compute_declared_scope_completeness, validate_scope_environment)
from .values import Integer, value_from_json, value_to_json


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


PROBLEM_SCHEMA = "atlas.core-v1.grounded-decision-problem/1"


def grounded_decision_problem_payload(problem_id, problem):
    """Return the closed, versioned representation admitted by M1c.2.2."""
    if type(problem_id) is not DecisionProblemId or type(problem) is not GroundedDecisionProblem:
        raise ValidationError("grounded decision problem admission requires exact types")
    return {
        "schema": PROBLEM_SCHEMA, "id": problem_id.value,
        "scope_id": problem.scope_id.value, "snapshot": problem.snapshot.value,
        "context": problem.context.value, "request": problem.request.value,
        "manifest_version": problem.manifest_version, "rule_id": problem.rule_id.value,
        "objective": {"property": problem.objective.property.value,
                       "version": problem.objective.version,
                       "direction": problem.objective.direction,
                       "epistemic_status": problem.objective.epistemic_status},
        "candidates": [{
            "candidate": item.candidate.value, "truth": item.truth.value,
            "grounding_result": _result_payload(item.grounding_result),
            "exclusion_reason": item.exclusion_reason,
            "objective_value": None if item.objective_value is None else {
                "value": value_to_json(item.objective_value.value),
                "knowledge_id": item.objective_value.knowledge_id.value,
                "property": item.objective_value.property.value,
                "version": item.objective_value.version,
                "epistemic_status": item.objective_value.epistemic_status,
            }} for item in problem.candidates],
        "grounding_status": problem.grounding_status.value,
    }


def _required_keys(value, keys, message):
    if type(value) is not dict or set(value) != set(keys):
        raise ValidationError(message)


def restore_grounded_decision_problem(raw):
    """Decode only an exact GDP payload; semantic checks happen at the store boundary."""
    _required_keys(raw, {"schema", "id", "scope_id", "snapshot", "context", "request",
                         "manifest_version", "rule_id", "objective", "candidates",
                         "grounding_status"}, "invalid persisted grounded decision problem")
    if raw["schema"] != PROBLEM_SCHEMA or type(raw["schema"]) is not str:
        raise ValidationError("unsupported grounded decision problem schema")
    if any(type(raw[key]) is not str for key in ("id", "scope_id", "snapshot", "context", "request", "manifest_version", "rule_id", "grounding_status")):
        raise ValidationError("grounded decision problem identity fields require exact strings")
    _required_keys(raw["objective"], {"property", "version", "direction", "epistemic_status"}, "invalid persisted objective")
    if any(type(raw["objective"][key]) is not str for key in ("property", "version", "direction", "epistemic_status")):
        raise ValidationError("objective fields require exact strings")
    if type(raw["candidates"]) is not list:
        raise ValidationError("persisted candidates require an exact list")
    candidates = []
    for item in raw["candidates"]:
        _required_keys(item, {"candidate", "truth", "grounding_result", "exclusion_reason", "objective_value"}, "invalid persisted candidate")
        if type(item["candidate"]) is not str or type(item["truth"]) is not str or type(item["grounding_result"]) is not dict:
            raise ValidationError("invalid persisted candidate shape")
        if item["exclusion_reason"] is not None and type(item["exclusion_reason"]) is not str:
            raise ValidationError("invalid persisted exclusion reason")
        result = _result_from_payload_strict(item["grounding_result"])
        objective_raw = item["objective_value"]
        objective = None
        if objective_raw is not None:
            _required_keys(objective_raw, {"value", "knowledge_id", "property", "version", "epistemic_status"}, "invalid persisted objective value")
            if (type(objective_raw["value"]) is not dict or
                any(type(objective_raw[key]) is not str for key in ("knowledge_id", "property", "version", "epistemic_status"))):
                raise ValidationError("invalid persisted objective value shape")
            objective = ObjectiveValue(value_from_json_strict(objective_raw["value"]), KnowledgeId(objective_raw["knowledge_id"]),
                                       PropertyId(objective_raw["property"]), objective_raw["version"], objective_raw["epistemic_status"])
        candidates.append(GroundedCandidate(DescriptionId(item["candidate"]), EvaluationTruth(item["truth"]), result,
                                             item["exclusion_reason"], objective))
    return DecisionProblemId(raw["id"]), GroundedDecisionProblem(
        DecisionScopeId(raw["scope_id"]), SnapshotId(raw["snapshot"]), ContextId(raw["context"]),
        DescriptionId(raw["request"]), raw["manifest_version"], RuleId(raw["rule_id"]),
        M1Objective(PropertyId(raw["objective"]["property"]), raw["objective"]["version"],
                    raw["objective"]["direction"], raw["objective"]["epistemic_status"]),
        tuple(candidates), GroundingStatus(raw["grounding_status"]))


def _result_from_payload_strict(raw):
    # The existing M1c.1 decoder is used only after the complete closed shape
    # boundary.  In particular, no mapping conversion may silently collapse a
    # duplicate binding or an arbitrary scalar may be turned into a tuple.
    _required_keys(raw, {"rule_id", "rule_version", "bindings", "truth", "conclusion",
                         "effective_dependencies", "missing_reads", "ambiguous_reads",
                         "snapshot", "context", "grounding_evidence"}, "invalid persisted grounding result")
    if type(raw["bindings"]) is not list or type(raw["effective_dependencies"]) is not list or type(raw["missing_reads"]) is not list or type(raw["ambiguous_reads"]) is not list:
        raise ValidationError("grounding result collections require exact lists")
    if any(type(x) is not dict or set(x) != {"participant", "description"} or type(x["participant"]) is not str or type(x["description"]) is not str for x in raw["bindings"]):
        raise ValidationError("invalid grounding result bindings")
    if any(type(x) is not str for x in (raw["rule_id"], raw["rule_version"], raw["truth"], raw["snapshot"], raw["context"], raw["grounding_evidence"])):
        raise ValidationError("invalid grounding result scalar")
    if any(type(x) is not str for x in raw["effective_dependencies"]):
        raise ValidationError("invalid grounding result dependency")
    if len({x["participant"] for x in raw["bindings"]}) != len(raw["bindings"]):
        raise ValidationError("duplicate grounding result binding")
    if raw["conclusion"] is not None:
        c = raw["conclusion"]
        _required_keys(c, {"predicate", "version", "participants", "polarity", "epistemic_status",
                           "scope", "provenance", "rule_id", "rule_version", "dependencies"},
                       "invalid persisted grounding conclusion")
        if (any(type(c[key]) is not str for key in ("predicate", "version", "polarity", "epistemic_status", "rule_id", "rule_version")) or
            type(c["participants"]) is not list or type(c["provenance"]) is not list or type(c["dependencies"]) is not list or
            any(type(x) is not str for x in c["participants"]) or any(type(x) is not str for x in c["provenance"]) or
            any(type(x) is not str for x in c["dependencies"])):
            raise ValidationError("invalid persisted grounding conclusion shape")
        if type(c["scope"]) is not str and (type(c["scope"]) is not list or any(type(x) is not str for x in c["scope"])):
            raise ValidationError("invalid persisted grounding conclusion scope")
        if len(set(c["dependencies"])) != len(c["dependencies"]):
            raise ValidationError("duplicate grounding conclusion dependency")
    for read in raw["missing_reads"]:
        _required_keys(read, {"participant", "description", "property", "version"}, "invalid persisted missing read")
        if any(type(read[key]) is not str for key in ("participant", "description", "property", "version")):
            raise ValidationError("invalid persisted missing read shape")
    for read in raw["ambiguous_reads"]:
        _required_keys(read, {"participant", "description", "property", "version", "knowledge_ids"}, "invalid persisted ambiguous read")
        if (any(type(read[key]) is not str for key in ("participant", "description", "property", "version")) or
            type(read["knowledge_ids"]) is not list or any(type(x) is not str for x in read["knowledge_ids"])):
            raise ValidationError("invalid persisted ambiguous read shape")
        if len(set(read["knowledge_ids"])) != len(read["knowledge_ids"]):
            raise ValidationError("duplicate ambiguous read knowledge identity")
    return _result_from_payload(raw)


def value_from_json_strict(raw):
    if type(raw) is not dict or set(raw) != {"kind", "value"} or type(raw["kind"]) is not str:
        raise ValidationError("invalid persisted objective integer value")
    if raw["kind"] != "integer" or type(raw["value"]) is not str:
        raise ValidationError("objective value must be an exact integer representation")
    return value_from_json(raw, "integer")


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


def _eligible_historical_objective_supports(store, candidate, property_id, version,
                                            snapshot, visible_scopes):
    """Return the M1-admissible objective supports in one history."""
    return tuple(record for record in store.records.values()
                 if isinstance(record, PropertyAssertion)
                 and record.id in snapshot.record_ids
                 and ("property", record.id.value) not in store.isolated
                 and record.description == candidate
                 and record.property == property_id
                 and record.version == version
                 and record.scope in visible_scopes
                 and record.epistemic_status == "exact"
                 and type(record.value) is Integer)


def _validate_persisted_objective_support(store, candidate, problem_objective,
                                          objective_value, snapshot, visible_scopes):
    """Validate a persisted support under the problem's objective authority."""
    if type(objective_value) is not ObjectiveValue:
        raise GroundingError(f"TRUE candidate has no persisted objective support: {candidate.value}")
    if (objective_value.property != problem_objective.property or
            objective_value.version != problem_objective.version or
            objective_value.epistemic_status != problem_objective.epistemic_status):
        raise GroundingError(f"persisted objective value disagrees with the problem objective: {candidate.value}")
    record = store.records.get(objective_value.knowledge_id.value)
    if not isinstance(record, PropertyAssertion) or record.id != objective_value.knowledge_id:
        raise GroundingError(f"persisted objective support is not the referenced property: {candidate.value}")
    if ("property", record.id.value) in store.isolated:
        raise GroundingError(f"persisted objective support is isolated: {candidate.value}")
    if record.id not in snapshot.record_ids:
        raise GroundingError(f"persisted objective support is outside the historical snapshot: {candidate.value}")
    if record.scope not in visible_scopes:
        raise GroundingError(f"persisted objective support is outside the historical context: {candidate.value}")
    if (record.description != candidate or record.property != problem_objective.property or
            record.version != problem_objective.version or type(record.value) is not Integer or
            record.epistemic_status != problem_objective.epistemic_status or
            record.value != objective_value.value):
        raise GroundingError(f"persisted objective support disagrees with the candidate: {candidate.value}")
    eligible = _eligible_historical_objective_supports(
        store, candidate, problem_objective.property, problem_objective.version,
        snapshot, visible_scopes)
    if len(eligible) != 1:
        raise GroundingError(f"historical M1 cost is not uniquely admissible for {candidate.value}")
    if eligible[0].id != objective_value.knowledge_id:
        raise GroundingError(f"persisted objective support is not the unique historical support: {candidate.value}")


def validate_persisted_grounded_decision_problem(store, problem):
    """Validate an already decoded historical GDP against active prerequisites.

    This deliberately checks the persisted fields directly.  It must never
    construct an expected GDP from the scope and grounding.
    """
    store._check()
    scope = store.decision_scopes.get(problem.scope_id.value)
    grounding = store.decision_groundings.get(problem.scope_id.value)
    if scope is None or grounding is None:
        raise GroundingError("grounded decision problem references an invalid source grounding")
    validate_scope_environment(store, scope)
    if (problem.snapshot != scope.snapshot or problem.context != scope.context or
            problem.request != scope.request or
            problem.manifest_version != scope.manifest.manifest_version):
        raise GroundingError("persisted grounded decision problem environment disagrees with scope")
    if grounding.status is not GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE:
        raise GroundingError("decision grounding is not complete for its declared scope")
    if compute_declared_scope_completeness(store, scope, grounding) is not GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE:
        raise GroundingError("decision grounding is not complete for its declared scope")

    if len(scope.manifest.prescribed_rule_ids) != 1:
        raise GroundingError("M1 requires exactly one prescribed historical rule")
    rule_id = scope.manifest.prescribed_rule_ids[0]
    snapshot = store.open_snapshot(scope.snapshot.value)
    rule_matches = [x for x in snapshot.rule_definitions if x[0] == rule_id.value]
    if len(rule_matches) != 1 or problem.rule_id != rule_id:
        raise GroundingError("persisted grounded decision problem rule disagrees with the manifest")
    if rule_matches[0][1] != store.rules[rule_id.value].version:
        raise GroundingError("historical rule version is not active")

    objective_version = _objective_version(snapshot)
    expected_objective = M1Objective(PropertyId("cost"), objective_version, "minimize", "exact")
    if problem.objective != expected_objective:
        raise GroundingError("persisted objective definition disagrees with the historical snapshot")

    manifest_candidates = scope.manifest.candidate_description_ids
    observations = grounding.observations
    if (tuple(item.candidate for item in problem.candidates) != manifest_candidates or
            tuple(item.candidate for item in observations) != manifest_candidates or
            len(problem.candidates) != len(observations)):
        raise GroundingError("persisted candidates do not exactly match the manifest and grounding order")
    _, visible_scopes = _historical_context(store, scope)
    for candidate, observation in zip(problem.candidates, observations):
        if (candidate.truth is not observation.truth or
                candidate.grounding_result != observation.grounding_result or
                candidate.exclusion_reason != observation.exclusion_reason):
            raise GroundingError("persisted candidate disagrees with its historical grounding observation")
        if candidate.truth is EvaluationTruth.TRUE:
            if candidate.objective_value is None:
                raise GroundingError(f"TRUE candidate has no objective value: {candidate.candidate.value}")
            if (candidate.objective_value.property != problem.objective.property or
                    candidate.objective_value.version != problem.objective.version or
                    candidate.objective_value.epistemic_status != problem.objective.epistemic_status):
                raise GroundingError(
                    f"persisted objective value disagrees with the problem objective: {candidate.candidate.value}")
            _validate_persisted_objective_support(store, candidate.candidate,
                                                  problem.objective, candidate.objective_value,
                                                  snapshot,
                                                  visible_scopes)
        elif candidate.objective_value is not None:
            raise GroundingError(f"non-TRUE candidate has an objective value: {candidate.candidate.value}")


def _objective_for_true(store, candidate, snapshot, visible_scopes, version):
    records = _eligible_historical_objective_supports(
        store, candidate, PropertyId("cost"), version, snapshot, visible_scopes)
    if not records:
        # Keep the M1c.2.1 diagnostic for a present but unusable assertion;
        # unusable assertions are not members of the admissible support set.
        matching = tuple(record for record in store.records.values()
                         if isinstance(record, PropertyAssertion)
                         and record.id in snapshot.record_ids
                         and ("property", record.id.value) not in store.isolated
                         and record.description == candidate
                         and record.property == PropertyId("cost")
                         and record.version == version
                         and record.scope in visible_scopes)
        if any(type(record.value) is not Integer for record in matching):
            raise GroundingError(f"historical M1 cost is not an exact integer for {candidate.value}")
        if any(record.epistemic_status != "exact" for record in matching):
            raise GroundingError(f"historical M1 cost is not exact for {candidate.value}")
        raise GroundingError(f"required historical M1 cost is missing for {candidate.value}")
    if len(records) != 1:
        raise GroundingError(f"required historical M1 cost is ambiguous for {candidate.value}")
    record = records[0]
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
