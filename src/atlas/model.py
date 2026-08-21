from dataclasses import dataclass
from enum import Enum
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
    id: KnowledgeId; predicate: PredicateId; version: str; participants: tuple[DescriptionId,...]; polarity: str; scope: object; epistemic_status: str; provenance: tuple[SourceId,...]; derivation_id: KnowledgeId | None = None
    def __post_init__(self):
        if type(self.id) is not KnowledgeId or type(self.predicate) is not PredicateId:
            raise ValidationError("invalid relation assertion identity domains")
        if type(self.participants) is not tuple or any(type(x) is not DescriptionId for x in self.participants):
            raise ValidationError("invalid relation participants")
        _text(self.version); _text(self.polarity); _text(self.epistemic_status)
        if type(self.scope) is not str and (type(self.scope) is not tuple or any(type(x) is not str for x in self.scope)):
            raise ValidationError("invalid relation assertion scope")
        if type(self.provenance) is not tuple or any(type(x) is not SourceId for x in self.provenance):
            raise ValidationError("invalid relation assertion provenance")
        if self.derivation_id is not None and type(self.derivation_id) is not KnowledgeId:
            raise ValidationError("invalid relation assertion derivation reference")
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
    description_ids: tuple[DescriptionId, ...] = ()
    def __post_init__(self):
        if type(self.id) is not SnapshotId: raise ValidationError("snapshot requires a SnapshotId")
        if self.parent is not None and type(self.parent) is not SnapshotId:
            raise ValidationError("snapshot parent requires a SnapshotId")
        if type(self.record_ids) is not tuple or any(type(record_id) is not KnowledgeId for record_id in self.record_ids):
            raise ValidationError("snapshot record_ids require KnowledgeId values")
        if len({record_id.value for record_id in self.record_ids}) != len(self.record_ids):
            raise ValidationError("snapshot record_ids contain a duplicate")
        for refs in (self.predicate_versions, self.property_versions, self.rule_versions):
            if type(refs) is not tuple or any(type(x) is not tuple or len(x) != 2 or any(type(v) is not str or not v for v in x) for x in refs):
                raise ValidationError("snapshot semantic references require identity/version pairs")
            if len({x[0] for x in refs}) != len(refs):
                raise ValidationError("snapshot semantic references contain a duplicate identity")
        if type(self.context_ids) is not tuple or any(type(x) is not ContextId for x in self.context_ids):
            raise ValidationError("snapshot context references require ContextId values")
        if len({x.value for x in self.context_ids}) != len(self.context_ids):
            raise ValidationError("snapshot context_ids contain a duplicate")
        if type(self.context_definitions) is not tuple or any(type(x) is not tuple or len(x) != 3 for x in self.context_definitions):
            raise ValidationError("snapshot context definitions require exact triples")
        if any(type(x[0]) is not str or not x[0] or type(x[1]) is not tuple or
               any(type(scope) is not str for scope in x[1]) or type(x[2]) is not tuple or
               any(type(rule) is not str for rule in x[2]) for x in self.context_definitions):
            raise ValidationError("snapshot context definitions require exact triples")
        if len({x[0] for x in self.context_definitions}) != len(self.context_definitions):
            raise ValidationError("snapshot context definitions contain a duplicate")
        if type(self.rule_definitions) is not tuple or any(type(x) is not tuple or len(x) != 4 or type(x[3]) is not bool for x in self.rule_definitions):
            raise ValidationError("snapshot rule definitions require exact quadruples")
        if any(type(x[0]) is not str or not x[0] or type(x[1]) is not str or not x[1] or
               type(x[2]) is not str for x in self.rule_definitions):
            raise ValidationError("snapshot rule definitions require exact quadruples")
        if len({x[0] for x in self.rule_definitions}) != len(self.rule_definitions):
            raise ValidationError("snapshot rule definitions contain a duplicate")
        if type(self.description_ids) is not tuple or any(type(x) is not DescriptionId for x in self.description_ids):
            raise ValidationError("snapshot description_ids require DescriptionId values")
        if len(set(x.value for x in self.description_ids)) != len(self.description_ids):
            raise ValidationError("snapshot description_ids contain a duplicate")
