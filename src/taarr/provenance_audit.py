"""Structural and provenance checks for TAARR catalog and benchmark records.

This tool checks traceability metadata; it cannot decide whether a legal interpretation
is correct. Human source verification and adjudication remain mandatory.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from .dataset import OUTCOMES
from .evaluate import read_jsonl
from .sources import is_official_https_url


def _issue(code: str, severity: str, location: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "location": location, "message": message}


def audit_records(catalog: list[dict[str, Any]], benchmark: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    versions: dict[str, dict[str, Any]] = {}
    clauses: set[str] = set()
    obligations: set[str] = set()
    for record in catalog:
        if isinstance(record.get("obligation_id"), str):
            obligations.add(record["obligation_id"])
    for index, record in enumerate(catalog, 1):
        loc = f"catalog:{index}"
        version_id = record.get("version_id")
        clause_id = record.get("clause_id")
        if isinstance(version_id, str):
            if version_id in versions:
                issues.append(_issue("DUPLICATE_VERSION", "error", loc, f"Duplicate version_id {version_id}."))
            versions[version_id] = record
        if isinstance(clause_id, str):
            clauses.add(clause_id)
        source = record.get("source_url")
        if not isinstance(source, str) or not is_official_https_url(source):
            issues.append(_issue("NON_OFFICIAL_SOURCE", "error", loc, "source_url must be HTTPS on an official RBI/SEBI domain."))
        if record.get("verification_status") != "gold_verified":
            issues.append(_issue("SOURCE_NOT_GOLD_VERIFIED", "warning", loc, "Catalog record is not marked gold_verified; do not present it as independently verified gold."))
        start, end = record.get("effective_from"), record.get("effective_to")
        if isinstance(start, str) and isinstance(end, str) and end <= start:
            issues.append(_issue("INVALID_INTERVAL", "error", loc, "effective_to must be later than effective_from."))
        for relation_type in ("exemptions", "dependencies"):
            relations = record.get(relation_type, [])
            if not isinstance(relations, list):
                issues.append(_issue("INVALID_RELATIONS", "error", loc, f"{relation_type} must be a list."))
                continue
            for rel_index, relation in enumerate(relations, 1):
                rloc = f"{loc}.{relation_type}[{rel_index}]"
                if not isinstance(relation, dict):
                    issues.append(_issue("INVALID_RELATION", "error", rloc, "Relation must be an object."))
                    continue
                url = relation.get("official_url")
                if not isinstance(url, str) or not is_official_https_url(url):
                    issues.append(_issue("RELATION_SOURCE_INVALID", "error", rloc, "Relation must cite an official HTTPS RBI/SEBI source."))
                if relation_type == "dependencies":
                    target = relation.get("target_obligation_id") or relation.get("to_obligation_id")
                    if target not in obligations:
                        issues.append(_issue("DEPENDENCY_TARGET_UNRESOLVED", "warning", rloc, f"Dependency target {target!r} is not in the catalog obligation set."))
    item_ids: set[str] = set()
    groups: dict[str, set[str]] = defaultdict(set)
    gold_count = 0
    outcome_counts = {label: 0 for label in sorted(OUTCOMES)}
    for index, item in enumerate(benchmark, 1):
        loc = f"benchmark:{index}"
        item_id = item.get("benchmark_item_id")
        if not isinstance(item_id, str) or not item_id:
            issues.append(_issue("MISSING_ITEM_ID", "error", loc, "benchmark_item_id is required."))
        elif item_id in item_ids:
            issues.append(_issue("DUPLICATE_ITEM_ID", "error", loc, f"Duplicate benchmark_item_id {item_id}."))
        else:
            item_ids.add(item_id)
        group, split = item.get("split_group_id"), item.get("split")
        if isinstance(group, str) and isinstance(split, str) and split:
            groups[group].add(split)
        if item.get("annotation_status") == "gold_verified":
            if item.get("gold_outcome") not in OUTCOMES:
                issues.append(_issue("GOLD_OUTCOME_INVALID", "error", loc, "gold_verified item must have a valid four-way outcome."))
            else:
                gold_count += 1
                outcome_counts[item["gold_outcome"]] += 1
            annotations = item.get("annotations")
            if not isinstance(annotations, dict) or not isinstance(annotations.get("adjudication"), dict):
                issues.append(_issue("GOLD_ADJUDICATION_MISSING", "error", loc, "gold_verified item requires adjudication metadata."))
            for ref_index, ref in enumerate(item.get("gold_obligations", []), 1):
                rloc = f"{loc}.gold_obligations[{ref_index}]"
                if not isinstance(ref, dict):
                    issues.append(_issue("INVALID_GOLD_REFERENCE", "error", rloc, "Gold obligation reference must be an object."))
                    continue
                url = ref.get("official_url")
                if not isinstance(url, str) or not is_official_https_url(url):
                    issues.append(_issue("GOLD_SOURCE_INVALID", "error", rloc, "Gold source must use an official RBI/SEBI HTTPS URL."))
                if ref.get("version_id") not in versions:
                    issues.append(_issue("GOLD_VERSION_UNRESOLVED", "error", rloc, f"version_id {ref.get('version_id')!r} is absent from catalog."))
                else:
                    catalog_version = versions[ref["version_id"]]
                    if catalog_version.get("verification_status") != "gold_verified":
                        issues.append(_issue("GOLD_VERSION_NOT_VERIFIED", "error", rloc, "Gold item references a catalog version that is not independently source-verified."))
                    if ref.get("clause_id") != catalog_version.get("clause_id"):
                        issues.append(_issue("GOLD_CLAUSE_MISMATCH", "error", rloc, "Gold clause_id does not match the catalog version."))
    leakage = sorted(group for group, splits in groups.items() if len(splits) > 1)
    for group in leakage:
        issues.append(_issue("SPLIT_GROUP_LEAKAGE", "error", group, "Related items appear in more than one split."))
    errors = sum(issue["severity"] == "error" for issue in issues)
    warnings = sum(issue["severity"] == "warning" for issue in issues)
    return {
        "catalog_n": len(catalog),
        "obligation_n": len(obligations),
        "version_n": len(versions),
        "benchmark_n": len(benchmark),
        "gold_verified_n": gold_count,
        "gold_outcome_counts": outcome_counts,
        "split_group_leakage": leakage,
        "error_count": errors,
        "warning_count": warnings,
        "status": "blocked" if errors else ("needs_review" if warnings or gold_count == 0 else "checks_passed"),
        "issues": issues,
        "limitations": [
            "Structural checks do not prove legal interpretation or completeness of amendment lineage.",
            "Source-located records are not gold-verified unless independently reviewed and adjudicated.",
            "An empty gold benchmark means research performance metrics are unavailable.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit TAARR source provenance and benchmark readiness.")
    parser.add_argument("--catalog", default="data/obligations/obligations.jsonl")
    parser.add_argument("--benchmark", default="data/benchmark/benchmark.jsonl")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    try:
        result = audit_records(read_jsonl(args.catalog), read_jsonl(args.benchmark))
        payload = json.dumps(result, indent=2) + "\n"
        if args.output:
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 1 if result["status"] == "blocked" else 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
