"""Pure M1b.1 rule grounding and evaluation."""

import json
from collections.abc import Mapping
from types import MappingProxyType

from .errors import GroundingError, UnsupportedRuleError, ValidationError
from .identity import ContextId, DescriptionId, PropertyId, RuleId, SnapshotId, PredicateId
from .model import (AmbiguousRead, EvaluationTruth, GroundedConclusion,
                    GroundingResult, MissingRead, PropertyAssertion, RelationTerm)
from .evidence import evidence_for
from .provenance import canonical_provenance
from .values import FiniteSetSymbol


class _State:
    def __init__(self):
        self.dependencies, self.missing, self.ambiguous = [], [], []
        self.provenance, self.epistemic = [], []
    def dependency(self, ident):
        if ident not in self.dependencies: self.dependencies.append(ident)
    def source(self, ident):
        if ident not in self.provenance: self.provenance.append(ident)


def _identifier(cls, value, label):
    if type(value) is cls: return value
    if type(value) is str: return cls(value)
    raise ValidationError(f"{label} requires its exact Atlas identifier domain")


def _historical_rule(snapshot, rule_id):
    matches = [x for x in snapshot.rule_definitions if x[0] == rule_id.value]
    if len(matches) != 1: raise GroundingError("rule is not fixed by the requested snapshot")
    ident, version, payload, supported = matches[0]
    if not supported: raise UnsupportedRuleError(f"rule {ident}@{version} is unsupported")
    try: return version, json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc: raise GroundingError("invalid historical rule") from exc


def _historical_context(snapshot, context_id):
    matches = [x for x in snapshot.context_definitions if x[0] == context_id.value]
    if len(matches) != 1: raise GroundingError("context is not fixed by the requested snapshot")
    _, scopes, enabled = matches[0]
    return tuple(scopes), tuple(enabled)


def _property_version(snapshot, property_id):
    versions = [version for ident, version in snapshot.property_versions if ident == property_id.value]
    if len(versions) != 1: raise GroundingError("property version is not unique in the snapshot")
    return versions[0]


def _scope(scopes): return scopes[0] if len(scopes) == 1 else tuple(scopes)


def _terminal_provenance(store, dependencies):
    sources = {source for dependency in dependencies
               for source in getattr(store.records.get(dependency.value), "provenance", ())}
    return canonical_provenance(sources)


def _expr(store, expression, bindings, snapshot, scopes, state):
    if type(expression) is not dict: raise GroundingError("invalid rule expression")
    op = expression.get("op")
    if type(op) is not str: raise GroundingError("invalid rule operator")
    if op == "property":
        participant, raw_property = expression.get("participant"), expression.get("property")
        if type(participant) is not str or participant not in bindings or type(raw_property) is not str:
            raise GroundingError("invalid property expression")
        property_id = PropertyId(raw_property)
        version = expression.get("version")
        if type(version) is not str or not version or (property_id.value, version) not in snapshot.property_versions:
            raise GroundingError("property version is outside the requested snapshot")
        spec = store.vocabulary.prop(property_id, version)
        if spec is None: raise GroundingError("unresolved property vocabulary entry")
        description = bindings[participant]
        effective_ids = set(store._effective_record_ids(snapshot.id))
        candidates = [record for record in store.records.values()
                      if isinstance(record, PropertyAssertion)
                      and record.id in effective_ids
                      and ("property", record.id.value) not in store.isolated
                      and record.description == description
                      and record.property == property_id and record.version == version
                      and record.scope in scopes]
        candidates.sort(key=lambda record: record.id.value)
        if not candidates:
            state.missing.append(MissingRead(participant, description, property_id, version))
            return EvaluationTruth.UNKNOWN, None
        if len(candidates) > 1:
            ids = tuple(record.id for record in candidates)
            state.ambiguous.append(AmbiguousRead(participant, description, property_id, version, ids))
            for record in candidates:
                state.dependency(record.id)
                for source in record.provenance: state.source(source)
                state.epistemic.append(record.epistemic_status)
            return EvaluationTruth.UNKNOWN, None
        record = candidates[0]
        if spec.value_kind != "finite_set<symbol>" or type(record.value) is not FiniteSetSymbol:
            raise GroundingError("property value is incompatible with this operator")
        if record.epistemic_status != "exact":
            raise GroundingError(
                f"M1b.1 does not support property epistemic status {record.epistemic_status!r}"
            )
        state.dependency(record.id)
        for source in record.provenance: state.source(source)
        state.epistemic.append(record.epistemic_status)
        return EvaluationTruth.TRUE, record.value
    if op in {"set_union", "set_subset"}:
        lt, left = _expr(store, expression.get("left"), bindings, snapshot, scopes, state)
        rt, right = _expr(store, expression.get("right"), bindings, snapshot, scopes, state)
        if lt is EvaluationTruth.UNKNOWN or rt is EvaluationTruth.UNKNOWN: return EvaluationTruth.UNKNOWN, None
        if type(left) is not FiniteSetSymbol or type(right) is not FiniteSetSymbol:
            raise GroundingError("set operator requires finite_set<symbol>")
        if op == "set_union":
            items = list(left.items)
            for item in right.items:
                if item not in items: items.append(item)
            return EvaluationTruth.TRUE, FiniteSetSymbol(tuple(items))
        return (EvaluationTruth.TRUE if all(item in right.items for item in left.items)
                else EvaluationTruth.FALSE), None
    raise GroundingError(f"unsupported rule operator: {op}")


