PROMPT_VERSION = "corpus-miner-v1"


def build_prompt(numbered_source: str) -> str:
    return f"""You are extracting bounded local knowledge for Atlas.
Use only the numbered source below for SOURCE FACTS. Do not silently complete it
with pretrained knowledge. Unsupported ideas must be HYPOTHESIS or QUESTION.
Do not build an Atlas ontology or taxonomy. Preserve local vocabulary where a
translation would change meaning. Extract only useful distinctions, not a full
summary. Return JSON only, with schema_version 1 and keys observations, claims,
questions.

Every observation needs key, facet, statement, start_line, end_line. Claims must
have status DERIVED_INTERPRETATION or HYPOTHESIS and supported_by observation
keys. Questions need question, reason, evidence_needed, and derived_from keys.

SOURCE:
{numbered_source}
"""
