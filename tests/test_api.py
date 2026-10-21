from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from taarr.api import create_app
from taarr.catalog import load_catalog
from taarr.models import (
    MissingFactsPolicy,
    NoVersionPolicy,
    ResolverPolicy,
    UnknownPrecedencePolicy,
)


def policy():
    return ResolverPolicy(
        no_version=NoVersionPolicy.DROP,
        missing_facts=MissingFactsPolicy.KLEENE,
        unknown_precedence=UnknownPrecedencePolicy.INDETERMINATE_FIRST,
    )


@pytest.fixture
def client():
    return TestClient(
        create_app(
            catalog=load_catalog("data/obligations/obligations.jsonl"),
            benchmark_path="data/benchmark/benchmark.jsonl",
            resolver_policy=policy(),
        )
    )


def test_health_reports_catalog_and_configured_policy(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["policy_configured"] is True
    assert payload["catalog"]["obligations"] >= 1
    assert payload["catalog"]["versions"] >= 1


def test_query_returns_deterministic_outcome_and_provenance(client):
    response = client.post(
        "/api/v1/query",
        json={
            "query": "RBI KYC due notice",
            "reference_date": "2025-07-01",
            "entity_profile": {"is_rbi_regulated_entity": True},
            "obligation_ids": ["RBI-KYC-P38E-DUE-NOTICES"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["retrieved_count"] == 1
    result = payload["outcomes"][0]
    assert result["outcome"] == "Applicable"
    assert result["version_id"] == "RBI-KYC-P38E-v1"
    assert result["evidence"][0]["verification_status"] == "source_text_human_confirmed"
    assert payload["policy"]["no_version"] == "DROP"


def test_query_with_missing_entity_fact_abstains(client):
    response = client.post(
        "/api/v1/query",
        json={
            "query": "KYC notice",
            "reference_date": "2025-07-01",
            "entity_profile": {},
        },
    )
    assert response.status_code == 200
    assert response.json()["outcomes"][0]["outcome"] == "Indeterminate"
    assert "is_rbi_regulated_entity" in response.json()["outcomes"][0]["missing_facts"]


def test_query_can_target_obligation_id_without_retrieval(client):
    response = client.post(
        "/api/v1/query",
        json={
            "query": "Any query text",
            "reference_date": "2025-07-01",
            "entity_profile": {"is_rbi_regulated_entity": False},
            "obligation_ids": ["RBI-KYC-P38E-DUE-NOTICES"],
        },
    )
    assert response.status_code == 200
    assert response.json()["outcomes"][0]["outcome"] == "Not applicable"


def test_unknown_target_obligation_id_is_404(client):
    response = client.post(
        "/api/v1/query",
        json={
            "query": "KYC",
            "reference_date": "2025-07-01",
            "entity_profile": {},
            "obligation_ids": ["NOT-FOUND"],
        },
    )
    assert response.status_code == 404


def test_clause_explorer_shows_version_and_verification_status(client):
    response = client.get("/api/v1/clause/paragraph-38(e)")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version_count"] == 1
    assert payload["versions"][0]["verification_status"] == "source_text_human_confirmed"


def test_clause_not_found_is_404(client):
    assert client.get("/api/v1/clause/no-such-clause").status_code == 404


def test_benchmark_scores_only_gold_verified_rows(client):
    # As of 2026-10-21, data/benchmark/benchmark.jsonl holds 127 real
    # gold_verified items (see docs/DECISIONS.md D-009). This test checks the
    # loader's own safety property -- draft-status rows are never scored --
    # not the resulting accuracy number, which is expected to be high due to
    # documented circularity (see docs/ILLUSTRATIVE_EVAL.md,
    # docs/EVALUATION_NEXT_STEPS.md): the benchmark's facts/expected outcomes
    # were generated from the same rule engine being evaluated.
    response = client.post("/api/v1/benchmark/run", json={"system_config": "TAARR"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["n"] == 127
    assert payload["message"] == "Scored gold-verified benchmark items only."
    assert len(payload["items"]) == 127


def test_benchmark_run_excludes_non_gold_rows(tmp_path, client):
    # A row that is not annotation_status == "gold_verified" must never be
    # scored, even if it ends up in the benchmark ledger file by mistake.
    mixed_path = tmp_path / "mixed_benchmark.jsonl"
    mixed_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "benchmark_item_id": "FAKE-DRAFT-0001",
                        "annotation_status": "draft",
                        "target_obligation_id": "RBI-KYC-P38E-DUE-NOTICES",
                        "reference_date": "2025-07-01",
                        "entity_profile": {"is_rbi_regulated_entity": True},
                        "gold_outcome": "Applicable",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    draft_only_client = TestClient(
        create_app(
            catalog=load_catalog("data/obligations/obligations.jsonl"),
            benchmark_path=str(mixed_path),
            resolver_policy=policy(),
        )
    )
    response = draft_only_client.post("/api/v1/benchmark/run", json={"system_config": "TAARR"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["n"] == 0
    assert payload["metrics"]["accuracy"] is None
    assert "Draft annotation candidates are intentionally excluded" in payload["message"]
    assert payload["items"] == []


def test_llm_crosscheck_rejects_blank_api_key(client):
    response = client.post("/api/v1/baseline/llm-crosscheck", json={"api_key": "", "limit": 1})
    assert response.status_code == 422


def test_llm_crosscheck_uses_gemini_and_never_leaks_key(client, monkeypatch):
    from taarr import api as api_module

    captured = {}

    def fake_batch(*, api_key, items, catalog, http_client, model):
        captured["api_key"] = api_key
        from taarr.llm_baseline import LlmClassification
        return [LlmClassification(outcome="Applicable", raw_text="LABEL: Applicable\nREASON: stub")
                for _ in items], None

    monkeypatch.setattr(api_module, "classify_batch_with_gemini", fake_batch)

    response = client.post(
        "/api/v1/baseline/llm-crosscheck",
        json={"api_key": "secret-test-key", "limit": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert captured["api_key"] == "secret-test-key"
    assert payload["n"] == 2
    assert "secret-test-key" not in json.dumps(payload)
    assert "agreement_with_gold" in payload
    assert all("llm_outcome" in row for row in payload["items"])


def test_llm_crosscheck_falls_back_to_env_key(client, monkeypatch):
    from taarr import api as api_module

    monkeypatch.setenv("GEMINI_API_KEY", "env-fallback-key")
    captured = {}

    def fake_batch(*, api_key, items, catalog, http_client, model):
        captured["api_key"] = api_key
        from taarr.llm_baseline import LlmClassification
        return [LlmClassification(outcome="Applicable", raw_text="LABEL: Applicable\nREASON: stub")
                for _ in items], None

    monkeypatch.setattr(api_module, "classify_batch_with_gemini", fake_batch)

    response = client.post("/api/v1/baseline/llm-crosscheck", json={"limit": 1})
    assert response.status_code == 200
    assert captured["api_key"] == "env-fallback-key"
    assert "env-fallback-key" not in json.dumps(response.json())


def test_llm_crosscheck_errors_clearly_with_no_key_anywhere(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.post("/api/v1/baseline/llm-crosscheck", json={"limit": 1})
    assert response.status_code == 422
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_health_reports_whether_gemini_key_is_configured(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "some-key")
    assert client.get("/api/v1/health").json()["gemini_api_key_configured"] is True
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert client.get("/api/v1/health").json()["gemini_api_key_configured"] is False


def test_query_fails_closed_if_policy_is_unconfigured(monkeypatch):
    # The developer's local .env may configure the resolver; this test must
    # explicitly simulate a deployment where policy values are absent.
    for key in (
        "TAARR_NO_VERSION_POLICY",
        "TAARR_MISSING_FACTS_POLICY",
        "TAARR_UNKNOWN_PRECEDENCE_POLICY",
    ):
        monkeypatch.delenv(key, raising=False)
    client = TestClient(
        create_app(catalog=load_catalog("data/obligations/obligations.jsonl"), resolver_policy=None)
    )
    response = client.post(
        "/api/v1/query",
        json={
            "query": "KYC",
            "reference_date": date(2025, 7, 1).isoformat(),
            "entity_profile": {"is_rbi_regulated_entity": True},
        },
    )
    assert response.status_code == 503
    assert "policy is not configured" in response.json()["detail"]


def test_query_rejects_blank_query(client):
    response = client.post(
        "/api/v1/query",
        json={"query": "  ", "reference_date": "2025-07-01", "entity_profile": {}},
    )
    assert response.status_code == 422
