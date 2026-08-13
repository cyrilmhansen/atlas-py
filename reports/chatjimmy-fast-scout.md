# ChatJimmy fast Semantic Spider scout

## Scope and configuration

This is a non-authoritative scout experiment against the public ChatJimmy route only:

- endpoint: `https://chatjimmy.ai/api/chat`
- model: `llama3.1-8B`
- access: anonymous public route; no oMLX or private API backend
- extractor status retained from the previous experiment: **FAIL**
- scout status after re-audit: **FAST_SCOUT_MARGINAL**

Corpus Miner V4, its prompt, validator and facets were not modified. The scout
used four fixed Atlas tensions, with four sequential calls per tension. Each
raw prompt and response is retained under
`experiments/chatjimmy-public/scout/calls/`.

## Tensions and audit unit

The tensions were:

1. QuickDraw region representation lifecycle;
2. claim scope and justified derivation;
3. digital-line contracts from the Bresenham work;
4. cross-domain transfer around B1 intersection and `ordered_merge`.

The audit counted the three requested top-level candidate positions per call
(48 positions total). Nested examples were treated as elaboration of their
parent, not as independently useful discoveries. This conservative rule keeps
the count comparable when the model over-produced nested examples.

| tension | calls | candidates | useful | redundant | irrelevant | unsupported-but-testable | misleading |
|---|---:|---:|---:|---:|---:|---:|---:|
| region lifecycle | 4 | 12 | 0 | 4 | 4 | 4 | 0 |
| claim scope | 4 | 12 | 0 | 4 | 4 | 3 | 1 |
| digital-line contract | 4 | 12 | 0 | 3 | 5 | 2 | 2 |
| cross-domain transfer | 4 | 12 | 0 | 5 | 4 | 3 | 0 |
| **total** | **16** | **48** | **0** | **16** | **17** | **12** | **3** |

Useful candidate rate was **0/48 (0%)**. Misleading rate was **3/48
(6.25%)**. The model often restated the tension in generic research language,
but did not produce a source-grounded, non-redundant Atlas next step.

## Audit findings

The strongest region-lifecycle suggestion was to measure conversion cost and
reuse. That is sensible, but it is already present in the Atlas reservoir as
an open B2/B1 conversion question and as the measured, local B0-to-B1 result.
It is therefore **REDUNDANT**, not a newly useful discovery.

The strongest claim-scope suggestion was a controlled comparison of claims
that differ only in modality or scope. The existing claim-scope expedition
already identifies this as the next discriminating question. It is useful
research direction, but a restatement of retained knowledge rather than a new
scout contribution.

The cross-domain answers mostly proposed “synonymy”, “invariant”, or
“counterexample” tests without specifying a concrete invariant, source, or
observable outcome. The digital-line answers included unsupported generic
proposals and dubious implementation attributions. In particular, a suggestion
that OpenGL supplies a Bresenham implementation and suggestions to use random
or hashed tie-breaking are not supported by the supplied Atlas evidence and
were audited as misleading.

No scout suggestion was accepted as new Atlas knowledge. The two strongest
directions nevertheless lead to useful follow-up work if independently
executed: a real conversion lifecycle measurement, and a paired claim-scope
test. Neither was treated as validated by this scout.

## Latency and concurrency

The 16 sequential scout calls all returned HTTP 200. Mean latency was
0.342 s, with observed range 0.317-0.394 s. The fixed concurrency batch used
8 calls at each level:

| concurrency | wall seconds | successful | requests/s |
|---:|---:|---:|---:|
| 1 | 2.775 | 8/8 | 2.88 |
| 2 | 2.965 | 8/8 | 2.70 |
| 4 | 2.621 | 8/8 | 3.05 |
| 8 | 2.615 | 8/8 | 3.06 |

There were no HTTP failures or observable rate-limit errors in this small
batch. The apparent gain from 4/8 is too small and the batch is too short to
claim a scaling law; it only shows that this public endpoint tolerated the
fixed probe. This is client-side concurrency, not server-side batching.

