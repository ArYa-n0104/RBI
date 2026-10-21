# Illustrative comparison runner (not the real evaluation)

`scripts/illustrative_eval.py` runs the full TAARR resolver and its three ablations
(`ablation_no_temporal`, `ablation_no_abstention`, `ablation_no_exemptions_dependencies`)
against `data/benchmark/draft_items.jsonl` and scores them against the draft items'
`gold_outcome` field.

**This is not the project's real evaluation.** `src/taarr/evaluate.py` and
`src/taarr/experiments.py` are intentionally untouched: they still refuse to score
anything that is not `annotation_status == "gold_verified"`, and the real benchmark
(`data/benchmark/benchmark.jsonl`) is still empty. This script exists only as a
sanity check that the resolver's own ablations behave the way the research design
expects, run on today's data, before real gold labels exist to measure it properly.

## Run it

```bash
python scripts/illustrative_eval.py
```

Writes `reports/illustrative/latest.json` (gitignored -- a generated output, not
checked in) and prints a summary table.

## Result as of 2026-10-21 (60 obligations, 127 draft items, all source-text human-confirmed)

| Configuration | Accuracy | Macro F1 | Coverage |
|---|---|---|---|
| full_taarr | 1.000 | 0.750 | 1.000 |
| ablation_no_temporal | 1.000 | 0.750 | 1.000 |
| ablation_no_abstention | 0.976 | 0.661 | 1.000 |
| ablation_no_exemptions_dependencies | 0.976 | 0.717 | 1.000 |

## Why these numbers cannot be reported as real accuracy -- three specific reasons

1. **No gold data.** These are draft hypotheses written by one person (the assistant,
   checked once by the project owner for source-text accuracy only), not a verified
   answer key. Zero items are `gold_verified`.
2. **Circularity.** The draft items were generated from the same obligation records
   the resolver reads, specifically to produce one expected-positive and one
   expected-negative case per obligation. The resolver scoring 100% against its own
   construction is expected, not evidence of correctness against an independent
   test. A real evaluation needs items an independent annotator wrote or checked
   without seeing the resolver's expected answer.
3. **Macro F1 artifact.** The draft set has zero `Conflict` examples, so that class
   scores precision/recall/F1 = 0 by definition (no true or predicted instances),
   which pulls every configuration's 4-class macro F1 down by a fixed amount
   regardless of how well the other three classes are handled. This is a benchmark
   coverage gap (see `docs/DATASET_SPEC.md` on not inventing Conflict examples just
   to balance classes), not a resolver weakness.

## What this result is actually useful for

The *relative* ordering across configurations is a legitimate, if small, internal
consistency check: removing abstention or exemption/dependency handling measurably
hurts macro F1 (0.750 -> 0.661 / 0.717) even though accuracy barely moves, because
the handful of `Indeterminate` items are exactly where those mechanisms matter. That
the ablations are implemented, run, and visibly differ from the full resolver is
useful evidence the research design's distinctions are real in code -- it is not
evidence of the resolver's real-world accuracy.
