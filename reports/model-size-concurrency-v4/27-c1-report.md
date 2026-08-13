# Corpus evaluation

- backend: `http://192.168.1.188:8000`
- model: `Qwen3.6-27B-oQ4e-fp16-mtp`
- prompt: `corpus-miner-v4`
- reference_context_sha256: `15b9ce1a268b666e6d31d4598ee79b95da3a68eca2eee2b49a88d1623b81ebab`
- thinking: `off`
- streaming: `no`
- concurrency: `1`

| Source | JSON/provenance | Observations | Claims | Hypotheses | Questions | Duration (s) | Prompt | Completion | Reasoning | Error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| a1-unresolved.md | yes | 2 | 0 | 0 | 1 | 9.902 | 896 | 247 | n/a |  |
| a2-resolved.md | yes | 3 | 0 | 0 | 0 | 7.617 | 914 | 209 | n/a |  |
| b1-evidence-request.md | yes | 3 | 0 | 0 | 1 | 11.113 | 904 | 352 | n/a |  |
| binary-search.md | yes | 20 | 2 | 0 | 0 | 38.366 | 1721 | 1566 | n/a |  |
| c2-irrelevant-absence.md | yes | 3 | 0 | 0 | 0 | 8.151 | 902 | 225 | n/a |  |
| histogram-sort.md | yes | 30 | 2 | 0 | 0 | 50.152 | 1850 | 2278 | n/a |  |
| python-heapq-merge.md | yes | 8 | 0 | 0 | 0 | 15.081 | 942 | 548 | n/a |  |
| python-heapq-open-questions.md | yes | 8 | 0 | 0 | 0 | 15.896 | 1016 | 555 | n/a |  |
| quicksort.md | yes | 15 | 2 | 0 | 0 | 32.402 | 1881 | 1298 | n/a |  |
| rfc9110-safe-methods.md | yes | 4 | 0 | 0 | 0 | 11.271 | 1003 | 332 | n/a |  |
| sort.md | yes | 13 | 0 | 0 | 0 | 27.730 | 2035 | 1066 | n/a |  |
| sqlite-indexed-sort.md | yes | 9 | 2 | 0 | 0 | 22.429 | 990 | 844 | n/a |  |

## Human audit

- unsupported fact?
- important omission?
- over-generalisation?
- useful question?
- ontology leakage?
