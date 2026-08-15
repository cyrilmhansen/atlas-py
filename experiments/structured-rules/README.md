# Structured Rules POC

## Question

Can the existing `Description / Relation / Fact` substrate carry the two
array axioms as persistent structured expressions, without creating a
description for every invocation or concrete array state?

## Representation

`rules.json` stores two generic rules. Terms are structured nodes of kind
`var`, `const` and `app`; applications contain a name and ordered arguments.
Rules contain a left-hand term, a right-hand term and structured `not_equal`
conditions. The state before the write is the variable `A`; the state after
the write is the nested expression `set(..., A)`. No concrete state is a
description in the rule representation.

The Python mechanism performs only term construction, substitution, repeated
variable consistency, tri-valued condition checking (`true`, `false`,
`unknown`) and rule instantiation. It contains
no array-specific dispatch. The separate oracle gives `get` and `set` their
ordinary concrete array semantics.

## Protocol and results

The runner instantiates both rules over three arrays, three indices and two
values. It checks every consequence against the independent oracle. It also
checks that the second rule is not applicable when `i == j`.

The falsification checks remove the inequality condition, use an ungrounded
premise, provide an unknown condition kind, reverse the input/output state in a
rule, attempt conflicting bindings for a repeated variable, and test that
distinct variables are not silently identified even when temporarily assigned
the same concrete value.

## Instrumentation

- generic concepts introduced: 3 term kinds, substitution, equality and one
  inequality premise;
- persisted rules: 2;
- concrete arrays: 3; indices: 3; values: 2;
- substitutions checked: 72;
- consequences verified: 54;
- counter-tests detected: 6 classes of error.

## Verdict

**SUPPORTED.** The two laws are persisted as structured data and instantiated
by a small generic mechanism. Variables and terms remain internal constituents
of a rule-bearing fact/expression; no new fundamental Atlas type is required
by this experiment.

The result is deliberately local. It does not establish a general theorem
prover, a complete constraint language, versioned state model, or a general
algebra of contracts. Term/Rule/NotEqual are currently a candidate structured
representation for Atlas knowledge; they are not yet integrated into the
`Description / Relation / Fact` corpus or kernel.

## Bisect-left postcondition extension

This second experiment tests only the observable postcondition of
`bisect_left`. `bisect_rules.json` persists one postcondition containing
structured comparisons, half-open `Interval` expressions and two universal
quantifiers. The law is stored once; concrete bindings are created only while
validating finite instances.

The generic extension adds `Interval`, `Comparison`, `Forall`, and a structured
predicate for environmental facts, plus tri-valued expression evaluation. It
has no knowledge of bisect, sorted arrays or Python.
An evaluator supplied by the runner gives opaque applications such as `get`,
`key` and `succ` their concrete meaning. A bound variable shadows an outer
binding only in its quantified body and does not alter the persisted rule.

`Forall` aggregates exactly as follows: any `false` makes the result `false`;
otherwise any `unknown` makes it `unknown`; otherwise it is `true`. This makes
the result independent of whether an unknown element is visited before or
after a false element. A non-boolean body or postcondition constraint is an
explicit error: only the identities `True`, `False` and `UNKNOWN` are accepted,
not merely values equal to them such as `0` or `1`. A domain must be an `Interval`; `[start,end)` is half-open,
`start == end` is empty and true, unknown bounds produce `unknown`, while
reversed or non-integer (including boolean) ground bounds are rejected.

The persisted postcondition includes the structured fact
`sorted_slice(a, lo, hi, key)`. Its applicability is true only when the
environment explicitly marks that slice as sorted, false when explicitly
marked non-sorted, and unknown when no fact is supplied. No mechanism proving
sortedness is introduced.

The independent oracle uses the normal `bisect_left` behavior on seven cases:
duplicates, `ip == lo`, `ip == hi`, non-zero `lo`, `hi < len(a)`, `lo == hi`,
including a non-empty `ip == hi` case, identity keys, and a non-trivial `len`
key.
The structured postcondition is checked against the oracle-provided `ip`.
The runner also verifies that an ungrounded interval/body is `unknown`, never
implicitly true.

Counter-tests cover weakening `<` to `<=`, weakening `>=` to `>`, extending an
interval by one element, an out-of-range `ip`, checking one passing element
instead of a universal property, bound-variable capture, both orders of
`unknown`/`false` aggregation, nested and successive reuse of `p`, invalid
intervals, explicit sortedness states, and strict rejection of non-boolean
values in quantified bodies and postconditions.

