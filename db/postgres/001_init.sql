-- TAARR relational/vector store schema (PostgreSQL + pgvector).
-- The schema stores candidates and research evidence; it does not decide legal outcomes.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS source_documents (
    source_id TEXT PRIMARY KEY,
    regulator TEXT NOT NULL CHECK (regulator IN ('RBI', 'SEBI')),
    title TEXT NOT NULL,
    official_url TEXT NOT NULL,
    publication_date DATE,
    retrieved_at TIMESTAMPTZ,
    sha256 TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS obligation_versions (
    version_id TEXT PRIMARY KEY,
    obligation_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    clause_id TEXT NOT NULL,
    regulator TEXT NOT NULL CHECK (regulator IN ('RBI', 'SEBI')),
    official_url TEXT NOT NULL,
    clause_text TEXT NOT NULL,
    clause_summary TEXT NOT NULL DEFAULT '',
    effective_from DATE NOT NULL,
    effective_to DATE,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(clause_text, '') || ' ' || coalesce(clause_summary, ''))
    ) STORED,
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);
CREATE INDEX IF NOT EXISTS obligation_versions_search_idx ON obligation_versions USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS obligation_versions_identity_idx ON obligation_versions (obligation_id, effective_from, effective_to);
CREATE TABLE IF NOT EXISTS clause_chunks (
    chunk_id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES obligation_versions(version_id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1536),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS clause_chunks_version_idx ON clause_chunks(version_id);
-- After embeddings exist: CREATE INDEX clause_chunks_embedding_hnsw_idx ON clause_chunks USING hnsw (embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS benchmark_annotations (
    annotation_id BIGSERIAL PRIMARY KEY,
    benchmark_item_id TEXT NOT NULL,
    annotator_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('Applicable','Not applicable','Indeterminate','Conflict')),
    rationale TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_packet_hash TEXT,
    UNIQUE (benchmark_item_id, annotator_id)
);
CREATE TABLE IF NOT EXISTS benchmark_adjudications (
    benchmark_item_id TEXT PRIMARY KEY,
    outcome TEXT NOT NULL CHECK (outcome IN ('Applicable','Not applicable','Indeterminate','Conflict')),
    rationale TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    adjudicated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_packet_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resolution_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    query_text TEXT NOT NULL,
    reference_date DATE NOT NULL,
    entity_profile JSONB NOT NULL,
    resolver_policy JSONB NOT NULL,
    results JSONB NOT NULL,
    source_version_ids TEXT[] NOT NULL DEFAULT '{}',
    source_urls TEXT[] NOT NULL DEFAULT '{}',
    catalog_snapshot_hash TEXT,
    duration_ms DOUBLE PRECISION,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS resolution_audit_created_idx ON resolution_audit(created_at DESC);
CREATE INDEX IF NOT EXISTS resolution_audit_date_idx ON resolution_audit(reference_date);
CREATE TABLE IF NOT EXISTS evaluation_runs (
    run_id UUID PRIMARY KEY,
    system_config TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    policy JSONB NOT NULL,
    metrics JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes TEXT
);
