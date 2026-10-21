# Architecture Implementation Status

## Working now
- React + TypeScript + Vite interface and FastAPI API.
- JSONL clause-version catalog and deterministic resolver.
- Lexical bootstrap retrieval (token overlap; not BM25 or dense semantic retrieval).
- Four outcomes, temporal intervals, three-valued condition evaluation, modeled exemptions/dependencies, structured evidence records.
- Clause/version API, exemption listing API, gold-only benchmark scoring endpoint, JSONL validation, dual-annotation agreement CLI, gold-only baseline/ablation experiment runner, provenance/readiness audit, tests and CI.
- `.env.example` contains provisional local-development policy settings; review them before gold annotation.
- **Gold benchmark is built and scored** (not empty — see below): 127 `gold_verified` items, n=127 accuracy=1.0 macro-F1=0.75.
- **LLM calls are implemented, but only in two places that never decide an outcome** (updated 2026-10-22):
  - *Autofill* (`src/taarr/fact_extraction.py`) turns a free-text description into entity-profile facts for the guided UI, constrained to a closed 43-fact registry with server-side validation and a required quote from the user's text.
  - *B6 cross-check* (`src/taarr/llm_baseline.py`) asks Gemini to independently classify benchmark items, for comparison against gold labels only.
  Both read the API key/model from `.env` (`src/taarr/settings.py`) and make exactly one API call per UI click. Neither touches `reasoning.py`; the deterministic resolver still produces every TAARR outcome and reason.
- **Guided, non-expert UI** ("Check my rules" tab): describe → confirm answers → plain-English checklist, plus a circular browser (`frontend/src/Checklist.tsx`), built on `GET /api/v1/facts` and `POST /api/v1/checklist`.

## Portability decision
- The default workflow has no external database dependency. The repository's JSONL catalog and benchmark are portable, version-controlled data files; the catalog is loaded into memory.
- Docker Compose, PostgreSQL/pgvector and Neo4j scaffolding were removed to avoid requiring external services or machine-specific setup.
- If persistence becomes necessary, prefer Python's built-in SQLite stored in a project-local data directory, with a way to disable it. SQLite persistence is a future enhancement, not currently implemented.
- No installation of Docker, PostgreSQL, Neo4j, vector services or LLM API keys is required for the current app.
- The experiment runner writes local JSON reports with policy, timestamp, Git commit when available, Python version, metrics and predictions/evidence; generated reports are Git-ignored.
- The provenance audit checks source-domain allowlists, duplicate IDs, interval shape, benchmark-to-catalog references, gold adjudication metadata, and split-group leakage. It cannot establish legal correctness.

## Not yet implemented
- Dense embeddings and semantic/vector retrieval.
- BM25 or other dedicated ranking-based hybrid retrieval.
- Graph traversal over amendment/exemption/dependency relations in a graph database.
- LLM-assisted *explanation drafting* (the deterministic engine still produces every reason string itself; the two LLM uses above are form-filling and an independent cross-check, not explanation generation).
- Live persistent resolution audit writes.
- Multi-user authentication.
- Independent (non-circular) validation of the gold benchmark's expected outcomes — see `docs/RESEARCH_EVALUATION.md` "Current status" and the circularity caveat in `docs/PENDING_TWO_PERSON_VERIFICATION.txt`.
- B1–B4 as separately-running retrieval systems (they exist only as ablations of B5 in the experiment runner, not as standalone dense/hybrid/graph systems).

Do not describe planned capabilities as implemented in a thesis, poster, or defence.