def ground(store, rule_id, bindings, snapshot, context):
    store._check()
    rule_id, snapshot_id, context_id = (_identifier(RuleId, rule_id, "rule_id"),
                                        _identifier(SnapshotId, snapshot, "snapshot"),
                                        _identifier(ContextId, context, "context"))
    snap = store.open_snapshot(snapshot_id.value)
    rule_version, payload = _historical_rule(snap, rule_id)
    scopes, enabled = _historical_context(snap, context_id)
    if rule_id.value not in enabled: raise GroundingError("rule is not enabled by the requested context")
    declared, head = payload.get("participants"), payload.get("head")
    if type(declared) is not list or any(type(x) is not str for x in declared) or type(head) is not dict:
        raise GroundingError("invalid historical rule structure")
    if not isinstance(bindings, Mapping): raise ValidationError("bindings require a mapping")
    if any(type(key) is not str for key in bindings): raise ValidationError("binding names must be exact strings")
    if len(bindings) != len(declared) or any(name not in bindings for name in declared) or any(name not in declared for name in bindings):
        raise GroundingError("bindings must exactly match declared participants")
    ordered = []
    for name in declared:
        value = bindings[name]
        if type(value) is not DescriptionId: raise ValidationError("bindings require DescriptionId values")
        if value not in snap.description_ids: raise GroundingError("binding references a description absent from the requested snapshot")
        ordered.append((name, value))
    bound = MappingProxyType(dict(ordered))
    state = _State()
    truth, _ = _expr(store, payload.get("when"), bound, snap, scopes, state)
    conclusion = None
    if truth is EvaluationTruth.TRUE:
        predicate_raw, version, participants, polarity = (head.get("predicate"), head.get("version"),
                                                           head.get("participants"), head.get("polarity"))
        if (type(predicate_raw) is not str or type(version) is not str or type(participants) is not list
                or type(polarity) is not str or participants != declared or polarity not in {"positive", "negative"}):
            raise GroundingError("invalid rule head")
        predicate = PredicateId(predicate_raw)
        if (predicate.value, version) not in snap.predicate_versions:
            raise GroundingError("rule head predicate version is outside the snapshot")
        provenance = _terminal_provenance(store, tuple(state.dependencies))
        conclusion = GroundedConclusion(
            RelationTerm(predicate, version, tuple(bound[name] for name in participants)), polarity,
            "exact", _scope(scopes), provenance, rule_id, rule_version,
            tuple(state.dependencies))
    result = GroundingResult(rule_id, rule_version, bound, truth, conclusion,
                             tuple(state.dependencies), tuple(state.missing), tuple(state.ambiguous),
                             snapshot_id, context_id, "pending")
    object.__setattr__(result, "grounding_evidence", evidence_for(result, declared))
    return result
