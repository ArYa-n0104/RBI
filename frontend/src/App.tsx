import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  getClause,
  getHealth,
  listObligations,
  runBenchmark,
  runLlmCrossCheck,
  runQuery,
} from "./api";
import type {
  BenchmarkResponse,
  ClauseHistoryResponse,
  HealthResponse,
  LlmCrossCheckResponse,
  ObligationSummary,
  QueryResponse,
  Resolution,
} from "./types";

type View = "query" | "clauses" | "benchmark" | "llm-crosscheck";
type TriState = "unknown" | "true" | "false";
const INITIAL_REFERENCE_DATE = "2025-07-01";

function toProfile(
  entityType: string,
  rbiRegulated: TriState,
  isListed: TriState,
  layer: string,
  marketCapRank: string,
): Record<string, unknown> {
  const profile: Record<string, unknown> = {};
  if (entityType.trim()) profile.entity_type = entityType.trim();
  if (rbiRegulated !== "unknown") profile.is_rbi_regulated_entity = rbiRegulated === "true";
  if (isListed !== "unknown") profile.is_listed_entity = isListed === "true";
  if (layer !== "unknown") profile.entity = { layer };
  if (marketCapRank.trim()) {
    const rank = Number(marketCapRank);
    if (Number.isFinite(rank) && rank > 0) profile.market_cap_rank = rank;
  }
  return profile;
}

function shortVerification(value: string | null | undefined): string {
  if (!value) return "Verification not recorded";
  if (value === "gold_verified") return "Gold verified";
  return value.replaceAll("_", " ");
}

function OutcomeBadge({ outcome }: { outcome: Resolution["outcome"] }) {
  const className = outcome
    ? outcome === "Applicable"
      ? "outcome-badge applicable"
      : outcome === "Not applicable"
        ? "outcome-badge not-applicable"
        : outcome === "Indeterminate"
          ? "outcome-badge indeterminate"
          : "outcome-badge conflict"
    : "outcome-badge dropped";
  return <span className={className}>{outcome ?? "Dropped by temporal policy"}</span>;
}

