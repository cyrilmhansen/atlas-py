"""M1c.1 finite decision scopes and their observable grounding runs."""

import json
from types import MappingProxyType
from .errors import AdmissionError, GroundingError, ValidationError
from .identity import DecisionScopeId, DescriptionId, RuleId, SnapshotId, ContextId, KnowledgeId, PredicateId, PropertyId, SourceId
from .model import (AmbiguousRead, DecisionGrounding, DecisionScope, EvaluationTruth,
                    GroundedConclusion, GroundingManifest, GroundingObservation,
                    GroundingResult, GroundingStatus, MissingRead, RelationTerm,
                    DiscoveryEvidence, DiscoveryExclusion, DiscoveryExclusionReason,
                    DiscoveryQuery)
from .model import (DECISION_GROUNDING_LEGACY_SCHEMA, DECISION_GROUNDING_CURRENT_SCHEMA,
                    DECISION_SCOPE_LEGACY_SCHEMA, DECISION_SCOPE_CURRENT_SCHEMA)
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
    return {"schema": DECISION_SCOPE_CURRENT_SCHEMA, "id": scope.id.value,
            "snapshot": scope.snapshot.value, "context": scope.context.value,
            "intention": scope.intention.value, "request": scope.request.value,
            "manifest": {"manifest_version": scope.manifest.manifest_version,
            "candidate_description_ids": [x.value for x in scope.manifest.candidate_description_ids],
            "prescribed_rule_ids": [x.value for x in scope.manifest.prescribed_rule_ids]}}


def grounding_payload(grounding):
    def discovery_payload(evidence):
        if evidence is None:
            return None
        return {"schema": evidence.schema,
                "query": {"kind": evidence.query.kind, "predicate": evidence.query.predicate.value,
                          "version": evidence.query.version,
                          "participants": [x.value for x in evidence.query.participants],
                          "polarity": evidence.query.polarity},
                "found": [x.value for x in evidence.found],
                "included": [x.value for x in evidence.included],
                "excluded": [{"knowledge_id": x.knowledge_id.value, "reason": x.reason.value}
                             for x in evidence.excluded]}
    observations = [{"candidate": x.candidate.value, "traversed": x.traversed,
                "truth": None if x.truth is None else x.truth.value, "grounding_result": None if x.grounding_result is None else _result_payload(x.grounding_result),
                "exclusion_reason": x.exclusion_reason, "structural_error": x.structural_error,
                "discovery_evidence": discovery_payload(x.discovery_evidence)} for x in grounding.observations]
    if grounding.schema == DECISION_GROUNDING_LEGACY_SCHEMA:
        observations = [{key: value for key, value in item.items() if key != "discovery_evidence"} for item in observations]
        return {"id": grounding.scope_id.value, "scope_id": grounding.scope_id.value,
            "status": grounding.status.value, "interrupted": grounding.interrupted, "pruned": grounding.pruned,
            "observations": observations}
    return {"schema": grounding.schema, "id": grounding.scope_id.value, "scope_id": grounding.scope_id.value,
            "status": grounding.status.value, "interrupted": grounding.interrupted, "pruned": grounding.pruned,
            "observations": observations}


def restore_scope(p):
    legacy_keys = {"id", "snapshot", "context", "request", "manifest"}
    current_keys = legacy_keys | {"schema", "intention"}
    if type(p) is not dict or (set(p) != legacy_keys and set(p) != current_keys):
        raise ValidationError("invalid persisted decision scope")
    # The closed shape is the format discriminator.  A seven-key payload is
    # current and must carry the only current schema; its schema value must
    # never reclassify it as the historical five-key payload.
    if set(p) == legacy_keys:
        schema = DECISION_SCOPE_LEGACY_SCHEMA
        intention = DescriptionId("intent:selection")
    else:
        if p["schema"] != DECISION_SCOPE_CURRENT_SCHEMA:
            raise ValidationError("unsupported persisted decision scope schema")
        schema = DECISION_SCOPE_CURRENT_SCHEMA
        intention = _id(DescriptionId, p["intention"], "intention")
    return DecisionScope(_id(DecisionScopeId, p["id"], "decision scope"),
                        _id(SnapshotId, p["snapshot"], "snapshot"),
                        _id(ContextId, p["context"], "context"), intention,
                        _id(DescriptionId, p["request"], "request"),
                        validate_grounding_manifest(_manifest(p["manifest"])), schema)


