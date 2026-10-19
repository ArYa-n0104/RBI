# Provenance and Gold-Readiness Audit

Run from the repository root:

```bash
python -m taarr.provenance_audit
```

Optional explicit paths and JSON output:

```bash
python -m taarr.provenance_audit --catalog data/obligations/obligations.jsonl --benchmark data/benchmark/benchmark.jsonl --output reports/provenance_audit/latest.json
```

The audit checks official RBI/SEBI HTTPS source domains, version and item ID uniqueness, date intervals, relation source links, benchmark references to known clause versions, adjudication metadata for gold items, and split-group leakage.

Statuses:
- `checks_passed`: structural checks passed and at least one gold item is present.
- `needs_review`: no blocking structural errors, but warnings exist or the gold benchmark is empty.
- `blocked`: one or more blocking structural errors exist.

This is not a legal validation system. It cannot confirm that a source is the latest version, that an amendment lineage is complete, or that an outcome is legally correct. Source verification and independent annotation/adjudication remain human responsibilities. The current source-located catalog record should remain unverified until that review is completed.
