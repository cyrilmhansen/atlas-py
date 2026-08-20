from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from .identity import *
from .values import Value, _text
from .errors import ValidationError

def _tuple(value, message):
    if type(value) is not tuple:
        raise ValidationError(message)
    return value

def _freeze(value):
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValidationError("payload keys must be exact strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    if type(value) in (str, int, float, bool) or value is None:
        if type(value) is str: _text(value, allow_empty=True)
        return value
    raise ValidationError("payload contains a non-persistable value")

def thaw(value):
    if type(value) is MappingProxyType:
        return {key: thaw(item) for key, item in value.items()}
    if type(value) is tuple:
        return [thaw(item) for item in value]
    return value

@dataclass(frozen=True, slots=True, eq=False)
class Description:
    id: DescriptionId; label: str
    def __post_init__(self):
        if type(self.id) is not DescriptionId: raise ValidationError("description requires a DescriptionId")
        _text(self.label, allow_empty=True)
    def __eq__(self, other): return type(other) is type(self) and self.id == other.id
    def __hash__(self): return hash((type(self), self.id))

@dataclass(frozen=True, slots=True)
class Source:
    id: SourceId
    def __post_init__(self):
        if type(self.id) is not SourceId: raise ValidationError("source requires a SourceId")
@dataclass(frozen=True, slots=True)
class PropertyAssertion:
    id: KnowledgeId; description: DescriptionId; property: PropertyId; version: str; value: Value; scope: str; epistemic_status: str; provenance: tuple[SourceId,...]
    def __post_init__(self):
        if type(self.id) is not KnowledgeId or type(self.description) is not DescriptionId or type(self.property) is not PropertyId:
            raise ValidationError("invalid property assertion identity domains")
        _text(self.version); _text(self.scope); _text(self.epistemic_status)
        if type(self.provenance) is not tuple or any(type(x) is not SourceId for x in self.provenance):
            raise ValidationError("invalid property assertion provenance")
@dataclass(frozen=True, slots=True)
class RelationAssertion:
    id: KnowledgeId; predicate: PredicateId; version: str; participants: tuple[DescriptionId,...]; polarity: str; scope: str; epistemic_status: str; provenance: tuple[SourceId,...]
    def __post_init__(self):
        if type(self.id) is not KnowledgeId or type(self.predicate) is not PredicateId:
            raise ValidationError("invalid relation assertion identity domains")
        if type(self.participants) is not tuple or any(type(x) is not DescriptionId for x in self.participants):
            raise ValidationError("invalid relation participants")
        _text(self.version); _text(self.polarity); _text(self.scope); _text(self.epistemic_status)
        if type(self.provenance) is not tuple or any(type(x) is not SourceId for x in self.provenance):
            raise ValidationError("invalid relation assertion provenance")
@dataclass(frozen=True, slots=True)
class Rule:
    id: RuleId; version: str; payload: dict[str, Any]; evaluation_supported: bool = True
    def __post_init__(self):
        if type(self.id) is not RuleId or type(self.version) is not str or not self.version:
            raise ValidationError("invalid rule identity or version")
        frozen = _freeze(self.payload)
        if type(frozen) is not MappingProxyType: raise ValidationError("rule payload must be an object")
        object.__setattr__(self, "payload", frozen)
        if type(self.evaluation_supported) is not bool: raise ValidationError("invalid rule evaluation status")

@dataclass(frozen=True, slots=True)
class Context:
    id: ContextId; visible_scopes: tuple[str,...]; enabled_rules: tuple[RuleId,...]
    def __post_init__(self):
        if type(self.id) is not ContextId or type(self.visible_scopes) is not tuple or type(self.enabled_rules) is not tuple:
            raise ValidationError("invalid context types")
        for scope in self.visible_scopes: _text(scope)
        if any(type(rule) is not RuleId for rule in self.enabled_rules): raise ValidationError("enabled_rules require RuleId values")
@dataclass(frozen=True, slots=True)
class Snapshot:
    id: SnapshotId
    parent: SnapshotId | None
    record_ids: tuple[KnowledgeId, ...]
    predicate_versions: tuple[tuple[str, str], ...] = ()
    property_versions: tuple[tuple[str, str], ...] = ()
    rule_versions: tuple[tuple[str, str], ...] = ()
    context_ids: tuple[ContextId, ...] = ()
    context_definitions: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = ()
    rule_definitions: tuple[tuple[str, str, str, bool], ...] = ()
    def __post_init__(self):
        if type(self.id) is not SnapshotId: raise ValidationError("snapshot requires a SnapshotId")
        if self.parent is not None and type(self.parent) is not SnapshotId:
            raise ValidationError("snapshot parent requires a SnapshotId")
        if type(self.record_ids) is not tuple or any(type(record_id) is not KnowledgeId for record_id in self.record_ids):
            raise ValidationError("snapshot record_ids require KnowledgeId values")
        for refs in (self.predicate_versions, self.property_versions, self.rule_versions):
            if type(refs) is not tuple or any(type(x) is not tuple or len(x) != 2 or any(type(v) is not str or not v for v in x) for x in refs):
                raise ValidationError("snapshot semantic references require identity/version pairs")
        if type(self.context_ids) is not tuple or any(type(x) is not ContextId for x in self.context_ids):
            raise ValidationError("snapshot context references require ContextId values")
        if type(self.context_definitions) is not tuple or any(type(x) is not tuple or len(x) != 3 for x in self.context_definitions):
            raise ValidationError("snapshot context definitions require exact triples")
        if type(self.rule_definitions) is not tuple or any(type(x) is not tuple or len(x) != 4 or type(x[3]) is not bool for x in self.rule_definitions):
            raise ValidationError("snapshot rule definitions require exact quadruples")
KnowledgeRecord = PropertyAssertion | RelationAssertion