def restore_grounding(p):
    legacy_keys = {"id", "scope_id", "status", "interrupted", "pruned", "observations"}
    current_keys = legacy_keys | {"schema"}
    if type(p) is not dict or set(p) not in (legacy_keys, current_keys) or p["id"] != p["scope_id"] or type(p["observations"]) is not list:
        raise ValidationError("invalid persisted decision grounding")
    schema = DECISION_GROUNDING_LEGACY_SCHEMA if set(p) == legacy_keys else p["schema"]
    if schema not in {DECISION_GROUNDING_LEGACY_SCHEMA, DECISION_GROUNDING_CURRENT_SCHEMA}:
        raise ValidationError("unsupported persisted decision grounding schema")
    observations=[]
    for x in p["observations"]:
        old_keys = {"candidate", "traversed", "truth", "grounding_result", "exclusion_reason", "structural_error"}
        new_keys = old_keys | {"discovery_evidence"}
        expected = new_keys if schema == DECISION_GROUNDING_CURRENT_SCHEMA else old_keys
        if type(x) is not dict or set(x) != expected: raise ValidationError("invalid persisted grounding observation")
        result = None if x["grounding_result"] is None else _result_from_payload(x["grounding_result"])
        evidence = None
        if "discovery_evidence" in x:
            raw = x["discovery_evidence"]
            if raw is not None:
                if type(raw) is not dict or set(raw) != {"schema", "query", "found", "included", "excluded"}:
                    raise ValidationError("invalid persisted discovery evidence")
                q = raw["query"]
                if type(q) is not dict or set(q) != {"kind", "predicate", "version", "participants", "polarity"}:
                    raise ValidationError("invalid persisted discovery query")
                evidence = DiscoveryEvidence(
                    raw["schema"],
                    DiscoveryQuery(q["kind"], _id(PredicateId, q["predicate"], "predicate"), q["version"],
                                   tuple(_id(DescriptionId, x, "participant") for x in q["participants"]), q["polarity"]),
                    tuple(_id(KnowledgeId, x, "found knowledge") for x in raw["found"]),
                    tuple(_id(KnowledgeId, x, "included knowledge") for x in raw["included"]),
                    tuple(_restore_discovery_exclusion(item) for item in raw["excluded"]))
        observations.append(GroundingObservation(_id(DescriptionId, x["candidate"], "candidate"), x["traversed"], None if x["truth"] is None else EvaluationTruth(x["truth"]), result, x["exclusion_reason"], x["structural_error"], evidence))
    grounding = DecisionGrounding(_id(DecisionScopeId, p["scope_id"], "decision scope"), tuple(observations), GroundingStatus(p["status"]), p["interrupted"], p["pruned"], schema)
    if schema == DECISION_GROUNDING_CURRENT_SCHEMA and any(x.discovery_evidence is None for x in observations if x.structural_error is None):
        raise ValidationError("current decision grounding requires discovery evidence")
    return grounding


