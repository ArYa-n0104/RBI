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

API usage: the cross-check sends ALL selected benchmark items to Gemini in a
single request (classify_batch_with_gemini), so one click is one API call no
matter how many items are checked. Each clause text is included once even if
several items share it.

No API key is ever stored, logged, or written to any file by this module.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from .catalog import Catalog
from .models import Outcome
from .settings import DEFAULT_MODEL, gemini_model

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
DEFAULT_TIMEOUT_SECONDS = 60.0
BATCH_TIMEOUT_SECONDS = 180.0
SUGGESTED_MODELS = "gemini-3.5-flash-lite, gemini-3.1-flash-lite, gemini-2.5-flash-lite"

_OUTCOME_LABELS = [outcome.value for outcome in Outcome]

__all__ = [
    "DEFAULT_MODEL",
    "LlmClassification",
    "build_batch_prompt",
    "build_prompt",
    "classify_batch_with_gemini",
    "classify_with_gemini",
    "default_model",
    "generate_text",
    "generation_config",
    "parse_outcome",
]


def default_model() -> str:
    """The model named by GEMINI_MODEL in .env (re-read on every call)."""
    return gemini_model()


class HttpClient(Protocol):
    """Minimal shape of httpx.Client, so tests can pass a fake."""

    def post(self, url: str, *, json: dict[str, Any], params: dict[str, str], timeout: float) -> Any: ...


@dataclass(frozen=True)
class LlmClassification:
    outcome: str | None
    raw_text: str
    error: str | None = None


def generation_config(model: str, *, max_output_tokens: int, **extra: Any) -> dict[str, Any]:
    """Build generationConfig that is safe for both old and new Gemini models.

    Gemini 3 and later ignore temperature and Google has said later models
    will reject it with HTTP 400, so it is only sent to 1.x / 2.x models.
    Newer models may also "think" before answering, and those thinking tokens
    come out of maxOutputTokens, so callers pass a generous budget; only the
    tokens actually used are billed.
    """
    config: dict[str, Any] = {"maxOutputTokens": max_output_tokens, **extra}
    if re.match(r"^gemini-[12](\.|-)", model):
        config["temperature"] = 0.0
    return config


def _friendly_http_error(status: int, body: str, model: str) -> str:
    return f"{_friendly_http_message(status, body, model)} (HTTP {status})"


def _friendly_http_message(status: int, body: str, model: str) -> str:
    lowered = body.lower()
    if status == 404 or "not found" in lowered:
        return (
            f"The model '{model}' does not exist or your key cannot use it. "
            f"Change GEMINI_MODEL in your .env to a valid model, for example {SUGGESTED_MODELS}. "
            "The .env file is re-read on every click, so just save it and try again."
        )
    if status == 429:
        return (
            f"Gemini's rate limit was reached for '{model}'. Wait about a minute and try again, "
            "or set GEMINI_MODEL in your .env to a different model "
            f"(for example {SUGGESTED_MODELS}) and click again — no restart needed."
        )
    if status in (400, 401, 403) and ("api key" in lowered or "api_key" in lowered or "permission" in lowered):
        return (
            "Google rejected the API key. Check GEMINI_API_KEY in your .env "
            "(get a key at https://aistudio.google.com/app/apikey)."
        )
    return f"Gemini API error: {body[:300]}"


