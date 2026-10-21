"""TAARR HTTP API.

Run from the repository root after installing the package:
    uvicorn taarr.api:app --reload

The app refuses resolution requests until all policy choices are explicitly
configured in the environment or injected into create_app(). This prevents the
unresolved Build Plan / Review Paper differences from becoming silent defaults.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .catalog import Catalog, load_catalog
from .fact_extraction import DEFAULT_REGISTRY_PATH, extract_facts, load_fact_registry
from .llm_baseline import classify_batch_with_gemini, default_model
from .models import (
    MissingFactsPolicy,
    NoVersionPolicy,
    Outcome,
    ResolverPolicy,
    UnknownPrecedencePolicy,
)
from .reasoning import resolve_obligation
from .settings import env_file_path, gemini_api_key

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "does", "for", "from",
    "how", "in", "is", "it", "me", "of", "on", "or", "please", "should",
    "the", "their", "this", "to", "what", "when", "which", "with", "would",
}


NO_KEY_DETAIL = (
    "No Gemini API key found. Add GEMINI_API_KEY=... to the .env file in the project folder "
    "and click again (no restart needed). You can still answer the questions yourself."
)

POLICY_NOT_CONFIGURED_DETAIL = (
    "Resolution policy is not configured. Set TAARR_NO_VERSION_POLICY, "
    "TAARR_MISSING_FACTS_POLICY and TAARR_UNKNOWN_PRECEDENCE_POLICY after "
    "resolving the documented algorithm ambiguity (GitHub issue #1)."
)


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2_000)
    reference_date: date
    entity_profile: dict[str, Any]
    obligation_ids: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must contain non-whitespace text")
        return value


class BenchmarkRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_config: Literal["TAARR"] = "TAARR"
    limit: int | None = Field(default=None, ge=1, le=5_000)


class LlmCrossCheckRequest(BaseModel):
    """An independent LLM read of the same gold benchmark items.

    If api_key is omitted, the server falls back to the GEMINI_API_KEY
    environment variable (set it in .env, which is git-ignored and never
    pushed). Either way, the key is forwarded to Google's Gemini API for
    this request only -- it is never written to disk, logged, or stored in
    app state.
    """

    model_config = ConfigDict(extra="forbid")

    api_key: str | None = Field(default=None, min_length=1, max_length=400)
    model: str = Field(default_factory=default_model, max_length=100)
    limit: int = Field(default=10, ge=1, le=127)


class ChecklistRequest(BaseModel):
    """Run every obligation in the catalog against one entity profile."""

    model_config = ConfigDict(extra="forbid")

    entity_profile: dict[str, Any] = Field(default_factory=dict)
    reference_date: date
    regulator: Literal["RBI", "SEBI"] | None = None


class FactExtractionRequest(BaseModel):
    """A plain-English description of the organisation, to be turned into form answers."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=3_000)
    api_key: str | None = Field(default=None, min_length=1, max_length=400)
    model: str = Field(default_factory=default_model, max_length=100)


def policy_from_environment() -> ResolverPolicy | None:
    """Load all three policy choices, or return None if any is unset."""
    no_version = os.getenv("TAARR_NO_VERSION_POLICY", "").strip()
    missing_facts = os.getenv("TAARR_MISSING_FACTS_POLICY", "").strip()
    unknown_precedence = os.getenv("TAARR_UNKNOWN_PRECEDENCE_POLICY", "").strip()
    if not all((no_version, missing_facts, unknown_precedence)):
        return None
    try:
        return ResolverPolicy(
            no_version=NoVersionPolicy(no_version),
            missing_facts=MissingFactsPolicy(missing_facts),
            unknown_precedence=UnknownPrecedencePolicy(unknown_precedence),
        )
    except ValueError:
        return None


