#!/usr/bin/env python3
"""Small generic term/rule mechanism used by the structured-rules POC."""

from dataclasses import dataclass
from itertools import product
from operator import ge, gt, le, lt


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


@dataclass(frozen=True)
class Interval:
    start: Term
    end: Term


@dataclass(frozen=True)
class Comparison:
    operator: str
    left: Term
    right: Term


@dataclass(frozen=True)
class Forall:
    variable: str
    domain: Interval
    body: object


@dataclass(frozen=True)
class Predicate:
    name: str
    args: tuple


@dataclass(frozen=True)
class Postcondition:
    rule_id: str
    constraints: tuple


UNKNOWN = object()


def is_boolean_result(value):
    return value is True or value is False or value is UNKNOWN


def term_from_data(data):
    kind = data["kind"]
    if kind in {"var", "const"}:
        return Term(kind, data["name"])
    if kind == "app":
        return Term(kind, data["name"], tuple(term_from_data(arg) for arg in data["args"]))
    raise ValueError(f"unknown term kind: {kind}")


def expression_from_data(data):
    kind = data["kind"]
    if kind in {"var", "const", "app"}:
        return term_from_data(data)
    if kind == "interval":
        return Interval(term_from_data(data["start"]), term_from_data(data["end"]))
    if kind == "comparison":
        if data["operator"] not in {"<", "<=", ">", ">="}:
            raise ValueError(f"unsupported comparison operator: {data['operator']}")
        return Comparison(
            data["operator"],
            term_from_data(data["left"]),
            term_from_data(data["right"]),
        )
    if kind == "forall":
        return Forall(
            data["variable"],
            expression_from_data(data["domain"]),
            expression_from_data(data["body"]),
        )
    if kind == "predicate":
        return Predicate(data["name"], tuple(term_from_data(arg) for arg in data["args"]))
    raise ValueError(f"unknown expression kind: {kind}")


def postcondition_from_data(data):
    constraints = tuple(expression_from_data(item) for item in data["constraints"])
    return Postcondition(data["id"], constraints)


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


def evaluate_term(term, environment, application_evaluator):
    if term.kind == "var":
        return environment.get(term.name, UNKNOWN)
    if term.kind == "const":
        return environment.get(term.name, term.name)
    arguments = tuple(evaluate_term(arg, environment, application_evaluator) for arg in term.args)
    if any(value is UNKNOWN for value in arguments):
        return UNKNOWN
    return application_evaluator(term.name, arguments)


def evaluate_expression(expression, environment, application_evaluator, predicate_evaluator=None):
    if isinstance(expression, Term):
        return evaluate_term(expression, environment, application_evaluator)
    if isinstance(expression, Interval):
        start = evaluate_term(expression.start, environment, application_evaluator)
        end = evaluate_term(expression.end, environment, application_evaluator)
        if start is UNKNOWN or end is UNKNOWN:
            return UNKNOWN
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
            raise TypeError("interval bounds must be non-boolean integers")
        if start > end:
            raise ValueError(f"invalid half-open interval: start {start} > end {end}")
        return range(start, end)
    if isinstance(expression, Predicate):
        if predicate_evaluator is None:
            raise ValueError(f"no predicate evaluator for {expression.name}")
        arguments = tuple(evaluate_term(arg, environment, application_evaluator) for arg in expression.args)
        if any(value is UNKNOWN for value in arguments):
            return UNKNOWN
        result = predicate_evaluator(expression.name, arguments)
        if not is_boolean_result(result):
            raise TypeError(f"predicate {expression.name} did not return true/false/unknown")
        return result
    if isinstance(expression, Comparison):
        left = evaluate_term(expression.left, environment, application_evaluator)
        right = evaluate_term(expression.right, environment, application_evaluator)
        if left is UNKNOWN or right is UNKNOWN:
            return UNKNOWN
        operators = {"<": lt, "<=": le, ">": gt, ">=": ge}
        return operators[expression.operator](left, right)
    if isinstance(expression, Forall):
        if not isinstance(expression.domain, Interval):
            raise TypeError("forall domain must be an Interval")
        domain = evaluate_expression(expression.domain, environment, application_evaluator, predicate_evaluator)
        if domain is UNKNOWN:
            return UNKNOWN
        unknown = False
        for value in domain:
            scoped_environment = dict(environment)
            scoped_environment[expression.variable] = value
            result = evaluate_expression(expression.body, scoped_environment, application_evaluator, predicate_evaluator)
            if not is_boolean_result(result):
                raise TypeError("forall body must return true/false/unknown")
            if result is UNKNOWN:
                unknown = True
            if result is False:
                return False
        return UNKNOWN if unknown else True
    raise TypeError(f"unknown expression: {expression!r}")


def evaluate_postcondition(postcondition, environment, application_evaluator, predicate_evaluator=None):
    unknown = False
    for constraint in postcondition.constraints:
        result = evaluate_expression(constraint, environment, application_evaluator, predicate_evaluator)
        if not is_boolean_result(result):
            raise TypeError("postcondition constraints must return true/false/unknown")
        if result is False:
            return False
        if result is UNKNOWN:
            unknown = True
    return UNKNOWN if unknown else True


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
