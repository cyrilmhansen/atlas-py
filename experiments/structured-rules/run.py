#!/usr/bin/env python3
"""Execute the structured array-law POC."""

import copy
import json
from dataclasses import replace
from bisect import bisect_left
from pathlib import Path

from structured_rules import (
    ConcreteArray,
    Comparison,
    Forall,
    Interval,
    OrderedSequence,
    Postcondition,
    OrderedPrefixRule,
    evaluate_ordered_prefix,
    UNKNOWN,
    all_substitutions,
    condition_status,
    extend_substitution,
    instantiate,
    evaluate_expression,
    evaluate_postcondition,
    postcondition_from_data,
    ordered_prefix_rule_from_data,
    ordered_sequence,
    annotations,
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


def load_postconditions():
    data = json.loads((ROOT / "bisect_rules.json").read_text(encoding="utf-8"))
    return [postcondition_from_data(item) for item in data["rules"]]


def load_prefix_rules():
    data = json.loads((ROOT / "prefix_rules.json").read_text(encoding="utf-8"))
    return [ordered_prefix_rule_from_data(item) for item in data["rules"]]


def application_evaluator(array, key_function):
    def evaluate(name, arguments):
        if name == "get":
            index, concrete_array = arguments
            return concrete_array.values[index]
        if name == "key":
            return key_function(arguments[0])
        if name == "succ":
            return arguments[0] + 1
        raise ValueError(f"unknown application in bisect evaluator: {name}")

    return evaluate


def predicate_evaluator(sorted_facts):
    def evaluate(name, arguments):
        if name != "sorted_slice":
            raise ValueError(f"unknown predicate in bisect evaluator: {name}")
        array, lo, hi, key_name = arguments
        return sorted_facts.get((id(array), lo, hi, key_name), UNKNOWN)

    return evaluate


def bisect_environment(array, x, lo, hi, key_function, key_name):
    ip = bisect_left(array.values, x, lo, hi, key=key_function)
    return {
        "a": array,
        "x": x,
        "lo": lo,
        "ip": ip,
        "hi": hi,
        "key": key_name,
    }, ip


def verify_bisect_postcondition(postcondition, array, x, lo, hi, key_function, key_name):
    environment, ip = bisect_environment(array, x, lo, hi, key_function, key_name)
    facts = {(id(array), lo, hi, key_name): True}
    result = evaluate_postcondition(
        postcondition,
        environment,
        application_evaluator(array, key_function),
        predicate_evaluator(facts),
    )
    assert result is True, (environment, result)
    return ip, 2 * (hi - lo)


def run_bisect_checks():
    postcondition = load_postconditions()[0]
    cases = [
        (ConcreteArray((1, 1, 2, 4)), 1, 0, 4, lambda value: value, "identity"),
        (ConcreteArray((1, 2, 2, 4)), 2, 0, 4, lambda value: value, "identity"),
        (ConcreteArray((1, 2, 3, 4)), 3, 1, 4, lambda value: value, "identity"),
        (ConcreteArray((0, 1, 2, 3)), 2, 1, 3, lambda value: value, "identity"),
        (ConcreteArray((0, 1, 2, 3)), 4, 1, 3, lambda value: value, "identity"),
        (ConcreteArray((0, 1, 2)), 1, 1, 1, lambda value: value, "identity"),
        (ConcreteArray(("a", "bb", "ccc", "dddd")), 3, 0, 4, len, "len"),
    ]
    instances = 0
    visited = 0
    for array, x, lo, hi, key_function, key_name in cases:
        _, count = verify_bisect_postcondition(postcondition, array, x, lo, hi, key_function, key_name)
        instances += 1
        visited += count

    # Replacing < by <= accepts an invalid insertion point in the presence of duplicates.
    duplicate_env = {"a": ConcreteArray((1, 1, 2)), "x": 1, "lo": 0, "ip": 1, "hi": 3, "key": "identity"}
    left_forall = postcondition.constraints[3]
    assert isinstance(left_forall, Forall)
    weak_left = replace(left_forall, body=replace(left_forall.body, operator="<="))
    weak_left_rule = replace(postcondition, constraints=(postcondition.constraints[0], postcondition.constraints[1], postcondition.constraints[2], weak_left, postcondition.constraints[4]))
    duplicate_facts = {(id(duplicate_env["a"]), 0, 3, "identity"): True}
    duplicate_predicates = predicate_evaluator(duplicate_facts)
    duplicate_eval = application_evaluator(duplicate_env["a"], lambda value: value)
    assert evaluate_postcondition(postcondition, duplicate_env, duplicate_eval, duplicate_predicates) is False
    assert evaluate_postcondition(weak_left_rule, duplicate_env, duplicate_eval, duplicate_predicates) is True

    # Replacing >= by > rejects a valid lower bound containing an equal value.
    right_forall = postcondition.constraints[4]
    weak_right = replace(right_forall, body=replace(right_forall.body, operator=">"))
    weak_right_rule = replace(postcondition, constraints=(postcondition.constraints[0], postcondition.constraints[1], postcondition.constraints[2], postcondition.constraints[3], weak_right))
    right_env = {"a": ConcreteArray((1, 1, 2)), "x": 1, "lo": 0, "ip": 0, "hi": 3, "key": "identity"}
    right_facts = {(id(right_env["a"]), 0, 3, "identity"): True}
    right_eval = application_evaluator(right_env["a"], lambda value: value)
    right_predicates = predicate_evaluator(right_facts)
    assert evaluate_postcondition(postcondition, right_env, right_eval, right_predicates) is True
    assert evaluate_postcondition(weak_right_rule, right_env, right_eval, right_predicates) is False

    # Extending [lo, ip) by one element is detected by the structured forall.
    valid_env = {"a": ConcreteArray((1, 2, 3)), "x": 2, "lo": 0, "ip": 1, "hi": 3, "key": "identity"}
    wrong_domain = replace(
        left_forall,
        domain=Interval(
            left_forall.domain.start,
            term_from_data({"kind": "app", "name": "succ", "args": [{"kind": "var", "name": "ip"}]}),
        ),
    )
    wrong_domain_rule = replace(postcondition, constraints=(postcondition.constraints[0], postcondition.constraints[1], postcondition.constraints[2], wrong_domain, postcondition.constraints[4]))
    valid_facts = {(id(valid_env["a"]), 0, 3, "identity"): True}
    valid_eval = application_evaluator(valid_env["a"], lambda value: value)
    valid_predicates = predicate_evaluator(valid_facts)
    assert evaluate_postcondition(postcondition, valid_env, valid_eval, valid_predicates) is True
    assert evaluate_postcondition(wrong_domain_rule, valid_env, valid_eval, valid_predicates) is False

    # A missing bound or a body depending on an unbound variable is explicit unknown.
    incomplete = dict(valid_env)
    del incomplete["ip"]
    assert evaluate_postcondition(postcondition, incomplete, application_evaluator(incomplete["a"], lambda value: value), predicate_evaluator({})) is UNKNOWN
    unknown_body = replace(
        right_forall.body,
        right=term_from_data({"kind": "var", "name": "unbound"}),
    )
    assert evaluate_expression(
        unknown_body,
        {"a": valid_env["a"], "p": 0},
        application_evaluator(valid_env["a"], lambda value: value),
    ) is UNKNOWN

    # An out-of-range ip is rejected by the explicit bounds.
    out_of_range = dict(valid_env, ip=4)
    assert evaluate_postcondition(postcondition, out_of_range, application_evaluator(out_of_range["a"], lambda value: value), predicate_evaluator({(id(out_of_range["a"]), 0, 3, "identity"): True})) is False

    # Checking one passing element is not universal verification.
    right_body = right_forall.body
    one_element_env = {"a": ConcreteArray((2, 2, 4)), "x": 3, "lo": 0, "ip": 0, "hi": 3, "key": "identity", "p": 2}
    evaluator = application_evaluator(one_element_env["a"], lambda value: value)
    assert evaluate_expression(right_body, one_element_env, evaluator) is True
    assert evaluate_postcondition(postcondition, one_element_env, evaluator, predicate_evaluator({(id(one_element_env["a"]), 0, 3, "identity"): True})) is False

    # The bound p shadows an outer p only while evaluating the body and does not leak.
    captured = {"a": ConcreteArray((0, 1)), "x": 0, "lo": 0, "ip": 0, "hi": 2, "key": "identity", "p": 99}
    captured_facts = {(id(captured["a"]), 0, 2, "identity"): True}
    assert evaluate_postcondition(postcondition, captured, application_evaluator(captured["a"], lambda value: value), predicate_evaluator(captured_facts)) is True
    assert captured["p"] == 99

    # Unknown is accumulated rather than returned early, and false dominates it.
    status_term = term_from_data({"kind": "app", "name": "status", "args": [{"kind": "var", "name": "p"}]})
    status_body = Comparison("<", status_term, term_from_data({"kind": "const", "name": "1"}))
    status_forall = Forall("p", Interval(term_from_data({"kind": "const", "name": "0"}), term_from_data({"kind": "const", "name": "2"})), status_body)
    def status_evaluator(statuses):
        return lambda name, arguments: statuses.get(arguments[0], UNKNOWN) if name == "status" else (_ for _ in ()).throw(ValueError(name))

    # Boolean contracts use identity, not Python equality: 0 and 1 are invalid.
    literal_body = term_from_data({"kind": "var", "name": "result"})
    literal_domain = Interval(
        term_from_data({"kind": "const", "name": "0"}),
        term_from_data({"kind": "const", "name": "1"}),
    )
    for literal in (True, False, UNKNOWN):
        environment = {"result": literal, "0": 0, "1": 1}
        assert evaluate_expression(
            Forall("p", literal_domain, literal_body),
            environment,
            status_evaluator({}),
        ) is literal
        assert evaluate_postcondition(
            Postcondition("literal", (literal_body,)),
            environment,
            status_evaluator({}),
        ) is literal
    for invalid in (0, 1, "true"):
        environment = {"result": invalid, "0": 0, "1": 1}
        try:
            evaluate_expression(Forall("p", literal_domain, literal_body), environment, status_evaluator({}))
        except TypeError as error:
            assert "true/false/unknown" in str(error)
        else:
            raise AssertionError(f"invalid Forall boolean result accepted: {invalid!r}")
        try:
            evaluate_postcondition(Postcondition("literal", (literal_body,)), environment, status_evaluator({}))
        except TypeError as error:
            assert "true/false/unknown" in str(error)
        else:
            raise AssertionError(f"invalid postcondition boolean result accepted: {invalid!r}")

    numeric_env = {"0": 0, "1": 1, "2": 2}
    assert evaluate_expression(status_forall, numeric_env, status_evaluator({0: UNKNOWN, 1: 2})) is False
    assert evaluate_expression(status_forall, numeric_env, status_evaluator({0: 2, 1: UNKNOWN})) is False
    status_forall3 = replace(status_forall, domain=Interval(status_forall.domain.start, term_from_data({"kind": "const", "name": "3"})))
    numeric_env["3"] = 3
    assert evaluate_expression(status_forall3, numeric_env, status_evaluator({0: 0, 1: UNKNOWN, 2: 0})) is UNKNOWN
    assert evaluate_expression(status_forall, numeric_env, status_evaluator({0: 0, 1: 0})) is True
    empty_forall = replace(status_forall, domain=Interval(status_forall.domain.start, term_from_data({"kind": "const", "name": "0"})))
    assert evaluate_expression(empty_forall, numeric_env, status_evaluator({})) is True

    # Nested and successive quantifiers may reuse p without leaking bindings.
    inner = Forall("p", status_forall.domain, Comparison(">=", term_from_data({"kind": "var", "name": "p"}), term_from_data({"kind": "const", "name": "0"})))
    nested = Forall("p", status_forall.domain, inner)
    assert evaluate_expression(nested, {"p": 99, "0": 0, "1": 1, "2": 2}, application_evaluator(ConcreteArray((0, 1)), lambda value: value)) is True
    successive = Postcondition("successive", (status_forall, replace(status_forall, variable="p")))
    assert evaluate_postcondition(successive, numeric_env, status_evaluator({0: 0, 1: 0})) is True
    assert evaluate_expression(nested, {"p": 99, "0": 0, "1": 1, "2": 2}, application_evaluator(ConcreteArray((0, 1)), lambda value: value)) is True

    # Explicitly non-sorted and unknown sortedness do not authorize the law.
    marked_unsorted = {(id(valid_env["a"]), 0, 3, "identity"): False}
    assert evaluate_postcondition(postcondition, valid_env, valid_eval, predicate_evaluator(marked_unsorted)) is False
    assert evaluate_postcondition(postcondition, valid_env, valid_eval, predicate_evaluator({})) is UNKNOWN

    # Invalid and non-ground intervals have distinct behavior.
    invalid_interval = Interval(term_from_data({"kind": "const", "name": "2"}), term_from_data({"kind": "const", "name": "1"}))
    try:
        evaluate_expression(Forall("p", invalid_interval, status_body), {"1": 1, "2": 2}, status_evaluator({}))
    except ValueError as error:
        assert "invalid half-open interval" in str(error)
    else:
        raise AssertionError("reversed interval was accepted")
    try:
        evaluate_expression(Interval(term_from_data({"kind": "const", "name": "true"}), term_from_data({"kind": "const", "name": "2"})), {"true": True, "2": 2}, status_evaluator({}))
    except TypeError:
        pass
    else:
        raise AssertionError("non-integer interval bound was accepted")

    print(f"bisect postconditions persisted: 1; instances tested: {instances}; quantified elements visited: {visited}; postconditions verified: {instances}")
    print("bisect counter-tests detected: weak-left-bound, weak-right-bound, wrong-interval, out-of-range-ip, non-universal-single-element, bound-variable-capture, forall-truth-table, nested/successive-binding, invalid-interval, sortedness-precondition")
    print("bisect verdict: SUPPORTED")


def oracle_ordered_prefix(elements, annotations):
    if not isinstance(elements, (list, tuple)):
        raise TypeError("oracle sequence source must be a list or tuple")
    equality = {"EQ", "IN", "IS"}
    terminal = {"GT", "GE", "LT", "LE"}
    by_element = {}
    for element, category in annotations:
        if element in by_element:
            raise ValueError(f"ambiguous annotations for element: {element}")
        if category not in equality | terminal:
            raise ValueError(f"unknown annotation category: {category}")
        by_element[element] = category
    result = []
    for element in elements:
        category = by_element.get(element)
        if category is None:
            break
        if category in equality:
            result.append(element)
        elif category in terminal:
            result.append(element)
            break
        else:
            break
    return tuple(result)


def run_prefix_checks():
    rule = load_prefix_rules()[0]
    cases = [
        (("a", "b", "c", "d"), (("a", "EQ"), ("b", "EQ"), ("c", "EQ"))),
        (("a", "b", "c", "d"), (("a", "EQ"), ("b", "IN"), ("c", "GT"), ("d", "EQ"))),
        (("a", "b", "c", "d"), (("a", "EQ"), ("c", "EQ"))),
        (("a", "b", "c", "d"), (("b", "EQ"),)),
        (("a", "b", "c", "d"), (("a", "GT"), ("b", "EQ"))),
        (("a", "b", "c", "d"), (("a", "EQ"), ("b", "GT"), ("c", "EQ"))),
        (("a", "b"), (("a", "EQ"), ("b", "GT"))),
        (("a", "b", "c"), (("a", "EQ"),)),
        (("a", "b", "c", "d"), (("a", "EQ"), ("b", "EQ"), ("c", "EQ"), ("d", "EQ"))),
    ]
    verified = 0
    for index, constraints in cases:
        structured = evaluate_ordered_prefix(rule, ordered_sequence(index), annotations(constraints))
        oracle_result = oracle_ordered_prefix(index, constraints)
        assert structured == oracle_result, (index, constraints, structured, oracle_result)
        verified += 1

    valid_extra = 0
    assert evaluate_ordered_prefix(rule, ordered_sequence(("a", "b", "c")), annotations((("a", "EQ"), ("b", "EQ"), ("c", "EQ")))) == ("a", "b", "c")
    valid_extra += 1
    assert evaluate_ordered_prefix(rule, ordered_sequence(("a", "b", "c")), annotations((("a", "GT"), ("b", "EQ")))) == ("a",)
    valid_extra += 1
    assert evaluate_ordered_prefix(rule, ordered_sequence(()), annotations(())) == ()
    valid_extra += 1
    color_rule = OrderedPrefixRule("color_prefix", ("green",), ("amber", "red"))
    colors = annotations((("a", "green"), ("b", "amber"), ("c", "red")))
    assert evaluate_ordered_prefix(color_rule, ordered_sequence(("a", "b", "c")), colors) == ("a", "b")
    valid_extra += 1

    # The rule is about order, not membership in a set.
    first_order = ordered_sequence(("a", "b", "c"))
    second_order = ordered_sequence(("b", "a", "c"))
    order_query = annotations((("a", "EQ"), ("b", "GT"), ("c", "EQ")))
    assert evaluate_ordered_prefix(rule, first_order, order_query) == ("a", "b")
    assert evaluate_ordered_prefix(rule, second_order, order_query) == ("b",)

    # Explicit faulty interpretations are all rejected by discriminating cases.
    def continue_after_gap(index, constraints):
        matched = {column for column, _ in constraints}
        return tuple(column for column in index if column in matched)

    assert continue_after_gap(("a", "b", "c", "d"), (("a", "EQ"), ("c", "EQ"))) != ("a",)
    assert continue_after_gap(("a", "b", "c", "d"), (("a", "EQ"), ("b", "EQ"), ("c", "GT"), ("d", "EQ"))) != ("a", "b", "c")
    assert continue_after_gap(("a", "b", "c", "d"), (("b", "EQ"),)) != ()

    def treat_all_as_equality(index, constraints):
        by_column = {column for column, _ in constraints}
        return tuple(column for column in index if column in by_column)

    assert treat_all_as_equality(("a", "b", "c", "d"), (("a", "GT"), ("b", "EQ"))) != ("a",)
    assert evaluate_ordered_prefix(rule, first_order, order_query) != evaluate_ordered_prefix(rule, second_order, order_query)

    # Duplicate annotations are ambiguous in either input order and never normalized away.
    duplicate_errors = []
    for raw_annotations in (
        (("a", "green"), ("a", "amber")),
        (("a", "amber"), ("a", "green")),
    ):
        try:
            evaluate_ordered_prefix(color_rule, ordered_sequence(("a", "b")), annotations(raw_annotations))
        except ValueError as error:
            duplicate_errors.append(str(error))
        else:
            raise AssertionError("duplicate annotation was accepted")
    assert duplicate_errors == ["ambiguous annotations for element: a", "ambiguous annotations for element: a"]
    try:
        evaluate_ordered_prefix(color_rule, ordered_sequence(("a", "b")), annotations((("a", "green"), ("b", "green"), ("b", "amber"))))
    except ValueError as error:
        assert str(error) == "ambiguous annotations for element: b"
    else:
        raise AssertionError("duplicate annotation in a larger input was accepted")

    # Unknown categories, overlapping rule categories and unordered sources are rejected.
    try:
        evaluate_ordered_prefix(rule, ordered_sequence(("a",)), annotations((("a", "UNKNOWN"),)))
    except ValueError as error:
        assert str(error) == "unknown annotation category: UNKNOWN"
    else:
        raise AssertionError("unknown annotation category was accepted")
    try:
        ordered_prefix_rule_from_data({"id": "bad", "continue_categories": ["EQ"], "terminal_categories": ["EQ"]})
    except ValueError as error:
        assert str(error) == "continue and terminal categories must be disjoint"
    else:
        raise AssertionError("overlapping rule categories were accepted")
    for malformed in ("EQ", {"EQ"}, {"category": "EQ"}, ["EQ", 1]):
        try:
            ordered_prefix_rule_from_data({"id": "bad", "continue_categories": malformed, "terminal_categories": ["GT"]})
        except ValueError as error:
            assert "continue_categories must be a list of non-empty strings" in str(error)
        else:
            raise AssertionError(f"malformed category list was accepted: {malformed!r}")
    for unordered in ({"a", "b"}, {"a": 1, "b": 2}):
        try:
            ordered_sequence(unordered)
        except TypeError as error:
            assert "list or tuple" in str(error)
        else:
            raise AssertionError("unordered sequence source was accepted")

    # The independent oracle checks the same invalid-input contract itself.
    for raw_annotations in (
        (("a", "EQ"), ("a", "GT")),
        (("a", "GT"), ("a", "EQ")),
    ):
        try:
            oracle_ordered_prefix(("a", "b"), raw_annotations)
        except ValueError as error:
            assert str(error) == "ambiguous annotations for element: a"
        else:
            raise AssertionError("oracle accepted duplicate annotation")

    invalid_count = 2 + 1 + 1 + 2 + 1 + 4
    print(f"ordered-prefix rules persisted: 1; valid instances tested: {len(cases) + valid_extra}; invalid inputs rejected: {invalid_count}; prefixes verified: {verified + valid_extra}")
    print("ordered-prefix counter-tests detected: ignored-order, continued-after-gap, continued-after-range, suffix-without-prefix, equality-range-collapse, reordered-index, duplicate-annotations, unknown-category, overlapping-categories, unordered-source")
    print("ordered-prefix verdict: SUPPORTED")


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
    run_bisect_checks()
    run_prefix_checks()


if __name__ == "__main__":
    main()
