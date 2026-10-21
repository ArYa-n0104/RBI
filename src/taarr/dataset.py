"""Structural validation for the TAARR JSONL benchmark.

This validates format and research-data invariants, not legal correctness.
Human source verification and adjudication remain required.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

OUTCOMES = {"Applicable", "Not applicable", "Indeterminate", "Conflict"}
ANNOTATION_STATUSES = {"draft", "single_pass_reviewed", "dual_annotated", "adjudicated", "gold_verified"}
# "single_pass_reviewed": meaning changed 2026-10-21 (see D-005 in docs/DECISIONS.md).
# The project owner opted out of the annotator/reviewer role for the 2026-10-21
# bulk-added obligations. From that date, this status means the assistant independently
# re-fetched the clause from the official source a second time and the two fetches
# agreed (corrected if they didn't) -- NOT that a human reviewed or approved it, and
# NOT the project's two-independent-annotator protocol. No inter-annotator agreement is
# implied. This must never be scored as gold; evaluate.py/experiments.py/
# provenance_audit.py only ever score/require annotation_status == "gold_verified", so
# this status is automatically excluded from any reported metric.
REQUIRED_FIELDS = {
    "benchmark_item_id",
    "query",
    "reference_date",
    "entity_profile",
    "missing_facts_intentionally_omitted",
    "target_obligation_id",
    "gold_obligations",
    "effective_dates",
    "exemptions_dependencies",
    "gold_outcome",
    "gold_explanation",
    "annotation_status",
    "annotations",
    "scenario_tags",
    "split_group_id",
}


def _is_iso_date(value: Any) -> bool:
    """Accept only canonical YYYY-MM-DD dates, not all alternate ISO representations."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _is_https_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _valid_annotation(record: Any) -> bool:
    return isinstance(record, dict) and record.get("outcome") in OUTCOMES