Instrumentation reports one persisted postcondition, seven concrete instances,
38 quantified elements visited, and seven verified postconditions. The narrow
verdict is **SUPPORTED**: finite universal quantification and explicit
applicability facts remain a small generic extension in this validation scope.
This does not establish a general theorem prover, symbolic quantifier
reasoning, a sortedness prover, or a complete contract language; integration
with `Description / Relation / Fact` remains untested.

## Ordered index-prefix extension

This third experiment persists one data-driven `OrderedPrefixRule` in
`prefix_rules.json`. Its inputs are an `OrderedSequence` of elements and an
order-independent collection of `Annotation` values associating an element
with a category. The rule data declares which categories are
continuing (`EQ`, `IN`, `IS`) and which are terminal range categories
(`GT`, `GE`, `LT`, `LE`). The engine traverses the actual sequence, stops at a
missing element or terminal category, and returns the maximal prefix. It does
not contain SQLite branches or hard-code those category sets.

Each element may have at most one applicable annotation. Duplicate annotations
are rejected with the same explicit error regardless of their input order.
Rule categories must be non-empty strings in lists, and the continuing and
terminal sets must be disjoint. Unknown annotation categories and unordered
sequence sources (`set` or `dict`) are rejected rather than normalized.
Category fields must be actual lists of non-empty strings; strings, sets,
dicts, non-text elements, and overlapping category sets are rejected.

The oracle is separate and intentionally concrete. Nine instances cover the
required gaps, suffixes, range stops, duplicate categories, different index
lengths, and full-prefix cases. The structured result is compared with the
oracle without creating a description for each possible prefix. Two sequences
with the same elements but different order produce different prefixes.

The falsification checks detect ignoring order, continuing after a gap or a
range, accepting a suffix without its left prefix, collapsing equality and
range categories, and treating reordered indexes as equivalent.

Instrumentation reports one persisted ordered-prefix rule, 13 valid instances,
11 invalid inputs rejected, and 13 verified prefixes. The narrow verdict is
**SUPPORTED**: an ordered sequence can remain an internal structured value and
a single rule can be applied to concrete sequences of different lengths. No
collection algebra or SQLite planner was introduced; richer symbolic
sequences and constraints beyond the uniqueness/category contract remain
outside this experiment.

## Finite-set relation extension

This fourth experiment persists one generic set relation in `set_rules.json`.
`FiniteSetValue` is a structured finite set of explicit `Atom` values;
`SetUnion` derives a required set and `SetSubset` evaluates the resulting
relation. The persisted rule declares participant bindings, a predicate, and
a head relation. It resolves `ParticipantProperty` values through
`(ParticipantId, property_id)` facts, then returns a `GroundedRelation` that
retains predicate, grounded participants, status, and derived set. It contains
no SQLite, index, query, column, or covering-index vocabulary.

Member identity is explicit: strings are converted to exact `Atom("symbol", s)`
payloads, while arbitrary Python objects, booleans, numbers, subclasses and
Atom-like objects are rejected. `Atom.kind` and `Atom.value` are exact `str`
values; canonical finite-set equality is based on sorted atom kind/payload pairs
and does not use host hashing for identity. Participant identity is likewise
carried by exact `ParticipantId(namespace, local_id)` values; facts are validated
as `(ParticipantId, property_id)` keys before any lookup and cannot be addressed
by arbitrary host objects. Order is not semantic and duplicate source members
are rejected. Missing participant facts return `unknown`, with no fallback to
another participant. The independent oracle validates its own raw input,
participant access, and grounded relation.

Ten valid instances cover the required empty, full, partial, false, and
reordered cases, including one resource evaluated against two consumers and
two resources evaluated against two consumers. Twenty-eight invalid inputs or
ASTs are rejected. The falsification checks cover omitted search or output
requirements, non-empty intersection mistaken for subset, inverted inclusion,
order sensitivity, participant identity, cross-participant property reuse,
incomplete facts, invalid member domains, and invalid persisted ASTs.

Instrumentation reports one persisted set-relation rule, ten valid instances,
twenty-eight invalid inputs rejected, and ten verified relations. The narrow verdict
is **SUPPORTED**: explicit finite-set members, participant-bound properties,
union, subset, and a derived relation are enough for this case without
pre-creating combinations or introducing a general collection algebra. Full
integration with `Description / Relation / Fact` remains untested.