function ResultCard({ result }: { result: Resolution }) {
  const [expanded, setExpanded] = useState(false);
  const sources = result.evidence.filter(
    (item) => typeof item.source_url === "string",
  );
  return (
    <article className="result-card">
      <div className="result-heading">
        <div>
          <div className="eyebrow">{result.obligation_id}</div>
          <h3>{result.clause_id || "Clause not selected"}</h3>
        </div>
        <OutcomeBadge outcome={result.outcome} />
      </div>
      <p className="result-reason">{result.reason}</p>
      {result.missing_facts && result.missing_facts.length > 0 && (
        <div className="missing-facts">
          <strong>Facts needed</strong>
          <div className="tag-row">
            {result.missing_facts.map((fact) => (
              <span className="fact-tag" key={fact}>{fact}</span>
            ))}
          </div>
        </div>
      )}
      <div className="result-meta">
        {result.version_id && <span>Version: {result.version_id}</span>}
        {typeof result.retrieval_score === "number" && (
          <span>Lexical match score: {result.retrieval_score}</span>
        )}
      </div>
      {sources.length > 0 && (
        <div className="source-links">
          <strong>Source evidence</strong>
          {sources.map((item, index) => (
            <a
              key={`${String(item.source_url)}-${index}`}
              href={String(item.source_url)}
              target="_blank"
              rel="noreferrer"
            >
              {String(item.clause_id || item.version_id || "Open official source")}
            </a>
          ))}
        </div>
      )}
      <button className="text-button" type="button" onClick={() => setExpanded(!expanded)}>
        {expanded ? "Hide full evidence chain" : `Inspect evidence chain (${result.evidence.length})`}
      </button>
      {expanded && (
        <pre className="evidence-json">{JSON.stringify({
          evidence: result.evidence,
          dependencies: result.dependencies ?? [],
        }, null, 2)}</pre>
      )}
      {result.evidence.some((item) => item.verification_status && item.verification_status !== "gold_verified") && (
        <div className="draft-warning">
          <strong>Source verification note:</strong> This record is not a gold-verified
          benchmark item. Confirm its amendment lineage and adjudication status before relying on it.
        </div>
      )}
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("query");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [obligations, setObligations] = useState<ObligationSummary[]>([]);
  const [query, setQuery] = useState("Does the RBI KYC customer notice obligation apply?");
  const [referenceDate, setReferenceDate] = useState(INITIAL_REFERENCE_DATE);
  const [entityType, setEntityType] = useState("RBI-regulated financial entity");
  const [rbiRegulated, setRbiRegulated] = useState<TriState>("true");
  const [isListed, setIsListed] = useState<TriState>("unknown");
  const [layer, setLayer] = useState("unknown");
  const [marketCapRank, setMarketCapRank] = useState("");
  const [queryResult, setQueryResult] = useState<QueryResponse | null>(null);
  const [selectedClause, setSelectedClause] = useState<ClauseHistoryResponse | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);
  const [clauseFilter, setClauseFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [pageError, setPageError] = useState("");
  const [catalogError, setCatalogError] = useState("");
  const [geminiApiKey, setGeminiApiKey] = useState("");
  const [crossCheckLimit, setCrossCheckLimit] = useState("10");
  const [crossCheckLoading, setCrossCheckLoading] = useState(false);
  const [crossCheckError, setCrossCheckError] = useState("");
  const [crossCheck, setCrossCheck] = useState<LlmCrossCheckResponse | null>(null);

  useEffect(() => {
    let mounted = true;
    Promise.all([getHealth(), listObligations()])
      .then(([healthResponse, obligationsResponse]) => {
        if (!mounted) return;
        setHealth(healthResponse);
        setObligations(obligationsResponse.items);
      })
      .catch((error: unknown) => {
        if (!mounted) return;
        setCatalogError(error instanceof Error ? error.message : "Could not reach TAARR API.");
      });
    return () => {
      mounted = false;
    };
  }, []);

  const filteredObligations = useMemo(() => {
    const needle = clauseFilter.trim().toLowerCase();
    if (!needle) return obligations;
    return obligations.filter((item) =>
      [
        item.obligation_id,
        item.instrument_title ?? "",
        item.instrument_id ?? "",
        item.regulator ?? "",
        item.clause_id ?? "",
        item.clause_summary ?? "",
      ].join(" ").toLowerCase().includes(needle),
    );
  }, [clauseFilter, obligations]);

  async function handleQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setPageError("");
    setQueryResult(null);
    try {
      const result = await runQuery({
        query,
        reference_date: referenceDate,
        entity_profile: toProfile(entityType, rbiRegulated, isListed, layer, marketCapRank),
      });
      setQueryResult(result);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "Query failed.");
    } finally {
      setLoading(false);
    }
  }

  async function openClause(clauseId: string) {
    setLoading(true);
    setPageError("");
    try {
      setSelectedClause(await getClause(clauseId));
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "Could not open clause.");
    } finally {
      setLoading(false);
    }
  }

  async function handleBenchmark() {
    setLoading(true);
    setPageError("");
    try {
      setBenchmark(await runBenchmark());
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "Benchmark run failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCrossCheck(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCrossCheckLoading(true);
    setCrossCheckError("");
    try {
      const limit = Math.max(1, Math.min(127, Number(crossCheckLimit) || 10));
      const trimmedKey = geminiApiKey.trim();
      setCrossCheck(
        await runLlmCrossCheck(trimmedKey ? { api_key: trimmedKey, limit } : { limit }),
      );
    } catch (error) {
      setCrossCheckError(error instanceof Error ? error.message : "Cross-check run failed.");
    } finally {
      setCrossCheckLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="TAARR home">
          <span className="brand-mark">T</span>
          <span>
            <strong>TAARR</strong>
            <small>Regulatory reasoning</small>
          </span>
        </a>
        <div className="topbar-right">
          <span className="environment-pill"><span className="status-dot" /> Research prototype</span>
          <a className="github-link" href="https://github.com/ArYa-n0104/RBI" target="_blank" rel="noreferrer">
            Repository ↗
          </a>
        </div>
      </header>

      <main id="top" className="main-content">
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow hero-eyebrow">TEMPORAL · APPLICABILITY · PROVENANCE</div>
            <h1>Understand the rule.<br /><span>Prove why it applies.</span></h1>
            <p>
              Query RBI and SEBI obligations by reference date and entity profile.
              TAARR keeps the decision deterministic and exposes the source evidence behind it.
            </p>
          </div>
          <div className="hero-stats">
            <div><strong>{health?.catalog.obligations ?? "—"}</strong><span>Obligations loaded</span></div>
            <div><strong>{health?.catalog.versions ?? "—"}</strong><span>Versions loaded</span></div>
            <div><strong>4</strong><span>Decision outcomes</span></div>
          </div>
        </section>

        {catalogError && (
          <div className="notice error-notice">
            <strong>API connection issue</strong>
            <p>{catalogError}</p>
            <span>Start the backend with <code>uvicorn taarr.api:app --reload</code> from the repository root.</span>
          </div>
        )}

        {health && !health.policy_configured && (
          <div className="notice policy-notice">
            <strong>Resolver policy needs an explicit decision</strong>
            <p>
              The Build Plan and Review Paper disagree on the no-in-force-version and missing-fact
              ordering cases. Query resolution is disabled until those policy variables are set in
              the backend <code>.env</code>; no default has been silently chosen.
            </p>
            <a href="https://github.com/ArYa-n0104/RBI/blob/main/docs/DECISIONS.md" target="_blank" rel="noreferrer">
              Review the open design decision ↗
            </a>
          </div>
        )}

        {pageError && (
          <div className="notice error-notice" role="alert">
            <strong>Action could not be completed</strong>
            <p>{pageError}</p>
          </div>
        )}

        <nav className="view-tabs" aria-label="TAARR workspaces">
          <button className={view === "query" ? "active" : ""} onClick={() => setView("query")}>
            <span>01</span> Reasoning console
          </button>
          <button className={view === "clauses" ? "active" : ""} onClick={() => setView("clauses")}>
            <span>02</span> Clause explorer
          </button>
          <button className={view === "benchmark" ? "active" : ""} onClick={() => setView("benchmark")}>
            <span>03</span> Benchmark
          </button>
          <button className={view === "llm-crosscheck" ? "active" : ""} onClick={() => setView("llm-crosscheck")}>
            <span>04</span> AI cross-check
          </button>
        </nav>

        {view === "query" && (
          <section className="workspace">
            <div className="workspace-heading">
              <div>
                <div className="eyebrow">OBLIGATION RESOLUTION</div>
                <h2>Ask a regulatory question</h2>
                <p>The reference date and supplied entity facts shape the decision.</p>
              </div>
              <div className="policy-indicator">
                <span className={health?.policy_configured ? "status-dot green" : "status-dot amber"} />
                {health?.policy_configured ? "Policy configured" : "Policy not configured"}
              </div>
            </div>

            <div className="query-layout">
              <form className="query-form" onSubmit={handleQuery}>
                <label className="field-label" htmlFor="question">Your question</label>
                <textarea
                  id="question"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Which KYC obligation applies to this entity?"
                  rows={4}
                  required
                  maxLength={2000}
                />
                <label className="field-label" htmlFor="reference-date">Reference date</label>
                <input
                  id="reference-date"
                  type="date"
                  value={referenceDate}
                  onChange={(event) => setReferenceDate(event.target.value)}
                  required
                />
                <div className="form-divider" />
                <div className="section-label">ENTITY PROFILE</div>
                <label className="field-label" htmlFor="entity-type">Entity description</label>
                <input
                  id="entity-type"
                  value={entityType}
                  onChange={(event) => setEntityType(event.target.value)}
                  placeholder="e.g. NBFC, listed company, bank"
                />
                <label className="field-label" htmlFor="rbi-regulated">RBI-regulated entity?</label>
                <select id="rbi-regulated" value={rbiRegulated} onChange={(event) => setRbiRegulated(event.target.value as TriState)}>
                  <option value="unknown">Not specified</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
                <label className="field-label" htmlFor="entity-layer">RBI NBFC layer (if relevant)</label>
                <select id="entity-layer" value={layer} onChange={(event) => setLayer(event.target.value)}>
                  <option value="unknown">Not specified</option>
                  <option value="base">Base layer</option>
                  <option value="middle">Middle layer</option>
                  <option value="upper">Upper layer</option>
                  <option value="top">Top layer</option>
                </select>
                <label className="field-label" htmlFor="is-listed">SEBI-listed entity?</label>
                <select id="is-listed" value={isListed} onChange={(event) => setIsListed(event.target.value as TriState)}>
                  <option value="unknown">Not specified</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
                <label className="field-label" htmlFor="market-cap-rank">Market-cap rank (if relevant)</label>
                <input
                  id="market-cap-rank"
                  type="number"
                  min="1"
                  value={marketCapRank}
                  onChange={(event) => setMarketCapRank(event.target.value)}
                  placeholder="Leave blank if unknown"
                />
                <button className="primary-button" type="submit" disabled={loading || !query.trim() || !referenceDate}>
                  {loading ? <><span className="spinner" /> Resolving…</> : <>Resolve obligation <span>→</span></>}
                </button>
                <p className="form-footnote">
                  Missing facts remain unknown. They are not automatically treated as false.
                </p>
              </form>

              <div className="results-panel">
                <div className="results-topline">
                  <div>
                    <div className="eyebrow">DECISION OUTPUT</div>
                    <h3>{queryResult ? `${queryResult.outcomes.length} result(s)` : "Results appear here"}</h3>
                  </div>
                  {queryResult && <span className="date-chip">As of {queryResult.reference_date}</span>}
                </div>
                {!queryResult && (
                  <div className="empty-state">
                    <div className="empty-icon">↳</div>
                    <h3>Evidence first, answer second</h3>
                    <p>Run a query to see the four-way outcome, relevant clause version, missing facts and provenance.</p>
                    <div className="outcome-mini-grid">
                      <span className="mini-applicable">Applicable</span>
                      <span className="mini-na">Not applicable</span>
                      <span className="mini-indeterminate">Indeterminate</span>
                      <span className="mini-conflict">Conflict</span>
                    </div>
                  </div>
                )}
                {queryResult && (
                  <>
                    <div className="run-summary">
                      <div><span>Policy</span><strong>{queryResult.policy.no_version} / {queryResult.policy.missing_facts}</strong></div>
                      <div><span>Retrieved</span><strong>{queryResult.retrieved_count}</strong></div>
                    </div>
                    {queryResult.outcomes.length === 0 ? (
                      <div className="empty-state compact">
                        <h3>No matching clause was retrieved</h3>
                        <p>Try regulator, instrument, clause number or a more specific obligation phrase.</p>
                      </div>
                    ) : (
                      <div className="result-list">
                        {queryResult.outcomes.map((result, index) => (
                          <ResultCard key={`${result.obligation_id}-${index}`} result={result} />
                        ))}
                      </div>
                    )}
                    <p className="disclaimer">{queryResult.notice}</p>
                  </>
                )}
              </div>
            </div>
          </section>
        )}

        {view === "clauses" && (
          <section className="workspace">
            <div className="workspace-heading">
              <div>
                <div className="eyebrow">SOURCE CORPUS</div>
                <h2>Clause explorer</h2>
                <p>Inspect source-linked obligations and the versions currently loaded in the catalog.</p>
              </div>
              <span className="date-chip">{obligations.length} catalog record(s)</span>
            </div>
            <div className="explorer-layout">
              <div className="explorer-list">
                <label className="field-label" htmlFor="clause-filter">Search obligations</label>
                <input
                  id="clause-filter"
                  value={clauseFilter}
                  onChange={(event) => setClauseFilter(event.target.value)}
                  placeholder="Search by instrument, clause or topic"
                />
                {filteredObligations.length === 0 ? (
                  <p className="muted">No records match that search.</p>
                ) : filteredObligations.map((item) => (
                  <button
                    className={selectedClause?.clause_id === item.clause_id ? "clause-list-item selected" : "clause-list-item"}
                    key={item.obligation_id}
                    onClick={() => item.clause_id && openClause(item.clause_id)}
                  >
                    <span className="clause-regulator">{item.regulator ?? "REG"}</span>
                    <strong>{item.clause_id ?? item.obligation_id}</strong>
                    <span>{item.instrument_title ?? item.instrument_id}</span>
                    <small>{shortVerification(item.verification_status)}</small>
                  </button>
                ))}
              </div>
              <div className="clause-detail">
                {!selectedClause ? (
                  <div className="empty-state">
                    <div className="empty-icon">§</div>
                    <h3>Select a clause</h3>
                    <p>Its loaded version history and official source records will appear here.</p>
                  </div>
                ) : (
                  <>
                    <div className="eyebrow">CLAUSE HISTORY</div>
                    <h3>{selectedClause.clause_id}</h3>
                    <p className="muted">{selectedClause.version_count} version record(s) loaded.</p>
                    {selectedClause.versions.map((version, index) => (
                      <article className="version-card" key={String(version.version_id ?? index)}>
                        <div className="version-header">
                          <strong>{String(version.version_id ?? "Unnamed version")}</strong>
                          <span className="verification-pill">{shortVerification(String(version.verification_status ?? ""))}</span>
                        </div>
                        <p>{String(version.clause_summary ?? version.clause_text ?? "No summary available.")}</p>
                        <div className="date-range">
                          <span>From: {String(version.effective_from ?? "Not recorded")}</span>
                          <span>To: {version.effective_to ? String(version.effective_to) : "Open end (verify current status)"}</span>
                        </div>
                        {typeof version.source_url === "string" && (
                          <a href={version.source_url} target="_blank" rel="noreferrer" className="source-anchor">
                            Open official source ↗
                          </a>
                        )}
                      </article>
                    ))}
                  </>
                )}
              </div>
            </div>
          </section>
        )}

        {view === "benchmark" && (
          <section className="workspace">
            <div className="workspace-heading">
              <div>
                <div className="eyebrow">RESEARCH EVALUATION</div>
                <h2>Benchmark dashboard</h2>
                <p>Only adjudicated, gold-verified items are scored. Draft items remain in the annotation queue.</p>
              </div>
              <button className="primary-button compact-button" onClick={handleBenchmark} disabled={loading}>
                {loading ? "Running…" : "Run TAARR benchmark →"}
              </button>
            </div>
            {!benchmark ? (
              <div className="empty-state benchmark-empty">
                <div className="empty-icon">∑</div>
                <h3>Evaluation starts with trustworthy labels</h3>
                <p>Run the benchmark to score the verified ledger. Draft hypotheses are intentionally excluded.</p>
              </div>
            ) : (
              <>
                <div className="metric-grid">
                  <Metric label="Gold items scored" value={benchmark.metrics.n} />
                  <Metric label="Accuracy" value={benchmark.metrics.accuracy === null ? "—" : `${(benchmark.metrics.accuracy * 100).toFixed(1)}%`} />
                  <Metric label="Macro F1" value={benchmark.metrics.macro_f1 === null ? "—" : benchmark.metrics.macro_f1.toFixed(3)} />
                  <Metric label="Dropped predictions" value={benchmark.metrics.dropped_predictions} />
                </div>
                <div className="notice info-notice">{benchmark.message}</div>
                <div className="per-class-grid">
                  {Object.entries(benchmark.metrics.per_outcome).map(([name, metric]) => (
                    <div className="class-metric" key={name}>
                      <strong>{name}</strong>
                      <span>Support {metric.support}</span>
                      <span>Precision {(metric.precision * 100).toFixed(1)}%</span>
                      <span>Recall {(metric.recall * 100).toFixed(1)}%</span>
                      <span>F1 {metric.f1.toFixed(3)}</span>
                    </div>
                  ))}
                </div>
                {benchmark.items.length > 0 && (
                  <div className="benchmark-table-wrap">
                    <table className="benchmark-table">
                      <thead><tr><th>Item</th><th>Gold</th><th>Prediction</th><th>Match</th></tr></thead>
                      <tbody>
                        {benchmark.items.map((item) => (
                          <tr key={String(item.benchmark_item_id)}>
                            <td>{String(item.benchmark_item_id)}</td>
                            <td>{String(item.gold_outcome)}</td>
                            <td>{String(item.predicted_outcome ?? "Dropped")}</td>
                            <td>{item.correct ? "Yes" : "No"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </section>
        )}

        {view === "llm-crosscheck" && (
          <section className="workspace">
            <div className="workspace-heading">
              <div>
                <div className="eyebrow">INDEPENDENT BASELINE &middot; B6</div>
                <h2>AI cross-check</h2>
                <p>
                  Ask Gemini to read the same clause text and entity facts on its own, without ever
                  seeing TAARR&apos;s answer, then compare its outcome against the gold label.
                </p>
              </div>
            </div>

            <div className="notice policy-notice">
              <strong>What this does and does not prove</strong>
              <p>
                TAARR&apos;s own outcome always comes from the deterministic resolver — this screen
                never changes it. Gemini is given only the clause text, the entity facts and the
                date, and answers independently. Agreement with the gold label is a useful, fast
                signal, but it is <em>not</em> a substitute for the project&apos;s required human
                two-person verification (see <code>docs/ANNOTATION_PROTOCOL.md</code>). An LLM can
                misread a clause or be inconsistent across runs.
              </p>
            </div>

            <div className="query-layout">
              <form className="query-form" onSubmit={handleCrossCheck}>
                {health?.gemini_api_key_configured ? (
                  <div className="notice info-notice">
                    A Gemini key is already configured on the server (<code>.env</code>). Leave the
                    field below blank to use it, or paste a different key to override it for this run.
                  </div>
                ) : (
                  <p className="form-footnote">
                    No server-side key found. Paste one below, or add{" "}
                    <code>GEMINI_API_KEY=...</code> to your local <code>.env</code> (git-ignored,
                    never pushed) so this tab works without typing a key each time.
                  </p>
                )}
                <label className="field-label" htmlFor="gemini-key">
                  Gemini API key {health?.gemini_api_key_configured ? "(optional — overrides .env)" : ""}
                </label>
                <input
                  id="gemini-key"
                  type="password"
                  autoComplete="off"
                  value={geminiApiKey}
                  onChange={(event) => setGeminiApiKey(event.target.value)}
                  placeholder={
                    health?.gemini_api_key_configured
                      ? "Leave blank to use the server's .env key"
                      : "Paste your own Gemini API key"
                  }
                  required={!health?.gemini_api_key_configured}
                />
                <p className="form-footnote">
                  Sent only to the local TAARR backend for this one request, then forwarded
                  directly to Google. Never written to disk, logged, or stored by this app. Get a
                  key at{" "}
                  <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer">
                    aistudio.google.com/app/apikey
                  </a>
                  .
                </p>
                <label className="field-label" htmlFor="crosscheck-limit">
                  How many gold items to check (1–127)
                </label>
                <input
                  id="crosscheck-limit"
                  type="number"
                  min={1}
                  max={127}
                  value={crossCheckLimit}
                  onChange={(event) => setCrossCheckLimit(event.target.value)}
                />
                <button
                  className="primary-button"
                  type="submit"
                  disabled={
                    crossCheckLoading ||
                    (!geminiApiKey.trim() && !health?.gemini_api_key_configured)
                  }
                >
                  {crossCheckLoading ? (
                    <><span className="spinner" /> Asking Gemini…</>
                  ) : (
                    <>Run cross-check <span>→</span></>
                  )}
                </button>
              </form>

              <div className="results-panel">
                <div className="results-topline">
                  <div>
                    <div className="eyebrow">AGREEMENT WITH GOLD</div>
                    <h3>{crossCheck ? `${crossCheck.n} item(s) checked` : "Results appear here"}</h3>
                  </div>
                  {crossCheck && <span className="date-chip">Model: {crossCheck.model}</span>}
                </div>

                {crossCheckError && (
                  <div className="notice error-notice" role="alert">
                    <strong>Cross-check could not be completed</strong>
                    <p>{crossCheckError}</p>
                  </div>
                )}

                {!crossCheck && !crossCheckError && (
                  <div className="empty-state">
                    <div className="empty-icon">⇄</div>
                    <h3>Two independent readers, one clause</h3>
                    <p>
                      Paste a Gemini API key and run the check to see how often an independent
                      language model agrees with TAARR&apos;s gold-verified answers.
                    </p>
                  </div>
                )}

                {crossCheck && (
                  <>
                    <div className="metric-grid">
                      <Metric
                        label="Agreement rate"
                        value={
                          crossCheck.agreement_with_gold.accuracy === null
                            ? "—"
                            : `${(crossCheck.agreement_with_gold.accuracy * 100).toFixed(1)}%`
                        }
                      />
                      <Metric
                        label="Macro F1"
                        value={
                          crossCheck.agreement_with_gold.macro_f1 === null
                            ? "—"
                            : crossCheck.agreement_with_gold.macro_f1.toFixed(3)
                        }
                      />
                      <Metric label="Items checked" value={crossCheck.n} />
                      <Metric
                        label="Unparseable responses"
                        value={crossCheck.agreement_with_gold.dropped_predictions}
                      />
                    </div>
                    <div className="notice info-notice">{crossCheck.notice}</div>
                    <div className="benchmark-table-wrap">
                      <table className="benchmark-table">
                        <thead>
                          <tr><th>Item</th><th>Gold</th><th>Gemini</th><th>Agrees</th></tr>
                        </thead>
                        <tbody>
                          {crossCheck.items.map((item) => (
                            <tr key={item.benchmark_item_id}>
                              <td>{item.benchmark_item_id}</td>
                              <td>{item.gold_outcome}</td>
                              <td title={item.error ?? item.llm_raw_text}>
                                {item.llm_outcome ?? (item.error ? "Error" : "Unparsed")}
                              </td>
                              <td>{item.agrees_with_gold ? "Yes" : "No"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            </div>
          </section>
        )}

        <footer className="footer">
          <div>TAARR · Temporal and Applicability-Aware Regulatory Reasoning</div>
          <div>Deterministic decisions · Clause-level evidence · Research prototype</div>
        </footer>
      </main>
    </div>
  );
}
