# TAARR Research Evaluation Protocol

This document operationalizes the supplied Build Plan. It distinguishes implemented mechanics from claims that require evidence.

## Research contributions to test

1. **Dataset:** manually verified entity-profile + reference-date + clause-version + four-outcome RBI/SEBI benchmark. Target 100–200 items, beginning with a narrow set of instruments with amendment history. The current benchmark is empty; this contribution is not complete.
2. **Algorithm:** deterministic obligation-level resolution integrating temporal validity, three-valued applicability conditions, exemption/dependency handling and four outcomes. Demonstrate value with comparisons and ablations.
3. **Differentiating capability:** clause/version-level provenance trail with amendment, exemption and dependency links; test evidence completeness and citation correctness.
4. **System contribution:** portable React + FastAPI architecture using JSONL files and an in-memory resolver by default. Avoid external services for reproducibility; if persistence is required later, prefer Python built-in SQLite before considering external database infrastructure.

## Dataset design
Each item labels one target obligation for a natural-language query, reference date and entity profile. Preserve publication date separately from effective date. Store stable obligation IDs separately from clause-version IDs. Split by obligation/amendment lineage, not random rows, to prevent leakage.

Stratify 100–200 target items across:
- pre-amendment and post-amendment dates;
- distinct entity types and condition thresholds;
- true and false applicability predicates;
- intentionally missing required facts (Indeterminate);
- source-grounded exemptions and dependencies;
- genuine unresolved conflicts only where official evidence supports them.

Every gold item needs two independent outcomes and rationales, adjudication, and official source/version verification. Report Cohen's kappa with paired sample size and confusion matrix. Draft rows are not gold.

## Baselines
Evaluate all systems on the same frozen test set:
- **B1 lexical retrieval + fixed outcome:** weak retrieval baseline, not a legal decision system.
- **B2 no temporal filtering:** same records and conditions but ignore effective intervals.
- **B3 no three-valued abstention:** force missing facts into a documented baseline behavior; never production policy.
- **B4 no exemptions/dependencies:** remove relation traversal.
- **B5 full TAARR:** temporal filtering, three-valued conditions, exceptions/dependencies and evidence trace.
- **Optional B6 RAG/LLM:** only after implementation; freeze and disclose model, prompts and settings.

Avoid claiming superiority over systems not actually run. Report oracle-retrieval separately from end-to-end retrieval when feasible.

## Metrics
- Four-way accuracy, macro-F1, per-outcome precision/recall/F1 and confusion matrix.
- Temporal version selection accuracy.
- Retrieval Recall@k and obligation completeness.
- Exemption/dependency accuracy on the relevant subset.
- Indeterminate precision/recall, false-decision rate on incomplete profiles, selective accuracy.
- Citation correctness and provenance completeness.
- Median and p95 latency.
- Annotation agreement (Cohen's kappa), paired n, outcome counts and adjudication rate.

## Ablations
Compare B5 with B2/B3/B4, one component removed at a time. Report changes in macro-F1 and targeted error metrics. Freeze the dataset snapshot and record commit SHA, policy settings, environment, timestamp and model/version if any.

## Reproducibility checklist
- [ ] D-001 and D-003 approved and versioned.
- [ ] Dataset split grouped by obligation/amendment lineage.
- [ ] Source snapshots and hashes recorded; redistribution rights checked.
- [ ] Gold labels independently annotated and adjudicated.
- [ ] Baseline code, configuration and outputs archived.
- [ ] Empty benchmark metrics reported as unavailable, never as zero accuracy.
- [ ] Every result identifies dataset version, commit, policy and configuration.

## Current status
The gold benchmark is empty and draft items are unverified. No measured novelty, superiority, or regulatory accuracy claim is justified yet.
