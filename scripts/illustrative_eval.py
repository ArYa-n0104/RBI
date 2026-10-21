"""Illustrative-only comparison: full TAARR resolver vs. its own ablations.

THIS IS NOT THE PROJECT'S REAL EVALUATION. It is kept deliberately separate from
src/taarr/evaluate.py and src/taarr/experiments.py, which refuse to score anything
that is not annotation_status == "gold_verified" -- by design, because the benchmark
has no gold-verified items yet (see docs/PENDING_TWO_PERSON_VERIFICATION.txt).

This script instead scores against draft_items.jsonl's `gold_outcome`, which is a
DRAFT HYPOTHESIS written by one person, not a verified answer key. Every output of
this script is tagged "ILLUSTRATIVE_NOT_VERIFIED": true and must never be reported,
quoted, or plotted as if it were a real accuracy/F1 number. Its only legitimate use
is a sanity check: does the resolver's own ablations behave the way the research
design says they should (full > no_temporal > no_abstention > no_exemptions),
before real gold data exists to measure it properly.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from taarr.catalog import load_catalog  # noqa: E402
from taarr.dataset import OUTCOMES  # noqa: E402
from taarr.experiments import _catalog_variant, _policy_from_env, _resolve_item  # noqa: E402

LABELS = sorted(OUTCOMES)

ILLUSTRATIVE_WARNING = (
    "ILLUSTRATIVE ONLY -- NOT THE PROJECT'S REAL EVALUATION. Scored against "
    "draft_items.jsonl's gold_outcome, a one-person draft hypothesis, not a "
    "verified answer key. 0 benchmark items are gold_verified as of this run. "
    "Do not report these numbers as accuracy, F1, or any other verified metric "
    "in the paper. See docs/PENDING_TWO_PERSON_VERIFICATION.txt."
)


def _read_jsonl(path: str) -> list[dict]:
    items = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.append(json.loads(line))
    return items


def _score_against_draft_hypothesis(items: list[dict], predictions: list[dict]) -> dict:
    """Same confusion-matrix mechanics as evaluate.score, but against ALL draft
    hypothesis outcomes rather than gold_verified rows. Never call this gold."""
    hyp = {}
    for item in items:
        outcome = item.get("gold_outcome")
        if outcome in OUTCOMES:
            hyp[item["benchmark_item_id"]] = outcome
    pred = {p["benchmark_item_id"]: p["outcome"] for p in predictions if p.get("outcome") in OUTCOMES}
    matched = sorted(set(hyp) & set(pred))
    missing = sorted(set(hyp) - set(pred))
    cm = {a: {b: 0 for b in LABELS} for a in LABELS}
    for key in matched:
        cm[hyp[key]][pred[key]] += 1
    per_class = {}
    f1s = []
    for label in LABELS:
        tp = cm[label][label]
        fp = sum(cm[a][label] for a in LABELS if a != label)
        fn = sum(cm[label][b] for b in LABELS if b != label)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        per_class[label] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "support": sum(cm[label].values())}
        f1s.append(f)
    return {
        "hypothesis_n": len(hyp),
        "matched_n": len(matched),
        "coverage": round(len(matched) / len(hyp), 4) if hyp else None,
        "illustrative_accuracy": round(sum(cm[x][x] for x in LABELS) / len(matched), 4) if matched else None,
        "illustrative_macro_f1": round(sum(f1s) / len(LABELS), 4) if matched else None,
        "per_class": per_class,
        "confusion_matrix": cm,
        "missing_prediction_ids": missing,
    }


def run(draft_path: str, catalog_path: str) -> dict:
    items = _read_jsonl(draft_path)
    policy = _policy_from_env()
    catalog = load_catalog(catalog_path)
    modes = {
        "full_taarr": ("full", "Full configured temporal and applicability resolver."),
        "ablation_no_temporal": ("no_temporal", "Uses latest recorded version regardless of reference date."),
        "ablation_no_abstention": ("no_abstention", "Imputes absent applicability facts to force predicates false; diagnostic only."),
        "ablation_no_exemptions_dependencies": ("no_exceptions_dependencies", "Removes exemption and dependency rules before resolution."),
    }
    report: dict = {
        "ILLUSTRATIVE_NOT_VERIFIED": True,
        "warning": ILLUSTRATIVE_WARNING,
        "draft_path": draft_path,
        "catalog_path": catalog_path,
        "items_n": len(items),
        "annotation_status_counts": dict(Counter(i.get("annotation_status") for i in items)),
        "experiments": {},
    }
    for name, (mode, description) in modes.items():
        variant = _catalog_variant(catalog, mode)
        predictions = [_resolve_item(item, variant, policy, mode) for item in items]
        metrics = _score_against_draft_hypothesis(items, predictions)
        report["experiments"][name] = {"description": description, "metrics": metrics}
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", default="data/benchmark/draft_items.jsonl")
    parser.add_argument("--catalog", default="data/obligations/obligations.jsonl")
    parser.add_argument("--output", default="reports/illustrative/latest.json")
    args = parser.parse_args(argv)

    report = run(args.draft, args.catalog)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("=" * 72)
    print(ILLUSTRATIVE_WARNING)
    print("=" * 72)
    print(f"{'Configuration':<36}{'Accuracy':>10}{'Macro F1':>10}{'Coverage':>10}")
    for name, experiment in report["experiments"].items():
        m = experiment["metrics"]
        acc = f"{m['illustrative_accuracy']:.3f}" if m["illustrative_accuracy"] is not None else "n/a"
        f1 = f"{m['illustrative_macro_f1']:.3f}" if m["illustrative_macro_f1"] is not None else "n/a"
        cov = f"{m['coverage']:.3f}" if m["coverage"] is not None else "n/a"
        print(f"{name:<36}{acc:>10}{f1:>10}{cov:>10}")
    print(f"\nFull report written to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