@dataclass(frozen=True, slots=True)
class Derivation:
    knowledge_id: KnowledgeId
    rule_id: RuleId
    rule_version: str
    bindings: tuple[tuple[str, DescriptionId], ...]
    snapshot: SnapshotId
    context: ContextId
    dependencies: tuple[KnowledgeId, ...]
    grounding_evidence: str
    def __post_init__(self):
        if type(self.knowledge_id) is not KnowledgeId or type(self.rule_id) is not RuleId:
            raise ValidationError("invalid derivation identity domains")
        _text(self.rule_version)
        if type(self.bindings) is not tuple or any(
            type(item) is not tuple or len(item) != 2 or type(item[0]) is not str or
            type(item[1]) is not DescriptionId for item in self.bindings
        ):
            raise ValidationError("invalid derivation bindings")
        if len({item[0] for item in self.bindings}) != len(self.bindings):
            raise ValidationError("duplicate derivation binding")
        if type(self.snapshot) is not SnapshotId or type(self.context) is not ContextId:
            raise ValidationError("invalid derivation environment")
        if type(self.dependencies) is not tuple or any(type(x) is not KnowledgeId for x in self.dependencies):
            raise ValidationError("invalid derivation dependencies")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValidationError("duplicate derivation dependency")
        if type(self.grounding_evidence) is not str or not self.grounding_evidence:
            raise ValidationError("derivation requires grounding evidence")


KnowledgeRecord = PropertyAssertion | RelationAssertion


