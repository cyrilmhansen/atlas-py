# ChatJimmy backend experiment

## Configuration

- backend: oMLX OpenAI-compatible server at `http://192.168.1.188:8000`
- model: `Qwen3.5-0.8B-OptiQ-4bit`
- prompt: `corpus-miner-v4`
- Reference Context: default, SHA-256 recorded in `experiments/chatjimmy-atlas/regression-set.md`
- thinking: off
- Corpus Miner semantics, facets, validator and ontology: unchanged

## Quality

The initial unbounded Corpus Miner run was stopped after two fixtures because
`a1-unresolved.md` was invalid and `a2-resolved.md` generated 32,768 completion
tokens while remaining invalid. This is a decisive operational failure, not a
semantic pass.

A complete 12-fixture safety-capped run (`max_tokens=512`, experiment-local
only) produced 1/12 valid extractions. The 11 invalid responses were dominated
by truncated or malformed JSON; one also missed the required schema version and
one had a malformed observation. The single valid response (`quicksort.md`)
contained no claims and no questions. No reliable semantic audit of claims or
questions is possible from this run because the outputs did not pass the V4
contract gate.

Classification: **EXTRACTOR_FAIL**.

Strongest failure: output-contract reliability and unconstrained completion
behaviour, rather than evidence that the small model lacks all relevant domain
knowledge. The failure must not be converted into durable Atlas knowledge.

## Wall behaviour

The experiment-local bounded probe used four exact V4 prompts and
`max_tokens=256`:

| client concurrency | requests | wall seconds | requests/minute |
|---:|---:|---:|---:|
| 1 | 4 | 4.586 | 52.3 |
| 2 | 4 | 3.400 | 70.6 |
| 4 | 4 | 2.653 | 90.5 |

All four responses in each probe reached the cap, so these numbers describe a
bounded generation throughput probe, not successful extraction throughput.
They show client-side parallel requests can overlap on this server, but do not
prove server-side batching or explain its scheduler. The streaming probe also
returned server timing fields including TTFT, but no fixture-level TTFT was
retained by the unchanged Corpus Miner report format.

Fastest useful configuration observed: concurrency 4 for the bounded micro
probe. It is not a useful production extraction configuration because quality
failed.

## Scout role

Three candidate-only prompts were sent for existing Atlas frontier items:
claim scope, QuickDraw region conversion, and digital-line contracts. They
returned quickly (roughly 0.95–1.65 seconds each) but each response hit the
256-token cap. The outputs contained some relevant experiment ideas, but also
obvious generic drift: for example, the digital-line answer substituted HTTP
endpoint-policy examples for raster-line contracts, and the claim-scope answer
used an unsupported “superset” criterion. The region-conversion answer offered
candidate factors but included arbitrary threshold language.

Scout assessment: weak but non-zero candidate generation. It can be used only
as a cheap, non-authoritative challenger when every output is independently
verified; it is not a Corpus Miner extractor.

## Final role

**B — FAST_SCOUT, with a low-confidence qualification.** The speed is real on
short bounded requests, but the quality and contract failures prevent routine
extraction. A plausible architecture is many cheap candidate branches followed
by stronger-model harvest and verification. No ChatJimmy output is promoted to
durable knowledge by this experiment.

## Limits

The experiment does not establish a saturation curve, quality of the larger
models exposed by the server, or production throughput under successful long
extractions. The safety cap was necessary to complete a fixed quality table and
must not be mistaken for a V4 configuration change.
