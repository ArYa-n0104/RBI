# TAARR Dataset Specification

This specification implements the dataset requirements in the *TAARR Build Plan* (Novelty 1, pp. 2–3) and *TAARR Review Paper* (Table III and benchmark construction, pp. 12–13). It intentionally does not contain fabricated regulatory labels.

## Research unit

**One benchmark item is one target-obligation decision** for a natural-language question, a reference date, and one entity profile. This keeps the primary gold outcome unambiguous for accuracy, macro-F1, abstention, and ablation metrics. An item's `gold_obligations` lists the relevant target and supporting/source obligations; `target_obligation_id` identifies which obligation the single `gold_outcome` labels.

The live application may return multiple obligation decisions for one user query. For benchmark scoring, create one item per target obligation and preserve the same query/date/profile where necessary. When grouping examples for train/dev/test or evaluation, keep items tied to the same obligation/version/amendment lineage in the same split to reduce leakage.

## Required item fields

Each non-empty line of `data/benchmark/benchmark.jsonl` is one JSON object:

| Field | Meaning |
|---|---|
| `benchmark_item_id` | Stable unique ID, e.g. `TAARR-BENCH-0001`. |
| `query` | Natural-language question about regulatory applicability. |
| `reference_date` | Date (ISO 8601 `YYYY-MM-DD`) on which applicability is evaluated. |
| `entity_profile` | Known entity type and relevant attributes. Include only known facts; do not silently infer omitted attributes. |
| `missing_facts_intentionally_omitted` | Attribute names deliberately withheld for abstention tests. Empty array when none. |
| `target_obligation_id` | Stable ID of the obligation whose outcome is labelled in this item. |
| `gold_obligations` | Relevant clause/obligation records with instrument/version IDs, clause identifiers, official URLs, and the source text or a short faithful extract for annotation. |
| `effective_dates` | Date and version evidence; publication and effective dates must remain distinct. The validity interval is start-inclusive and end-exclusive. |
| `exemptions_dependencies` | Relevant exemption, exclusion, dependency and cross-reference records, including their priority only where a source establishes one. |
| `gold_outcome` | Exactly one of `Applicable`, `Not applicable`, `Indeterminate`, `Conflict`. |
| `gold_explanation` | Concise explanation grounded in the official evidence and identifying why the gold outcome follows. |
| `annotation_status` | `draft`, `dual_annotated`, `adjudicated`, or `gold_verified`. |
| `annotations` | Independent annotator outcomes/notes and adjudication metadata; see annotation protocol below. |
| `scenario_tags` | Tags used to stratify evaluation, e.g. `pre_amendment`, `post_amendment`, `missing_fact`, `exemption`. |
| `split_group_id` | Group identifier preventing related versions/amendment variants leaking across benchmark splits. |

### Obligation/version references

Each `gold_obligations` element should include:
- `obligation_id`: stable identity across amendment events where the normative obligation continues;
- `version_id`: a specific text/version, not the stable obligation ID;
- `instrument_id`, `clause_id`, `official_url`;
- `clause_text`: exact relevant text or a clearly identified faithful extract; preserve subsection numbering;
- `source_publication_date`, `effective_from`, `effective_to` (nullable);
- `amendment_lineage`: ordered event references or IDs linking the source wording to earlier/later versions;
- `role`: `target`, `supporting`, `exemption`, `dependency`, or `definition`.

An `effective_to` of null means the end date is not recorded in the dataset; it is not proof that the provision is currently in force. Validity uses `effective_from <= reference_date < effective_to`, with null treated as an open end only after the source record has been verified.

### Relation records

A relation record should include `relation_id`, `relation_type`, `from_clause_id`, `to_clause_id`, `official_url`, `effective_from`, `effective_to`, `condition` (structured when possible), `priority` (nullable unless legally grounded), and `verification_status`.

Recognised relation types for the data model include `AMENDS`, `REPEALS`, `SUPERSEDES`, `EXEMPTS`, `EXCLUDES`, `DEPENDS_ON`, `DEFINES`, `CROSS_REFERENCES`, and `OVERRULES`. These are schema vocabulary, not a claim that every relation exists in the corpus.

## Label semantics

- **Applicable:** the target obligation is in force on the reference date, the entity conditions evaluate true, no active overriding exemption removes it, and known dependencies resolve compatibly.
- **Not applicable:** the target is in scope for evaluation but an established condition is false, an applicable exemption/exclusion removes it, or a dependency is unsatisfied under the final adjudicated policy.
- **Indeterminate:** one or more essential entity facts or pieces of source/version evidence are missing, so a defensible binary applicability result cannot be made.
- **Conflict:** authoritative in-force records produce incompatible results and no documented precedence rule resolves them.

These semantics must be applied consistently and recorded in adjudication notes. The Build Plan and Review Paper disagree on the special case where no target version is in force; that unresolved policy is recorded in [DECISIONS.md](DECISIONS.md). Do not create gold cases for that edge case until the decision is frozen.

## Annotation protocol

1. Acquire and archive the official source/version evidence; record URL and acquisition metadata.
2. Segment provisions at clause/sub-clause granularity. Do not treat an entire instrument as one version when only a paragraph changes.
3. Prepare items that cover amendment-sensitive dates, distinct entity categories, active exemptions, dependencies, deliberately missing facts, and genuine conflicts where supported by official sources.
4. Have two annotators label items independently, without seeing each other's outcome.
5. Adjudicate disagreement against the official text and amendment lineage; record the rationale.
6. Mark `gold_verified` only after source URLs, clause IDs, effective dates, related provisions, gold outcome and explanation have been checked.
7. Measure agreement using Cohen's kappa on the independent labels before adjudication. Also report counts per outcome and per scenario tag.
8. Do not invent Conflict examples merely to balance classes. Include them only when sources genuinely cannot be reconciled automatically.
9. Report annotation limitations and the effect of manual curation, as required by the review's threats-to-validity section.

Recommended final benchmark size in the project documents: **100–200 items**. The initial corpus should be narrow and deep, beginning with the RBI KYC Master Direction and SEBI LODR Regulations, subject to confirming source-version feasibility.

## Validation and release

Run:

```bash
python -m taarr.dataset validate data/benchmark/benchmark.jsonl
pytest
```

The validator checks file structure and core invariants; it cannot certify legal correctness. Human source verification remains mandatory. Keep raw official PDFs/text extracts, normalized clause records, and benchmark item labels logically separate, and release only material permitted for redistribution.