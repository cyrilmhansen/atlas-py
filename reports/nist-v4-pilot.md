# NIST DADS — Corpus Miner V4 pilot

## Configuration

- Corpus: 12 bounded entries from the NIST Dictionary of Algorithms and Data Structures (DADS).
- Model: `Qwen3.6-27B-oQ4e-fp16-mtp`.
- Prompt: `corpus-miner-v4`.
- Thinking: `off`.
- Streaming: yes.
- Reference Context SHA-256: `15b9ce1a268b666e6d31d4598ee79b95da3a68eca2eee2b49a88d1623b81ebab`.
- Acquisition manifest: `pilot_nist_v4/manifest.json`.
- Exact prompts: `reports/nist-v4-prompts/`.
- Raw response/debug artifacts: `reports/nist-v4-responses/`.
- Source texts supplied to the miner: `pilot_nist_v4/sources_md/`.

The source cleanup removed HTML tags, scripts/styles and repeated whitespace
mechanically. No related entry was followed and no external definition was
added. The numbered prompt source is the retained local text in each `.md`
fixture.

## Run summary

| Measure | Result |
|---|---:|
| Sources evaluated | 12 |
| Valid extractions | 12/12 |
| Invalid extractions | 0 |
| Observations | 143 |
| Claims | 8 |
| Hypotheses | 0 |
| Questions | 0 |
| Total duration | 315.38 s |
| Median duration | 26.54 s |
| Prompt tokens | 19,277 |
| Completion tokens | 12,372 |
| Total tokens | 31,649 |

The server supplied no `reasoning_tokens` field because thinking was disabled.
The saved response artifacts retain the complete usage objects returned by the
server.

## Selection

| Entry | Why selected |
|---|---|
| `binary-search` | Named search mechanism, precondition, complexity and overflow limitation. |
| `quicksort` | Named sort with variants, worst/typical complexity and implementation trade-offs. |
| `binary-search-tree` | Data structure with invariants, implementations and related structures. |
| `heap-sort` | Sort linked to heap representation, in-place property and primary references. |
| `data-structure` | Mostly definitional entry with examples, scope and associated operations. |
| `bit-vector` | Small representation-focused and potentially low-signal entry. |
| `search` | General concept with many specializations and related structures. |
| `breadth-first-search` | Graph mechanism with an explicit queue relationship. |
| `depth-first-search` | Graph mechanism with traversal ambiguity, aliases and historical references. |
| `counting-sort` | Restricted-universe precondition, multi-pass mechanism and alternatives. |
| `sort` | Formal contract, stability, memory/workload factors and terminology. |
| `histogram-sort` | Multi-pass mechanism with rank assumptions, memory and performance caveats. |

The intentionally awkward cases were `bit-vector` (small and sparse),
`depth-first-search` (multiple meanings and traversal timing), and
`histogram-sort` (long, notation-heavy and assumption-dependent).

## Per-source human audit

The following audit was performed after all 12 runs, using each retained source
and its saved response. “Good” means no material unsupported observation was
found in the sampled extraction; it does not mean every possible useful fact
was extracted.

| Source | Support | Important omission | Interpretation / question discipline | Facet pressure |
|---|---|---|---|---|
| `binary-search` | Good for sorted-input precondition, halving mechanism, linked-list caveat, overflow warning and references. | The source’s implementation links are captured as references rather than analysed. | Two claims are useful, but the array-vs-linked-list comparison is slightly broader than the cited text. No question was invented. | `property` carries both complexity and safety limitation. |
| `binary-search-tree` | Good coverage of invariant, variants, pointer implementation and references. | No material omission for this bounded entry. | Empty claims/questions is appropriate. | Several “part of/used in” relations fit `relation`. |
| `bit-vector` | All five observations are directly supported by the short source. | No material omission detected. | Correct low-signal behaviour: no claim/question. | Representation efficiency is expressed as `mechanism`/`property`, a mild ambiguity. |
| `breadth-first-search` | Queue implementation and level-order relation are directly supported. | No material omission for the entry. | Empty claims/questions is appropriate. | Queue usage is a relation/mechanism boundary. |
| `counting-sort` | Two-pass mechanism, small-distinct-key condition and comparisons are supported. | No material omission detected. | No unsupported claim/question. | “Counting sort is a kind of histogram sort” is represented as `relation`; acceptable locally. |
| `data-structure` | Definition, examples, redundancy and associated operations are supported. | The broad scope of “data structure” could use a sharper boundary, but the source itself is broad. | Empty claims/questions is appropriate. | Definition vs property is not always obvious. |
| `depth-first-search` | Both definitions, DFS alias, traversal timing ambiguity and references are supported. | No material omission detected. | Empty claims/questions is appropriate despite the source’s internal ambiguity. | `relation` is carrying specializations and related concepts; this is useful but heterogeneous. |
| `heap-sort` | Heap/extraction mechanism, complexity, in-place relation and references are supported. | No material omission detected. | Claims combine source observations but the phrase “modern standard implementation” is broader than the local wording and should be checked in future audits. | Historical attribution is appropriately `reference`; “tournament sort” is a term/alias boundary. |
| `histogram-sort` | Three passes, rank constraints, auxiliary arrays, memory/page-fault caveat and asymptotic qualification are mostly well captured. | No material omission detected. | Claim 1 compresses assumptions; claim 2 (“potentially fewer buckets”) is plausible but not explicitly established by the source and is the clearest over-generalisation in this run. No question was generated. | Formulae and distribution assumptions fit poorly into the current facet vocabulary. |
| `quicksort` | Pivot/partition/recursion, variants, complexity and references are supported. | No material omission detected. | Claims are useful; the dual-pivot memory explanation follows the source’s stated rationale but remains a local claim. | Variant/implementation distinction is carried by `relation`, `mechanism` and `property`. |
| `search` | Definition, specializations, related structures and references are supported. | No material omission detected. | Empty claims/questions is appropriate; the long relation list is source-grounded. | `relation` is under pressure from “specialization” vs “related to”. |
| `sort` | Contract, permutation property, stability mechanism and workload factors are supported. | No material omission detected. | Empty claims/questions is appropriate. | Formal property, historical note and reference are clearly different but all remain local facets. |

