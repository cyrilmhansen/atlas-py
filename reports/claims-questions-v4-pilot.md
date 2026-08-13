# Corpus Miner V4 — claims and questions stress pilot

## Scope

This is a fixed second real-corpus experiment against the committed V4
harness. No prompt, schema, facet, validator, Reference Context, or backend
was changed during acquisition or audit.

The corpus was selected before extraction. Selection rationale and semantic
pressure are retained in `claims_questions_v4_pilot/manifest.json`; they were
not sent to the model.

## Source inventory and selection rationale

| Fixture | Source / locator | Pressure selected before extraction |
|---|---|---|
| `rfc9110-safe-methods.md` | IETF RFC 9110, §9.2.1 | qualified comparison; implementation side effect exception; non-affirmation |
| `rfc9110-idempotent-retry.md` | IETF RFC 9110, §9.2.2 | conditional retry conclusion; intended-vs-incidental effect distinction |
| `sqlite-index-statistics.md` | SQLite Query Planning, §§1.5–1.6 | competing indexes; statistics-conditioned choice |
| `sqlite-or-union.md` | SQLite Query Planning, §1.8 | competing mechanisms; missing-index fallback; future possibility |
| `sqlite-indexed-sort.md` | SQLite Query Planning, §§2.1–2.3 | competing plans; similar asymptotic work; storage trade-off |
| `python-sort-stability.md` | Python Sorting Techniques | stable/in-place comparison; compositional guarantee |
| `python-heapq-merge.md` | Python `heapq` documentation | streaming versus materialised alternatives; size-conditioned choice |
| `python-heapq-open-questions.md` | Python `heapq`, Priority Queue Implementation Notes | explicit open questions; tie-breaking evidence and constraints |
| `cpp-stable-sort.md` | cppreference, `std::stable_sort` | standard-library guarantee; preconditions and local scope |
| `sqlite-concurrency.md` | SQLite FAQ 5 | embedded versus client/server comparison; workload qualification |
| `sqlite-dynamic-typing.md` | SQLite FAQ 2–3 | explicit question; apparent contradiction; exception |
| `sqlite-explain-evidence.md` | SQLite Requirement Matrix, EXPLAIN | explicit evidence-to-requirement relation |

The corpus contains 5 comparison/choice passages, 2 explicit-question
passages, one explicit evidence relation, and several exception or conditional
passages. It deliberately mixes RFC, standards-reference, and implementation
documentation families.

## Frozen configuration

- prompt: `corpus-miner-v4`
- model: `Qwen3.6-27B-oQ4e-fp16-mtp`
- endpoint: `http://192.168.1.188:8000`
- thinking: off
- streaming: on for observability only
- Reference Context: default
- Reference Context SHA-256: `15b9ce1a268b666e6d31d4598ee79b95da3a68eca2eee2b49a88d1623b81ebab`
- extraction prompts: `reports/claims-questions-v4-prompts/`
- response telemetry: `reports/claims-questions-v4-responses/`

The endpoint returned HTTP 200 for `/v1/models` and exposed the requested
model. The 12 local source hashes are recorded in the manifest.

## Aggregate extraction metrics

| Metric | Result |
|---|---:|
| selected passages | 12 |
| valid extractions | 12/12 |
| observations | 73 |
| claims | 2 |
| hypotheses | 0 |
| questions emitted | 0 |
| prompt tokens | 11,662 |
| completion tokens | 5,534 |
| total tokens | 17,196 |
| reasoning tokens | n/a (thinking off) |

The absence of claims on 11 of 12 passages is not counted as a failure: those
passages could be represented as source observations without an additional
interpretation. The absence of questions is audited separately below because
five source question forms were deliberately included.

## Claim audit

### `sqlite-indexed-sort.md`

#### Claim 1 — `SUPPORTED_DERIVATION`

> SQLite's query planner selects between index-based retrieval and sorting
> based on estimated total time, which is influenced by table size and
> WHERE-clause constraints, despite both methods having similar asymptotic
> complexity (N log N).

Supported by the passage's explicit statements that both alternatives can
require N log N work, that SQLite estimates total time, and that table size
and WHERE constraints affect the choice. The claim is a faithful compression
of those linked observations.

#### Claim 2 — `TOO_BROAD`

> Index-based ORDER BY is preferred over sorting primarily for reduced
> temporary storage usage, as it avoids accumulating the entire result set,
> whereas covering indices offer further cost reduction by eliminating rowid
> lookups.

