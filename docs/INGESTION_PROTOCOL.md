# Clause-Level Ingestion Protocol

This protocol supports the TAARR Build Plan's offline ingestion flow and Novelty 1 dataset work. It distinguishes a source document, a stable obligation, a clause version, and a benchmark item.

## Bootstrap source selected

The first clause-level record is RBI KYC paragraph 38(e), introduced by RBI/2025-26/51 dated 12 June 2025. The official amendment says the changes take effect immediately and adds paragraph 38(e) concerning advance notice and reminders for periodic KYC updates. The official consolidated Master Direction page located during bootstrap reports that it is updated as of 14 August 2025.

- [Official RBI amendment, 12 June 2025](https://www.rbi.org.in/scripts/NotificationUser.aspx/searchnew/searchnew/NotificationUser.aspx?Id=12866)
- [Official RBI consolidated KYC Master Direction](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566)

This source finding supports the initial candidate record, but it does **not** complete the full amendment lineage or prove that no later amendment changed the clause. The first record is marked `source_located_clause_not_gold_verified` for that reason.

## Ingestion steps

1. Start at an official RBI or SEBI index/consolidated instrument. Record the URL and the visible consolidation date.
2. Download or archive the official HTML/PDF to a local, non-public working area. Preserve original bytes and calculate SHA-256; record the retrieval date, content type and file path in the source register.
3. Extract text while preserving heading, chapter, paragraph, subparagraph, tables and footnotes. Keep the original extract next to normalized data for review.
4. Segment the source at clause/sub-clause granularity. If an amendment changes only paragraph 38(e), create a new version for that clause instead of treating the entire direction as replaced.
5. For every amendment, capture the source publication date and its express commencement/effective date separately. If effective date is not stated clearly, mark the metadata unresolved and do not create a verified gold item that depends on it.
6. Compare the consolidated wording with relevant amendment notifications and create explicit `AMENDS`, `REPEALS`, `SUPERSEDES`, `EXEMPTS`, `DEPENDS_ON`, and definition/cross-reference links only when supported by source text.
7. Human-check the candidate obligation text, source locator, effective interval, entity conditions, exemptions and dependencies.
8. Generate draft benchmark scenarios only after the target version and relevant source text are available. Keep them in `data/benchmark/draft_items.jsonl` while awaiting two independent annotations and adjudication.
9. Move an item into `data/benchmark/benchmark.jsonl` only after both independent annotations, adjudication, source verification and matching gold explanation are recorded. Never score draft items as benchmark performance.

## Temporal invariants

Version validity uses the start-inclusive, end-exclusive interval:

```text
effective_from <= reference_date < effective_to
```

A null `effective_to` is an open interval only after the latest relevant source check. Do not infer current validity only because an old source page remains reachable. Keep `obligation_id` stable across versions where appropriate; always assign a distinct `version_id` for changed wording.

## Draft versus gold data

- `data/obligations/obligations.jsonl` is the source-linked obligation/version inventory.
- `data/benchmark/draft_items.jsonl` is the annotation queue. Its proposed outcome labels are hypotheses and its items are not gold truth.
- `data/benchmark/benchmark.jsonl` is reserved for adjudicated, gold-verified items used for reported evaluation.

The draft file contains three candidate examples for applicability, non-applicability and missing-fact abstention over the same target clause. A fourth Conflict case is deliberately absent: the source review has not established a genuine unreconciled conflict, and artificially inventing one would undermine the study.


## Reproducible local source tooling

The repository includes `taarr.sources` to fetch one or more source register records and `taarr.extract` to convert saved source pages/PDFs to text for annotation.

List the official records:

```bash
python -m taarr.sources list
```

Fetch the first RBI KYC candidate sources:

```bash
python -m taarr.sources fetch RBI-KYC-CONSOLIDATED RBI-KYC-AMEND-2025-06-12
```

The output prints the hashed local filename. The source snapshot is kept under `data/raw/<source_id>/` and is excluded from Git. A JSONL acquisition manifest records its URL and SHA-256. The download utility follows only HTTPS URLs under `rbi.org.in` and `sebi.gov.in` and their subdomains; third-party redirects are rejected.

Extract text using the exact path printed by the fetch command:

```bash
python -m taarr.extract "data/raw/RBI-KYC-AMEND-2025-06-12/<hash>.html" --output data/extracted/RBI-KYC-AMEND-2025-06-12.txt
```

Install the optional PDF dependency with `pip install -e ".[dev,ingest]"`. Text extraction is a human-review aid, not a legal clause segmenter or automatic truth-labeler. Verify wording, subsection IDs, effective dates, amendment links, and relevant definitions against the official source before promotion to gold data.
