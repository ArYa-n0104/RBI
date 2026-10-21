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

    def post(self, url, *, json, params, timeout):
        self.payload = json
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
