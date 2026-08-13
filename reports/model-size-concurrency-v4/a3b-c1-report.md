# Corpus evaluation

- backend: `http://192.168.1.188:8000`
- model: `Qwen3.6-35B-A3B-oQ4e-fp16-mtp`
- prompt: `corpus-miner-v4`
- reference_context_sha256: `15b9ce1a268b666e6d31d4598ee79b95da3a68eca2eee2b49a88d1623b81ebab`
- thinking: `off`
- streaming: `no`
- concurrency: `1`

| Source | JSON/provenance | Observations | Claims | Hypotheses | Questions | Duration (s) | Prompt | Completion | Reasoning | Error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| a1-unresolved.md | no | 0 | 0 | 0 | 0 | 6.815 | 896 | 253 | n/a | question requires non-empty evidence_needed |
| a2-resolved.md | yes | 2 | 0 | 0 | 0 | 1.782 | 914 | 154 | n/a |  |
| b1-evidence-request.md | yes | 1 | 0 | 0 | 1 | 1.802 | 904 | 186 | n/a |  |
| binary-search.md | yes | 8 | 0 | 0 | 0 | 5.713 | 1721 | 690 | n/a |  |
| c2-irrelevant-absence.md | yes | 3 | 0 | 0 | 0 | 1.689 | 902 | 224 | n/a |  |
| histogram-sort.md | yes | 14 | 3 | 0 | 0 | 9.081 | 1850 | 1521 | n/a |  |
| python-heapq-merge.md | yes | 8 | 0 | 0 | 0 | 2.854 | 942 | 540 | n/a |  |
| python-heapq-open-questions.md | yes | 4 | 1 | 0 | 2 | 4.647 | 1016 | 568 | n/a |  |
| quicksort.md | yes | 10 | 2 | 0 | 0 | 7.252 | 1881 | 975 | n/a |  |
| rfc9110-safe-methods.md | yes | 4 | 0 | 0 | 0 | 2.439 | 1003 | 333 | n/a |  |
| sort.md | yes | 9 | 0 | 0 | 0 | 6.933 | 2035 | 782 | n/a |  |
| sqlite-indexed-sort.md | yes | 7 | 0 | 0 | 0 | 2.955 | 990 | 525 | n/a |  |

## Human audit

- unsupported fact?
- important omission?
- over-generalisation?
- useful question?
- ontology leakage?
