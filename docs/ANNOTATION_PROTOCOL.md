# TAARR Annotation and Agreement Protocol

This protocol keeps annotation agreement, adjudication and source verification separate. Cohen's kappa is an agreement statistic; it does not prove a label is legally correct.

## Unit and required evidence

Each benchmark row labels one target-obligation decision for a query, reference date and entity profile. Annotators must independently review the same frozen item packet, including:
- official source URL and clause/sub-clause identifier;
- source publication date separately from effective date;
- version interval and amendment lineage relevant to the reference date;
- entity-scope facts, definitions and missing required facts;
- any relevant exclusions, exemptions, dependencies and precedence language;
- a concise rationale tied to the source evidence.

Use only the four labels: `Applicable`, `Not applicable`, `Indeterminate`, and `Conflict`. Missing facts are not false facts. Do not infer a priority absent source support. Do not resolve the open policy choices in `docs/DECISIONS.md` by personal preference.

## Independent annotation and adjudication

1. Freeze the source packet and item ID before annotation.
2. Annotator 1 and Annotator 2 label independently without seeing the other's outcome or rationale.
3. Store each label and rationale under `annotations.annotator_1` and `annotations.annotator_2`.
4. Mark `dual_annotated` only when both outcomes exist.
5. Compare labels and review disagreements against official text. An adjudicator records `annotations.adjudication.outcome`, rationale, reviewer identifier and date.
6. Mark `adjudicated` when adjudication is recorded. Mark `gold_verified` only after the target version, source URL, effective dates and amendment lineage have also been checked.
7. The `gold_outcome` of a `gold_verified` item must equal the adjudicated outcome. The dataset validator enforces this equality.
8. Keep provisional rows in `data/benchmark/draft_items.jsonl`; only verified gold rows belong in `data/benchmark/benchmark.jsonl`.

## Calculate inter-annotator agreement

From the repository root:

```bash
python -m taarr.annotation data/benchmark/draft_items.jsonl
```

The report includes paired-label count, excluded/unpaired count, observed agreement, expected agreement, Cohen's kappa and a four-by-four confusion matrix. Items without two valid independent labels are excluded rather than treated as disagreements. If no paired labels exist, kappa is reported as `null`, not zero.

Report the number of paired items alongside kappa. Because four outcomes may be imbalanced, include the confusion matrix and per-outcome counts in the study report. Do not claim reliability from a tiny or non-representative subset. Kappa is not a substitute for adjudication or legal source verification.

## Before publishing a benchmark release

- [ ] The item has two independent labels and rationales.
- [ ] Disagreement, if any, has an adjudication record.
- [ ] The target obligation and exact clause version are source-grounded.
- [ ] Publication date and effective date are separately evidenced.
- [ ] No open D-001/D-003 ambiguity affects the gold outcome, or the project owner has approved and versioned the applicable policy.
- [ ] Related versions and scenarios share a split-group key to prevent train/test leakage.
- [ ] `python -m taarr.dataset validate data/benchmark/benchmark.jsonl` passes.
- [ ] `python -m taarr.annotation data/benchmark/draft_items.jsonl` has been reviewed and its paired sample size is disclosed.
