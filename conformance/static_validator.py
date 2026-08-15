"""Static validation for the declarative Core V1 C0 fixture.

This module deliberately validates declarations only.  It does not implement
grounding, coverage:v1, decision selection, persistence, or any Atlas engine.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


class FixtureError(ValueError):
    """The fixture is structurally invalid for the C0 contract."""


ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9:_-]*$")
INTEGER_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")
VALUE_KINDS = {"symbol", "integer", "finite_set<symbol>", "sequence<symbol>"}
EPISTEMIC_STATUSES = {"exact", "bound", "estimate", "unknown"}
POLARITIES = {"positive", "negative"}


def _mapping(value, where):
    if type(value) is not dict:
        raise FixtureError(f"{where} must be an object")
    return value


def _list(value, where):
    if type(value) is not list:
        raise FixtureError(f"{where} must be a list")
    return value


def _exact_string(value, where, *, identifier=False, nonempty=True):
    if type(value) is not str or (nonempty and not value):
        raise FixtureError(f"{where} must be an exact non-empty string")
    if identifier and ID_RE.fullmatch(value) is None:
        raise FixtureError(f"{where} is not a valid identifier: {value!r}")
    return value


def _unique_strings(values, where, *, identifiers=False):
    values = _list(values, where)
    seen = set()
    for index, value in enumerate(values):
        value = _exact_string(value, f"{where}[{index}]", identifier=identifiers)
        if value in seen:
            raise FixtureError(f"duplicate value in {where}: {value!r}")
        seen.add(value)
    return values


def _record_metadata(record, where):
    _exact_string(record.get("id"), f"{where}.id", identifier=True)
    _exact_string(record.get("scope"), f"{where}.scope")
    status = _exact_string(record.get("epistemic_status"), f"{where}.epistemic_status")
    if status not in EPISTEMIC_STATUSES:
        raise FixtureError(f"unsupported epistemic status in {where}: {status!r}")
    provenance = _unique_strings(record.get("provenance"), f"{where}.provenance")
    if not provenance:
        raise FixtureError(f"{where}.provenance must not be empty")


def _validate_value(value, where, expected_kind=None):
    value = _mapping(value, where)
    kind = _exact_string(value.get("kind"), f"{where}.kind")
    if kind not in VALUE_KINDS:
        raise FixtureError(f"unsupported value kind in {where}: {kind!r}")
    if expected_kind is not None and kind != expected_kind:
        raise FixtureError(f"{where} has kind {kind!r}, expected {expected_kind!r}")

    if kind == "symbol":
        _exact_string(value.get("value"), f"{where}.value", nonempty=False)
    elif kind == "integer":
        number = value.get("value")
        if type(number) is not str or INTEGER_RE.fullmatch(number) is None:
            raise FixtureError(f"{where}.value must be a canonical integer string")
    else:
        items = _list(value.get("items"), f"{where}.items")
        seen = set()
        for index, item in enumerate(items):
            item = _exact_string(item, f"{where}.items[{index}]", nonempty=False)
            if kind == "finite_set<symbol>" and item in seen:
                raise FixtureError(f"duplicate finite_set item in {where}: {item!r}")
            seen.add(item)


def _validate_vocab(vocabulary):
    vocabulary = _mapping(vocabulary, "vocabulary")
    predicates = _list(vocabulary.get("predicates"), "vocabulary.predicates")
    properties = _list(vocabulary.get("properties"), "vocabulary.properties")
    predicate_map = {}
    property_map = {}
    for index, predicate in enumerate(predicates):
        where = f"vocabulary.predicates[{index}]"
        predicate = _mapping(predicate, where)
        ident = _exact_string(predicate.get("id"), f"{where}.id", identifier=True)
        if ident in predicate_map:
            raise FixtureError(f"duplicate predicate id: {ident!r}")
        version = _exact_string(predicate.get("version"), f"{where}.version")
        arity = predicate.get("arity")
        if type(arity) is not int or type(arity) is bool or arity < 0:
            raise FixtureError(f"{where}.arity must be a non-negative integer")
        roles = _unique_strings(predicate.get("roles"), f"{where}.roles")
        if len(roles) != arity:
            raise FixtureError(f"{where}.roles length does not match arity")
        predicate_map[ident] = (version, arity, roles)
    for index, prop in enumerate(properties):
        where = f"vocabulary.properties[{index}]"
        prop = _mapping(prop, where)
        ident = _exact_string(prop.get("id"), f"{where}.id", identifier=True)
        if ident in property_map:
            raise FixtureError(f"duplicate property id: {ident!r}")
        version = _exact_string(prop.get("version"), f"{where}.version")
        value_kind = _exact_string(prop.get("value"), f"{where}.value")
        if value_kind not in VALUE_KINDS:
            raise FixtureError(f"unsupported property value kind: {value_kind!r}")
        property_map[ident] = (version, value_kind)
    return predicate_map, property_map


def _validate_descriptions(records):
    records = _list(records, "descriptions")
    result = {}
    for index, record in enumerate(records):
        where = f"descriptions[{index}]"
        record = _mapping(record, where)
        ident = _exact_string(record.get("id"), f"{where}.id", identifier=True)
        if ident in result:
            raise FixtureError(f"duplicate description id: {ident!r}")
        _exact_string(record.get("label"), f"{where}.label", nonempty=False)
        result[ident] = record
    return result


def _validate_facts(records, descriptions, properties):
    records = _list(records, "facts")
    result = {}
    for index, record in enumerate(records):
        where = f"facts[{index}]"
        record = _mapping(record, where)
        _record_metadata(record, where)
        if record.get("kind") != "property":
            raise FixtureError(f"{where}.kind must be 'property'")
        description = _exact_string(record.get("description"), f"{where}.description", identifier=True)
        prop = _exact_string(record.get("property"), f"{where}.property", identifier=True)
        if description not in descriptions:
            raise FixtureError(f"unresolved fact description: {description!r}")
        if prop not in properties:
            raise FixtureError(f"unresolved fact property: {prop!r}")
        _validate_value(record.get("value"), f"{where}.value", properties[prop][1])
        ident = record["id"]
        if ident in result:
            raise FixtureError(f"duplicate fact id: {ident!r}")
        result[ident] = record
    return result


def _validate_relations(records, descriptions, predicates):
    records = _list(records, "relations")
    result = {}
    for index, record in enumerate(records):
        where = f"relations[{index}]"
        record = _mapping(record, where)
        _record_metadata(record, where)
        predicate = _exact_string(record.get("predicate"), f"{where}.predicate", identifier=True)
        version = _exact_string(record.get("version"), f"{where}.version")
        if predicate not in predicates or predicates[predicate][0] != version:
            raise FixtureError(f"unresolved or wrong-version predicate: {predicate!r}")
        participants = _unique_strings(record.get("participants"), f"{where}.participants", identifiers=True)
        if len(participants) != predicates[predicate][1] or any(item not in descriptions for item in participants):
            raise FixtureError(f"invalid relation participants in {where}")
        polarity = _exact_string(record.get("polarity"), f"{where}.polarity")
        if polarity not in POLARITIES:
            raise FixtureError(f"unsupported relation polarity: {polarity!r}")
        ident = record["id"]
        if ident in result:
            raise FixtureError(f"duplicate relation id: {ident!r}")
        result[ident] = record
    return result


def _validate_expression(expression, where, participants, properties):
    expression = _mapping(expression, where)
    op = _exact_string(expression.get("op"), f"{where}.op")
    if op == "property":
        participant = _exact_string(expression.get("participant"), f"{where}.participant", identifier=True)
        prop = _exact_string(expression.get("property"), f"{where}.property", identifier=True)
        if participant not in participants or prop not in properties:
            raise FixtureError(f"unresolved property expression in {where}")
    elif op in {"set_union", "set_subset"}:
        _validate_expression(expression.get("left"), f"{where}.left", participants, properties)
        _validate_expression(expression.get("right"), f"{where}.right", participants, properties)
    else:
        raise FixtureError(f"unsupported expression operator: {op!r}")


def _validate_rules(records, predicates, properties):
    records = _list(records, "rules")
    result = {}
    for index, record in enumerate(records):
        where = f"rules[{index}]"
        record = _mapping(record, where)
        ident = _exact_string(record.get("id"), f"{where}.id", identifier=True)
        if ident in result:
            raise FixtureError(f"duplicate rule id: {ident!r}")
        _exact_string(record.get("version"), f"{where}.version")
        participants = _unique_strings(record.get("participants"), f"{where}.participants", identifiers=True)
        _validate_expression(record.get("when"), f"{where}.when", participants, properties)
        head = _mapping(record.get("head"), f"{where}.head")
        predicate = _exact_string(head.get("predicate"), f"{where}.head.predicate", identifier=True)
        version = _exact_string(head.get("version"), f"{where}.head.version")
        if predicate not in predicates or predicates[predicate][0] != version:
            raise FixtureError(f"unresolved or wrong-version rule head predicate: {predicate!r}")
        head_participants = _unique_strings(head.get("participants"), f"{where}.head.participants", identifiers=True)
        if head_participants != participants:
            raise FixtureError(f"rule head participants differ from rule participants in {where}")
        polarity = _exact_string(head.get("polarity"), f"{where}.head.polarity")
        if polarity not in POLARITIES:
            raise FixtureError(f"unsupported rule head polarity: {polarity!r}")
        result[ident] = record
    return result


def _validate_contexts(records, rules):
    records = _list(records, "contexts")
    result = {}
    for index, record in enumerate(records):
        where = f"contexts[{index}]"
        record = _mapping(record, where)
        ident = _exact_string(record.get("id"), f"{where}.id", identifier=True)
        if ident in result:
            raise FixtureError(f"duplicate context id: {ident!r}")
        _unique_strings(record.get("visible_scopes"), f"{where}.visible_scopes")
        enabled = _unique_strings(record.get("enabled_rules"), f"{where}.enabled_rules", identifiers=True)
        if any(rule not in rules for rule in enabled):
            raise FixtureError(f"unresolved context rule in {where}")
        result[ident] = record
    return result


def _validate_snapshots(records):
    records = _list(records, "snapshots")
    result = {}
    for index, record in enumerate(records):
        where = f"snapshots[{index}]"
        record = _mapping(record, where)
        ident = _exact_string(record.get("id"), f"{where}.id", identifier=True)
        if ident in result:
            raise FixtureError(f"duplicate snapshot id: {ident!r}")
        parent = record.get("parent")
        if parent is not None:
            _exact_string(parent, f"{where}.parent", identifier=True)
        if record.get("active_records") != "all":
            raise FixtureError(f"unsupported active_records policy in {where}")
        result[ident] = record
    return result


def _validate_supersession(value, facts, properties, existing_ids):
    value = _mapping(value, "supersession")
    source_id = _exact_string(value.get("replaces"), "supersession.replaces", identifier=True)
    replacement_id = _exact_string(value.get("replacement_id"), "supersession.replacement_id", identifier=True)
    future_snapshot = _exact_string(value.get("future_snapshot"), "supersession.future_snapshot", identifier=True)
    if source_id not in facts:
        raise FixtureError(f"supersession source is not a fact: {source_id!r}")
    if replacement_id in existing_ids or replacement_id == source_id:
        raise FixtureError(f"supersession replacement id is not fresh: {replacement_id!r}")
    source = facts[source_id]
    prop = source["property"]
    _validate_value(value.get("replacement_value"), "supersession.replacement_value", properties[prop][1])
    if not future_snapshot:
        raise FixtureError("supersession.future_snapshot must be non-empty")


def validate_fixture(fixture):
    fixture = _mapping(fixture, "fixture")
    if fixture.get("schema") != "atlas.conformance.core-v1/1":
        raise FixtureError("unsupported or missing fixture schema")
    _exact_string(fixture.get("fixture_id"), "fixture.fixture_id", identifier=True)
    _exact_string(fixture.get("description"), "fixture.description", nonempty=False)
    predicates, properties = _validate_vocab(fixture.get("vocabulary"))
    descriptions = _validate_descriptions(fixture.get("descriptions"))
    facts = _validate_facts(fixture.get("facts"), descriptions, properties)
    relations = _validate_relations(fixture.get("relations"), descriptions, predicates)
    rules = _validate_rules(fixture.get("rules"), predicates, properties)
    contexts = _validate_contexts(fixture.get("contexts"), rules)
    snapshots = _validate_snapshots(fixture.get("snapshots"))

    decision = _mapping(fixture.get("decision"), "decision")
    for field, values in {
        "intent": descriptions,
        "request": descriptions,
        "context": contexts,
        "snapshot": snapshots,
    }.items():
        ident = _exact_string(decision.get(field), f"decision.{field}", identifier=True)
        if ident not in values:
            raise FixtureError(f"unresolved decision.{field}: {ident!r}")
    _exact_string(decision.get("manifest_version"), "decision.manifest_version")

    existing_ids = set(descriptions) | set(facts) | set(relations) | set(rules) | set(contexts) | set(snapshots)
    _validate_supersession(fixture.get("supersession"), facts, properties, existing_ids)
    return True


def load_fixture(path=None):
    if path is None:
        path = Path(__file__).parent / "fixtures" / "m1-coverage.json"
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


if __name__ == "__main__":
    validate_fixture(load_fixture())
    print("static fixture: valid")