## Classification and architectural consequence

The public ChatJimmy route is operationally usable as a very fast text scout,
but this run does not justify using it as an Atlas knowledge generator. Its
role should be limited to generating cheap, explicitly untrusted hypotheses
that require reservoir or authoritative-source verification. It must not feed
Corpus Miner V4 extraction, claim validation, ontologies, or durable knowledge
without a separate audit.

The extractor remains **FAIL** from the previous public-backend experiment;
this scout result does not repair or reinterpret that gate. No Corpus Miner V4
change is justified.

## Reproduction

```sh
PYTHONPATH=. python3 experiments/chatjimmy-public/run_fast_scout.py \
  experiments/chatjimmy-public/scout
```

The script uses only the public endpoint and stores the exact prompts and raw
responses. The prior `192.168.1.188` run remains invalid for identifying the
ChatJimmy backend and is not used here.

## Value re-audit of the unsupported bucket

No new ChatJimmy calls were made. The 12 candidates previously placed in
`UNSUPPORTED_BUT_TESTABLE` were re-read against the Atlas reservoir using
the operational test: would handing this item to a fresh Semantic Spider save
a meaningful research step?

| id | candidate summary | reclassification |
|---|---|---|
| R-1 | compare a B0-to-B1 conversion using a sparse-matrix representation with the existing conversion | **NOVEL_AND_DISCRIMINATING** |
| R-2 | investigate B1-to-B2 conversion using a sparse matrix | **GENERIC_BUT_TESTABLE** |
| R-3 | investigate B0-to-B2 conversion using a sparse matrix | **GENERIC_BUT_TESTABLE** |
| R-4 | accelerate B0-to-B1 with parallel processing or caching | **GENERIC_BUT_TESTABLE** |
| C-1 | test whether coffee/pastry association survives adjustment for other items | **GENERIC_BUT_TESTABLE** |
| C-2 | test whether a weekend interaction result survives holidays and atypical workweeks | **GENERIC_BUT_TESTABLE** |
| C-3 | test whether communication intimacy changes between casual, business and emergency contexts | **GENERIC_BUT_TESTABLE** |
| D-1 | use OpenCV/Pygame/OpenGL as implementation or source directions | **MISLEADING_AFTER_CHECK** |
| D-2 | compare alternative tie-breaking implementations | **GENERIC_BUT_TESTABLE** |
| X-1 | test transfer of an invariant between two domains | **GENERIC_BUT_TESTABLE** |
| X-2 | test transfer of a complexity property between two domains | **GENERIC_BUT_TESTABLE** |
| X-3 | test transfer of a variant or counterexample between two domains | **GENERIC_BUT_TESTABLE** |

Counts: **1 NOVEL_AND_DISCRIMINATING, 10 GENERIC_BUT_TESTABLE, 0
REDUNDANT_AFTER_CHECK, 1 MISLEADING_AFTER_CHECK**.

R-1 would create a new branch: implement or locate a sparse intermediate for
the exact B0 result, then measure conversion time, storage, and application
time against the existing B0-to-B1 path. The discriminating observation is
whether it preserves the Region while changing the conversion/application
trade-off. This branch is not in the current Atlas frontier, which records
the native B0-to-B1 path and open lifecycle questions but no sparse-matrix
alternative. It is a useful scout lead, not a validated engineering fact.

The remaining ten testable items are concrete enough to execute but do not
save a meaningful research step: they say to compare contexts, transfer a
generic invariant/property, or try a broad optimization without specifying a
new source, mechanism, or discriminating observable. D-1 is worse: the
response presents OpenGL as a Bresenham implementation/source direction
without evidence in the retained corpus, so the proposed direction is
materially misleading as stated.

The revised scout classification is **FAST_SCOUT_MARGINAL**. ChatJimmy can
occasionally save a stronger Spider a research step by naming a concrete
unexplored branch, but the yield here is 1/12 and the remaining output
requires substantial human filtering. It is not a reliable autonomous
frontier generator.
