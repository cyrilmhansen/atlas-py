# Corpus Miner V4 — question semantics isolation pilot

## Objective and frozen boundary

This experiment isolates question semantics and `evidence_needed` without
changing Corpus Miner V4. The six fixtures were declared in pairs before the
model run; the manifest rationale was not included in any prompt.

Configuration:

- prompt: `corpus-miner-v4`
- model: `Qwen3.6-27B-oQ4e-fp16-mtp`
- endpoint: `http://192.168.1.188:8000`
- thinking: off
- Reference Context: default
- Reference Context SHA-256: `15b9ce1a268b666e6d31d4598ee79b95da3a68eca2eee2b49a88d1623b81ebab`
- streaming: enabled for observability only
- prompts: `reports/questions-evidence-v4-prompts/`
- responses: `reports/questions-evidence-v4-responses/`

The endpoint returned HTTP 200 and exposed the requested model. Final fixture
hashes and expectations are in `question_semantics_v4_pilot/manifest.json`.

## Controlled pairs and predeclared expectations

| Pair | Fixture | Expected question state | Expected evidence |
|---|---|---|---|
| A | `a1-unresolved` | `RETAIN` | none declared |
| A | `a2-resolved` | `SUPPRESS` | none |
| B | `b1-evidence-request` | `RETAIN` | `a benchmark varying batch size from 1 to 1024 under the sustained-write workload` |
| B | `b2-measurement-prose` | `OPTIONAL` | none |
| C | `c1-bounded` | `SUPPRESS` | none |
| C | `c2-irrelevant-absence` | `SUPPRESS` | none |

Pair A changes whether the explicit question is locally answered. Pair B
changes a literal evidence request into ordinary measurement prose. Pair C
tests bounded completeness and an irrelevant omission.

## Aggregate extraction metrics

| Metric | Result |
|---|---:|
| fixtures | 6 |
| valid extractions | 6/6 |
| observations | 17 |
| claims | 0 |
| hypotheses | 0 |
| questions emitted | 2 |
| prompt tokens | 5,408 |
| completion tokens | 1,490 |
| total tokens | 6,898 |
| reasoning tokens | n/a (thinking off) |

An initial local fixture construction error caused two invalid locators: the
negative-control sentences had accidentally been written on one line while
the model cited lines 2 and 3. The fixtures were corrected before the final
controlled run; the two corrected fixtures were rerun with the same frozen
configuration. No invalid response is retained as an experimental result.

## Per-fixture audit

| Fixture | Valid | Question emitted | Audit | Evidence audit |
|---|---|---:|---|---|
| `a1-unresolved` | yes | yes | `PASS` — unresolved source question retained | derived evidence suggestion is appropriate; no source evidence was falsely asserted |
| `a2-resolved` | yes | no | `PASS` — locally resolved question suppressed | none invented |
| `b1-evidence-request` | yes | yes | `PASS` — unresolved question retained | exact requested text preserved |
| `b2-measurement-prose` | yes | no | `PASS` — ordinary measurement prose did not become a question | no `evidence_needed` invented |
| `c1-bounded` | yes | no | `PASS` — bounded statement remained observation-only | none |
| `c2-irrelevant-absence` | yes | no | `PASS` — irrelevant absence did not generate a question | none |

### Produced question: `a1-unresolved`

```json
{
  "question": "Does rebuilding the index after each update preserve latency under sustained writes?",
  "reason": "Determining whether this specific update strategy maintains performance characteristics is necessary to evaluate the mechanism's suitability for write-heavy workloads.",
  "evidence_needed": "Latency measurements or policy details regarding sustained writes.",
  "derived_from": ["obs_2"]
}
```

This is an `UNRESOLVED_SOURCE_QUESTION`. The evidence text is a derived
request for information, not a claim that such measurements exist.

### Produced question: `b1-evidence-request`

```json
{
  "question": "At what batch size does batching become faster than one-by-one writes?",
  "reason": "Determining this threshold is necessary to select an optimal batch size for the sustained-write workload, distinguishing between regimes where batching provides a performance benefit versus those where it does not.",
  "evidence_needed": "a benchmark varying batch size from 1 to 1024 under the sustained-write workload",
  "derived_from": ["obs_batch_size_question", "obs_evidence_needed"]
}
```

The `evidence_needed` value preserves the literal source request exactly apart
from the surrounding JSON representation.

All complete response objects, including the four empty-question outputs, are
retained in the response directory. No claims were produced, so the known
claim scope-broadening pressure was not exercised here.

## Semantic classification

The audit distinguishes syntax from semantics:

- `a1-unresolved`: `UNRESOLVED_SOURCE_QUESTION`
- `a2-resolved`: `LOCALLY_RESOLVED_SOURCE_QUESTION`
- `b1-evidence-request`: `UNRESOLVED_SOURCE_QUESTION`
- `b2-measurement-prose`: no source question form; no question required
- `c1-bounded`: no source question form; no question required
- `c2-irrelevant-absence`: no source question form and no consequence if unknown

The experiment therefore does not treat every question-shaped string as a
question that must survive extraction. Local resolution is a meaningful
suppression condition.

## Decision questions

1. **Does V4 reliably preserve unresolved explicit questions?** Yes in this
   controlled sample: 2/2 retained.
2. **Does V4 suppress locally resolved question forms?** Yes in this sample:
   Pair A2 was suppressed.
3. **Does literal `Evidence needed:` survive correctly?** Yes: B1 preserved
   the requested text exactly enough for the declared contract.
4. **Does V4 invent questions in matched negative controls?** No: B2, C1 and
   C2 emitted none.
5. **Is a V5 question-policy change justified?** No. This experiment supports
   the current V4 behavior for the tested distinction. The sample is small and
   does not establish robustness for partial answers, multiple questions, or
   contradictory evidence.

## Conclusion

The previous stress pilot's zero-question result was not sufficient evidence
of a V4 failure because its question forms were locally answered. This isolated
experiment shows that V4 can retain unresolved questions, suppress a locally
resolved question, preserve literal `evidence_needed`, and remain silent on
negative controls. V4 remains frozen.

## Unknown

- behavior for a partial answer leaving a decision-relevant gap;
- behavior for multiple explicit questions in one source;
- behavior when the literal evidence request conflicts with nearby prose;
- whether these results persist across a larger model/source distribution.
