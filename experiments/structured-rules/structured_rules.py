#!/usr/bin/env python3
"""Small generic term/rule mechanism used by the structured-rules POC."""

from dataclasses import dataclass
from itertools import product
from operator import ge, gt, le, lt
import re


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


@dataclass(frozen=True)
class OrderedSequence:
    elements: tuple

    def __init__(self, source):
        if not isinstance(source, (list, tuple)):
            raise TypeError("ordered sequence source must be a list or tuple")
        object.__setattr__(self, "elements", tuple(source))


@dataclass(frozen=True)
class Annotation:
    element: str
    category: str


@dataclass(frozen=True)
class OrderedPrefixRule:
    rule_id: str
    continue_categories: tuple
    terminal_categories: tuple


@dataclass(frozen=True, init=False)
class FiniteSetValue:
    elements: tuple

    def __init__(self, source):
        if not isinstance(source, tuple):
            raise TypeError("finite set source must be a tuple")
        atoms = tuple(atom_from_value(element) for element in source)
        ordered = tuple(sorted(atoms, key=lambda atom: atom.canonical_key()))
        if any(left.canonical_key() == right.canonical_key() for left, right in zip(ordered, ordered[1:])):
            raise ValueError("finite set source contains duplicate elements")
        object.__setattr__(self, "elements", ordered)

    @classmethod
    def _from_union_atoms(cls, atoms):
        if any(type(atom) is not Atom for atom in atoms):
            raise TypeError("finite-set union requires exact Atom values")
        ordered = sorted(atoms, key=lambda atom: atom.canonical_key())
        unique = []
        for atom in ordered:
            if not unique or atom.canonical_key() != unique[-1].canonical_key():
                unique.append(atom)
        instance = object.__new__(cls)
        object.__setattr__(instance, "elements", tuple(unique))
        return instance

    def __eq__(self, other):
        return isinstance(other, FiniteSetValue) and self.elements == other.elements


@dataclass(frozen=True)
class Atom:
    kind: str
    value: str

    def __post_init__(self):
        if type(self.kind) is not str or not self.kind:
            raise TypeError("atom kind must be a non-empty string")
        if type(self.value) is not str:
            raise TypeError("atom value must be a string")

    def canonical_key(self):
        return self.kind, self.value


def atom_from_value(value):
    if type(value) is Atom:
        return value
    if isinstance(value, str):
        return Atom("symbol", value)
    raise TypeError("finite set members must be symbol strings or Atom values")


@dataclass(frozen=True)
class SetReference:
    name: str


@dataclass(frozen=True)
class SetUnion:
    left: object
    right: object


@dataclass(frozen=True)
class SetSubset:
    left: object
    right: object


@dataclass(frozen=True)
class ParticipantReference:
    name: str


@dataclass(frozen=True)
class ParticipantProperty:
    participant: ParticipantReference
    property_name: str


@dataclass(frozen=True)
class ParticipantId:
    namespace: str
    local_id: str

    def __post_init__(self):
        if type(self.namespace) is not str or not self.namespace:
            raise TypeError("participant namespace must be a non-empty string")
        if type(self.local_id) is not str or not self.local_id:
            raise TypeError("participant local_id must be a non-empty string")


def participant_id(namespace, local_id):
    return ParticipantId(namespace, local_id)


def validate_fact_environment(facts):
    if not hasattr(facts, "items"):
        raise TypeError("fact environment must be a mapping")
    validated = {}
    for key, value in facts.items():
        if type(key) is not tuple or len(key) != 2:
            raise TypeError("fact key must be (ParticipantId, property_id)")
        participant, property_id = key
        if type(participant) is not ParticipantId:
            raise TypeError("fact key must contain an exact ParticipantId")
        if type(property_id) is not str or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", property_id):
            raise TypeError("fact property_id must be an identifier string")
        if type(value) is not FiniteSetValue:
            raise TypeError("fact values must be exact FiniteSetValue values")
        validated[(participant, property_id)] = value
    return validated


@dataclass(frozen=True)
class SetRelationRule:
    rule_id: str
    participants: tuple
    predicate: str
    derived_name: str
    derivation: SetUnion
    relation: SetSubset


@dataclass(frozen=True)
class GroundedRelation:
    predicate: str
    participants: tuple
    status: object
    derived_value: object


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


def ordered_prefix_rule_from_data(data):
    continue_categories = data.get("continue_categories")
    terminal_categories = data.get("terminal_categories")
    for field, value in (("continue_categories", continue_categories), ("terminal_categories", terminal_categories)):
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            raise ValueError(f"{field} must be a list of non-empty strings")
        if len(set(value)) != len(value):
            raise ValueError(f"{field} must not contain duplicates")
    if set(continue_categories) & set(terminal_categories):
        raise ValueError("continue and terminal categories must be disjoint")
    return OrderedPrefixRule(
        data["id"],
        tuple(continue_categories),
        tuple(data["terminal_categories"]),
    )


