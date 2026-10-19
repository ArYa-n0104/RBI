# Experiment Runner

Run the full deterministic resolver and three controlled ablations on the gold-verified rows in the benchmark JSONL. Draft rows are always excluded from scoring.

## Run locally

From the repository root with the virtual environment activated and all three resolver policies configured in `.env`:

```bash
python -m taarr.experiments --benchmark data/benchmark/benchmark.jsonl --catalog data/obligations/obligations.jsonl --output reports/experiments/latest.json
```

The command writes a JSON report with policy settings, experiment descriptions, predictions/evidence, class metrics and confusion matrices. It prints a short status summary. Reports under `reports/experiments/` are generated outputs and should be reviewed before committing; do not commit reports containing sensitive profiles.

## Compared configurations

- `full_taarr`: configured temporal and applicability resolver.
- `ablation_no_temporal`: selects the latest recorded version regardless of reference date. This is intentionally a diagnostic baseline, not a safe resolver.
- `ablation_no_abstention`: imputes absent applicability facts to force predicates false. This is a simple documented baseline, not production behavior.
- `ablation_no_exemptions_dependencies`: removes exemption and dependency rules before resolution.

## Important interpretation limits

- Only rows with `annotation_status = "gold_verified"` and a valid four-way `gold_outcome` are scored.
- Empty gold data returns `status = "unavailable"`, not 0 accuracy.
- The no-temporal and no-abstention configurations are controlled approximations. Their assumptions must be disclosed in a paper.
- This runner does not prove legal correctness or novelty by itself. It produces comparable measurements once gold labels exist.
- Compare all configurations on the same frozen test items. Report the dataset snapshot, Git commit, policy and missing prediction coverage.
