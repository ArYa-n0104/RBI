# TAARR — Temporal and Applicability-Aware Regulatory Reasoning

TAARR is a research prototype for obligation-level regulatory applicability reasoning over official RBI and SEBI instruments. It is designed to answer **which version of a clause applied on a reference date, whether it applies to a specific entity, and why**, with clause-level evidence.

> **Research integrity:** The dataset and rule outcomes are the core contribution. The deterministic engine makes decisions; an LLM may help extract candidate records or draft an explanation, but it must not decide applicability. This prototype is decision support, not legal advice.

## Research basis

This repository follows the supplied *TAARR Build Plan* and *TAARR Review Paper*:

- **Dataset novelty:** a manually verified, date- and entity-specific RBI/SEBI applicability benchmark.
- **Algorithm novelty:** one deterministic obligation-level procedure integrating temporal validity, entity applicability, exemptions, dependencies, and four explicit outcomes.
- **Auditability:** every outcome should expose its evidence chain, clause IDs, official source URL, effective dates, and applicable exemption/dependency links.
- **Evaluation:** compare with standard dense RAG, hybrid GraphRAG, temporal KG-RAG, and deterministic exception baselines; report ablations and evaluation metrics.

## Outcomes

- `Applicable`
- `Not applicable`
- `Indeterminate` — essential entity facts or evidence are missing
- `Conflict` — equally prioritised authoritative rules cannot be reconciled automatically

These labels are not interchangeable. In particular, a missing fact is not evidence that an obligation does not apply.

## Planned architecture

1. **Offline ingestion:** official RBI/SEBI source documents → text/PDF extraction → clause segmentation → candidate obligation records → human verification.
2. **Retrieval:** PostgreSQL full-text search plus pgvector semantic retrieval.
3. **Versioned graph:** Neo4j nodes and relationships for obligations, versions, amendments, repeals, exemptions, dependencies, and entity categories.
4. **Resolution engine:** deterministic temporal filtering and three-valued condition evaluation, followed by exemption/dependency resolution.
5. **Explanation:** optional LLM drafts from the evidence record; cited clause IDs are checked, and the outcome cannot be changed by the LLM.
6. **Application:** React + TypeScript client and FastAPI API, including a query console, clause explorer, provenance trail, and benchmark dashboard.

## Repository status

The first data-foundation increment is in place: a machine-readable obligation-version record, dataset schema, source register, ingestion protocol, JSONL validator, unit tests, and GitHub Actions CI.

The official RBI KYC source pages have been located for a first pilot around paragraph 38(e). Three candidate examples for positive applicability, negative applicability and missing-fact abstention are staged in `data/benchmark/draft_items.jsonl`. They contain **provisional hypotheses, not verified gold labels**. The evaluation ledger `data/benchmark/benchmark.jsonl` intentionally remains empty until two independent annotations, adjudication and source/version verification have been completed. There is no invented Conflict item.

## Local setup

Requirements: Python 3.11+ and Git. For the data-foundation increment, no database or LLM key is required.

### Windows PowerShell

```powershell
git clone https://github.com/ArYa-n0104/RBI.git
cd RBI
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,ingest]"
python -m taarr.sources list
python -m taarr.dataset validate data/benchmark/benchmark.jsonl
python -m taarr.dataset validate data/benchmark/draft_items.jsonl
pytest
```

If PowerShell blocks activation, run this for the current terminal only, then activate:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
git clone https://github.com/ArYa-n0104/RBI.git
cd RBI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,ingest]"
python -m taarr.sources list
python -m taarr.dataset validate data/benchmark/benchmark.jsonl
python -m taarr.dataset validate data/benchmark/draft_items.jsonl
pytest
```

## Run the full application locally

Open two VS Code terminals from the repository root.

### Terminal 1 — API

```bash
python -m venv .venv
```

Activate the environment (Windows PowerShell: `.\\.venv\\Scripts\\Activate.ps1`; macOS/Linux: `source .venv/bin/activate`), then install and configure:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev,ingest]"
```

Copy `.env.example` to `.env`. The example now contains **provisional local-development settings** so you can run the UI and exercise the resolver:

- `TAARR_NO_VERSION_POLICY=NOT_APPLICABLE`
- `TAARR_MISSING_FACTS_POLICY=KLEENE`
- `TAARR_UNKNOWN_PRECEDENCE_POLICY=DEFINITIVE_RULES_FIRST`

These are explicit testing settings, **not final research/legal decisions**. Review [Decision log](docs/DECISIONS.md), get the project owner/supervisor to approve the unresolved D-001 and D-003 semantics, and version that decision before creating gold benchmark labels. For an existing checkout, `git pull` does not overwrite your local `.env`; copy the three values above into it manually if needed.

Then start the API:

```bash
uvicorn taarr.api:app --reload
```

API health and interactive endpoint documentation:
- http://127.0.0.1:8000/api/v1/health
- http://127.0.0.1:8000/docs

### Terminal 2 — React frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` and `/health` to the backend on port 8000. Use Node.js 22 for the frontend toolchain.

The UI currently provides the reasoning console, entity-profile inputs, date selection, clause/version explorer, source provenance, and gold-only benchmark dashboard. The catalog includes bootstrap source records marked `source_located_clause_not_gold_verified`; that status is intentionally visible and is not equivalent to legal verification. The gold benchmark starts empty by design.

### Run checks

From the repository root:

```bash
pytest
ruff check src tests
python -m taarr.dataset validate data/benchmark/benchmark.jsonl
python -m taarr.dataset validate data/benchmark/draft_items.jsonl
```

