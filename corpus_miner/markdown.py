import re

from .models import NumberedSource, ValidatedExtraction


def markdown_filename(source_id: str, content_hash: str) -> str:
    """Return the stable, filesystem-safe filename for one source version."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", source_id).strip("-._")
    return f"{safe or 'source'}--{content_hash[:12]}.md"


def render(source: NumberedSource, extraction: ValidatedExtraction, backend: str, model: str | None,
           output_name: str, locator: str | None = None) -> str:
    lines = [f"# Corpus entry: {source.source_id}", "", f"- content hash: `{source.content_hash}`",
             f"- locator: `{locator or 'n/a'}`", f"- backend: `{backend}`", f"- model: `{model or 'n/a'}`", "", "## Observations", ""]
    if extraction.observations:
        for obs in extraction.observations:
            lines += [f"### {obs['key']} — {obs['facet']}", "", obs["statement"], "",
                      f"Source lines: L{obs['start_line']}–L{obs['end_line']}", ""]
    else:
        lines += ["_None._", ""]
    lines += ["## Claims", ""]
    for claim in extraction.claims:
        refs = ", ".join(claim["supported_by"])
        lines += [f"- **{claim['status']}** {claim['statement']} _(supported by: {refs})_", ""]
    if not extraction.claims:
        lines += ["_None._", ""]
    lines += ["## Questions", ""]
    for question in extraction.questions:
        refs = ", ".join(question.get("derived_from", [])) or "none"
        lines += [f"- **Question:** {question['question']}", f"  - Reason: {question['reason']}",
                  f"  - Evidence needed: {question['evidence_needed']}", f"  - Derived from: {refs}", ""]
    if not extraction.questions:
        lines += ["_None._", ""]
    return "\n".join(lines) + "\n"
