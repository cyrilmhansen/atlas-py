"""M1c.1 finite decision scopes and their observable grounding runs."""

import json
from types import MappingProxyType
from .errors import AdmissionError, GroundingError, ValidationError
from .identity import DecisionScopeId, DescriptionId, RuleId, SnapshotId, ContextId, KnowledgeId, PredicateId, PropertyId, SourceId
from .model import (AmbiguousRead, DecisionGrounding, DecisionScope, EvaluationTruth,
                    GroundedConclusion, GroundingManifest, GroundingObservation,
                    GroundingResult, GroundingStatus, MissingRead, RelationTerm)
from .model import SUPPORTED_MANIFEST_VERSIONS
from .evidence import validate_grounding_evidence


def _id(cls, value, label):
    if type(value) is cls: return value
    if type(value) is str: return cls(value)
    raise ValidationError(f"{label} requires its exact Atlas identifier domain")


def _manifest(value):
    if type(value) is GroundingManifest: return value
    if type(value) is not dict: raise ValidationError("manifest requires an object")
    known = {"manifest_version", "candidate_description_ids", "prescribed_rule_ids"}
    if set(value) != known: raise ValidationError("manifest contains unknown or missing fields")
    candidates = value["candidate_description_ids"]
    rules = value["prescribed_rule_ids"]
    if type(candidates) is not list or type(rules) is not list:
        raise ValidationError("manifest fields require exact lists")
    return GroundingManifest(value["manifest_version"], tuple(_id(DescriptionId, x, "candidate") for x in candidates),
                             tuple(_id(RuleId, x, "rule") for x in rules))


def validate_grounding_manifest(manifest):
    """Validate the closed M1c.1 manifest contract at every boundary."""
    if type(manifest) is not GroundingManifest:
        raise ValidationError("grounding manifest requires an exact manifest")
    # GroundingManifest performs the closed-version check; keep this function
    # as the single named boundary used by admission and restore.
    if manifest.manifest_version not in SUPPORTED_MANIFEST_VERSIONS:
        raise ValidationError("unsupported grounding manifest version")
    return manifest


def _result_payload(result):
    def read_payload(read):
        return {"participant": read.participant, "description": read.description.value,
                "property": read.property.value, "version": read.version}
    conclusion = None
    if result.conclusion is not None:
        c = result.conclusion
        conclusion = {"predicate": c.term.predicate.value, "version": c.term.version,
                      "participants": [x.value for x in c.term.participants], "polarity": c.polarity,
                      "epistemic_status": c.epistemic_status, "scope": c.scope if type(c.scope) is str else list(c.scope),
                      "provenance": [x.value for x in c.provenance], "rule_id": c.rule_id.value,
                      "rule_version": c.rule_version, "dependencies": [x.value for x in c.dependencies]}
    return {"rule_id": result.rule_id.value, "rule_version": result.rule_version,
            "bindings": [{"participant": k, "description": v.value} for k, v in result.bindings.items()],
            "truth": result.truth.value, "conclusion": conclusion,
            "effective_dependencies": [x.value for x in result.effective_dependencies],
            "missing_reads": [read_payload(x) for x in result.missing_reads],
            "ambiguous_reads": [dict(read_payload(x), knowledge_ids=[i.value for i in x.knowledge_ids]) for x in result.ambiguous_reads],
            "snapshot": result.snapshot.value, "context": result.context.value,
            "grounding_evidence": result.grounding_evidence}


def _result_from_payload(p):
    bindings = MappingProxyType({x["participant"]: _id(DescriptionId, x["description"], "binding") for x in p["bindings"]})
    def missing(x): return MissingRead(x["participant"], _id(DescriptionId, x["description"], "description"), _id(PropertyId, x["property"], "property"), x["version"])
    def ambiguous(x): return AmbiguousRead(x["participant"], _id(DescriptionId, x["description"], "description"), _id(PropertyId, x["property"], "property"), x["version"], tuple(_id(KnowledgeId, i, "knowledge") for i in x["knowledge_ids"]))
    c = p.get("conclusion")
    conclusion = None
    if c is not None:
        scope = c["scope"] if type(c["scope"]) is str else tuple(c["scope"])
        conclusion = GroundedConclusion(RelationTerm(_id(PredicateId, c["predicate"], "predicate"), c["version"], tuple(_id(DescriptionId, x, "participant") for x in c["participants"])), c["polarity"], c["epistemic_status"], scope, tuple(_id(SourceId, x, "source") for x in c["provenance"]), _id(RuleId, c["rule_id"], "rule"), c["rule_version"], tuple(_id(KnowledgeId, x, "knowledge") for x in c["dependencies"]))
    return GroundingResult(_id(RuleId, p["rule_id"], "rule"), p["rule_version"], bindings,
                           EvaluationTruth(p["truth"]), conclusion,
                           tuple(_id(KnowledgeId, x, "knowledge") for x in p["effective_dependencies"]),
                           tuple(missing(x) for x in p["missing_reads"]), tuple(ambiguous(x) for x in p["ambiguous_reads"]),
                           _id(SnapshotId, p["snapshot"], "snapshot"), _id(ContextId, p["context"], "context"), p["grounding_evidence"])


