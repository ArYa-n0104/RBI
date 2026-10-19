# Architecture Implementation Status

## Working now
- React + TypeScript + Vite interface and FastAPI API.
- JSONL clause-version catalog and deterministic resolver.
- Lexical bootstrap retrieval (token overlap; not BM25 or dense semantic retrieval).
- Four outcomes, temporal intervals, three-valued condition evaluation, modeled exemptions/dependencies, structured evidence records.
- Clause/version API, exemption listing API, gold-only benchmark scoring endpoint, JSONL validation, dual-annotation agreement CLI, gold-only baseline/ablation experiment runner, provenance/readiness audit, tests and CI.
- `.env.example` contains provisional local-development policy settings; review them before gold annotation.

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
- LLM-assisted extraction or explanation calls; the deterministic engine currently produces reasons.
- Live persistent resolution audit writes.
- Multi-user authentication.
- Gold benchmark construction and quantitative baseline/ablation results (runner is implemented; current empty gold set means no performance metrics).

Do not describe planned capabilities as implemented in a thesis, poster, or defence.
