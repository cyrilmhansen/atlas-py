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
    Atom,
    GroundedRelation,
    FiniteSetValue,
    OrderedSequence,
    Postcondition,
    OrderedPrefixRule,
    ParticipantId,
    evaluate_set_relation,
    finite_set,
    participant_id,
    evaluate_ordered_prefix,
    UNKNOWN,
    all_substitutions,
    condition_status,
    extend_substitution,
    instantiate,
    evaluate_expression,
    evaluate_postcondition,
    postcondition_from_data,
    set_relation_rule_from_data,
    set_expression_from_data,
    validate_fact_environment,
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


def load_set_rules():
    data = json.loads((ROOT / "set_rules.json").read_text(encoding="utf-8"))
    return [set_relation_rule_from_data(item) for item in data["rules"]]


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


def oracle_set(source):
    if not isinstance(source, tuple):
        raise TypeError("oracle finite set source must be a tuple")
    try:
        result = set(source)
    except TypeError as error:
        raise TypeError("oracle finite set elements must be hashable") from error
    if len(result) != len(source):
        raise ValueError("oracle finite set source contains duplicate elements")
    return result


def oracle_grounded_relation(resource, consumer, facts):
    if type(resource) is not ParticipantId or type(consumer) is not ParticipantId:
        raise TypeError("oracle participants must be exact ParticipantId values")
    # Validate the complete participant-scoped environment before any lookup.
    # The oracle keeps its calculation independent, but shares the POC's
    # explicit input boundary so malformed unused facts cannot be ignored.
    checked = validate_fact_environment(facts)

    available = checked.get((resource, "available"), UNKNOWN)
    search = checked.get((consumer, "search_requirements"), UNKNOWN)
    output = checked.get((consumer, "output_requirements"), UNKNOWN)
    if available is UNKNOWN or search is UNKNOWN or output is UNKNOWN:
        return GroundedRelation("covers", (resource, consumer), UNKNOWN, None)

    def atom_key(atom):
        return (atom.kind, atom.value)

    required = []
    for atom in search.elements + output.elements:
        if not any(atom_key(atom) == atom_key(existing) for existing in required):
            required.append(atom)
    status = all(any(atom_key(required_atom) == atom_key(available_atom) for available_atom in available.elements) for required_atom in required)
    return GroundedRelation("covers", (resource, consumer), status, None)


