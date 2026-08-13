"""Create the predeclared, paired question-semantics control corpus."""
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).parent
SOURCES = ROOT / "sources"

CASES = [
    {
        "id": "a1-unresolved",
        "pair": "A",
        "expected_question_state": "RETAIN",
        "expected_evidence_needed": None,
        "rationale": "Explicit question; the bounded passage gives no answer or result.",
        "text": """An ordered index is used to answer lookups.\n\nQuestion: Does rebuilding the index after each update preserve latency under sustained writes?\n\nThe implementation description does not report a latency measurement or a policy for sustained writes.""",
    },
    {
        "id": "a2-resolved",
        "pair": "A",
        "expected_question_state": "SUPPRESS",
        "expected_evidence_needed": None,
        "rationale": "Same question form, followed by a local answer and result.",
        "text": """An ordered index is used to answer lookups.\n\nQuestion: Does rebuilding the index after each update preserve latency under sustained writes?\n\nYes. In this implementation the index is rebuilt after each update, and the bounded workload test reports stable latency under sustained writes. The question is therefore resolved within this passage.""",
    },
    {
        "id": "b1-evidence-request",
        "pair": "B",
        "expected_question_state": "RETAIN",
        "expected_evidence_needed": "a benchmark varying batch size from 1 to 1024 under the sustained-write workload",
        "rationale": "Unresolved question with a literal Evidence needed request.",
        "text": """The implementation batches writes to reduce per-operation overhead.\n\nQuestion: At what batch size does batching become faster than one-by-one writes?\n\nEvidence needed: a benchmark varying batch size from 1 to 1024 under the sustained-write workload.""",
    },
    {
        "id": "b2-measurement-prose",
        "pair": "B",
        "expected_question_state": "OPTIONAL",
        "expected_evidence_needed": None,
        "rationale": "Matched measurement description in ordinary prose, with no evidence request or question.",
        "text": """The implementation batches writes to reduce per-operation overhead.\n\nA benchmark varying batch size from 1 to 1024 under the sustained-write workload measures where batching becomes faster than one-by-one writes. The passage does not report the measured transition point.""",
    },
    {
        "id": "c1-bounded",
        "pair": "C",
        "expected_question_state": "SUPPRESS",
        "expected_evidence_needed": None,
        "rationale": "Bounded technical statement with no missing decision-relevant information.",
        "text": """The copy routine uses 64-bit words when both source and destination are 8-byte aligned.

For unaligned inputs it uses the generic byte path.

The two paths preserve the same byte sequence.""",
    },
    {
        "id": "c2-irrelevant-absence",
        "pair": "C",
        "expected_question_state": "SUPPRESS",
        "expected_evidence_needed": None,
        "rationale": "One implementation detail is absent, but the absence has no stated consequence for the bounded behavior.",
        "text": """The lookup routine returns the first matching record from the ordered index.

The passage does not specify which storage allocator backs the index.

That allocator detail does not affect the lookup order, returned record, or stated preconditions in this bounded description.""",
    },
]


def main() -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    manifest = []
    for case in CASES:
        path = SOURCES / f"{case['id']}.md"
        path.write_text(case["text"] + "\n", encoding="utf-8")
        manifest.append({
            "id": case["id"],
            "pair": case["pair"],
            "expected_question_state": case["expected_question_state"],
            "expected_evidence_needed": case["expected_evidence_needed"],
            "rationale": case["rationale"],
            "local_path": str(path),
            "content_hash": sha256(path.read_bytes()).hexdigest(),
        })
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"created {len(manifest)} fixed fixtures")


if __name__ == "__main__":
    main()