## Reference Context audit

The engineering Reference Context appears to have helped the model select
mechanisms, preconditions, complexity/performance information, representation
properties, limitations and primary references. The strongest examples are the
safe midpoint in `binary-search`, the linked-list cost distinction, the
auxiliary-array trade-off in `histogram-sort`, and the formal sorting contract.

No observation was accepted merely because it appeared in the Reference
Context. All accepted observations cite local numbered source lines. The
Reference Context was not inserted into any source text and did not create a
facet or ontology assignment.

## Recurring failure patterns

1. Claims can still widen a local statement into a familiar engineering
   comparison. The `binary-search` array comparison and the
   `histogram-sort` bucket-count comparison should not be treated as facts
   beyond this source.
2. `relation` is doing several jobs: specialization, alias/term relation,
   “used in”, and “related to”. This is semantic pressure, not a reason to
   modify facets during the pilot.
3. Formulae, asymptotic assumptions and probability/distribution conditions
   are representable as `property`, but the facet does not preserve their
   distinction by itself.
4. The model produced no questions. This is preferable to unsupported
   questions, but it means this corpus does not test recall of useful open
   questions strongly.

## Strongest successes

- `binary-search` retained both the sorted-input precondition and the integer
  overflow failure mode, including the safe midpoint alternative.
- `depth-first-search` preserved the source’s explicit ambiguity about when a
  vertex is considered relative to its children; it did not collapse that into
  one traversal contract.
- `histogram-sort` retained concrete multi-pass state, rank-function
  constraints, auxiliary storage and page-fault/memory limitations.
- `sort` retained a functional contract (ordered permutation) and the
  source’s stability construction rather than only extracting the name.
- `bit-vector` produced a small, source-proportional extraction with no
  fabricated claim or question.

## Strongest problems

- `histogram-sort` claim 2 should be treated as an unsupported or insufficiently
  qualified interpretation unless the source’s key-domain relationship is
  made explicit.
- `binary-search` claim 1 imports an array traversal comparison not stated in
  the bounded entry; it is a useful hypothesis at most.
- The current facets cannot distinguish a formal mathematical condition from
  an empirical performance observation without reading the statement and
  provenance.

## SEMANTIC PRESSURES

- **Facet ambiguity:** `relation` conflates specialization, alias, “used in” and
  “related to”.
- **Scope distinction:** an asymptotic bound, a workload condition and a
  machine/resource limitation all often land in `property`.
- **Source vs interpretation:** short claims can broaden a source fact while
  retaining valid evidence lines; provenance alone does not prove that the
  interpretation is sound.
- **Question provenance:** no questions were produced, so explicit-source
  question retention was not exercised by this corpus.
- **Synonym handling:** DADS exposes “also known as” and terminology history;
  these fit `term` or `reference` depending on wording.
- **Mechanism/representation:** heap, auxiliary array, queue and bit vector
  can be described as mechanisms, representations or relations to an
  algorithm, depending on the entry.
- **Local-vs-general claim pressure:** familiar statements about arrays,
  buckets or “modern standard” implementations can exceed the bounded entry.

These are observations for future work, not ontology promotions or facet
changes.

## Assessment and stop

V4 appears ready for a larger, still bounded real corpus only with continued
human audit of claims and source scope. The 12-entry pilot demonstrates useful
bounded extraction, strong locator discipline and proportionate low-signal
behaviour, but it does not establish reliable automatic interpretation.

### One next experiment

Run a second fixed corpus containing explicitly comparative and explicitly
questioned technical entries, then measure claim support and question recall
under the unchanged V4 configuration. Do not broaden the crawler or alter the
facets as part of that experiment.

## Source inventory

The exact URLs, retrieval dates, selection rationales and SHA-256 hashes are in
`pilot_nist_v4/manifest.json`. The entries are NIST DADS pages, including
[binary search](https://xlinux.nist.gov/dads/HTML/binarySearch.html),
[quicksort](https://xlinux.nist.gov/dads/HTML/quicksort.html),
[breadth-first search](https://xlinux.nist.gov/dads/HTML/breadthfirst.html),
[depth-first search](https://xlinux.nist.gov/dads/HTML/depthfirst.html),
[counting sort](https://xlinux.nist.gov/dads/HTML/countingsort.html), and
[sort](https://xlinux.nist.gov/dads/HTML/sort.html).
