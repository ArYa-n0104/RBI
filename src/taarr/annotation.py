"""Annotation quality checks for the TAARR benchmark.

This module reports inter-annotator agreement from independently entered labels.
It does not adjudicate labels, infer legal truth, or promote draft items to gold.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .dataset import OUTCOMES


def load_items(path: str | Path) -> list[dict[str, Any]]:
    """Load JSONL annotation records; fail clearly on malformed input."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Annotation ledger not found: {source}")
    items: list[dict[str, Any]] = []
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
                raise ValueError(f"{source}:{line_number}: expected a JSON object")
            items.append(item)
    return items


def agreement_report(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute Cohen's kappa over items with two valid independent outcomes."""
    labels = sorted(OUTCOMES)
    confusion = {first: {second: 0 for second in labels} for first in labels}
    eligible = 0
    excluded = 0
    annotator_1_counts: Counter[str] = Counter()
    annotator_2_counts: Counter[str] = Counter()

    for item in items:
        annotations = item.get("annotations")
        if not isinstance(annotations, dict):
            excluded += 1
            continue
        first = annotations.get("annotator_1")
        second = annotations.get("annotator_2")
        first_outcome = first.get("outcome") if isinstance(first, dict) else None
        second_outcome = second.get("outcome") if isinstance(second, dict) else None
        if first_outcome not in OUTCOMES or second_outcome not in OUTCOMES:
            excluded += 1
            continue
        eligible += 1
        confusion[first_outcome][second_outcome] += 1
        annotator_1_counts[first_outcome] += 1
        annotator_2_counts[second_outcome] += 1

    if not eligible:
        return {
            "n_paired": 0,
            "n_excluded": excluded,
            "observed_agreement": None,
            "expected_agreement": None,
            "cohen_kappa": None,
            "interpretation": "not computable: no items have two valid independent labels",
            "labels": labels,
            "confusion_matrix": confusion,
        }

    observed = sum(confusion[label][label] for label in labels) / eligible
    expected = sum(
        annotator_1_counts[label] * annotator_2_counts[label]
        for label in labels
    ) / (eligible * eligible)
    if expected == 1.0:
        kappa = 1.0 if observed == 1.0 else None
    else:
        kappa = (observed - expected) / (1.0 - expected)

    return {
        "n_paired": eligible,
        "n_excluded": excluded,
        "observed_agreement": round(observed, 6),
        "expected_agreement": round(expected, 6),
        "cohen_kappa": round(kappa, 6) if kappa is not None else None,
        "interpretation": (
            "not defined because expected agreement is 1 and observed agreement is not 1"
            if kappa is None else
            "agreement statistic only; not evidence that the legal label is correct"
        ),
        "labels": labels,
        "confusion_matrix": confusion,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report inter-annotator agreement; does not adjudicate or promote labels."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="data/benchmark/draft_items.jsonl",
        help="JSONL file containing annotator_1 and annotator_2 outcome records",
    )
    args = parser.parse_args(argv)
    try:
        report = agreement_report(load_items(args.path))
    except (OSError, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    if report["n_paired"] == 0:
        print(
            "NOTE: no paired annotations yet; do not report kappa as zero.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
