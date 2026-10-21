"""Gemini is called in exactly two places, once each: autofill and AI cross-check."""

import json

from fastapi.testclient import TestClient

from taarr.api import create_app
from taarr.llm_baseline import build_batch_prompt, generation_config

POLICY = {
    "TAARR_NO_VERSION_POLICY": "NOT_APPLICABLE",
    "TAARR_MISSING_FACTS_POLICY": "KLEENE",
    "TAARR_UNKNOWN_PRECEDENCE_POLICY": "DEFINITIVE_RULES_FIRST",
}


class _Resp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self.text}]}, "finishReason": "STOP"}]}


class CountingClient:
    """Fake Gemini: records every request and answers with whatever fits."""

    def __init__(self, status=200, body=None):
        self.calls = []
        self.status = status
        self.body = body

    def post(self, url, *, json, params, timeout):
        self.calls.append({"url": url, "payload": json})
        if self.body is not None:
            return _Resp(self.status, self.body)
        prompt = json["contents"][0]["parts"][0]["text"]
        if "CASES" in prompt:
            n = prompt.count("\nCase ")
            answers = [{"case": i + 1, "label": "Applicable", "reason": "stub"} for i in range(n)]
            return _Resp(200, _dumps({"answers": answers}))
        return _Resp(200, _dumps({"facts": []}))


def _dumps(obj):
    return json.dumps(obj)


def _app(monkeypatch, client):
    for name, value in POLICY.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    return TestClient(create_app(http_client=client))


def test_autofill_is_exactly_one_call(monkeypatch):
    fake = CountingClient()
    c = _app(monkeypatch, fake)
    assert c.post("/api/v1/facts/extract", json={"description": "We are an NBFC."}).status_code == 200
    assert len(fake.calls) == 1


def test_cross_check_of_many_items_is_exactly_one_call(monkeypatch):
    fake = CountingClient()
    c = _app(monkeypatch, fake)
    response = c.post("/api/v1/baseline/llm-crosscheck", json={"limit": 25})
    body = response.json()
    assert response.status_code == 200, body
    assert len(fake.calls) == 1
    assert body["api_calls"] == 1
    assert body["n"] == 25
    assert all(row["llm_outcome"] == "Applicable" for row in body["items"])


def test_nothing_else_calls_gemini(monkeypatch):
    fake = CountingClient()
    c = _app(monkeypatch, fake)
    c.get("/api/v1/health")
    c.get("/api/v1/facts")
    c.get("/api/v1/obligations")
    c.post("/api/v1/checklist", json={"entity_profile": {"is_rbi_regulated_entity": True},
                                       "reference_date": "2026-10-22"})
    c.post("/api/v1/query", json={"query": "risk", "reference_date": "2026-10-22",
                                   "entity_profile": {}})
    c.post("/api/v1/benchmark/run", json={"system_config": "TAARR"})
    assert fake.calls == []


def test_env_file_is_reread_on_every_click(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=file-key\nGEMINI_MODEL=gemini-3.5-flash-lite\n")
    monkeypatch.setenv("TAARR_ENV_FILE", str(env))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    fake = CountingClient()
    for name, value in POLICY.items():
        monkeypatch.setenv(name, value)
    c = TestClient(create_app(http_client=fake))

    assert c.get("/api/v1/health").json()["gemini_model"] == "gemini-3.5-flash-lite"
    c.post("/api/v1/facts/extract", json={"description": "We are an NBFC."})
    assert "gemini-3.5-flash-lite" in fake.calls[-1]["url"]

    env.write_text("GEMINI_API_KEY=file-key\nGEMINI_MODEL=gemini-2.5-flash-lite\n")  # no restart
    c.post("/api/v1/facts/extract", json={"description": "We are an NBFC."})
    assert "gemini-2.5-flash-lite" in fake.calls[-1]["url"]


def test_env_file_wins_over_shell_variable(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("GEMINI_MODEL=gemini-3.6-flash\n")
    monkeypatch.setenv("TAARR_ENV_FILE", str(env))
    monkeypatch.setenv("GEMINI_MODEL", "something-else")
    c = TestClient(create_app())
    assert c.get("/api/v1/health").json()["gemini_model"] == "gemini-3.6-flash"


def test_wrong_model_name_gives_a_fix_not_a_stack_of_json(monkeypatch):
    body = '{"error": {"code": 404, "message": "models/gemini-3.1-flash is not found", "status": "NOT_FOUND"}}'
    c = _app(monkeypatch, CountingClient(status=404, body=body))
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash")
    response = c.post("/api/v1/facts/extract", json={"description": "We are an NBFC."})
    detail = response.json()["detail"]
    assert response.status_code == 502
    assert "gemini-3.1-flash" in detail and "GEMINI_MODEL" in detail and ".env" in detail


def test_rate_limit_message_suggests_switching_model(monkeypatch):
    c = _app(monkeypatch, CountingClient(status=429, body='{"error": {"code": 429}}'))
    detail = c.post("/api/v1/baseline/llm-crosscheck", json={"limit": 3}).json()["detail"]
    assert "rate limit" in detail and "GEMINI_MODEL" in detail


def test_temperature_only_sent_to_older_models():
    assert "temperature" in generation_config("gemini-2.5-flash-lite", max_output_tokens=10)
    assert "temperature" not in generation_config("gemini-3.5-flash-lite", max_output_tokens=10)
    assert "temperature" not in generation_config("gemini-4-argon", max_output_tokens=10)


def test_batch_prompt_lists_each_clause_once():
    record = {"clause_id": "paragraph-38", "clause_text": "UNIQUE-CLAUSE-TEXT", "clause_summary": "s"}
    cases = [
        {"case": 1, "clause_key": "C1", "reference_date": "2026-01-01", "entity_profile": {}},
        {"case": 2, "clause_key": "C1", "reference_date": "2026-01-01", "entity_profile": {"x": True}},
    ]
    prompt = build_batch_prompt({"C1": record}, cases)
    assert prompt.count("UNIQUE-CLAUSE-TEXT") == 1
    assert "Case 1:" in prompt and "Case 2:" in prompt