def set_expression_from_data(data):
    kind = data["kind"]
    if kind == "set_ref":
        name = data.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("set reference name must be an identifier")
        return SetReference(name)
    if kind == "participant_property":
        participant = data.get("participant")
        if not isinstance(participant, dict) or participant.get("kind") != "participant_ref":
            raise ValueError("participant property requires a participant reference")
        name = participant.get("name")
        property_name = data.get("property")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("participant reference name must be an identifier")
        if not isinstance(property_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", property_name):
            raise ValueError("participant property name must be an identifier")
        return ParticipantProperty(ParticipantReference(name), property_name)
    if kind == "set_union":
        left = set_expression_from_data(data["left"])
        right = set_expression_from_data(data["right"])
        if not is_set_expression(left) or not is_set_expression(right):
            raise ValueError("set union operands must be set expressions")
        return SetUnion(left, right)
    if kind == "set_subset":
        left = set_expression_from_data(data["left"])
        right = set_expression_from_data(data["right"])
        if not is_set_expression(left) or not is_set_expression(right):
            raise ValueError("set subset operands must be set expressions")
        return SetSubset(left, right)
    if kind == "participant_ref":
        raise ValueError("participant references are only valid inside participant properties")
    raise ValueError(f"unknown set expression kind: {kind}")


def is_set_expression(expression):
    return isinstance(expression, (SetReference, ParticipantProperty, SetUnion))


def set_expression_references(expression):
    if isinstance(expression, ParticipantProperty):
        return {expression.participant.name}
    if isinstance(expression, SetUnion):
        return set_expression_references(expression.left) | set_expression_references(expression.right)
    return set()


def expression_references_name(expression, name):
    return isinstance(expression, SetReference) and expression.name == name


def set_relation_rule_from_data(data):
    participants = data.get("participants")
    predicate = data.get("predicate")
    derived_name = data.get("derived_name")
    if not isinstance(participants, list) or any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in participants):
        raise ValueError("participants must be a list of identifier names")
    if len(set(participants)) != len(participants):
        raise ValueError("participant names must be unique")
    if not isinstance(predicate, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", predicate):
        raise ValueError("predicate must be an identifier")
    if not isinstance(derived_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", derived_name):
        raise ValueError("derived_name must be an identifier")
    if derived_name in participants:
        raise ValueError("derived_name must not collide with a participant")
    derivation = set_expression_from_data(data["derivation"])
    relation = set_expression_from_data(data["relation"])
    if not isinstance(derivation, SetUnion) or not isinstance(relation, SetSubset):
        raise ValueError("set relation rule requires union derivation and subset relation")
    references = set_expression_references(derivation) | set_expression_references(relation)
    if not references <= set(participants):
        raise ValueError("participant property references an undeclared participant")
    if not expression_references_name(relation.left, derived_name):
        raise ValueError("relation must consume the derived set")
    return SetRelationRule(data["id"], tuple(participants), predicate, derived_name, derivation, relation)


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


def ordered_sequence(items):
    return OrderedSequence(items)


def annotations(items):
    return tuple(Annotation(element, category) for element, category in items)


def evaluate_ordered_prefix(rule, ordered_elements, annotations):
    """Return the maximal prefix admitted by a data-driven ordered rule."""
    by_element = {}
    known_categories = set(rule.continue_categories) | set(rule.terminal_categories)
    for annotation in annotations:
        if annotation.element in by_element:
            raise ValueError(f"ambiguous annotations for element: {annotation.element}")
        if annotation.category not in known_categories:
            raise ValueError(f"unknown annotation category: {annotation.category}")
        by_element[annotation.element] = annotation
    result = []
    for element in ordered_elements.elements:
        annotation = by_element.get(element)
        if annotation is None:
            break
        if annotation.category in rule.continue_categories:
            result.append(element)
            continue
        if annotation.category in rule.terminal_categories:
            result.append(element)
            break
        raise AssertionError("validated annotation category was not classified")
    return tuple(result)


def finite_set(source):
    return FiniteSetValue(source)


def evaluate_set_expression(expression, environment, facts=None):
    if isinstance(expression, SetReference):
        value = environment.get(expression.name, UNKNOWN)
        if value is UNKNOWN or isinstance(value, FiniteSetValue):
            return value
        raise TypeError(f"set reference {expression.name} is not a finite set")
    if isinstance(expression, ParticipantProperty):
        participant = environment.get(expression.participant.name, UNKNOWN)
        if participant is UNKNOWN:
            return UNKNOWN
        if type(participant) is not ParticipantId:
            raise TypeError("participant binding must be an exact ParticipantId")
        if facts is None:
            raise ValueError("participant properties require a fact environment")
        value = facts.get((participant, expression.property_name), UNKNOWN)
        if value is UNKNOWN or isinstance(value, FiniteSetValue):
            return value
        raise TypeError(f"fact {participant}.{expression.property_name} is not a finite set")
    if isinstance(expression, SetUnion):
        left = evaluate_set_expression(expression.left, environment, facts)
        right = evaluate_set_expression(expression.right, environment, facts)
        if left is UNKNOWN or right is UNKNOWN:
            return UNKNOWN
        return FiniteSetValue._from_union_atoms(left.elements + right.elements)
    raise TypeError(f"not a set-valued expression: {expression!r}")


def evaluate_set_relation(rule, environment, facts=None):
    if facts is not None:
        facts = validate_fact_environment(facts)
    participants = tuple(environment.get(name, UNKNOWN) for name in rule.participants)
    if any(value is not UNKNOWN and type(value) is not ParticipantId for value in participants):
        raise TypeError("participant binding must be an exact ParticipantId")
    derived = evaluate_set_expression(rule.derivation, environment, facts)
    if derived is UNKNOWN:
        return GroundedRelation(rule.predicate, participants, UNKNOWN, UNKNOWN)
    scoped_environment = dict(environment)
    scoped_environment[rule.derived_name] = derived
    relation = rule.relation
    left = evaluate_set_expression(relation.left, scoped_environment, facts)
    right = evaluate_set_expression(relation.right, scoped_environment, facts)
    if left is UNKNOWN or right is UNKNOWN:
        return GroundedRelation(rule.predicate, participants, UNKNOWN, derived)
    status = all(any(left_atom == right_atom for right_atom in right.elements) for left_atom in left.elements)
    return GroundedRelation(rule.predicate, participants, status, derived)


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
