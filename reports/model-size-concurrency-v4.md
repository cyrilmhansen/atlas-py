# Corpus Miner V4 — model size versus concurrency

## Scope and frozen configuration

This experiment used the committed V4 harness without changing its prompt,
schema, validator, facets, Reference Context, or backend. The endpoint was
`http://192.168.1.188:8000`, API key `ABCD`, prompt `corpus-miner-v4`, default
Reference Context, and thinking off. The fixed 12-source regression set is
listed in `model-size-concurrency-v4/selection-manifest.json`; sources were
reused from the committed NIST, claims/questions stress, and question-semantics
experiments.

The server inventory exposed Qwen 0.8B, Qwen 9B DFlash, Qwen 27B, and several
35B-A3B variants. The 9B candidate was not executable: the server returned
HTTP 409 because its previous load failed with a missing `rope_theta`. The
35B-A3B `oQ4e-fp16-mtp` variant did answer requests. Its total parameter class
is 35B, but its active MoE class is approximately A3B; it is reported as a
separate compute class, not as a conventionally smaller dense model.

## Quality-gate results

| model | class | concurrency=1 | valid | claims | questions | gate |
|---|---|---:|---:|---:|---:|---|
| Qwen3.6-27B-oQ4e-fp16-mtp | dense 27B reference | 12/12 | 12 | 8 | 2 | reference |
| Qwen3.6-35B-A3B-oQ4e-fp16-mtp | MoE, 35B total / ~3B active | 11/12 | 11 | 6 | 3 | **QUALITY_FAIL** |
| Qwen3.5-0.8B-OptiQ-4bit | dense 0.8B | incomplete after first failure | 0 observed at stop | — | — | **QUALITY_FAIL** |
| Qwen3.5-9B-DFlash | dense 9B | not run | — | — | — | unavailable (HTTP 409 load failure) |

The reference run produced 118 observations, 8 claims and 2 questions. Its
question behavior matched the already known V4 controls: the unresolved
question and explicit evidence request were retained, while the locally
resolved and irrelevant-absence controls were suppressed. The known baseline
also omits questions from `python-heapq-open-questions`; that is a reference
limitation, not a newly introduced regression.

The A3B run was much faster, but failed the contract on the first fixture:
the unresolved question used `evidence_needed: []`, which the frozen validator
rejects. This is a material semantic/contract failure, so no concurrency
benchmark was run for that model. It also emitted additional claims on the
selected passages; these were not treated as a quality win without a complete
scope audit. The 0.8B run reached a 32,768-token completion on the first
fixture and failed validation; it was stopped rather than used for throughput.

## Throughput measurements

The fixed-suite reference `concurrency=1` run completed in 250.11 s, or 2.88
sources/min, with median request latency 15.49 s, p95 43.67 s, and aggregate
completion generation 38.06 tokens/s. This is the direct comparison run for
the selected quality set.

The prior committed 12-source NIST throughput baseline remains the operational
reference for concurrency: 27B concurrency 1 was 319.60 s and concurrency 2
was 399.63 s (speedup 0.80, efficiency 0.40). Concurrency 3 and 4 were
inconclusive. Those figures are not silently merged with the fixed quality
suite because the corpora differ.

| model | concurrency | wall time (s) | src/min | median latency (s) | speedup within run |
|---|---:|---:|---:|---:|---:|
| Qwen3.6-27B reference, fixed quality suite | 1 | 250.11 | 2.88 | 15.49 | 1.00 |
| Qwen3.6-27B reference, prior NIST baseline | 1 | 319.60 | 2.25 | 26.80 | 1.00 |
| Qwen3.6-27B reference, prior NIST baseline | 2 | 399.63 | 1.80 | 55.22 | 0.80 |

No smaller model passed the quality gate, therefore the protocol correctly
did not spend requests on concurrency 2–4 for a failed model. There is no
evidence here for a quality-qualified smaller parallel configuration.

## Interpretation

The experiment does not support the hypothesis that reducing model size is a
safe route to a parallel routine extractor. The A3B MoE has substantially
lower per-request latency and would be attractive on throughput alone, but it
failed an explicit V4 question contract. The 0.8B model failed even earlier
and showed pathological completion length. The 27B reference remains the only
quality-qualified configuration in this experiment, with concurrency 1 as its
operational default based on the prior measured regression at concurrency 2.

The results do not imply that more free RAM yields more throughput, nor that
the runtime performs continuous batching or request fusion. Client-side
concurrency and server-side batching remain distinct mechanisms. The exact
saturation curve for the failed or unavailable candidates is unknown.

## Recommended next experiment

Repair the server-side loading issue for the 9B model and repeat only its
concurrency-1 quality gate against this frozen 12-source set; do not benchmark
concurrency until it passes the same semantic contract.
