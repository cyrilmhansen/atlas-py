from dataclasses import dataclass
from typing import Union
import re
from .errors import ValidationError


def _text(value, *, allow_empty=False):
    if type(value) is not str or (not allow_empty and not value):
        raise ValidationError("value must be an exact string")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValidationError("value must not contain isolated Unicode surrogates")
    return value


@dataclass(frozen=True, slots=True)
class Symbol:
    value: str
    def __post_init__(self): object.__setattr__(self, "value", _text(self.value, allow_empty=True))


@dataclass(frozen=True, slots=True)
class Integer:
    value: int
    def __post_init__(self):
        if type(self.value) is not int: raise ValidationError("integer rejects bool and coercions")


@dataclass(frozen=True, slots=True)
class FiniteSetSymbol:
    items: tuple[str, ...]
    def __post_init__(self):
        if type(self.items) is not tuple: raise ValidationError("finite_set requires an explicit tuple")
        for item in self.items:
            _text(item, allow_empty=True)
        if any(self.items[i] == self.items[j] for i in range(len(self.items)) for j in range(i)):
            raise ValidationError("finite_set requires distinct exact symbols")
    def __eq__(self, other): return isinstance(other, FiniteSetSymbol) and frozenset(self.items) == frozenset(other.items)
    def __hash__(self): return hash((type(self), frozenset(self.items)))


@dataclass(frozen=True, slots=True)
class SequenceSymbol:
    items: tuple[str, ...]
    def __post_init__(self):
        if type(self.items) is not tuple or any(type(x) is not str for x in self.items):
            raise ValidationError("sequence requires an explicit tuple of symbols")
        for item in self.items:
            _text(item, allow_empty=True)


Value = Union[Symbol, Integer, FiniteSetSymbol, SequenceSymbol]

_INTEGER_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")


def value_from_json(raw, expected=None):
    if type(raw) is not dict or type(raw.get("kind")) is not str:
        raise ValidationError("value must be a tagged object")
    kind = raw["kind"]
    if expected is not None and kind != expected: raise ValidationError("value kind does not match vocabulary")
    if kind == "symbol": return Symbol(raw.get("value"))
    if kind == "integer":
        number = raw.get("value")
        if type(number) is not str or _INTEGER_RE.fullmatch(number) is None:
            raise ValidationError("integer must be canonical decimal text")
        return Integer(int(number))
    items = raw.get("items")
    if type(items) is not list or any(type(x) is not str for x in items): raise ValidationError("items must be a list of exact strings")
    if kind == "finite_set<symbol>": return FiniteSetSymbol(tuple(items))
    if kind == "sequence<symbol>": return SequenceSymbol(tuple(items))
    raise ValidationError("unsupported Core V1 value kind")


def value_to_json(value):
    if type(value) is Symbol: return {"kind":"symbol", "value":value.value}
    if type(value) is Integer: return {"kind":"integer", "value":str(value.value)}
    if type(value) is FiniteSetSymbol: return {"kind":"finite_set<symbol>", "items":list(value.items)}
    if type(value) is SequenceSymbol: return {"kind":"sequence<symbol>", "items":list(value.items)}
    raise ValidationError("not an Atlas value")
