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

_Last updated: 2026-10-22._

All five original project phases are complete, and a guided, non-expert-facing
layer has since been built on top of the engine:

- **60 regulatory obligations** from the RBI KYC Master Direction (42) and SEBI LODR
  Regulations (18), all with `source_text_human_confirmed` verification status.
- **127 benchmark items**, all `gold_verified` after two independent human annotation
  passes (zero disagreements) plus source-text adjudication against the live
  official documents.
- **Real evaluation numbers:** n=127, accuracy=1.0, macro F1=0.75 (four-class:
  Applicable, Not applicable, Indeterminate, Conflict).
- **242 automated tests** across 14 test files, all passing; `ruff` clean.
- **Circularity caveat:** the 100% accuracy reflects internal consistency, not
  proven real-world correctness — the benchmark's expected outcomes were derived
  from the same resolver being evaluated. Breaking this circularity (independent
  legal review of expected outcomes) is the next research step. See
  `docs/PENDING_TWO_PERSON_VERIFICATION.txt` and `docs/DECISIONS.md` (D-001
  through D-009) for the full decision trail.
- **Guided "Check my rules" flow** (new): a non-expert describes their
  organisation in plain English, confirms a short list of answers, and gets a
  plain-English checklist of which of the 60 obligations apply — each one
  linked to its official circular and to the exact clause text. Built from a
  **closed 43-fact registry** (31 RBI-only, 12 SEBI-only, no overlap; a test
  enforces that the registry always matches exactly what the obligations use).
  A **circular browser** lets a user instead start from the RBI KYC Master
  Direction or the SEBI LODR Regulations and open any of their rules directly.
- **Optional Gemini features** (autofill the guided form; the B6 AI
  cross-check baseline) are not required to use the app and never decide an
  outcome — the deterministic resolver always does. Both read the API key and
  model from `.env`, re-read on every click, and each one is **exactly one
  API call** per click (the cross-check batches every selected item into a
  single request). See "Gemini key, model and API usage" below.

### What's left

- **Break the circularity above** — the single biggest open item. The 100%
  accuracy is the resolver agreeing with labels it effectively generated; an
  independent second reviewer (a person, not this codebase) needs to check a
  sample of the 127 gold items against the official text without seeing
  TAARR's own output first.
- **B6 (Gemini cross-check) itself is weak and inconsistent** — see the
  "AI cross-check" section below; treat its numbers as a signal, not a result.
- The dataset covers two instruments (RBI KYC, SEBI LODR). Extending to more
  RBI/SEBI instruments, or adding date-boundary benchmark items (none exist
  today — see `docs/RESEARCH_EVALUATION.md`), is future work, not done.
- B1–B4 (lexical retrieval, no-temporal, no-abstention, no-exemptions
  baselines) exist as ablations of B5, not as separately implemented
  retrieval systems (no PostgreSQL/pgvector/Neo4j — see "Planned
  architecture" above, which remains aspirational past the JSONL + in-memory
  resolver actually shipped).
- The paper/write-up described in the original Build Plan has not been written.

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

Copy `.env.example` to `.env`. The example contains the adopted D-001 no-version policy plus explicit settings for the still-open ordering questions:

- `TAARR_NO_VERSION_POLICY=NOT_APPLICABLE`
- `TAARR_MISSING_FACTS_POLICY=KLEENE`
- `TAARR_UNKNOWN_PRECEDENCE_POLICY=DEFINITIVE_RULES_FIRST`

D-001, D-002 and D-003 are finalized: `NOT_APPLICABLE` means TAARR emits a `Not applicable` result with temporal-filter evidence when no version is in force on the reference date; `KLEENE` means a missing fact is `UNKNOWN`, not a silent failure, and can still be overridden by a known-false sibling condition; `DEFINITIVE_RULES_FIRST` means an unknown applicability result is not final until exemptions and dependencies have had a chance to settle it. Review [Decision log](docs/DECISIONS.md) before labeling edge cases or creating gold benchmark labels. For an existing checkout, `git pull` does not overwrite your local `.env`; verify that the three values above are present in it.

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

The UI opens on **Check my rules**, the guided flow for someone who does not know the rule book. The other tabs are the reasoning console, clause/version explorer, gold-only benchmark dashboard and AI cross-check. All 60 obligations are `source_text_human_confirmed` and the benchmark dashboard shows real evaluation results (n=127, accuracy=1.0, macro F1=0.75).

### Check my rules (guided flow)

Two ways in, both leading to the same rule dialog:

- **Describe my organisation** (default): a 3-step guided flow.
  1. **Describe** your organisation in plain English, pick the date to check
     against, and choose RBI, SEBI or both. Optionally press *Autofill the
     answers*: Gemini sees only the closed list of 43 facts the catalogue can
     test, may return nothing else, and must quote your own words for every
     answer; the server re-checks every value and drops anything
     unsupported. Gemini never decides applicability — one click is one API
     call either way.
  2. **Confirm answers** — only the answers found in your text plus the 6
     questions that would settle the most rules; the full 43-question list is
     one click away. Each control is Yes/No/Not sure, a choice list, or a
     number box. An unanswered question stays unknown, never assumed false.
  3. **Your checklist** — leads with *Apply to you*; rules that only apply in
     a particular situation (e.g. a trust customer, a foreign student) are
     grouped together with their own questions so they don't clutter the main
     list; anything ruled out is folded away. Every row opens a dialog with
     the plain-English result, the exact question(s) that decide it (answer
     them right there), the official clause text, and a button to the
     official circular. Also: a plain-text download.
