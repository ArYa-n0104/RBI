import json

from fastapi.testclient import TestClient

from taarr.api import create_app
from taarr.fact_extraction import (
    build_prompt,
    extract_facts,
    load_fact_registry,
    validate_extraction,
)


def _used_attributes(node, acc):
    if isinstance(node, dict):
        if "attribute" in node:
            acc.add(node["attribute"])
        for v in node.values():
            _used_attributes(v, acc)
    elif isinstance(node, list):
        for v in node:
            _used_attributes(v, acc)


def test_registry_matches_obligations_exactly():
    registry = load_fact_registry()
    used = set()
    with open("data/obligations/obligations.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                for k in ("conditions", "exemptions", "dependencies"):
                    _used_attributes(rec.get(k), used)
    assert used == set(registry.facts)


DESC = "We are an NBFC with a high risk customer base."


def test_prompt_contains_only_registry_keys_and_options():
    registry = load_fact_registry()
    prompt = build_prompt(DESC, registry)
    assert "risk_category" in prompt and "low, medium, high" in prompt
    assert DESC in prompt


def test_validation_drops_bad_items():
    registry = load_fact_registry()
    raw = json.dumps({"facts": [
        {"key": "is_rbi_regulated_entity", "value": "true", "evidence": "We are an NBFC"},
        {"key": "risk_category", "value": "extreme", "evidence": "high risk"},
        {"key": "made_up_key", "value": "x", "evidence": "NBFC"},
        {"key": "is_listed_entity", "value": "true", "evidence": "we are listed on NSE"},
    ]})
    r = validate_extraction(raw, DESC, registry)
    assert r.facts == {"is_rbi_regulated_entity": True}
    assert r.unrecognised == ["made_up_key"]
    assert {x["key"] for x in r.rejected} == {"risk_category", "is_listed_entity"}


def test_bad_json_is_an_error():
    assert validate_extraction("nope", DESC, load_fact_registry()).error


class _Resp:
    status_code = 200

    def __init__(self, text):
        self._t = text
        self.text = text

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self._t}]}}]}


class _Client:
    def __init__(self, text):
        self.text = text
        self.payload = None
        self.url = ""

    def post(self, url, *, json, params, timeout):
        self.payload = json
        self.url = url
        return _Resp(self.text)


def test_extract_sends_schema_and_returns_facts():
    reply = json.dumps({"facts": [{"key": "risk_category", "value": "High", "evidence": "high risk"}]})
    client = _Client(reply)
    r = extract_facts(description=DESC, api_key="k", registry=load_fact_registry(), http_client=client)
    assert r.facts == {"risk_category": "high"}
    schema = client.payload["generationConfig"]["responseSchema"]
    assert "risk_category" in schema["properties"]["facts"]["items"]["properties"]["key"]["enum"]


def test_api_endpoints(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    reply = json.dumps({"facts": [{"key": "is_rbi_regulated_entity", "value": "true", "evidence": "We are an NBFC"}]})
    c = TestClient(create_app(http_client=_Client(reply)))
    assert len(c.get("/api/v1/facts").json()["facts"]) == 43
    assert c.post("/api/v1/facts/extract", json={"description": DESC}).status_code == 422
    ok = c.post("/api/v1/facts/extract", json={"description": DESC, "api_key": "k"})
    assert ok.status_code == 200 and ok.json()["facts"] == {"is_rbi_regulated_entity": True}


CHECKLIST_URL = "/api/v1/checklist"
POLICY = {
    "TAARR_NO_VERSION_POLICY": "NOT_APPLICABLE",
    "TAARR_MISSING_FACTS_POLICY": "KLEENE",
    "TAARR_UNKNOWN_PRECEDENCE_POLICY": "DEFINITIVE_RULES_FIRST",
}


def _client(monkeypatch):
    for name, value in POLICY.items():
        monkeypatch.setenv(name, value)
    return TestClient(create_app())


def test_checklist_covers_every_obligation(monkeypatch):
    c = _client(monkeypatch)
    body = c.post(CHECKLIST_URL, json={"entity_profile": {}, "reference_date": "2025-07-01"}).json()
    assert body["total"] == 60
    assert sum(body["counts"].values()) == 60
    # With no facts supplied, nothing is silently assumed false.
    assert body["counts"]["need_more_info"] > 0


def test_checklist_next_questions_are_plain_english_and_ranked(monkeypatch):
    c = _client(monkeypatch)
    body = c.post(CHECKLIST_URL, json={"entity_profile": {}, "reference_date": "2025-07-01"}).json()
    questions = body["next_questions"]
    assert questions and questions[0]["unblocks"] >= questions[-1]["unblocks"]
    assert all(q["question"].endswith("?") for q in questions)


def test_checklist_regulator_filter_and_answers_reduce_unknowns(monkeypatch):
    c = _client(monkeypatch)
    sebi = c.post(CHECKLIST_URL, json={
        "entity_profile": {}, "reference_date": "2025-07-01", "regulator": "SEBI",
    }).json()
    assert sebi["total"] == 18
    assert {row["regulator"] for rows in sebi["groups"].values() for row in rows} == {"SEBI"}

    answered = c.post(CHECKLIST_URL, json={
        "entity_profile": {"is_rbi_regulated_entity": True, "risk_category": "high"},
        "reference_date": "2025-07-01",
    }).json()
    assert answered["counts"]["applies"] > 0
    assert answered["counts"]["need_more_info"] < 60


def test_gemini_model_comes_from_the_environment(monkeypatch):
    """A model swap is an .env edit: no code change, no redeploy of the frontend."""
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.0-flash")
    client = _Client(json.dumps({"facts": []}))
    c = TestClient(create_app(http_client=client))
    assert c.get("/api/v1/health").json()["gemini_model"] == "gemini-2.0-flash"
    c.post("/api/v1/facts/extract", json={"description": DESC, "api_key": "k"})
    assert "gemini-2.0-flash" in client.url

    monkeypatch.delenv("GEMINI_MODEL")
    c2 = TestClient(create_app(http_client=_Client(json.dumps({"facts": []}))))
    assert c2.get("/api/v1/health").json()["gemini_model"] == "gemini-2.5-flash-lite"
