"""Internal, deterministic grounding evidence.

This is an integrity witness for accidental structural substitution.  It is
not a cryptographic signature or an authorization mechanism.
"""

import hashlib
import json
from collections.abc import Mapping

from .errors import ValidationError
from .identity import DescriptionId, KnowledgeId, SourceId
from .model import (AmbiguousRead, EvaluationTruth, GroundedConclusion,
                    GroundingResult, MissingRead)
from .provenance import canonical_provenance


def _text(value, label):
    if type(value) is not str or not value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValidationError(f"{label} must be exact non-empty text")
    return value


def _id(value, cls, label):
    if type(value) is not cls:
        raise ValidationError(f"{label} has an invalid identity domain")
    return ("id", cls.__name__, _text(value.value, label))


def _scope(scope):
    if type(scope) is str:
        return ("scope", "one", _text(scope, "scope"))
    if type(scope) is tuple and all(type(x) is str for x in scope):
        return ("scope", "many", tuple(_text(x, "scope") for x in scope))
    raise ValidationError("invalid scope for grounding evidence")


def _bindings(bindings, participants):
    if not isinstance(bindings, Mapping) or tuple(bindings) != tuple(participants):
        raise ValidationError("grounding bindings are not in rule participant order")
    return tuple((name, _id(bindings[name], DescriptionId, "binding")) for name in participants)


def _dependencies(values):
    if type(values) is not tuple or any(type(x) is not KnowledgeId for x in values):
        raise ValidationError("invalid evidence dependencies")
    return tuple(_id(x, KnowledgeId, "dependency") for x in values)


def _missing(read):
    if type(read) is not MissingRead:
        raise ValidationError("invalid missing read")
    return ("missing", _text(read.participant, "participant"),
            _id(read.description, DescriptionId, "description"),
            _id(read.property, type(read.property), "property"), _text(read.version, "version"))


def _ambiguous(read):
    if type(read) is not AmbiguousRead:
        raise ValidationError("invalid ambiguous read")
    return ("ambiguous", _text(read.participant, "participant"),
            _id(read.description, DescriptionId, "description"),
            _id(read.property, type(read.property), "property"), _text(read.version, "version"),
            _dependencies(read.knowledge_ids))


def _conclusion(conclusion):
    if conclusion is None:
        return None
    if type(conclusion) is not GroundedConclusion:
        raise ValidationError("invalid grounding conclusion")
    term = conclusion.term
    return ("conclusion",
            _id(term.predicate, type(term.predicate), "predicate"), _text(term.version, "predicate version"),
            ("participants", tuple(_id(x, DescriptionId, "participant") for x in term.participants)),
            ("polarity", _text(conclusion.polarity, "polarity")),
            ("epistemic_status", _text(conclusion.epistemic_status, "epistemic status")),
            _scope(conclusion.scope),
            ("provenance", tuple(_id(x, SourceId, "provenance") for x in canonical_provenance(conclusion.provenance))),
            _id(conclusion.rule_id, type(conclusion.rule_id), "conclusion rule"),
            _text(conclusion.rule_version, "conclusion rule version"),
            _dependencies(conclusion.dependencies))


def canonical_grounding(result, participants=None):
    """Return the explicit primitive representation covered by the witness."""
    if type(result) is not GroundingResult:
        raise ValidationError("grounding evidence requires an exact GroundingResult")
    if participants is None:
        participants = tuple(result.bindings) if isinstance(result.bindings, Mapping) else ()
    return ("atlas-grounding-evidence-v1",
            _id(result.rule_id, type(result.rule_id), "rule"), _text(result.rule_version, "rule version"),
            ("bindings", _bindings(result.bindings, participants)),
            ("snapshot", _id(result.snapshot, type(result.snapshot), "snapshot")),
            ("context", _id(result.context, type(result.context), "context")),
            ("truth", result.truth.value if type(result.truth) is EvaluationTruth else result.truth),
            _conclusion(result.conclusion),
            ("effective_dependencies", _dependencies(result.effective_dependencies)),
            ("missing_reads", tuple(_missing(x) for x in result.missing_reads)),
            ("ambiguous_reads", tuple(_ambiguous(x) for x in result.ambiguous_reads)))


def digest(canonical):
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), default=list).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evidence_for(result, participants=None):
    return digest(canonical_grounding(result, participants))


def validate_grounding_evidence(result, participants=None):
    if type(result.grounding_evidence) is not str or result.grounding_evidence != evidence_for(result, participants):
        raise ValidationError("grounding evidence does not match grounding content")
