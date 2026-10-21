from __future__ import annotations

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


def test_benchmark_does_not_score_draft_queue(client):
    response = client.post("/api/v1/benchmark/run", json={"system_config": "TAARR"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["n"] == 0
    assert payload["metrics"]["accuracy"] is None
    assert "Draft annotation candidates are intentionally excluded" in payload["message"]
    assert payload["items"] == []


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