def _decisive_facts(record: dict[str, Any]) -> list[str]:
    """Every fact a rule's conditions, exemptions or dependencies test, in order."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            attribute = node.get("attribute")
            if isinstance(attribute, str) and attribute not in found:
                found.append(attribute)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for key in ("conditions", "exemptions", "dependencies"):
        walk(record.get(key))
    return found


def _policy_to_dict(policy: ResolverPolicy) -> dict[str, str]:
    return {
        "no_version": policy.no_version.value,
        "missing_facts": policy.missing_facts.value,
        "unknown_precedence": policy.unknown_precedence.value,
    }


def _query_tokens(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if token not in STOP_WORDS and len(token) > 1
    }


def _retrieve(
    query: str,
    catalog: Catalog,
    limit: int,
) -> list[tuple[str, int]]:
    """Small lexical bootstrap retriever; replace with BM25 + pgvector later."""
    tokens = _query_tokens(query)
    if not tokens:
        return []
    query_lower = query.lower()
    scored: list[tuple[str, int]] = []
    for obligation_id, searchable_text in catalog.search_text.items():
        score = sum(1 for token in tokens if token in searchable_text)
        if query_lower in searchable_text:
            score += 3
        if score > 0:
            scored.append((obligation_id, score))
    scored.sort(key=lambda row: (-row[1], row[0]))
    return scored[:limit]


def _load_gold_items(path: str | Path) -> list[dict[str, Any]]:
    """Read only adjudicated gold rows from the frozen benchmark ledger."""
    source = Path(path)
    if not source.is_file():
        return []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    with source.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}:{line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(item, dict):
                raise TypeError(f"{source}:{line_number}: expected a JSON object")
            # Draft queue is a separate path and is never loaded by this function.
            if item.get("annotation_status") != "gold_verified":
                continue
            item_id = item.get("benchmark_item_id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{source}:{line_number}: missing benchmark_item_id")
            if item_id in seen:
                raise ValueError(f"{source}:{line_number}: duplicate benchmark_item_id {item_id!r}")
            if item.get("gold_outcome") not in {item.value for item in Outcome}:
                raise ValueError(f"{source}:{line_number}: invalid gold_outcome")
            seen.add(item_id)
            items.append(item)
    return items


def _classification_metrics(
    gold: list[str],
    predicted: list[str | None],
) -> dict[str, Any]:
    labels = [outcome.value for outcome in Outcome]
    correct = sum(actual == pred for actual, pred in zip(gold, predicted, strict=True))
    per_label: dict[str, dict[str, float | int]] = {}
    f1_values: list[float] = []
    for label in labels:
        tp = sum(actual == label and pred == label for actual, pred in zip(gold, predicted, strict=True))
        fp = sum(actual != label and pred == label for actual, pred in zip(gold, predicted, strict=True))
        fn = sum(actual == label and pred != label for actual, pred in zip(gold, predicted, strict=True))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {
            "support": sum(actual == label for actual in gold),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
        f1_values.append(f1)

    return {
        "n": len(gold),
        "accuracy": round(correct / len(gold), 4) if gold else None,
        "macro_f1": round(sum(f1_values) / len(f1_values), 4) if gold else None,
        "per_outcome": per_label,
        "dropped_predictions": sum(pred is None for pred in predicted),
    }


def create_app(
    *,
    catalog: Catalog | None = None,
    catalog_path: str | Path | None = None,
    benchmark_path: str | Path | None = None,
    resolver_policy: ResolverPolicy | None = None,
    http_client: Any | None = None,
) -> FastAPI:
    """Application factory with injection points for reliable tests."""
    effective_catalog_path = catalog_path or os.getenv(
        "TAARR_OBLIGATIONS_PATH", "data/obligations/obligations.jsonl"
    )
    effective_benchmark_path = benchmark_path or os.getenv(
        "TAARR_BENCHMARK_PATH", "data/benchmark/benchmark.jsonl"
    )
    loaded_catalog = catalog if catalog is not None else load_catalog(effective_catalog_path)
    selected_policy = resolver_policy if resolver_policy is not None else policy_from_environment()

    app = FastAPI(
        title="TAARR API",
        version="0.1.0",
        description=(
            "Temporal and Applicability-Aware Regulatory Reasoning. "
            "Decisions are deterministic and evidence-backed; an LLM is not used to decide applicability."
        ),
    )
    app.state.catalog = loaded_catalog
    app.state.resolver_policy = selected_policy
    app.state.benchmark_path = Path(effective_benchmark_path)
    app.state.fact_registry = load_fact_registry(
        os.getenv("TAARR_FACT_REGISTRY_PATH", DEFAULT_REGISTRY_PATH)
    )
    app.state.http_client = http_client  # None -> a real httpx.Client per request

    origins = [
        origin.strip()
        for origin in os.getenv("TAARR_CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health", tags=["system"])
    @app.get("/api/v1/health", tags=["system"])
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "taarr-api",
            "policy_configured": app.state.resolver_policy is not None,
            "policy_required": app.state.resolver_policy is None,
            "gemini_api_key_configured": bool(gemini_api_key()),
            "gemini_model": default_model(),
            "env_file_found": env_file_path() is not None,
            "catalog": {
                "obligations": app.state.catalog.obligation_count,
                "versions": app.state.catalog.version_count,
                "clauses": app.state.catalog.clause_count,
            },
        }

    @app.get("/api/v1/obligations", tags=["catalog"])
    def list_obligations() -> dict[str, Any]:
        rows = []
        for obligation_id, records in sorted(app.state.catalog.raw_versions.items()):
            latest = max(
                records,
                key=lambda item: item.get("effective_from", ""),
            )
            rows.append({
                "obligation_id": obligation_id,
                "instrument_id": latest.get("instrument_id"),
                "instrument_title": latest.get("instrument_title"),
                "regulator": latest.get("regulator"),
                "clause_id": latest.get("clause_id"),
                "clause_summary": latest.get("clause_summary"),
                "version_count": len(records),
                "verification_status": latest.get("verification_status"),
            })
        return {"count": len(rows), "items": rows}

    @app.get("/api/v1/clause/{clause_id}", tags=["catalog"])
    def get_clause(clause_id: str) -> dict[str, Any]:
        records = app.state.catalog.records_for_clause(clause_id)
        if not records:
            raise HTTPException(status_code=404, detail=f"Clause {clause_id!r} was not found")
        records.sort(key=lambda item: item.get("effective_from", ""))
        return {"clause_id": clause_id, "version_count": len(records), "versions": records}

    @app.get("/api/v1/clause/{clause_id}/exemptions", tags=["catalog"])
    def get_clause_exemptions(
        clause_id: str,
        reference_date: date | None = None,
    ) -> dict[str, Any]:
        records = app.state.catalog.records_for_clause(clause_id)
        if not records:
            raise HTTPException(status_code=404, detail=f"Clause {clause_id!r} was not found")
        relations: list[dict[str, Any]] = []
        for record in records:
            for item in record.get("exemptions", []):
                if reference_date is not None:
                    start = item.get("effective_from")
                    end = item.get("effective_to")
                    if start and reference_date < date.fromisoformat(start):
                        continue
                    if end and reference_date >= date.fromisoformat(end):
                        continue
                relations.append({
                    **item,
                    "parent_version_id": record.get("version_id"),
                    "parent_clause_id": record.get("clause_id"),
                })
        return {
            "clause_id": clause_id,
            "reference_date": reference_date.isoformat() if reference_date else None,
            "count": len(relations),
            "exemptions": relations,
        }

    @app.post("/api/v1/query", tags=["resolution"])
    def query_regulations(request: QueryRequest) -> dict[str, Any]:
        active_policy = app.state.resolver_policy
        if active_policy is None:
            raise HTTPException(
                status_code=503,
                detail=POLICY_NOT_CONFIGURED_DETAIL,
            )

        if request.obligation_ids is not None:
            unknown_ids = [
                obligation_id for obligation_id in request.obligation_ids
                if obligation_id not in app.state.catalog.obligations
            ]
            if unknown_ids:
                raise HTTPException(
                    status_code=404,
                    detail={"message": "Unknown obligation ID(s)", "obligation_ids": unknown_ids},
                )
            candidates = [(obligation_id, 0) for obligation_id in request.obligation_ids]
        else:
            candidates = _retrieve(request.query, app.state.catalog, request.limit)

        outcomes: list[dict[str, Any]] = []
        for obligation_id, retrieval_score in candidates:
            result = resolve_obligation(
                obligation_id,
                app.state.catalog.obligations,
                request.reference_date,
                request.entity_profile,
                active_policy,
            )
            if result is None:
                outcomes.append({
                    "obligation_id": obligation_id,
                    "outcome": None,
                    "reason": "Dropped because no version is in force under the configured policy.",
                    "reference_date": request.reference_date.isoformat(),
                    "retrieval_score": retrieval_score,
                    "evidence": [],
                })
            else:
                outcomes.append({**result.to_dict(), "retrieval_score": retrieval_score})

        return {
            "query": request.query,
            "reference_date": request.reference_date.isoformat(),
            "entity_profile": request.entity_profile,
            "policy": _policy_to_dict(active_policy),
            "retrieved_count": len(candidates),
            "outcomes": outcomes,
            "notice": (
                "Candidate regulatory records are decision support, not legal advice. "
                "Review verification_status and the source evidence before relying on an outcome."
            ),
        }

    @app.post("/api/v1/benchmark/run", tags=["benchmark"])
    def run_benchmark(request: BenchmarkRunRequest) -> dict[str, Any]:
        active_policy = app.state.resolver_policy
        if active_policy is None:
            raise HTTPException(
                status_code=503,
                detail="Configure all three TAARR resolution policy variables before running the benchmark.",
            )
        try:
            items = _load_gold_items(app.state.benchmark_path)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Could not load benchmark: {exc}") from exc
        if request.limit is not None:
            items = items[: request.limit]

        rows: list[dict[str, Any]] = []
        gold_labels: list[str] = []
        predicted_labels: list[str | None] = []
        for item in items:
            target_id = item.get("target_obligation_id")
            try:
                reference_date = date.fromisoformat(item["reference_date"])
            except (KeyError, TypeError, ValueError):
                rows.append({
                    "benchmark_item_id": item.get("benchmark_item_id"),
                    "error": "Invalid or missing reference_date",
                })
                continue
            result = resolve_obligation(
                target_id,
                app.state.catalog.obligations,
                reference_date,
                item.get("entity_profile", {}),
                active_policy,
            )
            predicted = result.outcome.value if result is not None else None
            gold = item["gold_outcome"]
            gold_labels.append(gold)
            predicted_labels.append(predicted)
            rows.append({
                "benchmark_item_id": item["benchmark_item_id"],
                "target_obligation_id": target_id,
                "gold_outcome": gold,
                "predicted_outcome": predicted,
                "correct": predicted == gold,
                "result": result.to_dict() if result is not None else None,
            })

        return {
            "system_config": request.system_config,
            "policy": _policy_to_dict(active_policy),
            "metrics": _classification_metrics(gold_labels, predicted_labels),
            "items": rows,
            "message": (
                "No gold-verified benchmark items are available. Draft annotation candidates are "
                "intentionally excluded and are never scored."
                if not rows else "Scored gold-verified benchmark items only."
            ),
        }

    @app.post("/api/v1/baseline/llm-crosscheck", tags=["baseline"])
    def run_llm_crosscheck(request: LlmCrossCheckRequest) -> dict[str, Any]:
        """Ask Gemini to independently classify a sample of gold items.

        This is the optional B6 baseline named in docs/RESEARCH_EVALUATION.md.
        Gemini never sees TAARR's own outcome -- only the clause text, the
        entity facts, and the reference date -- so agreement with the gold
        label is a weak independent signal, not proof that TAARR is correct.
        It does not replace the project's required human two-person
        verification. The effective api_key (request body, or GEMINI_API_KEY
        from .env as a fallback) is used for this request only and is never
        persisted or logged.
        """
        api_key = request.api_key or gemini_api_key()
        if not api_key:
            raise HTTPException(status_code=422, detail=NO_KEY_DETAIL)
        try:
            items = _load_gold_items(app.state.benchmark_path)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Could not load benchmark: {exc}") from exc
        items = items[: request.limit]
        if not items:
            raise HTTPException(status_code=404, detail="No gold-verified benchmark items are available.")

        usable: list[dict[str, Any]] = []
        for item in items:
            try:
                reference_date = date.fromisoformat(item["reference_date"])
            except (KeyError, TypeError, ValueError):
                continue
            usable.append({**item, "_reference_date": reference_date})

        batch = [
            {
                "obligation_id": item["target_obligation_id"],
                "entity_profile": item.get("entity_profile", {}),
                "reference_date": item["_reference_date"],
            }
            for item in usable
        ]
        # ONE Gemini request for every selected item (not one per item).
        shared = app.state.http_client
        if shared is not None:
            classifications, batch_error = classify_batch_with_gemini(
                api_key=api_key, items=batch, catalog=app.state.catalog,
                http_client=shared, model=request.model,
            )
        else:
            with httpx.Client() as client:
                classifications, batch_error = classify_batch_with_gemini(
                    api_key=api_key, items=batch, catalog=app.state.catalog,
                    http_client=client, model=request.model,
                )
        if batch_error:
            raise HTTPException(status_code=502, detail=batch_error)

        rows: list[dict[str, Any]] = []
        gold_labels: list[str] = []
        llm_labels: list[str | None] = []
        for item, classification in zip(usable, classifications, strict=True):
            gold = item["gold_outcome"]
            gold_labels.append(gold)
            llm_labels.append(classification.outcome)
            rows.append({
                "benchmark_item_id": item["benchmark_item_id"],
                "target_obligation_id": item["target_obligation_id"],
                "gold_outcome": gold,
                "llm_outcome": classification.outcome,
                "agrees_with_gold": classification.outcome == gold,
                "llm_raw_text": classification.raw_text,
                "error": classification.error,
            })

        return {
            "model": request.model,
            "api_calls": 1,
            "n": len(rows),
            "agreement_with_gold": _classification_metrics(gold_labels, llm_labels),
            "items": rows,
            "notice": (
                "This is an independent LLM cross-check, not a verification of TAARR's correctness. "
                "The model never sees TAARR's own outcome. Agreement is a convenience signal only and "
                "does not replace the project's required human two-person gold verification."
            ),
        }

    @app.post("/api/v1/checklist", tags=["resolution"])
    def build_checklist(request: ChecklistRequest) -> dict[str, Any]:
        """Resolve all obligations for one profile and group them for a reader.

        Nothing is guessed: a fact the user did not answer stays unknown, so the
        obligation lands in "need_more_info" together with the exact plain-English
        question that would settle it.
        """
        active_policy = app.state.resolver_policy
        if active_policy is None:
            raise HTTPException(status_code=503, detail=POLICY_NOT_CONFIGURED_DETAIL)

        catalog = app.state.catalog
        registry = app.state.fact_registry
        groups: dict[str, list[dict[str, Any]]] = {
            "applies": [], "does_not_apply": [], "need_more_info": [], "conflict": [], "dropped": [],
        }
        blockers: dict[str, list[str]] = {}

        for obligation_id in sorted(catalog.obligations):
            records = catalog.records_for_obligation(obligation_id)
            latest = max(records, key=lambda item: item.get("effective_from", "")) if records else {}
            if request.regulator and latest.get("regulator") != request.regulator:
                continue
            result = resolve_obligation(
                obligation_id, catalog.obligations, request.reference_date,
                request.entity_profile, active_policy,
            )
            row: dict[str, Any] = {
                "obligation_id": obligation_id,
                "regulator": latest.get("regulator"),
                "instrument_id": latest.get("instrument_id"),
                "instrument_title": latest.get("instrument_title"),
                "circular_url": latest.get("consolidated_source_url") or latest.get("source_url"),
                "effective_from": latest.get("effective_from"),
                "decided_by": _decisive_facts(latest),
                "clause_id": latest.get("clause_id"),
                "clause_summary": latest.get("clause_summary"),
                "action": latest.get("action"),
                "modality": latest.get("modality"),
                "deadline": latest.get("stated_implementation_deadline"),
                "verification_status": latest.get("verification_status"),
            }
            if result is None:
                row.update({
                    "outcome": None,
                    "reason": "No version of this rule was in force on the chosen date.",
                    "source_url": latest.get("source_url"),
                    "missing": [],
                    "evidence": [],
                })
                groups["dropped"].append(row)
                continue

            payload = result.to_dict()
            missing = []
            for key in payload["missing_facts"]:
                fact = registry.facts.get(key)
                missing.append({
                    "key": key,
                    "question": fact["question"] if fact else f"Unknown fact: {key}",
                })
                blockers.setdefault(key, []).append(obligation_id)
            row.update({
                "outcome": payload["outcome"],
                "reason": payload["reason"],
                "source_url": payload["source_url"] or latest.get("source_url"),
                "version_id": payload["version_id"],
                "missing": missing,
                "evidence": payload["evidence"],
                "dependencies": payload["dependencies"],
            })
            bucket = {
                "Applicable": "applies",
                "Not applicable": "does_not_apply",
                "Indeterminate": "need_more_info",
                "Conflict": "conflict",
            }[payload["outcome"]]
            groups[bucket].append(row)

        # Show the rules that are closest to being settled first.
        groups["need_more_info"].sort(key=lambda row: (len(row["missing"]), row["obligation_id"]))

        next_questions = []
        for key, obligation_ids in blockers.items():
            fact = registry.facts.get(key)
            if fact is None:
                continue
            next_questions.append({
                **fact,
                "unblocks": len(obligation_ids),
                "unblocks_obligation_ids": sorted(obligation_ids),
                "group_label": registry.groups.get(fact["group"], fact["group"]),
            })
        next_questions.sort(key=lambda item: (-item["unblocks"], item["key"]))

        return {
            "reference_date": request.reference_date.isoformat(),
            "regulator": request.regulator,
            "policy": _policy_to_dict(active_policy),
            "answered_fact_count": len(request.entity_profile),
            "counts": {name: len(rows) for name, rows in groups.items()},
            "total": sum(len(rows) for rows in groups.values()),
            "groups": groups,
            "next_questions": next_questions,
            "notice": (
                "Deterministic result from the rule catalogue, not legal advice. Unanswered questions "
                "stay unknown -- they are never assumed to be no. Check the linked source text before "
                "you act on any row."
            ),
        }

    @app.get("/api/v1/facts", tags=["facts"])
    def list_facts() -> dict[str, Any]:
        """The closed list of facts TAARR obligations can test, with plain-English questions."""
        registry = app.state.fact_registry
        return {"groups": registry.groups, "facts": list(registry.facts.values())}

    @app.post("/api/v1/facts/extract", tags=["facts"])
    def extract_entity_facts(request: FactExtractionRequest) -> dict[str, Any]:
        """Fill the fact form from a plain-English description using Gemini.

        Gemini only sees the closed fact list and may only return keys from it;
        every value is re-validated here and must be backed by a quote from the
        user's own text. It never decides applicability -- the user reviews the
        facts and the deterministic resolver does the rest.
        """
        api_key = request.api_key or gemini_api_key()
        if not api_key:
            raise HTTPException(status_code=422, detail=NO_KEY_DETAIL)
        shared = app.state.http_client
        if shared is not None:
            result = extract_facts(
                description=request.description, api_key=api_key,
                registry=app.state.fact_registry, http_client=shared, model=request.model,
            )
        else:
            with httpx.Client() as client:
                result = extract_facts(
                    description=request.description, api_key=api_key,
                    registry=app.state.fact_registry, http_client=client, model=request.model,
                )
        if result.error:
            raise HTTPException(status_code=502, detail=result.error)
        return {
            "facts": result.facts,
            "evidence": result.evidence,
            "rejected": result.rejected,
            "unrecognised": result.unrecognised,
            "model": result.model,
            "notice": "Please review these answers. Anything not stated in your text was left blank, not guessed.",
        }

    return app


load_dotenv()
app = create_app()
