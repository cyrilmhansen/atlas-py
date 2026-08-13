from dataclasses import dataclass
from typing import Any


ALLOWED_FACETS = {"term", "mechanism", "precondition", "property", "relation", "reference", "other"}
ALLOWED_CLAIM_STATUSES = {"DERIVED_INTERPRETATION", "HYPOTHESIS"}


@dataclass(frozen=True)
class NumberedSource:
    source_id: str
    text: str
    lines: tuple[str, ...]
    content_hash: str


@dataclass(frozen=True)
class ValidatedExtraction:
    schema_version: int
    observations: tuple[dict[str, Any], ...]
    claims: tuple[dict[str, Any], ...]
    questions: tuple[dict[str, Any], ...]