def _restore_discovery_exclusion(item):
    if type(item) is not dict or set(item) != {"knowledge_id", "reason"}:
        raise ValidationError("invalid persisted discovery exclusion")
    return DiscoveryExclusion(_id(KnowledgeId, item["knowledge_id"], "excluded knowledge"),
                             DiscoveryExclusionReason(item["reason"]))


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
    # Legacy scopes synthesize the historical intention rather than carrying
    # it in their payload.  That synthesized identity is still an intrinsic
    # scope claim and must be fixed by the scope's snapshot.
    if scope.intention not in snap.description_ids:
        raise GroundingError("decision scope intention is absent from snapshot")
    if scope.schema == DECISION_SCOPE_CURRENT_SCHEMA:
        if scope.intention == scope.request: raise GroundingError("decision scope intention and request must differ")
    if scope.request not in snap.description_ids: raise GroundingError("decision scope request is absent from snapshot")
    if any(x not in snap.description_ids for x in scope.manifest.candidate_description_ids): raise GroundingError("decision scope candidate is absent from snapshot")
    fixed_rules = {x[0]: x[1] for x in snap.rule_definitions}
    if not scope.manifest.prescribed_rule_ids: raise GroundingError("decision scope has no prescribed rule")
    if any(x.value not in fixed_rules for x in scope.manifest.prescribed_rule_ids): raise GroundingError("decision scope rule is absent from snapshot")
    for rule_id in scope.manifest.prescribed_rule_ids:
        rule = store.rules.get(rule_id.value)
        if rule is None or fixed_rules[rule_id.value] != rule.version:
            raise GroundingError("decision scope rule is absent from final rules")


def validate_scope_grounding_compatibility(scope, grounding):
    """Enforce the asymmetric historical/current format boundary."""
    pair = (scope.schema, grounding.schema)
    allowed = {
        (DECISION_SCOPE_LEGACY_SCHEMA, DECISION_GROUNDING_LEGACY_SCHEMA),
        (DECISION_SCOPE_LEGACY_SCHEMA, DECISION_GROUNDING_CURRENT_SCHEMA),
        (DECISION_SCOPE_CURRENT_SCHEMA, DECISION_GROUNDING_CURRENT_SCHEMA),
    }
    if pair not in allowed:
        raise GroundingError("current decision scope cannot use legacy grounding")


def validate_grounding_result(store, scope, observation, *, current_scope_semantics=False):
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
    admissible_record_ids = (set(store._effective_record_ids(snap.id))
                             if current_scope_semantics else set(snap.record_ids))
    if any(dep not in admissible_record_ids or dep.value not in store.records for dep in result.effective_dependencies):
        raise GroundingError("grounding result references an unresolved historical dependency")
    if result.truth is EvaluationTruth.TRUE and any(
            dep not in admissible_record_ids or dep.value not in store.records
            for dep in result.conclusion.dependencies):
        raise GroundingError("grounding conclusion references an unresolved historical dependency")
    validate_grounding_evidence(result, participants)


def validate_discovery_evidence(store, scope, observation):
    """Validate a persisted certificate by pure recomputation.

    The recomputation is an equality check only. It never replaces the
    persisted certificate and never writes or repairs the SQLite payload.
    """
    evidence = observation.discovery_evidence
    if evidence is None:
        return
    query = evidence.query
    snap = store.snapshots.get(scope.snapshot.value)
    if snap is None or query.participants != (observation.candidate, scope.intention):
        raise GroundingError("discovery query bindings disagree with scope")
    versions = [version for predicate, version in snap.predicate_versions if predicate == query.predicate.value]
    if len(versions) != 1 or versions[0] != query.version:
        raise GroundingError("discovery query predicate version is not fixed by snapshot")
    if query.predicate != PredicateId("realizes") or query.polarity != "positive":
        raise GroundingError("unsupported discovery query")
    if not any(x[0] == scope.context.value for x in snap.context_definitions):
        raise GroundingError("discovery query context is absent from snapshot")
    expected = discover_relation(store, scope, observation.candidate)
    if (evidence.query != expected.query or evidence.found != expected.found or
            evidence.included != expected.included or evidence.excluded != expected.excluded):
        raise GroundingError("discovery evidence disagrees with pure semantic discovery")