def scope_payload(scope):
    return {"id": scope.id.value, "snapshot": scope.snapshot.value, "context": scope.context.value,
            "request": scope.request.value, "manifest": {"manifest_version": scope.manifest.manifest_version,
            "candidate_description_ids": [x.value for x in scope.manifest.candidate_description_ids],
            "prescribed_rule_ids": [x.value for x in scope.manifest.prescribed_rule_ids]}}


def grounding_payload(grounding):
    return {"id": grounding.scope_id.value, "scope_id": grounding.scope_id.value,
            "status": grounding.status.value, "interrupted": grounding.interrupted, "pruned": grounding.pruned,
            "observations": [{"candidate": x.candidate.value, "traversed": x.traversed,
                "truth": None if x.truth is None else x.truth.value, "grounding_result": None if x.grounding_result is None else _result_payload(x.grounding_result),
                "exclusion_reason": x.exclusion_reason, "structural_error": x.structural_error} for x in grounding.observations]}


def restore_scope(p):
    if set(p) != {"id", "snapshot", "context", "request", "manifest"}: raise ValidationError("invalid persisted decision scope")
    return DecisionScope(_id(DecisionScopeId, p["id"], "decision scope"), _id(SnapshotId, p["snapshot"], "snapshot"), _id(ContextId, p["context"], "context"), _id(DescriptionId, p["request"], "request"), validate_grounding_manifest(_manifest(p["manifest"])))


def restore_grounding(p):
    if set(p) != {"id", "scope_id", "status", "interrupted", "pruned", "observations"} or p["id"] != p["scope_id"] or type(p["observations"]) is not list:
        raise ValidationError("invalid persisted decision grounding")
    observations=[]
    for x in p["observations"]:
        if type(x) is not dict or set(x) != {"candidate", "traversed", "truth", "grounding_result", "exclusion_reason", "structural_error"}: raise ValidationError("invalid persisted grounding observation")
        result = None if x["grounding_result"] is None else _result_from_payload(x["grounding_result"])
        observations.append(GroundingObservation(_id(DescriptionId, x["candidate"], "candidate"), x["traversed"], None if x["truth"] is None else EvaluationTruth(x["truth"]), result, x["exclusion_reason"], x["structural_error"]))
    return DecisionGrounding(_id(DecisionScopeId, p["scope_id"], "decision scope"), tuple(observations), GroundingStatus(p["status"]), p["interrupted"], p["pruned"])


def validate_scope_environment(store, scope):
    validate_grounding_manifest(scope.manifest)
    # The snapshot is historical evidence, not a fallback store.  A scope is
    # publishable only when every definition it names is also present in the
    # final restored definition maps.
    context = store.contexts.get(scope.context.value)
    if context is None:
        raise GroundingError("decision scope context is absent from final contexts")
    snap = store.snapshots.get(scope.snapshot.value)
    if snap is None: raise GroundingError("decision scope snapshot does not exist")
    if scope.context not in snap.context_ids: raise GroundingError("decision scope context is not fixed by snapshot")
    historical_contexts = [x for x in snap.context_definitions if x[0] == scope.context.value]
    if len(historical_contexts) != 1 or context.visible_scopes != historical_contexts[0][1] or tuple(x.value for x in context.enabled_rules) != historical_contexts[0][2]:
        raise GroundingError("decision scope context disagrees with final context")
    if scope.request not in snap.description_ids: raise GroundingError("decision scope request is absent from snapshot")
    if any(x not in snap.description_ids for x in scope.manifest.candidate_description_ids): raise GroundingError("decision scope candidate is absent from snapshot")
    fixed_rules = {x[0]: x[1] for x in snap.rule_definitions}
    if not scope.manifest.prescribed_rule_ids: raise GroundingError("decision scope has no prescribed rule")
    if any(x.value not in fixed_rules for x in scope.manifest.prescribed_rule_ids): raise GroundingError("decision scope rule is absent from snapshot")
    for rule_id in scope.manifest.prescribed_rule_ids:
        rule = store.rules.get(rule_id.value)
        if rule is None or fixed_rules[rule_id.value] != rule.version:
            raise GroundingError("decision scope rule is absent from final rules")


