"""Optional LLM cross-check baseline (B6 in docs/RESEARCH_EVALUATION.md).

TAARR's own outcome is always produced by the deterministic resolver in
reasoning.py. This module never feeds into that resolver and never changes a
TAARR outcome. It exists only so a user can ask an independent large language
model (Gemini) to read the same clause text and entity facts and answer the
same four-outcome question on its own, then compare that answer against
TAARR's result and against the benchmark's gold label.

This is NOT a substitute for the project's required human two-person
verification (docs/ANNOTATION_PROTOCOL.md). An LLM can be wrong, inconsistent
across runs, or miss a clause nuance. Treat agreement as a weak, convenient
signal -- not proof of legal correctness -- and always state that plainly
wherever these results are shown.

No API key is ever stored, logged, or written to any file by this module. The
caller supplies the key per call and it is forwarded directly to Google's API
over HTTPS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from .catalog import Catalog
from .models import Outcome

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_TIMEOUT_SECONDS = 30.0

_OUTCOME_LABELS = [outcome.value for outcome in Outcome]


class HttpClient(Protocol):
    """Minimal shape of httpx.Client, so tests can pass a fake."""

    def post(self, url: str, *, json: dict[str, Any], params: dict[str, str], timeout: float) -> Any: ...


@dataclass(frozen=True)
class LlmClassification:
    outcome: str | None
    raw_text: str
    error: str | None = None


def build_prompt(
    *,
    clause_text: str,
    clause_summary: str,
    clause_id: str,
    source_url: str,
    entity_profile: dict[str, Any],
    reference_date: date,
) -> str:
    """Build a prompt that asks the model to decide independently.

    The prompt deliberately never mentions TAARR's own outcome, so the
    model's answer is an independent read of the same source material --
    not a restatement of what the engine already said.
    """
    facts_lines = "\n".join(f"  - {key}: {value}" for key, value in sorted(entity_profile.items()))
    if not facts_lines:
        facts_lines = "  (no entity facts were supplied)"

    return f"""You are reviewing one regulatory clause from an official Indian RBI/SEBI
document. Decide, on your own reading of the clause text alone, whether the
obligation applies to the described entity on the given date.

Clause ID: {clause_id}
Source: {source_url}
Clause summary: {clause_summary}
Clause text:
\"\"\"
{clause_text}
\"\"\"

Reference date: {reference_date.isoformat()}
Entity facts:
{facts_lines}

Answer using exactly one of these four labels, and nothing else is allowed as
the label:
- Applicable
- Not applicable
- Indeterminate (use this if a fact you would need is missing from the entity
  facts above -- do not guess)
- Conflict (use this only if the clause text itself is self-contradictory)

Respond in exactly this format, two lines, nothing before or after:
LABEL: <one of the four labels above, verbatim>
REASON: <one sentence explaining your reasoning>"""


def parse_outcome(raw_text: str) -> str | None:
    """Pull one of the four exact outcome labels out of a model response."""
    text = raw_text.strip()
    for line in text.splitlines():
        if line.upper().startswith("LABEL:"):
            candidate = line.split(":", 1)[1].strip()
            for label in _OUTCOME_LABELS:
                if candidate.lower() == label.lower():
                    return label
    # Fallback: scan the whole response for an unambiguous single label.
    lowered = text.lower()
    hits = [label for label in _OUTCOME_LABELS if label.lower() in lowered]
    if len(hits) == 1:
        return hits[0]
    return None


def generate_text(
    *,
    api_key: str,
    model: str,
    payload: dict[str, Any],
    http_client: HttpClient,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[str | None, str | None]:
    """POST one generateContent request. Returns (text, None) or (None, error message)."""
    url = GEMINI_API_URL.format(model=model)
    try:
        response = http_client.post(url, json=payload, params={"key": api_key}, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 -- surface any transport error to the caller
        return None, f"Request failed: {exc}"
    if response.status_code != 200:
        return None, f"Gemini API returned HTTP {response.status_code}: {response.text[:300]}"
    try:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"], None
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return None, f"Unexpected Gemini response shape: {exc}"


def classify_with_gemini(
    *,
    api_key: str,
    obligation_id: str,
    catalog: Catalog,
    entity_profile: dict[str, Any],
    reference_date: date,
    model: str = DEFAULT_MODEL,
    http_client: HttpClient,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> LlmClassification:
    records = catalog.records_for_obligation(obligation_id)
    if not records:
        return LlmClassification(outcome=None, raw_text="", error=f"Unknown obligation_id {obligation_id!r}")
    record = max(records, key=lambda item: item.get("effective_from", ""))

    prompt = build_prompt(
        clause_text=record.get("clause_text", ""),
        clause_summary=record.get("clause_summary", ""),
        clause_id=record.get("clause_id", obligation_id),
        source_url=record.get("source_url", ""),
        entity_profile=entity_profile,
        reference_date=reference_date,
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 200},
    }
    raw_text, error = generate_text(
        api_key=api_key, model=model, payload=payload, http_client=http_client, timeout=timeout
    )
    if raw_text is None:
        return LlmClassification(outcome=None, raw_text="", error=error)

    outcome = parse_outcome(raw_text)
    error = None if outcome is not None else "Could not parse a valid outcome label from the response"
    return LlmClassification(outcome=outcome, raw_text=raw_text, error=error)
