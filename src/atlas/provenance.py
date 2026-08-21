from collections.abc import Iterable

from .errors import ValidationError
from .identity import SourceId


def canonical_provenance(values: Iterable[SourceId]) -> tuple[SourceId, ...]:
    """Return the stable semantic representation of terminal provenance."""
    try:
        values = tuple(values)
    except TypeError as exc:
        raise ValidationError("provenance must be iterable") from exc
    if any(type(source) is not SourceId for source in values):
        raise ValidationError("provenance contains an invalid source identity")
    return tuple(sorted(set(values), key=lambda source: source.value))