def validate_item(item: Any, line_number: int = 1) -> list[str]:
    """Return human-readable errors for one benchmark JSON object."""
    errors: list[str] = []
    prefix = f"line {line_number}"

    if not isinstance(item, dict):
        return [f"{prefix}: expected a JSON object"]

    missing = sorted(REQUIRED_FIELDS - item.keys())
    if missing:
        errors.append(f"{prefix}: missing required fields: {', '.join(missing)}")

    if not isinstance(item.get("benchmark_item_id"), str) or not item.get("benchmark_item_id", "").strip():
        errors.append(f"{prefix}: benchmark_item_id must be a non-empty string")
    if not isinstance(item.get("query"), str) or not item.get("query", "").strip():
        errors.append(f"{prefix}: query must be a non-empty string")
    if not _is_iso_date(item.get("reference_date")):
        errors.append(f"{prefix}: reference_date must be an ISO date YYYY-MM-DD")
    if not isinstance(item.get("entity_profile"), dict):
        errors.append(f"{prefix}: entity_profile must be an object")
    if not isinstance(item.get("missing_facts_intentionally_omitted"), list) or not all(
        isinstance(value, str) and value.strip()
        for value in item.get("missing_facts_intentionally_omitted", [])
    ):
        errors.append(f"{prefix}: missing_facts_intentionally_omitted must be a list of non-empty strings")

    obligations = item.get("gold_obligations")
    if not isinstance(obligations, list) or not obligations:
        errors.append(f"{prefix}: gold_obligations must be a non-empty array")
        obligations = []
    obligation_ids: set[str] = set()
    target_records: list[dict[str, Any]] = []
    for idx, obligation in enumerate(obligations):
        label = f"{prefix}: gold_obligations[{idx}]"
        if not isinstance(obligation, dict):
            errors.append(f"{label} must be an object")
            continue
        for field in ("obligation_id", "version_id", "instrument_id", "clause_id", "role"):
            if not isinstance(obligation.get(field), str) or not obligation.get(field, "").strip():
                errors.append(f"{label}.{field} must be a non-empty string")
        if isinstance(obligation.get("obligation_id"), str):
            obligation_ids.add(obligation["obligation_id"])
        if obligation.get("role") == "target":
            target_records.append(obligation)
        if not _is_https_url(obligation.get("official_url")):
            errors.append(f"{label}.official_url must be an HTTPS URL")
        if not isinstance(obligation.get("clause_text"), str) or not obligation.get("clause_text", "").strip():
            errors.append(f"{label}.clause_text must contain official text or a faithful extract")
        if obligation.get("role") not in {"target", "supporting", "exemption", "dependency", "definition"}:
            errors.append(f"{label}.role is not a supported role")
    target_id = item.get("target_obligation_id")
    if isinstance(target_id, str) and obligations and target_id not in obligation_ids:
        errors.append(f"{prefix}: target_obligation_id must appear in gold_obligations")
    matching_targets = [
        obligation
        for obligation in target_records
        if obligation.get("obligation_id") == target_id
    ]
    if obligations and not matching_targets:
        errors.append(f"{prefix}: target_obligation_id must identify an obligation with role='target'")
    if len(matching_targets) > 1:
        errors.append(f"{prefix}: exactly one gold_obligations record may be the target")

    effective_dates = item.get("effective_dates")
    if not isinstance(effective_dates, list):
        errors.append(f"{prefix}: effective_dates must be an array")
        effective_dates = []
    elif not effective_dates:
        errors.append(f"{prefix}: effective_dates must contain the target version's date evidence")

    effective_version_ids: set[str] = set()
    for idx, version in enumerate(effective_dates):
        label = f"{prefix}: effective_dates[{idx}]"
        if not isinstance(version, dict):
            errors.append(f"{label} must be an object")
            continue
        for field in ("version_id", "publication_date", "effective_from", "effective_to", "amendment_lineage"):
            if field not in version:
                errors.append(f"{label}.{field} is required (effective_to may be null)")
        version_id = version.get("version_id")
        if isinstance(version_id, str):
            if version_id in effective_version_ids:
                errors.append(f"{label}: duplicate version_id {version_id!r}")
            effective_version_ids.add(version_id)
        for field in ("publication_date", "effective_from"):
            if field in version and not _is_iso_date(version[field]):
                errors.append(f"{label}.{field} must be an ISO date")
        end = version.get("effective_to")
        if end is not None and not _is_iso_date(end):
            errors.append(f"{label}.effective_to must be an ISO date or null")
        start = version.get("effective_from")
        if _is_iso_date(start) and _is_iso_date(end) and date.fromisoformat(start) >= date.fromisoformat(end):
            errors.append(f"{label}: effective_from must be earlier than effective_to")
        if not isinstance(version.get("amendment_lineage"), list):
            errors.append(f"{label}.amendment_lineage must be an array")

    for target in matching_targets:
        if target.get("version_id") not in effective_version_ids:
            errors.append(f"{prefix}: target version_id must have an effective_dates record")

    relations = item.get("exemptions_dependencies")
    if not isinstance(relations, list):
        errors.append(f"{prefix}: exemptions_dependencies must be an array")
        relations = []
    allowed_relations = {
        "AMENDS", "REPEALS", "SUPERSEDES", "EXEMPTS", "EXCLUDES",
        "DEPENDS_ON", "DEFINES", "CROSS_REFERENCES", "OVERRULES",
    }
    for idx, relation in enumerate(relations):
        label = f"{prefix}: exemptions_dependencies[{idx}]"
        if not isinstance(relation, dict):
            errors.append(f"{label} must be an object")
            continue
        for field in ("relation_id", "relation_type", "from_clause_id", "to_clause_id", "official_url"):
            if not relation.get(field):
                errors.append(f"{label}.{field} is required")
        if relation.get("relation_type") not in allowed_relations:
            errors.append(f"{label}.relation_type is not a supported relation")
        if relation.get("official_url") and not _is_https_url(relation["official_url"]):
            errors.append(f"{label}.official_url must be an HTTPS URL")

    if item.get("gold_outcome") not in OUTCOMES:
        errors.append(f"{prefix}: gold_outcome must be one of {', '.join(sorted(OUTCOMES))}")
    if not isinstance(item.get("gold_explanation"), str) or not item.get("gold_explanation", "").strip():
        errors.append(f"{prefix}: gold_explanation must be non-empty")
    if item.get("annotation_status") not in ANNOTATION_STATUSES:
        errors.append(f"{prefix}: annotation_status must be one of {', '.join(sorted(ANNOTATION_STATUSES))}")
    annotations = item.get("annotations")
    if not isinstance(annotations, dict):
        errors.append(f"{prefix}: annotations must be an object")
        annotations = {}
    if not isinstance(item.get("scenario_tags"), list) or not all(
        isinstance(tag, str) and tag.strip() for tag in item.get("scenario_tags", [])
    ):
        errors.append(f"{prefix}: scenario_tags must be a list of non-empty strings")
    if not isinstance(item.get("split_group_id"), str) or not item.get("split_group_id", "").strip():
        errors.append(f"{prefix}: split_group_id must be a non-empty string")

    status = item.get("annotation_status")
    if status in {"dual_annotated", "adjudicated", "gold_verified"}:
        for annotator in ("annotator_1", "annotator_2"):
            if not _valid_annotation(annotations.get(annotator)):
                errors.append(f"{prefix}: {status} item requires {annotator}.outcome")
    if status in {"adjudicated", "gold_verified"}:
        adjudication = annotations.get("adjudication")
        if not _valid_annotation(adjudication):
            errors.append(f"{prefix}: {status} item requires adjudication.outcome")
        elif status == "gold_verified" and item.get("gold_outcome") != adjudication.get("outcome"):
            errors.append(f"{prefix}: gold_outcome must match adjudication.outcome for gold_verified items")

    return errors


def validate_file(path: str | Path) -> tuple[int, list[str]]:
    """Validate a JSONL file; blank lines and # comment lines are ignored."""
    source = Path(path)
    if not source.exists():
        return 0, [f"file not found: {source}"]
    if not source.is_file():
        return 0, [f"not a file: {source}"]

    errors: list[str] = []
    seen_ids: set[str] = set()
    validated_count = 0
    try:
        with source.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
                    continue
                validated_count += 1
                errors.extend(validate_item(item, line_number))
                if isinstance(item, dict):
                    item_id = item.get("benchmark_item_id")
                    if isinstance(item_id, str) and item_id:
                        if item_id in seen_ids:
                            errors.append(f"line {line_number}: duplicate benchmark_item_id {item_id!r}")
                        seen_ids.add(item_id)
    except OSError as exc:
        return validated_count, [f"could not read {source}: {exc}"]
    return validated_count, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the TAARR benchmark JSONL ledger.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate JSONL structure")
    validate_parser.add_argument("path", help="path to benchmark JSONL")
    args = parser.parse_args(argv)

    if args.command == "validate":
        count, errors = validate_file(args.path)
        if errors:
            print(f"FAILED: {len(errors)} issue(s) across {count} benchmark item(s).", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print(f"OK: {count} benchmark item(s) structurally valid.")
        if count == 0:
            print("NOTE: benchmark is empty; no regulatory gold labels have been created yet.")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
