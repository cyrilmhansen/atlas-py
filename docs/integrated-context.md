# Integrated execution context (S1b.3)

`dispatch --context-plan PLAN.json` uses the existing context-plan/1 or /2
operator contract. No policy, prompt, journal, semantic, or archive schema changes
are needed. A plan may select REVIEW (TASK + exact Git DIFF), retained SOURCE PNG
tablets, and existing Rust or Python SEMANTIC queries. See the context-plan tests
for complete /2 examples. Executable authority remains explicit; composition
never discovers or starts additional services.

## Authority and execution

Before this slice, `PvcContextComposition` concatenated per-selection frames in
operator order. Now Workflow stages compositions with `_stage_integrated_context`
after accepted-prompt and repository-witness validation and before executor
preparation or durable RUN_STARTED publication. `PvcContextComposition` and
`PvcContextSelection` remain the input authority. `_StagedPvcContext.contributions`
is a typed, immutable view of staged contributions (`PvcContextContribution`),
not another accepted context format. Text and image authority still use the
existing authenticated, sealed descriptors and executor-private registry.

TASK is the exact accepted prompt body, including whitespace and line endings.
A selected review TASK must match it byte-for-byte; otherwise execution fails.
Without a review TASK, composition inserts the accepted body directly. The
original prompt, including authorization front matter, is also retained unchanged
at the start of the effective input. DIFF stays the exact review-package Git
patch, not a summary. SOURCE stays an image attachment with textual provenance;
SEMANTIC stays canonical authenticated query-result text, not SOURCE or semantic
truth. Missing DIFF is not synthesized: explicitly request REVIEW to obtain it.

## Canonical rules

- Render version: `Atlas integrated context / 1`.
- Categories: TASK, DIFF, SOURCE, SEMANTIC, always in that order.
- Within each category: plan member order, then requested tablet order. Images
  retain globally unique ordinals in that same category-ordered traversal.
- Repeated `(snapshotId, tabletId)` is rejected, including repeats across
  selections with different purposes. Equal bytes with distinct identities are
  retained; composition does not guess equivalence.
- Unselected categories say `not selected`. A selected empty diff is a present
  zero-byte contribution. Empty semantic results remain exact result documents.
  Unavailable observations and invalid inputs raise errors, never become empty
  categories. Semantic adapter errors retain their underlying exception cause.
- Each contribution retains selection reason, snapshot/tablet/artifact identity,
  media type, tablet and payload digests, exact byte count, source spans and PVC
  provenance. Semantic payloads retain query, executable authority, repository
  witness, and normalized result. Review provenance retains expected head and
  patch witness.
- Rendering reuses the authenticated tablet frame with explicit category and
  item headers. Delimiter newlines do not belong to payload bytes; digests and
  byte counts disambiguate literal delimiter-like content. No text is normalized,
  truncated, summarized or reserialized.
- Final bound: at most 64 slots (conservatively reserving one for accepted TASK),
  16 MiB aggregate selected payload plus accepted TASK, and 16 MiB rendered
  supplement. These bounds are checked before staging and after rendering.
  Existing per-query and PVC validation limits still apply. This is a fail-closed
  byte ceiling, not a token optimizer; it excludes the original prompt envelope
  and the separately bounded parent supplement. Oversize plans must select less.

## Inspection and compatibility

Existing `reports/contexts/<execution-id>.txt` contains the exact supplement;
`<execution-id>-effective.txt` contains the exact textual execution input.
`history` now exposes the existing context/effective paths and effective SHA-256
(relative to the workflow runtime directory). Image identities and digests are
in the supplement; image bytes remain authenticated attachments, not text.
The existing derived-context archive and effective-input digest bind these bytes
into session provenance and recovery. Recovery does not recompose context or
rerun semantic queries. Already-qualified archives retain their original bytes.

The standalone `PvcContextSelection` execution API and legacy staging helper keep
their v0 framing for compatibility. New integrated callers use a
`PvcContextComposition`, even for one selection. Executions without explicit PVC
input are unchanged. There is only one new integrated renderer, not a second
context-plan or service architecture.

## Dogfood scenario and next questions

`test_atlas_prompt_parser_change_reaches_execution_and_replay` installs this
repository's actual `tools/atlas_agent/prompt.py` in an authorized fixture patch
path, adds a preservation comment, requests a definition observation, dispatches
through a capturing Codex executor, and verifies exact TASK/patch/query/result,
repository witness, effective bytes and archive-only replay. Its semantic server
is deliberately fake: this qualifies composition, not Pyright correctness.
SOURCE is honestly unselected; the existing four-category integration test also
checks authenticated image transport. No production model or PVC rasterizer is
invoked by these tests.

Representative rendering (excerpt; payloads/provenance omitted here only):

```text
Atlas integrated context / 1
Context is authorized model input, not semantic truth.
Purpose: operator context plan
## TASK (1 contributions)
### TASK.1 origin=validated PVC tablet
Selection reason: patch review package
... exact task payload and PVC provenance ...
## DIFF (1 contributions)
### DIFF.1 origin=validated PVC tablet
Selection reason: patch review package
... exact Git patch, including +    # Preserve authorized task bytes. ...
## SOURCE (not selected)
## SEMANTIC (1 contributions)
### SEMANTIC.1 origin=validated PVC tablet
Selection reason: python semantic context
... atlas-python-semantic/1 query and definition result for corpus_miner/parser.py ...
```

First dogfood questions: are source images worth their context cost compared to
patch hunks; is repeated accepted TASK plus review provenance too verbose; what
byte ceiling is practically useful; and do explicit selections miss relevant
context? No new language-server observations, automatic selection, token-budget
optimization, Rust migration, or runtime redesign are part of this slice.