def run_set_checks():
    rule = load_set_rules()[0]
    cases = [
        (("a", "b", "c"), ("a",), ("b",)),
        (("a", "b"), ("a",), ("c",)),
        (("a", "b", "c"), (), ("a", "c")),
        (("a", "b", "c"), ("a", "b", "c"), ()),
        ((), (), ()),
        (("c", "b", "a"), ("a",), ("b",)),
        (("a", "b", "c"), ("a",), ("b",)),
        (("a", "b", "c"), ("a",), ("c",)),
    ]

    def facts_for(resource, consumer, available, search, output):
        resource = participant_id("resource", resource)
        consumer = participant_id("consumer", consumer)
        return {
            (resource, "available"): finite_set(available),
            (consumer, "search_requirements"): finite_set(search),
            (consumer, "output_requirements"): finite_set(output),
        }

    verified = 0
    for number, (available, search, output) in enumerate(cases):
        resource, consumer = "R1", f"Q{number}"
        facts = facts_for(resource, consumer, available, search, output)
        resource_binding = participant_id("resource", resource)
        consumer_binding = participant_id("consumer", consumer)
        grounded = evaluate_set_relation(rule, {"resource": resource_binding, "consumer": consumer_binding}, facts)
        expected = oracle_grounded_relation(resource_binding, consumer_binding, facts)
        assert grounded.predicate == "covers"
        assert grounded.participants == (resource_binding, consumer_binding)
        assert (grounded.predicate, grounded.participants, grounded.status) == (expected.predicate, expected.participants, expected.status), (available, search, output, grounded, expected)
        union = []
        for element in search + output:
            if element not in union:
                union.append(element)
        assert grounded.derived_value == finite_set(tuple(union))
        verified += 1

    # The same resource participates in two relations with two consumers.
    r1 = participant_id("resource", "R1")
    q1 = participant_id("consumer", "Q1")
    q2 = participant_id("consumer", "Q2")
    shared_facts = {
        (r1, "available"): finite_set(("a", "b", "c")),
        (q1, "search_requirements"): finite_set(("a",)),
        (q1, "output_requirements"): finite_set(("b",)),
        (q2, "search_requirements"): finite_set(("a",)),
        (q2, "output_requirements"): finite_set(("d",)),
    }
    assert evaluate_set_relation(rule, {"resource": r1, "consumer": q1}, shared_facts).status is True
    assert evaluate_set_relation(rule, {"resource": r1, "consumer": q2}, shared_facts).status is False
    verified += 1

    # Correct reference cases pass before each intentionally faulty interpretation.
    reference_facts = facts_for("R1", "Q3", ("a", "b"), ("a",), ("c",))
    assert evaluate_set_relation(rule, {"resource": r1, "consumer": participant_id("consumer", "Q3")}, reference_facts).status is False
    assert finite_set(("a", "b")) == finite_set(("b", "a"))

    # Omitting output or search requirements is a different, incorrect calculation.
    assert all(any(left == right for right in finite_set(("a", "b")).elements) for left in finite_set(("a",)).elements)
    assert evaluate_set_relation(rule, {"resource": participant_id("resource", "R2"), "consumer": participant_id("consumer", "Q4")}, facts_for("R2", "Q4", ("b",), ("a",), ())).status is False

    # Non-empty intersection and inverted inclusion are not subset.
    requirements = finite_set(("a", "c"))
    available = finite_set(("a", "b"))
    assert any(left == right for left in requirements.elements for right in available.elements)
    assert not all(any(left == right for right in available.elements) for left in requirements.elements)
    assert not all(any(left == right for right in requirements.elements) for left in available.elements)

    # Requirements belong to their own consumer; a mutant reusing Q1 for Q2 fails.
    assert evaluate_set_relation(rule, {"resource": r1, "consumer": q1}, shared_facts).status is True
    assert evaluate_set_relation(rule, {"resource": r1, "consumer": q2}, shared_facts).status is False

    # Two resources remain distinct too.
    r2 = participant_id("resource", "R2")
    multi_facts = {
        **shared_facts,
        (r2, "available"): finite_set(("a", "d")),
    }
    assert evaluate_set_relation(rule, {"resource": r2, "consumer": q1}, multi_facts).status is False
    assert evaluate_set_relation(rule, {"resource": r2, "consumer": q2}, multi_facts).status is True
    assert evaluate_set_relation(rule, {"resource": r2, "consumer": q2}, {
        key: value for key, value in multi_facts.items() if key[0] != r2
    }).status is UNKNOWN

    # Missing participant facts remain unknown, with no fallback to another participant.
    for participant, property_name in (("R3", "available"), ("Q3", "search_requirements"), ("Q3", "output_requirements")):
        incomplete = facts_for("R3", "Q3", ("a",), ("a",), ())
        participant_key = participant_id("resource", participant) if property_name == "available" else participant_id("consumer", participant)
        del incomplete[(participant_key, property_name)]
        grounded = evaluate_set_relation(rule, {"resource": participant_id("resource", "R3"), "consumer": participant_id("consumer", "Q3")}, incomplete)
        assert grounded.status is UNKNOWN
        assert grounded.participants == (participant_id("resource", "R3"), participant_id("consumer", "Q3"))

    # The same rule works with non-SQLite property vocabulary.
    machine_job_facts = {
        (participant_id("machine", "M1"), "capabilities"): finite_set(("cpu", "gpu")),
        (participant_id("job", "J1"), "required_core"): finite_set(("cpu",)),
        (participant_id("job", "J1"), "required_optional"): finite_set(("gpu",)),
    }
    generic_rule_data = {
        "id": "can_run",
        "participants": ["machine", "job"],
        "predicate": "can_run",
        "derived_name": "required",
        "derivation": {"kind": "set_union", "left": {"kind": "participant_property", "participant": {"kind": "participant_ref", "name": "job"}, "property": "required_core"}, "right": {"kind": "participant_property", "participant": {"kind": "participant_ref", "name": "job"}, "property": "required_optional"}},
        "relation": {"kind": "set_subset", "left": {"kind": "set_ref", "name": "required"}, "right": {"kind": "participant_property", "participant": {"kind": "participant_ref", "name": "machine"}, "property": "capabilities"}},
    }
    generic_rule = set_relation_rule_from_data(generic_rule_data)
    generic_grounded = evaluate_set_relation(generic_rule, {"machine": participant_id("machine", "M1"), "job": participant_id("job", "J1")}, machine_job_facts)
    assert generic_grounded.predicate == "can_run"
    assert generic_grounded.participants == (participant_id("machine", "M1"), participant_id("job", "J1"))
    assert generic_grounded.status is True
    verified += 1

    # Host containers and ambiguous members do not define Atlas member identity.
    invalid_sources = [["a", "b"], "ab", {"a", "b"}, {"a": 1}, ((["a"],),), (True,), (1,), (1.0,), ("a", "a")]
    invalid_rejected = 0
    for source in invalid_sources:
        try:
            finite_set(source)
        except (TypeError, ValueError):
            invalid_rejected += 1
        else:
            raise AssertionError(f"invalid finite-set source was accepted: {source!r}")

    class HostObject:
        def __eq__(self, other):
            return True

        __hash__ = None

    class HostileString(str):
        def __eq__(self, other):
            return True

        def __hash__(self):
            return 0

    for hostile in (HostileString("x"), HostileString("Q1")):
        try:
            Atom("x", hostile)
        except TypeError:
            invalid_rejected += 1
        else:
            raise AssertionError("hostile string entered Atom")
        try:
            participant_id("resource", hostile)
        except TypeError:
            invalid_rejected += 1
        else:
            raise AssertionError("hostile string entered ParticipantId")

    # An otherwise valid, unused property is allowed by both the engine and
    # the oracle; validity is structural, not restricted to the rule's reads.
    unused_facts = dict(shared_facts)
    unused_facts[(r1, "unused_property")] = finite_set(("ignored",))
    assert evaluate_set_relation(rule, {"resource": r1, "consumer": q1}, unused_facts).status is True
    assert oracle_grounded_relation(r1, q1, unused_facts).status is True
    verified += 1

    class HostilePropertyId(str):
        def __eq__(self, other):
            return True

        def __hash__(self):
            return 0

    invalid_fact_environments = [
        {(r1, ""): finite_set(())},
        {(r1, True): finite_set(())},
        {(r1, 1): finite_set(())},
        {(r1, HostilePropertyId("available")): finite_set(())},
        {(object(), "available"): finite_set(())},
    ]
    for invalid_facts in invalid_fact_environments:
        for evaluator in (
            lambda environment: evaluate_set_relation(rule, {"resource": r1, "consumer": q1}, environment),
            lambda environment: oracle_grounded_relation(r1, q1, environment),
        ):
            try:
                evaluator(invalid_facts)
            except TypeError:
                invalid_rejected += 1
            else:
                raise AssertionError("invalid fact environment was accepted")

    assert Atom("x", "1") == Atom("x", "1")
    assert Atom("x", "1") != Atom("y", "1")

    try:
        finite_set((HostObject(),))
    except TypeError:
        invalid_rejected += 1
    else:
        raise AssertionError("custom host object entered finite set")

    assert finite_set((Atom("symbol", "1"),)) != finite_set((Atom("other", "1"),))

    class EvilAtom(Atom):
        def canonical_key(self):
            return ("symbol", "forged")

    class CanonicalKeyObject:
        def canonical_key(self):
            return ("symbol", "forged")

    for forged in (EvilAtom("symbol", "x"), CanonicalKeyObject()):
        try:
            finite_set((forged,))
        except TypeError:
            invalid_rejected += 1
        else:
            raise AssertionError("non-exact Atom-like object entered finite set")

    participant_invalid = [("ns", True), ("ns", 1), ("ns", 1.0), ("ns", HostObject())]
    for namespace, local_id in participant_invalid:
        try:
            participant_id(namespace, local_id)
        except TypeError:
            invalid_rejected += 1
        else:
            raise AssertionError("invalid participant identity was accepted")
    p1 = participant_id("resource", "same-looking")
    p2 = participant_id("resource", "other")
    assert p1 != p2
    assert evaluate_set_relation(rule, {"resource": p2, "consumer": q1}, {
        (p1, "available"): finite_set(("a",)),
        (q1, "search_requirements"): finite_set(("a",)),
        (q1, "output_requirements"): finite_set(()),
    }).status is UNKNOWN

    class FakeParticipantKey:
        def __eq__(self, other):
            return True

        def __hash__(self):
            return hash(("resource", "same-looking"))

    for fake_participant in (FakeParticipantKey(), True, 1, 1.0):
        try:
            evaluate_set_relation(rule, {"resource": r1, "consumer": q1}, {
                (fake_participant, "available"): finite_set(("a",)),
                (q1, "search_requirements"): finite_set(("a",)),
                (q1, "output_requirements"): finite_set(()),
            })
        except TypeError:
            pass
        else:
            raise AssertionError("invalid participant fact key was accepted")

    # The independent oracle rejects duplicate sources before calculation.
    try:
        oracle_set(("a", "a"))
    except ValueError:
        pass
    else:
        raise AssertionError("oracle accepted duplicate set source")

    # Invalid persisted expression shapes are rejected at load time.
    invalid_asts = [
        {"kind": "set_union", "left": ["a"], "right": {"kind": "set_ref", "name": "x"}},
        {"kind": "set_subset", "left": {"kind": "set_ref", "name": ["x"]}, "right": {"kind": "set_ref", "name": "y"}},
        {"kind": "set_ref", "name": "not valid"},
    ]
    for ast in invalid_asts:
        try:
            set_expression_from_data(ast)
        except (TypeError, ValueError):
            invalid_rejected += 1
        else:
            raise AssertionError(f"invalid persisted set AST was accepted: {ast!r}")

    persisted = json.loads((ROOT / "set_rules.json").read_text(encoding="utf-8"))["rules"][0]
    invalid_rules = []
    invalid_rules.append({**persisted, "participants": ["resource", "resource"]})
    invalid_rules.append({**persisted, "participants": ["resource"], "derived_name": "resource"})
    invalid_rules.append({**persisted, "derived_name": ["required"]})
    invalid_rules.append({**persisted, "derivation": {"kind": "set_union", "left": {"kind": "participant_property", "participant": {"kind": "participant_ref", "name": "ghost"}, "property": "search_requirements"}, "right": persisted["derivation"]["right"]}})
    invalid_rules.append({**persisted, "relation": {"kind": "set_subset", "left": {"kind": "set_ref", "name": "other"}, "right": persisted["relation"]["right"]}})
    for invalid_rule in invalid_rules:
        try:
            set_relation_rule_from_data(invalid_rule)
        except (TypeError, ValueError):
            invalid_rejected += 1
        else:
            raise AssertionError(f"invalid persisted relation rule was accepted: {invalid_rule!r}")

    print(f"finite-set rules persisted: 1; valid instances tested: {verified}; invalid inputs rejected: {invalid_rejected}; relations verified: {verified}")
    print("finite-set counter-tests detected: omitted-output, omitted-search, nonempty-intersection, inverted-subset, order-sensitive, participant-identity, cross-participant-properties, incomplete-input, invalid-member-domain, invalid-persisted-AST")
    print("finite-set verdict: SUPPORTED")


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
    run_set_checks()


if __name__ == "__main__":
    main()
