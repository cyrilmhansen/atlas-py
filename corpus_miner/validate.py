import json
from typing import Any

from .models import ALLOWED_CLAIM_STATUSES, ALLOWED_FACETS, NumberedSource, ValidatedExtraction


class ValidationError(ValueError):
    pass


def parse_and_validate(raw: str, source: NumberedSource) -> ValidatedExtraction:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValidationError("schema_version must be 1")
    observations = value.get("observations", [])
    claims = value.get("claims", [])
    questions = value.get("questions", [])
    if not all(isinstance(x, list) for x in (observations, claims, questions)):
        raise ValidationError("observations, claims and questions must be arrays")

    obs_keys: set[str] = set()
    for obs in observations:
        if not isinstance(obs, dict):
            raise ValidationError("observation must be an object")
        required = {"key", "facet", "statement", "start_line", "end_line"}
        if not required <= obs.keys():
            raise ValidationError("observation missing required field")
        key = obs["key"]
        if not isinstance(key, str) or not key or key in obs_keys:
            raise ValidationError(f"invalid or duplicate observation key: {key!r}")
        if obs["facet"] not in ALLOWED_FACETS:
            raise ValidationError(f"invalid observation facet: {obs['facet']!r}")
        if not isinstance(obs["statement"], str) or not obs["statement"].strip():
            raise ValidationError("observation statement must be non-empty")
        start, end = obs["start_line"], obs["end_line"]
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start or end > len(source.lines):
            raise ValidationError(f"invalid source locator for {key}: {start!r}-{end!r}")
        obs_keys.add(key)

    for claim in claims:
        if not isinstance(claim, dict) or claim.get("status") not in ALLOWED_CLAIM_STATUSES:
            raise ValidationError("claim status must be DERIVED_INTERPRETATION or HYPOTHESIS")
        if not isinstance(claim.get("statement"), str) or not claim["statement"].strip():
            raise ValidationError("claim statement must be non-empty")
        refs = claim.get("supported_by")
        if not isinstance(refs, list) or not refs or not all(isinstance(x, str) and x in obs_keys for x in refs):
            raise ValidationError("claim has invalid supported_by references")

    for question in questions:
        if not isinstance(question, dict):
            raise ValidationError("question must be an object")
        for field in ("question", "reason", "evidence_needed"):
            if not isinstance(question.get(field), str) or not question[field].strip():
                raise ValidationError(f"question requires non-empty {field}")
        refs = question.get("derived_from", [])
        if not isinstance(refs, list) or not all(isinstance(x, str) and x in obs_keys for x in refs):
            raise ValidationError("question has invalid derived_from references")
    return ValidatedExtraction(1, tuple(observations), tuple(claims), tuple(questions))