def discover_relation(store, scope, candidate):
    """Perform the one Core V1 discovery operation used by scope evaluation."""
    snap = store.snapshots[scope.snapshot.value]
    context = next(x for x in snap.context_definitions if x[0] == scope.context.value)
    visible = set(context[1])
    relation_version = [version for predicate, version in snap.predicate_versions if predicate == "realizes"]
    if len(relation_version) != 1:
        raise GroundingError("discovery predicate version is not unique in snapshot")
    query = DiscoveryQuery("relation", PredicateId("realizes"), relation_version[0],
                           (candidate, scope.intention), "positive")
    effective_ids = set(store._effective_record_ids(snap.id))
    matches = [record for record in store.records.values()
               if type(record).__name__ == "RelationAssertion" and record.id in effective_ids
               and ("relation", record.id.value) not in store.isolated
               and record.predicate == query.predicate and record.version == query.version
               and record.participants == query.participants and record.polarity == query.polarity]
    matches.sort(key=lambda record: record.id.value)
    found = tuple(record.id for record in matches)
    included = tuple(record.id for record in matches
                     if (set(record.scope) if type(record.scope) is tuple else {record.scope}) & visible)
    return DiscoveryEvidence("atlas.core-v1.discovery-evidence/1", query, found, included,
                             tuple(DiscoveryExclusion(record.id, DiscoveryExclusionReason.OUTSIDE_CONTEXT)
                                   for record in matches if record.id not in included))


def _missing_read_is_outside_context(store, scope, result):
    """Retain the pre-R1A diagnostic for a property hidden by the context.

    This is not a second relation discovery: it only explains an UNKNOWN
    property read already reported by the rule evaluator.
    """
    if result is None or not result.missing_reads:
        return False
    snap = store.snapshots[scope.snapshot.value]
    context = next(x for x in snap.context_definitions if x[0] == scope.context.value)
    visible = set(context[1])
    effective = set(store._effective_record_ids(snap.id))
    for read in result.missing_reads:
        if read.participant not in {"candidate", "request"}:
            continue
        for record in store.records.values():
            if (type(record).__name__ == "PropertyAssertion" and record.id in effective
                    and ("property", record.id.value) not in store.isolated
                    and record.description == read.description and record.property == read.property
                    and record.version == read.version
                    and not ((set(record.scope) if type(record.scope) is tuple else {record.scope}) & visible)):
                return True
    return False


def compute_declared_scope_completeness(store, scope, grounding):
    """Recompute status from the run, never from its persisted status field."""
    validate_scope_environment(store, scope)
    validate_scope_grounding_compatibility(scope, grounding)
    manifest_ids = {x.value for x in scope.manifest.candidate_description_ids}
    observed_ids = [x.candidate.value for x in grounding.observations]
    if len(observed_ids) != len(set(observed_ids)):
        raise ValidationError("duplicate grounding observation")
    if any(x not in manifest_ids for x in observed_ids):
        raise ValidationError("grounding observation is outside the manifest")
    for observation in grounding.observations:
        validate_grounding_result(
            store, scope, observation,
            current_scope_semantics=(grounding.schema == DECISION_GROUNDING_CURRENT_SCHEMA))
        if grounding.schema == DECISION_GROUNDING_CURRENT_SCHEMA:
            validate_discovery_evidence(store, scope, observation)
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
            evidence = discover_relation(store, scope, candidate)
            result = store.ground(rule, {"candidate": candidate, "request": scope.request}, scope.snapshot, scope.context)
            # Candidate scope membership is authoritative only when at least
            # one discovered relation is included. Excluded relations remain
            # certificate facts and do not veto another included relation.
            excluded = None if evidence.included else "excluded_by_context"
            observations.append(GroundingObservation(candidate, True, result.truth, result, excluded, None, evidence))
        except GroundingError as exc:
            observations.append(GroundingObservation(candidate, True, None, None, structural_error=str(exc)))
            invalid=True
    status = GroundingStatus.INVALID if invalid else GroundingStatus.COMPLETE_FOR_DECLARED_SCOPE
    grounding = DecisionGrounding(scope.id, tuple(observations), status, schema=DECISION_GROUNDING_CURRENT_SCHEMA)
    computed = compute_declared_scope_completeness(store, scope, grounding)
    if computed is not status:
        raise GroundingError("evaluated grounding status is inconsistent")
    return grounding
