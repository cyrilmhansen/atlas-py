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
