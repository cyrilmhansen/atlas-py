#!/usr/bin/env python3
"""Small generic term/rule mechanism used by the structured-rules POC."""

from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class Term:
    kind: str
    name: str
    args: tuple = ()

    def __str__(self):
        if self.kind == "var" or self.kind == "const":
            return self.name
        return f"{self.name}({', '.join(map(str, self.args))})"


@dataclass(frozen=True)
class NotEqual:
    left: Term
    right: Term


@dataclass(frozen=True)
class Rule:
    rule_id: str
    lhs: Term
    rhs: Term
    conditions: tuple


def term_from_data(data):
    kind = data["kind"]
    if kind in {"var", "const"}:
        return Term(kind, data["name"])
    if kind == "app":
        return Term(kind, data["name"], tuple(term_from_data(arg) for arg in data["args"]))
    raise ValueError(f"unknown term kind: {kind}")


def rule_from_data(data):
    conditions = []
    for item in data["conditions"]:
        if item.get("kind") != "not_equal":
            raise ValueError(f"unsupported condition kind: {item.get('kind')}")
        conditions.append(NotEqual(term_from_data(item["left"]), term_from_data(item["right"])))
    return Rule(data["id"], term_from_data(data["lhs"]), term_from_data(data["rhs"]), conditions)


def variables(term):
    if term.kind == "var":
        return {term.name}
    return set().union(*(variables(arg) for arg in term.args))


def rule_variables(rule):
    names = variables(rule.lhs) | variables(rule.rhs)
    for condition in rule.conditions:
        names |= variables(condition.left) | variables(condition.right)
    return names


def substitute(term, environment):
    if term.kind == "var":
        return environment.get(term.name, term)
    if term.kind == "const":
        return term
    return Term(term.kind, term.name, tuple(substitute(arg, environment) for arg in term.args))


def is_ground(term):
    return term.kind != "var" and all(is_ground(arg) for arg in term.args)


def extend_substitution(environment, variable, value):
    """Bind a variable consistently; repeated variables cannot disagree."""
    previous = environment.get(variable)
    if previous is not None and previous != value:
        return None
    result = dict(environment)
    result[variable] = value
    return result


def condition_status(condition, environment):
    left = substitute(condition.left, environment)
    right = substitute(condition.right, environment)
    if not is_ground(left) or not is_ground(right):
        return "unknown"
    return "true" if left != right else "false"


def instantiate(rule, environment):
    if any(condition_status(condition, environment) != "true" for condition in rule.conditions):
        return None
    return substitute(rule.lhs, environment), substitute(rule.rhs, environment)


def all_substitutions(rule, domains):
    names = sorted(rule_variables(rule))
    for values in product(*(domains[name] for name in names)):
        yield dict(zip(names, values))


@dataclass(frozen=True)
class ConcreteArray:
    values: tuple


def oracle(term, arrays):
    """Independent concrete semantics for the two array operations."""
    if term.kind == "var":
        raise ValueError(f"unsubstituted variable: {term}")
    if term.kind == "const":
        if term.name in arrays:
            return arrays[term.name]
        try:
            return int(term.name)
        except ValueError:
            return term.name
    if term.name == "get":
        index = oracle(term.args[0], arrays)
        array = oracle(term.args[1], arrays)
        return array.values[index]
    if term.name == "set":
        index = oracle(term.args[0], arrays)
        value = oracle(term.args[1], arrays)
        array = oracle(term.args[2], arrays)
        values = list(array.values)
        values[index] = value
        return ConcreteArray(tuple(values))
    raise ValueError(f"unknown operation for oracle: {term.name}")
