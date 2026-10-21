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
- **B6 LLM cross-check (implemented 2026-10-21):** `POST /api/v1/baseline/llm-crosscheck` (`src/taarr/llm_baseline.py`) asks Gemini to read the same clause text, entity facts and reference date independently, without ever seeing TAARR's own outcome, and reports agreement with the gold label. Model and temperature (0.0) are fixed in `llm_baseline.DEFAULT_MODEL`; the caller supplies their own API key per request and it is never persisted. This is a convenience signal, not a replacement for the two-person human verification required for gold status — state this caveat wherever B6 results are reported.

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

## Current status (2026-10-22)

The gold benchmark is **no longer empty** — this section was out of date and is
corrected here. Current state:

- 127 benchmark items, all `gold_verified` (two independent human annotation
  passes, zero disagreements, plus source-text adjudication).
- B5 (full TAARR) measured: n=127, accuracy=1.0, macro-F1=0.75.
- B6 (Gemini cross-check) implemented and runnable from the UI; see caveat below.
- B1–B4 are not separately implemented systems — see README "What's left".

**What is still not justified:** a real-world correctness or superiority
claim. The 1.0 accuracy is the resolver agreeing with labels effectively
derived from itself (see README "Circularity caveat"); it is evidence the
implementation matches its own specification, not evidence the specification
is legally correct. Closing that gap needs an independent reviewer checking
gold labels against the official clause text without seeing TAARR's output —
not yet done. The B6 agreement rate also varies a lot by sample and by Gemini
model (a 10-item run has shown anywhere from 30% to 80%), and on manual
inspection Gemini's errors cluster in one direction: it defaults to
"Applicable" for a regulated entity and misses exemptions or missing-fact
cases that should be "Not applicable" or "Indeterminate". Treat B6 numbers as
a rough, noisy signal, never as a validation of B5.