From `frontend/`:

```bash
npm run build
```

## Acquire and extract the official regulatory sources

Run the following from the repository root in the VS Code terminal. Downloads are restricted to HTTPS on official RBI/SEBI domains; raw source snapshots under `data/raw/` are local and ignored by Git.

```bash
python -m taarr.sources list
python -m taarr.sources fetch RBI-KYC-CONSOLIDATED RBI-KYC-AMEND-2025-06-12
```

The fetch command prints the exact local file path and SHA-256 hash. Copy that path into the extraction command; for example:

```bash
python -m taarr.extract "data/raw/RBI-KYC-AMEND-2025-06-12/PASTE_HASH_FILENAME_FROM_FETCH.html" --output data/extracted/RBI-KYC-AMEND-2025-06-12.txt
```

PDF extraction uses PyMuPDF, installed by `pip install -e ".[dev,ingest]"`. This step extracts text for review only. It does not create gold labels or automatically establish amendment lineage. Inspect extracted clause text against the official page/PDF before editing `data/obligations/obligations.jsonl` or drafting benchmark cases.

The acquisition manifest records URL, retrieval time, path, content type, size and SHA-256. Do not commit raw source documents unless redistribution is permitted. Review the acquisition manifest before sharing it; it can contain local paths.

## Pull the latest changes into VS Code

For an existing local checkout, open the TAARR folder in VS Code, then open **Terminal → New Terminal** and run:

```bash
git status
git pull --ff-only origin main
```

If you have local edits, commit or stash them before pulling. To get the latest work and verify it:

```bash
git pull --ff-only origin main
pip install -e ".[dev,ingest]"
python -m taarr.dataset validate data/benchmark/benchmark.jsonl
python -m taarr.dataset validate data/benchmark/draft_items.jsonl
pytest
```

If you have not cloned the repository, follow the setup steps above. Do not download individual files manually; use Git so the entire codebase stays in sync.

## Dataset safety and research integrity

- Store source URLs and provenance; retain publication dates and effective dates separately.
- Represent version intervals as **start-inclusive and end-exclusive**: `effective_from <= reference_date < effective_to`. A null `effective_to` means no recorded end date, not proof the clause remains current.
- Keep each obligation's stable ID distinct from its version ID.
- Do not invent regulatory clauses, effective dates, exemptions, dependencies, or Conflict examples.
- `draft_items.jsonl` is an annotation queue. A draft `gold_outcome` is a candidate hypothesis only and must not be reported as verified ground truth or used for final benchmark metrics.
- Move an item into `benchmark.jsonl` only after two independent annotations, adjudication, and official source/version verification.
- Keep raw source documents, extracted clauses, normalized obligation records and benchmark labels logically separate.
- Two annotators should label benchmark items independently; adjudicate disagreements against official text and report Cohen's kappa as specified in the review.
- Keep benchmark splits grouped by underlying obligation/instrument lineage to reduce leakage.
- Release only data permitted for redistribution; link to official source documents rather than assuming document contents can always be republished.

## Portable architecture

The default project deliberately avoids Docker and external database services. The obligation catalog and benchmark are version-controlled JSONL files; the API loads the catalog into memory. This makes the project straightforward to clone and run on another machine with Python 3.11+, Git, and Node.js 22 for the frontend.

Do not install PostgreSQL, Neo4j, Docker, or configure API keys for the current workflow. If persistent local audit/history is later required, prefer Python's built-in SQLite database stored under a project-local data/local directory, with a documented option to disable it. Keep this optional and never commit private user data or generated local database files. Dense vector retrieval and graph traversal are not currently active features.

## Research novelty and evaluation

Read [Research evaluation protocol](docs/RESEARCH_EVALUATION.md) for the proposed dataset contribution, baselines, ablations and metrics, and [Provenance and audit invariants](docs/PROVENANCE_AND_AUDIT.md) for the third differentiating capability. The current gold benchmark is intentionally empty: accuracy and novelty superiority are not yet measured. Never promote draft labels to gold without two independent annotations, adjudication and source/version verification.

## Core docs

- [Dataset schema and annotation guide](docs/DATASET_SPEC.md)
- [Source acquisition and feasibility pilot](docs/SOURCE_REGISTER.md)
- [Clause-level ingestion protocol](docs/INGESTION_PROTOCOL.md)
- [Dataset roadmap and unresolved decisions](docs/DECISIONS.md)
- [Independent annotation and Cohen's kappa protocol](docs/ANNOTATION_PROTOCOL.md)
- [Evaluation next steps](docs/EVALUATION_NEXT_STEPS.md)
- [Research evaluation protocol](docs/RESEARCH_EVALUATION.md)
- [Architecture implementation status](docs/ARCHITECTURE_STATUS.md)
- [Clause-level provenance and audit invariants](docs/PROVENANCE_AND_AUDIT.md)
- [Obligation-version schema](schemas/obligation_version.schema.json)
- [Benchmark item schema](schemas/benchmark_item.schema.json)
- [Data validation CLI](src/taarr/dataset.py)

## Contribution workflow

1. Create a focused branch for each unit of work.
2. Add or update tests with each behavior change.
3. Run `pytest` and both dataset validators before committing.
4. Never mark an item gold-verified until its official source and reasoning have been reviewed.
5. Keep change logs and dataset versions reproducible.

## Disclaimer

TAARR is an academic research prototype for explainable regulatory decision support. It is not legal advice and cannot replace qualified compliance or legal review.
