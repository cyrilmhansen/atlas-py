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
