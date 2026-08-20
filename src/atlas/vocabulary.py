from dataclasses import dataclass
from .identity import PredicateId, PropertyId
from .errors import ValidationError

def _vocab_text(value):
    if type(value) is not str or not value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValidationError("vocabulary text must be exact and valid Unicode")
    return value

@dataclass(frozen=True, slots=True)
class PredicateSpec:
    id: PredicateId; version: str; arity: int; roles: tuple[str, ...]
    def __post_init__(self):
        if type(self.id) is not PredicateId or type(self.arity) is not int or type(self.arity) is bool or self.arity < 0 or type(self.roles) is not tuple or len(self.roles) != self.arity: raise ValidationError("invalid predicate vocabulary")
        _vocab_text(self.version)
        for role in self.roles: _vocab_text(role)
        if len(set(self.roles)) != len(self.roles):
            raise ValidationError("predicate roles must be unique")

@dataclass(frozen=True, slots=True)
class PropertySpec:
    id: PropertyId; version: str; value_kind: str; cardinality: str = "multivalued"
    def __post_init__(self):
        if type(self.id) is not PropertyId or type(self.value_kind) is not str or self.value_kind not in {"symbol","integer","finite_set<symbol>","sequence<symbol>"}: raise ValidationError("invalid property vocabulary")
        _vocab_text(self.version)
        if type(self.cardinality) is not str or self.cardinality != "multivalued":
            raise ValidationError("invalid property cardinality")

@dataclass(frozen=True)
class Vocabulary:
    predicates: dict[tuple[str,str], PredicateSpec]
    properties: dict[tuple[str,str], PropertySpec]
    def predicate(self, ident, version):
        if type(ident) is not PredicateId: raise ValidationError("predicate lookup requires a PredicateId")
        return self.predicates.get((ident.value, version))
    def prop(self, ident, version):
        if type(ident) is not PropertyId: raise ValidationError("property lookup requires a PropertyId")
        return self.properties.get((ident.value, version))
