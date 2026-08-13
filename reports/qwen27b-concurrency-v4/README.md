# Qwen3.6-27B client-side concurrency experiment

## Configuration

- model: `Qwen3.6-27B-oQ4e-fp16-mtp`
- runtime: oMLX OpenAI-compatible server
- prompt: `corpus-miner-v4`
- thinking: off
- Reference Context: default
- corpus: committed initial NIST V4 corpus (`pilot_nist_v4/sources_md`, 12 sources)
- implementation baseline: `ce4da0e` — bounded concurrent evaluation
- concurrency: independent client-side HTTP requests; not model batching

## Results

| concurrency | valid | wall time | sources/min | median latency | completion tokens | speedup | efficiency |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 12/12 | 319.60 s | 2.25 | 26.80 s | 12,390 | 1.00 | 1.00 |
| 2 | 12/12 | 399.63 s | 1.80 | 55.22 s | 12,329 | 0.80 | 0.40 |
| 3 | inconclusive | — | — | — | — | — | — |
| 4 | inconclusive | — | — | — | — | — | — |

The completed runs used the same sources, prompt version, model, default
Reference Context and thinking setting. Both completed runs preserved source
coverage, valid locators and valid output shape for all 12 fixtures. No
cross-fixture contamination was observed.

The `concurrency=2` run was slower than `concurrency=1`; its measured speedup
was below one. Attempts at 3 and 4 were disrupted by server restart/saturation
and were not treated as measurements. A later retry also encountered the
restart window and was stopped; it does not establish the exact saturation
curve.

## Conclusion

For Qwen3.6-27B on the current oMLX configuration and current Corpus Miner
workload, there is no evidence that client-side concurrency improves
throughput. `concurrency=1` remains the operational default.

This result does not claim that the server cannot batch internally. Client-side
concurrency is a different mechanism from server-side batching, and no
server-side scheduling or batching metrics were available in this experiment.