class EvaluationTruth(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class RelationTerm:
    predicate: PredicateId
    version: str
    participants: tuple[DescriptionId, ...]
    def __post_init__(self):
        if type(self.predicate) is not PredicateId or type(self.version) is not str or not self.version:
            raise ValidationError("invalid relation term")
        if type(self.participants) is not tuple or any(type(x) is not DescriptionId for x in self.participants):
            raise ValidationError("invalid relation term participants")


@dataclass(frozen=True, slots=True)
class MissingRead:
    participant: str
    description: DescriptionId
    property: PropertyId
    version: str


@dataclass(frozen=True, slots=True)
class AmbiguousRead:
    participant: str
    description: DescriptionId
    property: PropertyId
    version: str
    knowledge_ids: tuple[KnowledgeId, ...]


@dataclass(frozen=True, slots=True)
class GroundedConclusion:
    term: RelationTerm
    polarity: str
    epistemic_status: str
    scope: object
    provenance: tuple[SourceId, ...]
    rule_id: RuleId
    rule_version: str
    dependencies: tuple[KnowledgeId, ...]
    def __post_init__(self):
        if type(self.term) is not RelationTerm:
            raise ValidationError("grounded conclusion requires an exact RelationTerm")
        if type(self.polarity) is not str or self.polarity not in {"positive", "negative"}:
            raise ValidationError("invalid grounded conclusion metadata")
        if type(self.epistemic_status) is not str or self.epistemic_status != "exact":
            raise ValidationError("unsupported grounded conclusion epistemic status")
        if type(self.scope) is not str and (type(self.scope) is not tuple or any(type(x) is not str for x in self.scope)):
            raise ValidationError("invalid grounded conclusion scope")
        if type(self.provenance) is not tuple or any(type(x) is not SourceId for x in self.provenance):
            raise ValidationError("invalid grounded conclusion provenance")
        if type(self.rule_id) is not RuleId or type(self.rule_version) is not str or not self.rule_version:
            raise ValidationError("invalid grounded conclusion rule reference")
        if type(self.dependencies) is not tuple or any(type(x) is not KnowledgeId for x in self.dependencies):
            raise ValidationError("invalid grounded conclusion dependencies")


@dataclass(frozen=True, slots=True)
class GroundingResult:
    rule_id: RuleId
    rule_version: str
    bindings: object
    truth: EvaluationTruth
    conclusion: GroundedConclusion | None
    effective_dependencies: tuple[KnowledgeId, ...]
    missing_reads: tuple[MissingRead, ...]
    ambiguous_reads: tuple[AmbiguousRead, ...]
    snapshot: SnapshotId
    context: ContextId
    grounding_evidence: str
    def __post_init__(self):
        if type(self.rule_id) is not RuleId or type(self.rule_version) is not str or not self.rule_version:
            raise ValidationError("invalid grounding rule reference")
        if type(self.truth) is not EvaluationTruth:
            raise ValidationError("invalid evaluation truth")
        if self.conclusion is not None and type(self.conclusion) is not GroundedConclusion:
            raise ValidationError("grounding conclusion requires an exact GroundedConclusion")
        if self.truth is EvaluationTruth.TRUE and self.conclusion is None:
            raise ValidationError("TRUE grounding requires a conclusion")
        if self.truth is not EvaluationTruth.TRUE and self.conclusion is not None:
            raise ValidationError("FALSE or UNKNOWN grounding cannot carry a conclusion")
        if type(self.effective_dependencies) is not tuple or any(type(x) is not KnowledgeId for x in self.effective_dependencies):
            raise ValidationError("invalid grounding dependencies")
        if type(self.missing_reads) is not tuple or type(self.ambiguous_reads) is not tuple:
            raise ValidationError("invalid grounding diagnostics")
        if type(self.snapshot) is not SnapshotId or type(self.context) is not ContextId:
            raise ValidationError("invalid grounding environment")
        if type(self.grounding_evidence) is not str or not self.grounding_evidence:
            raise ValidationError("grounding requires an evidence witness")


class GroundingStatus(str, Enum):
    COMPLETE_FOR_DECLARED_SCOPE = "complete_for_declared_scope"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


# M1c.1 has one deliberately closed manifest format.  Unknown versions are
# not interpreted as an unevaluable future format.
SUPPORTED_MANIFEST_VERSIONS = frozenset({"m1-grounding/1"})


@dataclass(frozen=True, slots=True)
class GroundingManifest:
    manifest_version: str
    candidate_description_ids: tuple[DescriptionId, ...]
    prescribed_rule_ids: tuple[RuleId, ...]
    def __post_init__(self):
        if type(self.manifest_version) is not str or not self.manifest_version:
            raise ValidationError("manifest requires a non-empty version")
        if self.manifest_version not in SUPPORTED_MANIFEST_VERSIONS:
            raise ValidationError("unsupported grounding manifest version")
        if type(self.candidate_description_ids) is not tuple or any(type(x) is not DescriptionId for x in self.candidate_description_ids):
            raise ValidationError("manifest candidates require DescriptionId values")
        if type(self.prescribed_rule_ids) is not tuple or any(type(x) is not RuleId for x in self.prescribed_rule_ids):
            raise ValidationError("manifest rules require RuleId values")
        if len({x.value for x in self.candidate_description_ids}) != len(self.candidate_description_ids):
            raise ValidationError("manifest contains a duplicate candidate")
        if len({x.value for x in self.prescribed_rule_ids}) != len(self.prescribed_rule_ids):
            raise ValidationError("manifest contains a duplicate rule")
    @property
    def version(self):
        return self.manifest_version


@dataclass(frozen=True, slots=True, eq=False)
class DecisionScope:
    id: DecisionScopeId
    snapshot: SnapshotId
    context: ContextId
    request: DescriptionId
    manifest: GroundingManifest
    def __post_init__(self):
        if type(self.id) is not DecisionScopeId or type(self.snapshot) is not SnapshotId or type(self.context) is not ContextId or type(self.request) is not DescriptionId:
            raise ValidationError("invalid decision scope identity domains")
        if type(self.manifest) is not GroundingManifest:
            raise ValidationError("decision scope requires a grounding manifest")
    def __eq__(self, other): return type(other) is type(self) and self.id == other.id
    def __hash__(self): return hash((type(self), self.id))


@dataclass(frozen=True, slots=True)
class GroundingObservation:
    candidate: DescriptionId
    traversed: bool
    truth: EvaluationTruth | None
    grounding_result: GroundingResult | None = None
    exclusion_reason: str | None = None
    structural_error: str | None = None
    def __post_init__(self):
        if type(self.candidate) is not DescriptionId or type(self.traversed) is not bool:
            raise ValidationError("invalid grounding observation identity")
        if self.truth is not None and type(self.truth) is not EvaluationTruth:
            raise ValidationError("invalid grounding observation truth")
        if self.grounding_result is not None and type(self.grounding_result) is not GroundingResult:
            raise ValidationError("invalid grounding observation result")
        for value in (self.exclusion_reason, self.structural_error):
            if value is not None and (type(value) is not str or not value): raise ValidationError("invalid grounding observation reason")
        if self.grounding_result is not None and self.structural_error is not None:
            raise ValidationError("grounding result cannot accompany a structural error")
        if self.structural_error is not None and self.truth is not None:
            raise ValidationError("structural error cannot claim a truth value")
        if not self.traversed and (self.grounding_result is not None or self.truth is not None):
            raise ValidationError("non-traversed observation cannot claim a grounding result")
        if self.traversed and self.grounding_result is None and self.structural_error is None:
            raise ValidationError("traversed observation requires a result or structural error")
        if self.grounding_result is not None and self.truth is not self.grounding_result.truth:
            raise ValidationError("observation truth disagrees with grounding result")


@dataclass(frozen=True, slots=True)
class DecisionGrounding:
    scope_id: DecisionScopeId
    observations: tuple[GroundingObservation, ...]
    status: GroundingStatus
    interrupted: bool = False
    pruned: bool = False
    def __post_init__(self):
        if type(self.scope_id) is not DecisionScopeId or type(self.observations) is not tuple or any(type(x) is not GroundingObservation for x in self.observations):
            raise ValidationError("invalid decision grounding")
        if type(self.status) is not GroundingStatus or type(self.interrupted) is not bool or type(self.pruned) is not bool:
            raise ValidationError("invalid decision grounding status")
        ids = [x.candidate.value for x in self.observations]
        if len(ids) != len(set(ids)): raise ValidationError("duplicate grounding observation")
