# Architecture Implementation Status

## Working now
- React + TypeScript + Vite interface and FastAPI API.
- JSONL clause-version catalog and deterministic resolver.
- Lexical bootstrap retrieval (token overlap; not BM25 or dense semantic retrieval).
- Four outcomes, temporal intervals, three-valued condition evaluation, modeled exemptions/dependencies, structured evidence records.
- Clause/version API, exemption listing API, gold-only benchmark scoring endpoint, JSONL validation, dual-annotation agreement CLI, tests and CI.
- `.env.example` contains provisional local-development policy settings; review them before gold annotation.

## Added for reproducible data services
- Docker Compose definitions for PostgreSQL with pgvector and Neo4j Community.
- PostgreSQL schema for clause versions, FTS, optional vector embeddings, independent annotations, adjudications, audit events and evaluation runs.
- Neo4j uniqueness constraints/indexes and recommended relationship vocabulary.

## Not yet wired into live query resolution
- PostgreSQL/pgvector and Neo4j are optional infrastructure at this point; the existing API reads the JSONL catalog and resolves in memory.
- Dense embeddings are not generated and no vector retrieval is active.
- The current retriever is lexical token overlap, not BM25.
- No LLM extraction or explanation call is active; the deterministic engine itself produces reasons.
- Resolution audit schema exists but live API audit writes are not enabled.
- No authenticated multi-user workflow is implemented; local single-tenant research mode is the current scope.
- Gold benchmark and quantitative comparisons are not complete.

Do not describe planned capabilities as implemented in a thesis, poster, or defence.