- **Browse circulars and rules**: pick the RBI KYC Master Direction or the
  SEBI LODR Regulations directly, search across all 60 rules, and open any
  one in the same dialog — for a user who already knows which circular they
  want rather than describing their organisation.

Endpoints behind it: `GET /api/v1/facts`, `POST /api/v1/facts/extract`, `POST /api/v1/checklist`.

### Gemini key, model and API usage

Gemini is used in exactly two places, and each click is exactly one API request:

| Where | Requests per click |
|---|---|
| *Check my rules* → **Autofill the answers** | 1 |
| *AI cross-check* → **Run cross-check** | 1 (all selected items go in one batched request) |

Nothing else calls Gemini — the checklist, its live re-runs, the reasoning console, the
clause explorer and the benchmark are all deterministic and local.

Both settings live in `.env` in the repository root:

```
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.5-flash-lite
```

`.env` is re-read on every click, so after a rate limit you can change `GEMINI_MODEL`,
save, and click again without restarting the backend. A value in `.env` wins over the same
variable exported in your shell. Use an exact model ID from ai.google.dev/models — see
`.env.example` for the current list (for example `gemini-3.1-flash` does not exist, and the
`gemini-2.0-*` models are shut down). `GET /api/v1/health` reports the model in use.

### AI cross-check (optional B6 baseline)

The fifth tab uses the key from `.env` to ask an independent LLM to read the same clause text and entity facts as TAARR — without ever seeing TAARR's own answer — then compares its outcome against the gold label. The key is sent only to your local backend for that one request, forwarded to Google, and never written to disk or logged. This is a fast, convenient sanity check; it is **not** a substitute for the project's required two-person human verification (`docs/ANNOTATION_PROTOCOL.md`). See `docs/RESEARCH_EVALUATION.md` for the B6 baseline definition.

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
- `draft_items.jsonl` tracks annotation status for all 127 items. All are now `gold_verified` after two independent annotations, adjudication, and source-text verification (see decisions D-005 through D-009).
- `benchmark.jsonl` contains all 127 gold_verified items. New items must follow the same promotion path: two independent annotations, adjudication, and official source/version verification.
- Keep raw source documents, extracted clauses, normalized obligation records and benchmark labels logically separate.
- Two annotators should label benchmark items independently; adjudicate disagreements against official text and report Cohen's kappa as specified in the review.
- Keep benchmark splits grouped by underlying obligation/instrument lineage to reduce leakage.
- Release only data permitted for redistribution; link to official source documents rather than assuming document contents can always be republished.

## Portable architecture

The default project deliberately avoids Docker and external database services. The obligation catalog and benchmark are version-controlled JSONL files; the API loads the catalog into memory. This makes the project straightforward to clone and run on another machine with Python 3.11+, Git, and Node.js 22 for the frontend.

Do not install PostgreSQL, Neo4j, Docker, or configure API keys for the current workflow. If persistent local audit/history is later required, prefer Python's built-in SQLite database stored under a project-local data/local directory, with a documented option to disable it. Keep this optional and never commit private user data or generated local database files. Dense vector retrieval and graph traversal are not currently active features.

## Research novelty and evaluation

Read [Research evaluation protocol](docs/RESEARCH_EVALUATION.md) for the dataset contribution, baselines, ablations and metrics, and [Provenance and audit invariants](docs/PROVENANCE_AND_AUDIT.md) for the third differentiating capability. The benchmark now has 127 gold_verified items producing real evaluation numbers (accuracy=1.0, macro F1=0.75). The circularity caveat applies — see `docs/PENDING_TWO_PERSON_VERIFICATION.txt`.

### Run baseline and ablation experiments

```bash
python -m taarr.experiments --benchmark data/benchmark/benchmark.jsonl \
  --catalog data/obligations/obligations.jsonl \
  --output reports/experiments/latest.json
```

See [Experiment Runner](docs/EXPERIMENT_RUNNER.md). Only `gold_verified` rows are scored. The four configurations (full_taarr, no_temporal, no_abstention, no_exemptions_dependencies) show which engine features matter.

### Audit provenance and benchmark readiness

```bash
python -m taarr.provenance_audit
```

Checks official-source URL domains, duplicate IDs, temporal interval structure, gold clause/version references, adjudication metadata, and split leakage. A structural pass is not legal verification. See [Provenance audit](docs/PROVENANCE_AUDIT.md).

## Core docs

- [Dataset schema and annotation guide](docs/DATASET_SPEC.md)
- [Source acquisition and feasibility pilot](docs/SOURCE_REGISTER.md)
- [Clause-level ingestion protocol](docs/INGESTION_PROTOCOL.md)
- [Dataset roadmap and unresolved decisions](docs/DECISIONS.md)
- [Independent annotation and Cohen's kappa protocol](docs/ANNOTATION_PROTOCOL.md)
- [Evaluation next steps](docs/EVALUATION_NEXT_STEPS.md)
- [Illustrative evaluation notes](docs/ILLUSTRATIVE_EVAL.md)
- [Verification status](docs/PENDING_TWO_PERSON_VERIFICATION.txt)
- [Research evaluation protocol](docs/RESEARCH_EVALUATION.md)
- [Architecture implementation status](docs/ARCHITECTURE_STATUS.md)
- [Clause-level provenance and audit invariants](docs/PROVENANCE_AND_AUDIT.md)
- [Resolution engine deep dive](docs/RESOLUTION_ENGINE.md)
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