def validate_grounding_result(store, scope, observation):
    """Validate a persisted result against the scope's historical world."""
    result = observation.grounding_result
    if result is None:
        return
    snap = store.snapshots.get(scope.snapshot.value)
    if snap is None or result.snapshot != scope.snapshot or result.context != scope.context:
        raise GroundingError("grounding result environment disagrees with scope")
    if result.rule_id not in scope.manifest.prescribed_rule_ids:
        raise GroundingError("grounding result rule is not prescribed by the manifest")
    matches = [x for x in snap.rule_definitions if x[0] == result.rule_id.value]
    if len(matches) != 1 or matches[0][1] != result.rule_version:
        raise GroundingError("grounding result rule version is not fixed by the snapshot")
    try:
        historical = json.loads(matches[0][2])
        participants = tuple(historical["participants"])
        head = historical["head"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GroundingError("invalid historical grounding rule") from exc
    bindings = result.bindings
    if not hasattr(bindings, "items") or tuple(bindings) != participants:
        raise GroundingError("grounding result bindings disagree with historical rule")
    if any(type(name) is not str or value not in snap.description_ids for name, value in bindings.items()):
        raise GroundingError("grounding result binding is outside the snapshot")
    if bindings.get("candidate") != observation.candidate or bindings.get("request") != scope.request:
        raise GroundingError("grounding result bindings disagree with scope")
    if result.truth is EvaluationTruth.TRUE:
        if result.conclusion is None or tuple(bindings[name] for name in head.get("participants", ())) != result.conclusion.term.participants:
            raise GroundingError("grounding conclusion disagrees with historical rule bindings")
        if result.conclusion.term.predicate.value != head.get("predicate") or result.conclusion.term.version != head.get("version") or result.conclusion.polarity != head.get("polarity"):
            raise GroundingError("grounding conclusion disagrees with historical rule head")
        # Evidence proves that the persisted payload matches its witness; it
        # does not make an arbitrary conclusion semantically admissible.
        if result.conclusion.dependencies != result.effective_dependencies:
            raise GroundingError("grounding conclusion dependencies disagree with effective dependencies")
    elif result.conclusion is not None:
        raise GroundingError("non-TRUE grounding cannot carry a conclusion")
    if len(set(result.effective_dependencies)) != len(result.effective_dependencies):
        raise GroundingError("grounding result contains duplicate dependencies")
    if any(dep not in snap.record_ids or dep.value not in store.records for dep in result.effective_dependencies):
        raise GroundingError("grounding result references an unresolved historical dependency")
    if result.truth is EvaluationTruth.TRUE and any(
            dep not in snap.record_ids or dep.value not in store.records
            for dep in result.conclusion.dependencies):
        raise GroundingError("grounding conclusion references an unresolved historical dependency")
    validate_grounding_evidence(result, participants)


def compute_declared_scope_completeness(store, scope, grounding):
    """Recompute status from the run, never from its persisted status field."""
    validate_scope_environment(store, scope)
    manifest_ids = {x.value for x in scope.manifest.candidate_description_ids}
    observed_ids = [x.candidate.value for x in grounding.observations]
    if len(observed_ids) != len(set(observed_ids)):
        raise ValidationError("duplicate grounding observation")
    if any(x not in manifest_ids for x in observed_ids):
        raise ValidationError("grounding observation is outside the manifest")
    for observation in grounding.observations:
        validate_grounding_result(store, scope, observation)
    if any(x.structural_error is not None for x in grounding.observations):
        return GroundingStatus.INVALID
    if grounding.interrupted or grounding.pruned:
        return GroundingStatus.INCOMPLETE
    if set(observed_ids) != manifest_ids or any(not x.traversed for x in grounding.observations):
        return GroundingStatus.INCOMPLETE
    return GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE


def evaluate(store, scope):
    validate_scope_environment(store, scope)
    if len(scope.manifest.prescribed_rule_ids) != 1: raise GroundingError("M1c.1 requires exactly one prescribed rule")
    rule = scope.manifest.prescribed_rule_ids[0]
    observations=[]; invalid=False
    for candidate in scope.manifest.candidate_description_ids:
        try:
            result = store.ground(rule, {"candidate": candidate, "request": scope.request}, scope.snapshot, scope.context)
            excluded = None
            snap = store.snapshots[scope.snapshot.value]
            context = next(x for x in snap.context_definitions if x[0] == scope.context.value)
            visible = set(context[1])
            for record in store.records.values():
                relevant = ((getattr(record, "predicate", None) == PredicateId("realizes") and
                             getattr(record, "participants", ()) == (candidate, scope.request) and
                             getattr(record, "polarity", None) == "positive") or
                            (getattr(record, "description", None) in {candidate, scope.request}))
                if relevant and record.id in snap.record_ids:
                    scopes = {record.scope} if type(record.scope) is str else set(record.scope)
                    if not scopes.intersection(visible): excluded = "excluded_by_context"
            observations.append(GroundingObservation(candidate, True, result.truth, result, excluded))
        except GroundingError as exc:
            observations.append(GroundingObservation(candidate, True, None, None, structural_error=str(exc)))
            invalid=True
    status = GroundingStatus.INVALID if invalid else GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE
    grounding = DecisionGrounding(scope.id, tuple(observations), status)
    computed = compute_declared_scope_completeness(store, scope, grounding)
    if computed is not status:
        raise GroundingError("evaluated grounding status is inconsistent")
    return grounding
