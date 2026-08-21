from dataclasses import dataclass
import re
from .errors import ValidationError

_ID = re.compile(r"^[\x00-\x7F]+$")


@dataclass(frozen=True, slots=True, eq=False)
class NominalId:
    value: str
    domain: str

    def __post_init__(self):
        if type(self.value) is not str or not self.value or _ID.fullmatch(self.value) is None:
            raise ValidationError("identifier must be a non-empty opaque ASCII string")
        if type(self.domain) is not str or not self.domain:
            raise ValidationError("identity domain must be explicit")

    def __str__(self):
        return self.value

    def __eq__(self, other):
        return type(self) is type(other) and self.value == other.value

    def __hash__(self):
        return hash((type(self), self.value))


def _factory(name, domain):
    def init(self, value):
        NominalId.__init__(self, value, domain)
    return dataclass(frozen=True, slots=True, init=False, eq=False)(type(name, (NominalId,), {"__init__": init}))


DescriptionId = _factory("DescriptionId", "description")
KnowledgeId = _factory("KnowledgeId", "knowledge")
SourceId = _factory("SourceId", "source")
ContextId = _factory("ContextId", "context")
SnapshotId = _factory("SnapshotId", "snapshot")
PredicateId = _factory("PredicateId", "predicate")
PropertyId = _factory("PropertyId", "property")
RuleId = _factory("RuleId", "rule")
DecisionScopeId = _factory("DecisionScopeId", "decision-scope")
DecisionProblemId = _factory("DecisionProblemId", "decision-problem")