def generate_text(
    *,
    api_key: str,
    model: str,
    payload: dict[str, Any],
    http_client: HttpClient,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[str | None, str | None]:
    """POST exactly one generateContent request. Returns (text, None) or (None, error).

    No retries: one call to this function is one API call.
    """
    url = GEMINI_API_URL.format(model=model)
    try:
        response = http_client.post(url, json=payload, params={"key": api_key}, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 -- surface any transport error to the caller
        return None, f"Could not reach Gemini: {exc}"
    if response.status_code != 200:
        return None, _friendly_http_error(response.status_code, response.text, model)
    try:
        candidate = response.json()["candidates"][0]
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return None, f"Unexpected Gemini response shape: {exc}"
    if not text.strip():
        reason = candidate.get("finishReason", "unknown")
        return None, f"Gemini returned no answer text (finish reason: {reason})."
    return text, None


# ---------------------------------------------------------------------------
# Single-item prompt (kept for the library API and its tests)
# ---------------------------------------------------------------------------


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
    lowered = text.lower()
    hits = [label for label in _OUTCOME_LABELS if label.lower() in lowered]
    if len(hits) == 1:
        return hits[0]
    return None


def _latest_record(catalog: Catalog, obligation_id: str) -> dict[str, Any] | None:
    records = catalog.records_for_obligation(obligation_id)
    if not records:
        return None
    return max(records, key=lambda item: item.get("effective_from", ""))


def classify_with_gemini(
    *,
    api_key: str,
    obligation_id: str,
    catalog: Catalog,
    entity_profile: dict[str, Any],
    reference_date: date,
    model: str | None = None,
    http_client: HttpClient,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> LlmClassification:
    """Classify ONE item with one API call. The API endpoint uses the batch version."""
    record = _latest_record(catalog, obligation_id)
    if record is None:
        return LlmClassification(outcome=None, raw_text="", error=f"Unknown obligation_id {obligation_id!r}")
    model = model or default_model()
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
        "generationConfig": generation_config(model, max_output_tokens=2048),
    }
    raw_text, error = generate_text(
        api_key=api_key, model=model, payload=payload, http_client=http_client, timeout=timeout
    )
    if raw_text is None:
        return LlmClassification(outcome=None, raw_text="", error=error)
    outcome = parse_outcome(raw_text)
    error = None if outcome is not None else "Could not parse a valid outcome label from the response"
    return LlmClassification(outcome=outcome, raw_text=raw_text, error=error)


# ---------------------------------------------------------------------------
# Batch: every item in ONE request
# ---------------------------------------------------------------------------


def build_batch_prompt(clauses: dict[str, dict[str, Any]], cases: list[dict[str, Any]]) -> str:
    """One prompt for many cases. Each clause appears once; cases point to it.

    Like the single prompt, it never contains TAARR's outcome or the gold label.
    """
    clause_blocks = []
    for key, record in clauses.items():
        clause_blocks.append(
            f"[{key}] {record.get('clause_id', '')} -- {record.get('instrument_title', '')}\n"
            f"Summary: {record.get('clause_summary', '')}\n"
            f"Text:\n\"\"\"\n{record.get('clause_text', '')}\n\"\"\""
        )
    case_blocks = []
    for case in cases:
        facts = case["entity_profile"]
        facts_text = (
            "; ".join(f"{key} = {json.dumps(value)}" for key, value in sorted(facts.items()))
            if facts else "(no entity facts were supplied)"
        )
        case_blocks.append(
            f"Case {case['case']}: clause [{case['clause_key']}], "
            f"reference date {case['reference_date']}, facts: {facts_text}"
        )
    clauses_text = "\n\n".join(clause_blocks)
    cases_text = "\n".join(case_blocks)
    return f"""You are reviewing regulatory clauses from official Indian RBI/SEBI documents.
For EVERY case below, decide on your own reading of the clause text whether the
obligation applies to the described entity on that case's reference date.

Use exactly one of these four labels per case:
- Applicable
- Not applicable
- Indeterminate (a fact you would need is missing from that case's facts -- do not guess)
- Conflict (only if the clause text itself is self-contradictory)

Judge each case only from its own facts. A fact that is not listed is unknown,
not false.

CLAUSES
{clauses_text}

CASES
{cases_text}

Return JSON only: {{"answers": [{{"case": <case number>, "label": "<label>", "reason": "<one sentence>"}}]}}
with one answer for every case."""


def _batch_schema() -> dict[str, Any]:
    return {
        "type": "OBJECT",
        "properties": {
            "answers": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "case": {"type": "INTEGER"},
                        "label": {"type": "STRING", "enum": _OUTCOME_LABELS},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["case", "label", "reason"],
                },
            }
        },
        "required": ["answers"],
    }


def classify_batch_with_gemini(
    *,
    api_key: str,
    items: list[dict[str, Any]],
    catalog: Catalog,
    http_client: HttpClient,
    model: str | None = None,
    timeout: float = BATCH_TIMEOUT_SECONDS,
) -> tuple[list[LlmClassification], str | None]:
    """Classify every item with ONE API call.

    Each item needs obligation_id, entity_profile and reference_date (a date).
    Returns one LlmClassification per item, in the same order, plus a
    request-level error (then every item carries that error too).
    """
    model = model or default_model()
    clauses: dict[str, dict[str, Any]] = {}
    clause_keys: dict[str, str] = {}
    cases: list[dict[str, Any]] = []
    results: list[LlmClassification | None] = [None] * len(items)

    for index, item in enumerate(items):
        obligation_id = item["obligation_id"]
        record = _latest_record(catalog, obligation_id)
        if record is None:
            results[index] = LlmClassification(None, "", f"Unknown obligation_id {obligation_id!r}")
            continue
        if obligation_id not in clause_keys:
            clause_keys[obligation_id] = f"C{len(clause_keys) + 1}"
            clauses[clause_keys[obligation_id]] = record
        cases.append({
            "case": index + 1,
            "clause_key": clause_keys[obligation_id],
            "reference_date": item["reference_date"].isoformat(),
            "entity_profile": item.get("entity_profile", {}),
        })

    if not cases:
        return [result or LlmClassification(None, "", "Nothing to classify") for result in results], None

    payload = {
        "contents": [{"parts": [{"text": build_batch_prompt(clauses, cases)}]}],
        "generationConfig": generation_config(
            model,
            max_output_tokens=min(32_768, 1_024 + 200 * len(cases)),
            responseMimeType="application/json",
            responseSchema=_batch_schema(),
        ),
    }
    raw_text, error = generate_text(
        api_key=api_key, model=model, payload=payload, http_client=http_client, timeout=timeout
    )
    if raw_text is None:
        return [result or LlmClassification(None, "", error) for result in results], error

    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip())
    try:
        answers = json.loads(cleaned)["answers"]
        if not isinstance(answers, list):
            raise TypeError("answers is not a list")
    except (ValueError, KeyError, TypeError) as exc:
        message = f"Could not read the model's reply as JSON: {exc}"
        return [result or LlmClassification(None, raw_text[:300], message) for result in results], message

    by_case: dict[int, dict[str, Any]] = {}
    for answer in answers:
        if isinstance(answer, dict) and isinstance(answer.get("case"), int):
            by_case.setdefault(answer["case"], answer)

    for case in cases:
        index = case["case"] - 1
        answer = by_case.get(case["case"])
        if answer is None:
            results[index] = LlmClassification(None, "", "The model did not answer this case.")
            continue
        label_text = str(answer.get("label", ""))
        outcome = next((label for label in _OUTCOME_LABELS if label.lower() == label_text.strip().lower()), None)
        outcome = outcome or parse_outcome(label_text)
        raw = f"LABEL: {label_text}\nREASON: {answer.get('reason', '')}"
        results[index] = LlmClassification(
            outcome, raw, None if outcome else "Could not parse a valid outcome label from the response"
        )
    return [result or LlmClassification(None, "", "Not classified") for result in results], None
