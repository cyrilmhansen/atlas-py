from dataclasses import dataclass
from typing import Any

SCHEMA = "atlas-agent-workflow/1"
PROMPT_SCHEMA = "atlas-agent-prompt/1"
ACTIONS = {"implementation", "patch_review", "state_audit", "checkpoint"}
SESSIONS = {"fresh", "reuse"}

@dataclass(frozen=True)
class Prompt:
    raw: bytes
    sha256: str
    generation: int
    parent: int | str
    checkpoint: str
    action: str
    expected_head: str
    session_mode: str
    body: str

    @property
    def canonical_name(self) -> str:
        return f"g{self.generation:06d}-{self.sha256}.txt"

@dataclass(frozen=True)
class ResultEnvelope:
    generation: int
    prompt_sha256: str
    action: str
    outcome: str
    classification: str
    report_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"schema": "atlas-agent-result/1", "generation": self.generation,
                "prompt_sha256": self.prompt_sha256, "action": self.action,
                "outcome": self.outcome, "classification": self.classification,
                "report_path": self.report_path}