The source supports less temporary storage and the covering-index reduction,
but says the planner's choice can depend on table size and constraints and
only says the indexed sort would *generally* probably be chosen. The semantic
jump is:

```text
less temporary storage is one stated advantage
→ temporary storage is the primary reason for preference
```

The first clause therefore overstates the decision rule. This is a smaller
scope-broadening failure than in the first NIST pilot, but it is the same
failure mechanism.

No unsupported claims were emitted for the other 11 passages.

## Question audit

No questions were produced. The following source questions were expected to
remain conservable under V4's explicit-source rule:

| Fixture | Source question | Audit |
|---|---|---|
| `python-heapq-open-questions.md` | How do equal-priority tasks preserve insertion order? | `IMPORTANT_OMISSION` |
| `python-heapq-open-questions.md` | How does tuple comparison behave for equal priorities and non-comparable tasks? | `IMPORTANT_OMISSION` |
| `python-heapq-open-questions.md` | If a task priority changes, how is it moved in the heap? | `IMPORTANT_OMISSION` |
| `python-heapq-open-questions.md` | How is a pending task found and removed? | `IMPORTANT_OMISSION` |
| `sqlite-dynamic-typing.md` | What datatypes does SQLite support? | `IMPORTANT_OMISSION` |

These are not merely questions invented by the auditor: they appear as
question forms in the selected source. The heapq passage answers them in the
same excerpt, but V4 explicitly permits retaining source-explicit questions
with `derived_from: []`; the run did not exercise that behavior successfully.

The SQLite EXPLAIN passage contains an `EVIDENCE-OF` requirement, not an
explicit request phrased as `Evidence needed:`. Consequently there is no
valid preservation case for the `evidence_needed` field in this corpus. That
boundary remains untested rather than failed.

No `USEFUL_DERIVED` question was required for a passage whose source supplied
no unresolved decision. In particular, the passages that only state a local
guarantee, precondition, or mechanism did not need a generated question.

## Facet pressure

The run used the frozen facets without validation errors. `property` and
`relation` remain semantically broad: for example, planner preference,
algorithmic equivalence, and workload qualification can all be represented
with nearby facet choices. This is a classification inconvenience, not a
demonstrated loss of source information. No facet protocol change is justified
by this run.

## Successful restraint

The model preserved the absence of claims across RFC method semantics, Python
sorting/heap behavior, C++ preconditions, SQLite concurrency, dynamic typing,
EXPLAIN evidence, and the OR-by-UNION limitation. It did not turn every
comparison or future possibility into a generalized claim. It also did not
invent claims from the default Reference Context.

## Recurring failure mechanisms

1. **Scope broadening recurs once.** A conditional cost-planner statement was
   compressed into a stronger “preferred primarily” rule.
2. **Question production remains absent.** The first NIST pilot emitted zero
   questions, and this deliberately question-heavy corpus also emitted zero.
   This is now a reproducible V4 weakness, not an accidental absence of
   question-shaped material.
3. **Explicit evidence preservation was not exercised.** The corpus included
   an evidence relation, but not a literal `Evidence needed:` field, so this
   remains an experimental gap.

The recurring patterns do not justify changing V4 in this experiment: the
instruction was to keep the harness frozen, and the evidence is now sufficient
to define a focused next experiment.

## Confirmed / Disproved / Unknown

### Confirmed

- V4 validates all 12 bounded real-source extractions.
- V4 can preserve a strong observation-only output when no additional claim is
  needed.
- V4 can produce a supported derived claim from linked conditional
  observations.
- Facet pressure is visible without demonstrated information loss.

### Disproved

- The assumption that a question-heavy source will cause V4 to preserve
  explicit questions was not supported; this run produced none.
- A claim's source support does not by itself prevent a stronger preference
  formulation (`TOO_BROAD`).

### Unknown

- Whether the question omission is caused by model restraint, prompt policy, or
  a validator/serialization interaction.
- Whether literal `Evidence needed:` text is preserved into `evidence_needed`.
- Whether a constrained question-only evaluation would improve recall without
  increasing unjustified derived questions.

## Conclusion

V4 remains unchanged. The experiment establishes a real stress boundary for
claims and questions, but it does not justify V5 yet: the next step should
isolate question/evidence behavior rather than alter the extraction contract
based on this mixed corpus.

## One recommended next experiment

Run a new fixed, non-production evaluation using the unchanged V4 harness on
paired passages with a source-explicit question and an explicit `Evidence
needed:` field, plus matched passages with no question. Audit recall and false
question emission separately. Do not mix that test with a new facet design or
claim policy.
