// Run against Neo4j 5 Community using cypher-shell or the browser.
CREATE CONSTRAINT obligation_id IF NOT EXISTS FOR (n:Obligation) REQUIRE n.obligation_id IS UNIQUE;
CREATE CONSTRAINT clause_version_id IF NOT EXISTS FOR (n:ClauseVersion) REQUIRE n.version_id IS UNIQUE;
CREATE CONSTRAINT source_id IF NOT EXISTS FOR (n:SourceDocument) REQUIRE n.source_id IS UNIQUE;
CREATE CONSTRAINT amendment_id IF NOT EXISTS FOR (n:AmendmentEvent) REQUIRE n.amendment_id IS UNIQUE;
CREATE INDEX clause_version_effective_from IF NOT EXISTS FOR (n:ClauseVersion) ON (n.effective_from);
CREATE INDEX clause_version_clause_id IF NOT EXISTS FOR (n:ClauseVersion) ON (n.clause_id);
// Recommended edges: VERSION_OF, AMENDED_BY, SUPERSEDES, REPEALED_BY,
// EXEMPTS, EXCLUDES, DEPENDS_ON, DEFINES and CROSS_REFERENCES.
// Relationships must carry relation_id, official_url, verification_status,
// and sourced effective dates/priority where applicable. Never invent priority.
