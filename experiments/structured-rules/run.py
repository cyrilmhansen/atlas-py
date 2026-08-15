#!/usr/bin/env python3
"""Execute the structured array-law POC."""

import copy
import json
from pathlib import Path

from structured_rules import (
    ConcreteArray,
    all_substitutions,
    condition_status,
    extend_substitution,
    instantiate,
    rule_from_data,
    substitute,
    term_from_data,
    variables,
    oracle,
)


ROOT = Path(__file__).parent


def load_rules():
    data = json.loads((ROOT / "rules.json").read_text(encoding="utf-8"))
    return [rule_from_data(item) for item in data["rules"]]


def load_rule_data():
    return json.loads((ROOT / "rules.json").read_text(encoding="utf-8"))["rules"]


def main():
    same_index, other_index = load_rules()
    arrays = {
        "A0": ConcreteArray(("a", "b", "c")),
        "A1": ConcreteArray(("x", "b", "z")),
        "A2": ConcreteArray(("p", "q", "r")),
    }
    indices = [term_from_data({"kind": "const", "name": str(i)}) for i in range(3)]
    values = [term_from_data({"kind": "const", "name": value}) for value in ("u", "v")]
    array_terms = [term_from_data({"kind": "const", "name": name}) for name in arrays]
    domains = {"A": array_terms, "i": indices, "j": indices, "v": values}

    checked = 0
    derived = 0
    for rule in (same_index, other_index):
        for environment in all_substitutions(rule, domains):
            result = instantiate(rule, environment)
            checked += 1
            if result is None:
                continue
            lhs, rhs = result
            assert oracle(lhs, arrays) == oracle(rhs, arrays), (rule.rule_id, environment, lhs, rhs)
            derived += 1

    # The second law is rejected exactly when i == j.
    equal_index = {"A": array_terms[0], "i": indices[1], "j": indices[1], "v": values[0]}
    assert instantiate(other_index, equal_index) is None

    # An ungrounded premise is unknown, never true because variable names differ.
    incomplete = {"i": indices[0]}
    assert condition_status(other_index.conditions[0], incomplete) == "unknown"
    assert instantiate(other_index, incomplete) is None

    # Dropping i != j exposes the concrete counterexample.
    unsafe = other_index.__class__(other_index.rule_id, other_index.lhs, other_index.rhs, ())
    unsafe_instance = instantiate(unsafe, equal_index)
    assert unsafe_instance is not None
    assert oracle(unsafe_instance[0], arrays) != oracle(unsafe_instance[1], arrays)

    # Swapping input/output state in the first law is not semantically valid.
    wrong_lhs = term_from_data({"kind": "app", "name": "get", "args": [
        {"kind": "var", "name": "i"}, {"kind": "var", "name": "A"}
    ]})
    wrong_rhs = term_from_data({"kind": "app", "name": "get", "args": [
        {"kind": "var", "name": "i"}, {"kind": "app", "name": "set", "args": [
            {"kind": "var", "name": "i"}, {"kind": "var", "name": "v"}, {"kind": "var", "name": "A"}
        ]}
    ]})
    wrong = same_index.__class__("wrong_state_order", wrong_lhs, wrong_rhs, ())
    wrong_instance = instantiate(wrong, {"A": array_terms[0], "i": indices[0], "v": values[0]})
    assert oracle(wrong_instance[0], arrays) != oracle(wrong_instance[1], arrays)

    # Repeated variables share one binding; distinct variables remain distinct
    # even when a temporary substitution assigns them the same concrete value.
    first = extend_substitution({}, "i", indices[0])
    assert first is not None and extend_substitution(first, "i", indices[1]) is None
    assert variables(other_index.lhs) >= {"i", "j"}
    same_value = {"i": indices[0], "j": indices[0]}
    assert "i" in variables(other_index.lhs) and "j" in variables(other_index.lhs)
    assert substitute(other_index.lhs, same_value).args[0] == substitute(other_index.lhs, same_value).args[1].args[0]
    assert instantiate(other_index, {"A": array_terms[0], "i": indices[0], "j": indices[1], "v": values[0]}) is not None

    # Persisted condition kinds are not silently reinterpreted.
    bad_rule = copy.deepcopy(load_rule_data()[1])
    bad_rule["conditions"][0]["kind"] = "equal"
    try:
        rule_from_data(bad_rule)
    except ValueError as error:
        assert "unsupported condition kind" in str(error)
    else:
        raise AssertionError("unknown condition kind was accepted")

    print(f"rules: 2; substitutions checked: {checked}; consequences verified: {derived}")
    print("counter-tests detected: missing condition, ungrounded premise, unknown kind, swapped state, conflicting binding, equal/distinct variables")
    print("verdict: SUPPORTED")


if __name__ == "__main__":
    main()
