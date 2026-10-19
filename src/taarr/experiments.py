"""Run TAARR and controlled ablations against gold-verified JSONL items.

Ablations are diagnostic baselines, not production policies. This module refuses to
score draft rows and reports metrics as unavailable when the gold set is empty.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from .catalog import load_catalog
from .evaluate import read_jsonl, score
from .models import (
    MissingFactsPolicy,
    NoVersionPolicy,
    ResolverPolicy,
    UnknownPrecedencePolicy,
)
from .reasoning import resolve_obligation


def _policy_from_env() -> ResolverPolicy:
    values = (
        os.getenv("TAARR_NO_VERSION_POLICY", "").strip(),
        os.getenv("TAARR_MISSING_FACTS_POLICY", "").strip(),
        os.getenv("TAARR_UNKNOWN_PRECEDENCE_POLICY", "").strip(),
    )
    if not all(values):
        raise ValueError("Set all three TAARR resolver policy variables before running experiments.")
    try:
        return ResolverPolicy(
            no_version=NoVersionPolicy(values[0]),
            missing_facts=MissingFactsPolicy(values[1]),
            unknown_precedence=UnknownPrecedencePolicy(values[2]),
        )
    except ValueError as exc:
        raise ValueError(f"Invalid TAARR resolver policy: {exc}") from exc


def _set_missing_false(condition: dict[str, Any], profile: dict[str, Any]) -> None:
    """Fill missing atomic facts with a value that makes the predicate false."""
    if "all_of" in condition:
        for child in condition["all_of"]:
            _set_missing_false(child, profile)
    elif "any_of" in condition:
        for child in condition["any_of"]:
            _set_missing_false(child, profile)
    elif "not" in condition:
        _set_missing_false(condition["not"], profile)
    else:
        attribute = condition.get("attribute")
        if not isinstance(attribute, str):
            return
        current: Any = profile
        parts = attribute.split(".")
        for part in parts[:-1]:
            if not isinstance(current, dict):
                return
            current = current.setdefault(part, {})
        if isinstance(current, dict) and parts[-1] not in current:
            expected = condition.get("value")
            current[parts[-1]] = False if expected is True else True if expected is False else "__MISSING_BASELINE__"


def _catalog_variant(catalog, mode: str):
    if mode not in {"full", "no_temporal", "no_exceptions_dependencies"}:
        return catalog
    updated = {}
    for obligation_id, obligation in catalog.obligations.items():
        versions = obligation.versions
        if mode == "no_temporal" and versions:
            # Deliberately select the latest recorded version for every date.
            latest = max(versions, key=lambda version: (version.effective_from, version.version_id))
            versions = (replace(latest, effective_from=date.min, effective_to=None),)
        if mode == "no_exceptions_dependencies":
            versions = tuple(replace(v, exemptions=(), dependencies=()) for v in versions)
        updated[obligation_id] = replace(obligation, versions=tuple(versions))
    return updated


def _resolve_item(item, obligations, policy, mode: str) -> dict[str, Any]:
    obligation_id = item.get("target_obligation_id")
    if not isinstance(obligation_id, str) or not obligation_id:
        raise ValueError(f"{item.get('benchmark_item_id')}: target_obligation_id is required")
    try:
        reference_date = date.fromisoformat(item["reference_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{item.get('benchmark_item_id')}: invalid reference_date") from exc
    profile = item.get("entity_profile")
    if not isinstance(profile, dict):
        raise ValueError(f"{item.get('benchmark_item_id')}: entity_profile must be an object")
    profile = json.loads(json.dumps(profile))
    if mode == "no_abstention":
        obligation = obligations.get(obligation_id)
        if obligation:
            # Baseline imputes missing facts as false predicates instead of abstaining.
            active = [v for v in obligation.versions if v.is_active(reference_date)]
            for version in active:
                _set_missing_false(version.applicability_condition, profile)
    result = resolve_obligation(
        obligation_id=obligation_id,
        obligations=obligations,
        reference_date=reference_date,
        entity_profile=profile,
        policy=policy,
    )
    return {
        "benchmark_item_id": item["benchmark_item_id"],
        "outcome": result.outcome.value if result is not None else None,
        "reason": result.reason if result is not None else "Dropped by no-version policy.",
        "version_id": result.version_id if result is not None else None,
        "clause_id": result.clause_id if result is not None else None,
        "source_url": result.source_url if result is not None else None,
        "missing_facts": list(result.missing_facts) if result is not None else [],
        "evidence": list(result.evidence) if result is not None else [],
    }


def run_experiments(benchmark_path: str, catalog_path: str, policy: ResolverPolicy) -> dict[str, Any]:
    items = read_jsonl(benchmark_path)
    gold_items = [
        item for item in items
        if item.get("annotation_status") == "gold_verified"
        and item.get("gold_outcome") in {"Applicable", "Not applicable", "Indeterminate", "Conflict"}
    ]
    catalog = load_catalog(catalog_path)
    modes = {
        "full_taarr": ("full", "Full configured temporal and applicability resolver."),
        "ablation_no_temporal": ("no_temporal", "Uses latest recorded version regardless of reference date."),
        "ablation_no_abstention": ("no_abstention", "Imputes absent applicability facts to force predicates false; diagnostic only."),
        "ablation_no_exemptions_dependencies": ("no_exceptions_dependencies", "Removes exemption and dependency rules before resolution."),
    }
    output: dict[str, Any] = {
        "benchmark_path": benchmark_path,
        "catalog_path": catalog_path,
        "policy": {
            "no_version": policy.no_version.value,
            "missing_facts": policy.missing_facts.value,
            "unknown_precedence": policy.unknown_precedence.value,
        },
        "input_n": len(items),
        "gold_n": len(gold_items),
        "drafts_excluded_n": len(items) - len(gold_items),
        "experiments": {},
        "warning": "Ablations are research baselines, not production behavior. Empty gold data means metrics are unavailable.",
    }
    for name, (mode, description) in modes.items():
        variant = _catalog_variant(catalog, mode)
        predictions = [_resolve_item(item, variant, policy, mode) for item in gold_items]
        metric_predictions = [
            {"benchmark_item_id": pred["benchmark_item_id"], "outcome": pred["outcome"]}
            for pred in predictions if pred["outcome"] is not None
        ]
        metrics = score(gold_items, metric_predictions)
        output["experiments"][name] = {
            "description": description,
            "metrics": metrics,
            "predictions": predictions,
        }
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run full TAARR and ablation experiments on gold items.")
    parser.add_argument("--benchmark", default="data/benchmark/benchmark.jsonl")
    parser.add_argument("--catalog", default="data/obligations/obligations.jsonl")
    parser.add_argument("--output", default="reports/experiments/latest.json")
    args = parser.parse_args(argv)
    try:
        policy = _policy_from_env()
        result = run_experiments(args.benchmark, args.catalog, policy)
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2) + "\\n", encoding="utf-8")
        print(json.dumps({
            "status": "completed",
            "output": str(destination),
            "gold_n": result["gold_n"],
            "drafts_excluded_n": result["drafts_excluded_n"],
            "metrics_status": {
                name: experiment["metrics"]["status"]
                for name, experiment in result["experiments"].items()
            },
            "note": result["warning"],
        }, indent=2))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
