#!/usr/bin/env python3
"""Minimal key-compatibility check for indexed lookup occurrences."""

import json
from pathlib import Path


def compatible(index_id, lookup_id, facts):
    required_indexes = {
        fact["object"]
        for fact in facts
        if fact.get("subject") == lookup_id and fact.get("predicate") == "requires"
    }
    index_keys = {
        fact["object"]
        for fact in facts
        if fact.get("subject") == index_id and fact.get("predicate") == "indexes"
    }
    search_keys = {
        fact["object"]
        for fact in facts
        if fact.get("subject") == lookup_id and fact.get("predicate") == "searches_by"
    }
    return index_id in required_indexes and bool(index_keys) and index_keys == search_keys


def compatible_pairs(facts):
    indexes = {fact["subject"] for fact in facts if fact.get("predicate") == "indexes"}
    lookups = {fact["subject"] for fact in facts if fact.get("predicate") == "searches_by"}
    return {
        (index_id, lookup_id)
        for index_id in indexes
        for lookup_id in lookups
        if compatible(index_id, lookup_id, facts)
    }


def main():
    corpus = json.loads(Path(__file__).with_name("associative-search.json").read_text())
    current = corpus["assertions"]
    assert compatible("representation.ordered_index_x", "operation.index_lookup_x", current)

    index_x_search_y = [
        {"subject": "index_x", "predicate": "indexes", "object": "column_x"},
        {"subject": "lookup_y", "predicate": "requires", "object": "index_x"},
        {"subject": "lookup_y", "predicate": "searches_by", "object": "column_y"},
    ]
    assert not compatible("index_x", "lookup_y", index_x_search_y)

    paired = [
        {"subject": "index_x", "predicate": "indexes", "object": "column_x"},
        {"subject": "index_y", "predicate": "indexes", "object": "column_y"},
        {"subject": "lookup_x", "predicate": "requires", "object": "index_x"},
        {"subject": "lookup_y", "predicate": "requires", "object": "index_y"},
        {"subject": "lookup_x", "predicate": "searches_by", "object": "column_x"},
        {"subject": "lookup_y", "predicate": "searches_by", "object": "column_y"},
    ]
    assert compatible_pairs(paired) == {("index_x", "lookup_x"), ("index_y", "lookup_y")}
    assert not compatible("index_x", "lookup_y", paired)
    assert not compatible("index_y", "lookup_x", paired)
    print("indexed-key compatibility: four cases passed")


if __name__ == "__main__":
    main()
