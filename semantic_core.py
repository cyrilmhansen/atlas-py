"""Tiny semantic vocabulary for the already-measured QuickDraw experiments."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Any, Mapping


@dataclass(frozen=True)
class Unit:
    name: str


COUNT = Unit("count")
BYTES = Unit("bytes")
MICROSECONDS = Unit("microseconds")
RATIO = Unit("ratio")


@dataclass(frozen=True)
class QuantityKind:
    name: str
    family: str


ACTIVE_PIXELS = QuantityKind("ActivePixels", "count")
BBOX_PIXELS = QuantityKind("BoundingBoxPixels", "count")
RUN_COUNT = QuantityKind("RunCount", "count")
TRANSITION_COUNT = QuantityKind("VerticalTransitionCount", "count")
REUSE_COUNT = QuantityKind("ReuseCount", "count")
PERSISTENT_STORAGE = QuantityKind("PersistentStorage", "storage")
TEMPORARY_STORAGE = QuantityKind("TemporaryStorage", "storage")
DURATION = QuantityKind("Duration", "duration")
DENSITY = QuantityKind("RegionDensity", "ratio")


@dataclass(frozen=True)
class Provenance:
    status: str                 # exact, derived, measured, estimate, bound
    source: str
    context: tuple[tuple[str, str], ...] = ()

    def short(self) -> str:
        context = ", ".join(f"{k}={v}" for k, v in self.context)
        return f"{self.status}:{self.source}" + (f" ({context})" if context else "")


@dataclass(frozen=True)
class LogicalObject:
    name: str
    kind: str


@dataclass(frozen=True)
class Representation:
    object: LogicalObject
    kind: str                  # bitmap_mask, runs, transitions

    def __str__(self) -> str:
        return f"{self.kind}({self.object.name})"


class Expr:
    kind: QuantityKind
    unit: Unit

    def evaluate(self, values: Mapping[str, Real]) -> Real:
        raise NotImplementedError

    def render(self) -> str:
        raise NotImplementedError

    def __add__(self, other: "Expr") -> "Expr":
        return _binary("+", self, other)

    def __sub__(self, other: "Expr") -> "Expr":
        return _binary("-", self, other)

    def __mul__(self, other: "Expr") -> "Expr":
        return _binary("*", self, other)

    def __rmul__(self, other: "Expr") -> "Expr":
        return _binary("*", other, self)

    def __truediv__(self, other: "Expr") -> "Expr":
        return _binary("/", self, other)


@dataclass(frozen=True)
class Quantity(Expr):
    value: Real | str
    kind: QuantityKind
    unit: Unit
    subject: str
    provenance: Provenance

    def evaluate(self, values: Mapping[str, Real]) -> Real:
        if isinstance(self.value, str):
            return values[self.value]
        return self.value

    def render(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class Binary(Expr):
    operator: str
    left: Expr
    right: Expr
    kind: QuantityKind
    unit: Unit

    def evaluate(self, values: Mapping[str, Real]) -> Real:
        left, right = self.left.evaluate(values), self.right.evaluate(values)
        return {"+": lambda: left + right, "-": lambda: left - right,
                "*": lambda: left * right, "/": lambda: left / right}[self.operator]()

    def render(self) -> str:
        return f"({self.left.render()} {self.operator} {self.right.render()})"


def _is_duration(expr: Expr) -> bool:
    return expr.kind is DURATION and expr.unit is MICROSECONDS


def _is_count(expr: Expr) -> bool:
    return expr.kind.family == "count" and expr.unit is COUNT


def _binary(operator: str, left: Expr, right: Expr) -> Expr:
    if not isinstance(left, Expr) or not isinstance(right, Expr):
        raise TypeError("expressions must contain semantic quantities")
    if operator in "+-":
        if not (_is_duration(left) and _is_duration(right)):
            raise TypeError(f"{operator} requires two durations, got {left.kind.name} and {right.kind.name}")
        return Binary(operator, left, right, DURATION, MICROSECONDS)
    if operator == "*":
        if _is_count(left) and _is_duration(right):
            return Binary(operator, left, right, DURATION, MICROSECONDS)
        if _is_duration(left) and _is_count(right):
            return Binary(operator, left, right, DURATION, MICROSECONDS)
        raise TypeError("multiplication is only count * duration in this prototype")
    if operator == "/":
        if left.kind is ACTIVE_PIXELS and right.kind is BBOX_PIXELS:
            return Binary(operator, left, right, DENSITY, RATIO)
        raise TypeError("division is only active_pixels / bbox_pixels in this prototype")
    raise TypeError(f"unsupported operator {operator}")


def quantity(value: Real | str, kind: QuantityKind, unit: Unit, subject: str,
             status: str, source: str, **context: str) -> Quantity:
    return Quantity(value, kind, unit, subject,
                    Provenance(status, source, tuple(sorted(context.items()))))


def active_pixels(region: LogicalObject, value: Real, status="exact", source="region structure") -> Quantity:
    return quantity(value, ACTIVE_PIXELS, COUNT, region.name, status, source)


def bbox_pixels(region: LogicalObject, value: Real, status="exact", source="region structure") -> Quantity:
    return quantity(value, BBOX_PIXELS, COUNT, region.name, status, source)


def measured(kind: QuantityKind, unit: Unit, value: Real, subject: str,
             source: str, **context: str) -> Quantity:
    return quantity(value, kind, unit, subject, "measured", source, **context)

