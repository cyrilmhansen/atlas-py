#!/usr/bin/env python3
"""Vocabulary-independent structural validator for the Atlas corpus."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).parent
CORPUS = ROOT / "associative-search.json"
STATUSES = {"exact", "bound", "estimate", "unknown"}
PROVENANCE_KINDS = {"source", "derived"}


def fail(message):
    raise ValueError(f"validation error: {message}")


def reject_constant(value):
    raise ValueError(f"validation error: non-standard JSON constant {value}")


def load_json(text):
    return json.loads(text, parse_constant=reject_constant)


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def validate_source(source, index):
    if not isinstance(source, dict):
        fail(f"source {index} must be an object")
    required = {"id", "title", "url", "locator", "accessed"}
    missing = required - source.keys()
    if missing:
        fail(f"source {index} missing {sorted(missing)}")
    for field in required:
        if not nonempty_string(source[field]):
            fail(f"source {source.get('id', index)} has empty or non-string {field}")


def validate_description(description, description_ids):
    if not isinstance(description, dict):
        fail("description element must be an object")
    required = {"id", "label", "role"}
    missing = required - description.keys()
    if missing:
        fail(f"description {description.get('id')} missing {sorted(missing)}")
    if not nonempty_string(description["id"]) or not nonempty_string(description["label"]):
        fail(f"description {description.get('id')} has an empty id or label")
    if not nonempty_string(description["role"]):
        fail(f"description {description['id']} has an empty role")
    if description["id"] in description_ids:
        fail(f"duplicate description id {description['id']}")
    description_ids.add(description["id"])


def validate_assertion(assertion, assertion_ids, description_ids, source_ids):
    if not isinstance(assertion, dict):
        fail("assertion element must be an object")
    required = {"id", "subject", "predicate", "status", "provenance", "assumptions", "scope"}
    missing = required - assertion.keys()
    if missing:
        fail(f"assertion {assertion.get('id')} missing {sorted(missing)}")
    assertion_id = assertion["id"]
    if not nonempty_string(assertion_id):
        fail("assertion id must be a non-empty string")
    if assertion_id in assertion_ids:
        fail(f"duplicate assertion id {assertion_id}")
    assertion_ids.add(assertion_id)
    if not nonempty_string(assertion["subject"]):
        fail(f"{assertion_id} subject must be a non-empty string")
    if assertion["subject"] not in description_ids:
        fail(f"{assertion_id} has unresolved subject {assertion['subject']}")
    if not nonempty_string(assertion["predicate"]):
        fail(f"{assertion_id} predicate must be a non-empty string")
    if not nonempty_string(assertion["status"]):
        fail(f"{assertion_id} status must be a non-empty string")
    if assertion["status"] not in STATUSES:
        fail(f"{assertion_id} has invalid status {assertion['status']}")
    has_object = "object" in assertion
    has_value = "value" in assertion
    if not has_object and not has_value:
        fail(f"{assertion_id} must have object, value, or both")
    if has_object:
        if not nonempty_string(assertion["object"]):
            fail(f"{assertion_id} object must be a non-empty string")
        if assertion["object"] not in description_ids:
            fail(f"{assertion_id} has unresolved object {assertion['object']}")
    if has_value:
        if assertion["value"] is None or isinstance(assertion["value"], (dict, list)):
            fail(f"{assertion_id} value must be a non-null scalar")
        if isinstance(assertion["value"], str) and not assertion["value"].strip():
            fail(f"{assertion_id} value must not be an empty string")
    if not isinstance(assertion["assumptions"], list) or not all(nonempty_string(item) for item in assertion["assumptions"]):
        fail(f"{assertion_id} assumptions must be a list of non-empty strings")
    if not isinstance(assertion["scope"], dict):
        fail(f"{assertion_id} scope must be an object")
    provenance = assertion["provenance"]
    if not isinstance(provenance, dict) or not {"source_id", "locator", "evidence"} <= provenance.keys():
        fail(f"{assertion_id} has incomplete provenance")
    for field in ("source_id", "locator", "evidence"):
        if not nonempty_string(provenance[field]):
            fail(f"{assertion_id} provenance {field} is empty")
    if provenance["source_id"] not in source_ids:
        fail(f"{assertion_id} has unknown source {provenance['source_id']}")
    kind = provenance.get("kind", "source")
    if kind not in PROVENANCE_KINDS:
        fail(f"{assertion_id} has invalid provenance kind {kind}")
    if kind == "derived":
        basis = provenance.get("basis")
        if not isinstance(basis, list) or not basis or not all(nonempty_string(item) for item in basis):
            fail(f"{assertion_id} derived provenance needs a non-empty basis list")
    elif "basis" in provenance:
        fail(f"{assertion_id} source provenance must not contain basis")


def validate_derivation_graph(assertions):
    by_id = {item["id"]: item for item in assertions}
    graph = {}
    for assertion in assertions:
        provenance = assertion["provenance"]
        if provenance.get("kind", "source") != "derived":
            continue
        basis = provenance["basis"]
        if assertion["id"] in basis:
            fail(f"{assertion['id']} derived provenance cannot reference itself")
        unknown = [item for item in basis if item not in by_id]
        if unknown:
            fail(f"{assertion['id']} has unknown basis {unknown}")
        graph[assertion["id"]] = basis

    visiting = set()
    visited = set()

    def visit(node, path):
        if node in visiting:
            cycle = " -> ".join(path + [node])
            fail(f"cycle in derived provenance: {cycle}")
        if node in visited:
            return
        visiting.add(node)
        for parent in graph.get(node, []):
            visit(parent, path + [node])
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node, [])


def validate_data(data):
    if not isinstance(data, dict):
        fail("top-level document must be an object")
    if data.get("schema") != "atlas-atomic-corpus-v0":
        fail("unexpected schema")
    for collection in ("sources", "descriptions", "assertions"):
        if collection not in data or not isinstance(data[collection], list):
            fail(f"top-level {collection} collection is required and must be a list")
    sources = data["sources"]
    descriptions = data["descriptions"]
    assertions = data["assertions"]
    source_ids = set()
    for index, source in enumerate(sources):
        validate_source(source, index)
        if source["id"] in source_ids:
            fail(f"duplicate source id {source['id']}")
        source_ids.add(source["id"])
    description_ids = set()
    for description in descriptions:
        validate_description(description, description_ids)
    assertion_ids = set()
    for assertion in assertions:
        validate_assertion(assertion, assertion_ids, description_ids, source_ids)
    validate_derivation_graph(assertions)
    return len(descriptions), len(assertions), len(sources)


def main(path=CORPUS):
    try:
        data = load_json(Path(path).read_text(encoding="utf-8"))
        descriptions, assertions, sources = validate_data(data)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(str(error))
    print(f"valid: {descriptions} descriptions, {assertions} assertions, {sources} sources")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) == 2 else CORPUS)
