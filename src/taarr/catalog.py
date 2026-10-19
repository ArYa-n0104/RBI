"""Load source-linked obligation versions into the deterministic TAARR model."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .models import (
    ClauseVersion,
    DependencyRule,
    ExceptionEffect,
    ExceptionRule,
    Obligation,
)


def _as_date(value: Any, field_name: str, *, nullable: bool = False) -> date | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO date string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date string") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must use canonical YYYY-MM-DD format")
    return parsed


def _object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return value


def _array(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a JSON array")
    return value


def _parse_exception(value: Any, obligation_id: str, version_id: str) -> ExceptionRule:
    item = _object(value, f"{obligation_id}/{version_id}.exemptions item")
    required_strings = ("relation_id", "clause_id", "official_url", "effect")
    for field_name in required_strings:
        if not isinstance(item.get(field_name), str) or not item[field_name].strip():
            raise ValueError(f"{obligation_id}/{version_id}.exemptions.{field_name} is required")
    condition = _object(item.get("condition"), f"{item['relation_id']}.condition")
    raw_priority = item.get("priority")
    if raw_priority is not None and (isinstance(raw_priority, bool) or not isinstance(raw_priority, int)):
        raise ValueError(f"{item['relation_id']}.priority must be an integer or null")
    start = _as_date(item.get("effective_from"), f"{item['relation_id']}.effective_from")
    end = _as_date(item.get("effective_to"), f"{item['relation_id']}.effective_to", nullable=True)
    if end is not None and start is not None and end <= start:
        raise ValueError(f"{item['relation_id']} has a non-positive effective interval")
    try:
        effect = ExceptionEffect(item["effect"])
    except ValueError as exc:
        raise ValueError(
            f"{item['relation_id']}.effect must be EXEMPT or NOT_EXEMPT"
        ) from exc
    return ExceptionRule(
        relation_id=item["relation_id"],
        clause_id=item["clause_id"],
        official_url=item["official_url"],
        condition=condition,
        effect=effect,
        effective_from=start,
        effective_to=end,
        priority=raw_priority,
    )


def _parse_dependency(value: Any, obligation_id: str, version_id: str) -> DependencyRule:
    item = _object(value, f"{obligation_id}/{version_id}.dependencies item")
    relation_id = item.get("relation_id")
    target_id = item.get("target_obligation_id") or item.get("to_obligation_id")
    clause_id = item.get("clause_id") or item.get("from_clause_id")
    source_url = item.get("official_url")
    for field_name, field_value in (
        ("relation_id", relation_id),
        ("target_obligation_id", target_id),
        ("clause_id", clause_id),
        ("official_url", source_url),
    ):
        if not isinstance(field_value, str) or not field_value.strip():
            raise ValueError(
                f"{obligation_id}/{version_id}.dependencies.{field_name} is required"
            )
    start = _as_date(item.get("effective_from"), f"{relation_id}.effective_from", nullable=True)
    end = _as_date(item.get("effective_to"), f"{relation_id}.effective_to", nullable=True)
    if end is not None and start is not None and end <= start:
        raise ValueError(f"{relation_id} has a non-positive effective interval")
    return DependencyRule(
        relation_id=relation_id,
        target_obligation_id=target_id,
        clause_id=clause_id,
        official_url=source_url,
        effective_from=start,
        effective_to=end,
    )


@dataclass(slots=True)
class Catalog:
    """An in-memory read-only view of versioned obligations plus search metadata."""

    obligations: dict[str, Obligation]
    raw_versions: dict[str, list[dict[str, Any]]]
    search_text: dict[str, str]

    @property
    def obligation_count(self) -> int:
        return len(self.obligations)

    @property
    def version_count(self) -> int:
        return sum(len(record.versions) for record in self.obligations.values())

    @property
    def clause_count(self) -> int:
        return sum(
            len({version.clause_id for version in record.versions})
            for record in self.obligations.values()
        )

    def records_for_clause(self, clause_id: str) -> list[dict[str, Any]]:
        return [
            record
            for records in self.raw_versions.values()
            for record in records
            if record.get("clause_id") == clause_id
        ]

    def records_for_obligation(self, obligation_id: str) -> list[dict[str, Any]]:
        return list(self.raw_versions.get(obligation_id, []))


def load_catalog(path: str | Path = "data/obligations/obligations.jsonl") -> Catalog:
    """Load JSONL obligation-version records; malformed records fail closed."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Obligation-version JSONL not found: {source}")

    grouped_versions: dict[str, list[ClauseVersion]] = {}
    raw_records: dict[str, list[dict[str, Any]]] = {}
    search_text: dict[str, list[str]] = {}
    seen_versions: set[str] = set()

    with source.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}:{line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{source}:{line_number}: expected a JSON object")

            for field_name in (
                "obligation_id", "version_id", "instrument_id", "regulator",
                "clause_id", "source_url", "clause_text", "clause_summary",
                "modality", "action", "verification_status",
            ):
                if not isinstance(record.get(field_name), str) or not record[field_name].strip():
                    raise ValueError(
                        f"{source}:{line_number}: {field_name} must be a non-empty string"
                    )
            obligation_id = record["obligation_id"]
            version_id = record["version_id"]
            if version_id in seen_versions:
                raise ValueError(f"{source}:{line_number}: duplicate version_id {version_id!r}")
            seen_versions.add(version_id)

            effective_from = _as_date(record.get("effective_from"), "effective_from")
            effective_to = _as_date(record.get("effective_to"), "effective_to", nullable=True)
            if effective_to is not None and effective_to <= effective_from:
                raise ValueError(
                    f"{source}:{line_number}: effective_from must precede effective_to"
                )
            condition_value = record.get("conditions")
            if condition_value is None:
                # Missing rule data must not silently turn into an always-true rule.
                condition: dict[str, Any] = {
                    "attribute": f"__condition_missing__.{obligation_id}",
                    "operator": "equals",
                    "value": True,
                }
            else:
                condition = _object(condition_value, "conditions")

            raw_exemptions = _array(record.get("exemptions", []), "exemptions")
            raw_dependencies = _array(record.get("dependencies", []), "dependencies")
            exceptions = tuple(
                _parse_exception(item, obligation_id, version_id) for item in raw_exemptions
            )
            dependencies = tuple(
                _parse_dependency(item, obligation_id, version_id) for item in raw_dependencies
            )

            precedence = record.get("precedence")
            if precedence is not None and (
                isinstance(precedence, bool) or not isinstance(precedence, int)
            ):
                raise ValueError(f"{source}:{line_number}: precedence must be integer or null")

            clause_version = ClauseVersion(
                obligation_id=obligation_id,
                version_id=version_id,
                clause_id=record["clause_id"],
                official_url=record["source_url"],
                clause_text=record["clause_text"],
                effective_from=effective_from,
                effective_to=effective_to,
                applicability_condition=condition,
                exemptions=exceptions,
                dependencies=dependencies,
                precedence=precedence,
                verification_status=record["verification_status"],
            )
            grouped_versions.setdefault(obligation_id, []).append(clause_version)
            raw_records.setdefault(obligation_id, []).append(record)
            search_fields = (
                record.get("regulator", ""),
                record.get("instrument_title", ""),
                record.get("instrument_id", ""),
                record.get("clause_id", ""),
                record.get("clause_text", ""),
                record.get("clause_summary", ""),
                record.get("action", ""),
                " ".join(record.get("subject_scope", [])) if isinstance(record.get("subject_scope"), list) else "",
            )
            search_text.setdefault(obligation_id, []).extend(
                str(field).lower() for field in search_fields if field
            )

    obligations = {
        obligation_id: Obligation(obligation_id, tuple(versions))
        for obligation_id, versions in grouped_versions.items()
    }
    return Catalog(
        obligations=obligations,
        raw_versions=raw_records,
        search_text={key: " ".join(values) for key, values in search_text.items()},
    )
