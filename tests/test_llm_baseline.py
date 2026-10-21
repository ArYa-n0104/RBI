from __future__ import annotations

from datetime import date

from taarr.catalog import load_catalog
from taarr.llm_baseline import build_prompt, classify_with_gemini, parse_outcome


def test_parse_outcome_reads_label_line():
    assert parse_outcome("LABEL: Applicable\nREASON: because yes") == "Applicable"


def test_parse_outcome_is_case_insensitive():
    assert parse_outcome("label: not applicable\nreason: n/a") == "Not applicable"


def test_parse_outcome_falls_back_to_single_mention():
    assert parse_outcome("I think this is Indeterminate given the gaps.") == "Indeterminate"


def test_parse_outcome_returns_none_when_ambiguous():
    assert parse_outcome("This could be Applicable or Not applicable, hard to say.") is None


def test_parse_outcome_returns_none_when_absent():
    assert parse_outcome("I cannot decide.") is None


def test_build_prompt_never_mentions_taarr_outcome():
    prompt = build_prompt(
        clause_text="Entities must send a notice.",
        clause_summary="Due notice requirement",
        clause_id="paragraph-38(e)",
        source_url="https://www.rbi.org.in/example",
        entity_profile={"is_rbi_regulated_entity": True},
        reference_date=date(2025, 7, 1),
    )
    assert "TAARR" not in prompt
    assert "Applicable" in prompt  # the label option itself, not an answer
    assert "paragraph-38(e)" in prompt
    assert "is_rbi_regulated_entity" in prompt


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.last_call = None

    def post(self, url, *, json, params, timeout):
        self.last_call = {"url": url, "json": json, "params": params, "timeout": timeout}
        return self._response


def test_classify_with_gemini_parses_successful_response():
    catalog = load_catalog("data/obligations/obligations.jsonl")
    fake_response = _FakeResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "LABEL: Applicable\nREASON: conditions met"}]}}]},
    )
    client = _FakeClient(fake_response)
    result = classify_with_gemini(
        api_key="fake-key",
        obligation_id="RBI-KYC-P38E-DUE-NOTICES",
        catalog=catalog,
        entity_profile={"is_rbi_regulated_entity": True},
        reference_date=date(2025, 7, 1),
        http_client=client,
    )
    assert result.outcome == "Applicable"
    assert result.error is None
    # The api key must be sent as a request param, never embedded in the prompt text.
    assert client.last_call["params"]["key"] == "fake-key"
    assert "fake-key" not in client.last_call["json"]["contents"][0]["parts"][0]["text"]


def test_classify_with_gemini_reports_http_errors():
    catalog = load_catalog("data/obligations/obligations.jsonl")
    client = _FakeClient(_FakeResponse(403, text="API key not valid"))
    result = classify_with_gemini(
        api_key="bad-key",
        obligation_id="RBI-KYC-P38E-DUE-NOTICES",
        catalog=catalog,
        entity_profile={},
        reference_date=date(2025, 7, 1),
        http_client=client,
    )
    assert result.outcome is None
    assert "403" in result.error


def test_classify_with_gemini_reports_unknown_obligation():
    catalog = load_catalog("data/obligations/obligations.jsonl")
    client = _FakeClient(_FakeResponse(200))
    result = classify_with_gemini(
        api_key="fake-key",
        obligation_id="NOT-A-REAL-ID",
        catalog=catalog,
        entity_profile={},
        reference_date=date(2025, 7, 1),
        http_client=client,
    )
    assert result.outcome is None
    assert "Unknown obligation_id" in result.error
