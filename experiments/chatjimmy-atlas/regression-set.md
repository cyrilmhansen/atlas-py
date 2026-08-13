# ChatJimmy regression-set identity

The fixed 12-fixture set is the same selection used by the committed model-size
comparison, not a new corpus:

- `binary-search.md`, `histogram-sort.md`, `quicksort.md`, `sort.md` from `pilot_nist_v4/sources_md`
- `python-heapq-merge.md`, `python-heapq-open-questions.md`, `rfc9110-safe-methods.md`, `sqlite-indexed-sort.md` from `claims_questions_v4_pilot/sources`
- `a1-unresolved.md`, `a2-resolved.md`, `b1-evidence-request.md`, `c2-irrelevant-absence.md` from `question_semantics_v4_pilot/sources`

Prompts use `corpus-miner-v4`, the default Reference Context, and thinking off.
The default Reference Context hash is
`15b9ce1a268b666e6d31d4598ee79b95da3a68eca2eee2b49a88d1623b81ebab`.

The first direct Corpus Miner run was intentionally unbounded and was stopped
after observing a 32,768-token completion on `a2-resolved.md`. The complete
quality table is the separate experiment-local run with an explicit
`max_tokens=512` safety cap; this cap is recorded because it is not a change to
Corpus Miner V4 and its results are not equivalent to an unbounded production
run.
