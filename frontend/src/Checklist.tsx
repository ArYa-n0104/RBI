import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { extractFacts, listFacts, runChecklist } from "./api";
import type {
  ChecklistBucket,
  ChecklistResponse,
  ChecklistRow,
  FactDefinition,
} from "./types";

const ROW_PREVIEW = 8;

type AnswerValue = boolean | string | number;
type Answers = Record<string, AnswerValue>;

function todayIso(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

const EXAMPLES: Array<{ label: string; text: string }> = [
  {
    label: "NBFC onboarding over an app",
    text:
      "We are an NBFC regulated by the RBI. We onboard individual customers through our app "
      + "without meeting them face to face, and some of them are rated high risk. We do not use "
      + "video based identification (V-CIP) yet.",
  },
  {
    label: "Bank with small accounts",
    text:
      "We are a bank regulated by the RBI. We open small accounts for walk-in customers, we use "
      + "video based identification (V-CIP) for onboarding, and our customers are individuals "
      + "rated low risk.",
  },
  {
    label: "Listed company, board questions",
    text:
      "We are a company listed on a stock exchange and we are in the top 2000 listed entities by "
      + "market capitalisation. Our chairperson is non-executive and is not related to the promoter. "
      + "Our paid up equity capital is 25 crore and our net worth is 600 crore.",
  },
];

const BUCKET_META: Array<{
  bucket: ChecklistBucket;
  title: string;
  blurb: string;
  tone: string;
  openByDefault: boolean;
}> = [
  {
    bucket: "applies",
    title: "Applies to you",
    blurb: "These rules are in force on your date and your answers meet their conditions.",
    tone: "applies",
    openByDefault: true,
  },
  {
    bucket: "need_more_info",
    title: "Need one more answer",
    blurb: "One fact is still unknown. Answer the question shown and the rule will move up or down.",
    tone: "unknown",
    openByDefault: true,
  },
  {
    bucket: "does_not_apply",
    title: "Does not apply to you",
    blurb: "Your answers rule these out, or no version was in force on your date.",
    tone: "no",
    openByDefault: false,
  },
  {
    bucket: "conflict",
    title: "Conflicting rules",
    blurb: "Two rules point in opposite directions. A human has to decide these.",
    tone: "conflict",
    openByDefault: true,
  },
  {
    bucket: "dropped",
    title: "Not in force on this date",
    blurb: "These rules exist in the catalogue but no version was in force on the date you chose.",
    tone: "no",
    openByDefault: false,
  },
];

function modalityLine(row: ChecklistRow): string {
  const action = row.action?.trim();
  if (!action) return row.clause_summary ?? row.obligation_id;
  const modality = (row.modality ?? "").toLowerCase();
  if (modality === "must") return `You must: ${action}`;
  if (modality === "must_not") return `You must not: ${action}`;
  if (modality === "may") return `You may: ${action}`;
  return action;
}

function verificationNote(value: string | null | undefined): string {
  if (value === "gold_verified") return "Gold verified by two reviewers";
  if (!value) return "Verification not recorded";
  return value.replaceAll("_", " ");
}

/** One question with Yes / No / Not sure chips, a choice list, or a number box. */
function QuestionControl({
  fact,
  value,
  onChange,
}: {
  fact: FactDefinition;
  value: AnswerValue | undefined;
  onChange: (value: AnswerValue | undefined) => void;
}) {
  if (fact.type === "boolean") {
    return (
      <div className="cl-chips" role="group" aria-label={fact.question}>
        <button
          type="button"
          className={value === true ? "cl-chip active" : "cl-chip"}
          onClick={() => onChange(value === true ? undefined : true)}
        >
          Yes
        </button>
        <button
          type="button"
          className={value === false ? "cl-chip active" : "cl-chip"}
          onClick={() => onChange(value === false ? undefined : false)}
        >
          No
        </button>
        <button
          type="button"
          className={value === undefined ? "cl-chip active muted" : "cl-chip muted"}
          onClick={() => onChange(undefined)}
        >
          Not sure
        </button>
      </div>
    );
  }

  if (fact.type === "enum") {
    return (
      <div className="cl-chips" role="group" aria-label={fact.question}>
        {(fact.values ?? []).map((option) => (
          <button
            key={option}
            type="button"
            className={value === option ? "cl-chip active" : "cl-chip"}
            onClick={() => onChange(value === option ? undefined : option)}
          >
            {option}
          </button>
        ))}
        <button
          type="button"
          className={value === undefined ? "cl-chip active muted" : "cl-chip muted"}
          onClick={() => onChange(undefined)}
        >
          Not sure
        </button>
      </div>
    );
  }

  return (
    <div className="cl-number-row">
      <input
        className="text-input"
        type="number"
        inputMode="decimal"
        min={fact.min}
        max={fact.max}
        placeholder="Leave blank if unknown"
        value={typeof value === "number" ? String(value) : ""}
        onChange={(event) => {
          const raw = event.target.value;
          if (!raw.trim()) {
            onChange(undefined);
            return;
          }
          const parsed = Number(raw);
          onChange(Number.isFinite(parsed) ? parsed : undefined);
        }}
      />
      {fact.unit && <span className="cl-unit">{fact.unit}</span>}
    </div>
  );
}

function ResultRow({
  row,
  facts,
  answers,
  onAnswer,
}: {
  row: ChecklistRow;
  facts: Map<string, FactDefinition>;
  answers: Answers;
  onAnswer: (key: string, value: AnswerValue | undefined) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <article className="cl-row">
      <div className="cl-row-main">
        <div>
          <p className="cl-row-action">{modalityLine(row)}</p>
          <div className="cl-row-tags">
            <span className="cl-tag">{row.regulator ?? "—"}</span>
            {row.clause_id && <span className="cl-tag mono">{row.clause_id}</span>}
            {row.deadline && <span className="cl-tag amber">Deadline {row.deadline}</span>}
          </div>
        </div>
        <button type="button" className="cl-link-button" onClick={() => setOpen((prior) => !prior)}>
          {open ? "Hide details" : "Why?"}
        </button>
      </div>

      {row.missing.length > 0 && (
        <div className="cl-inline-questions">
          {row.missing.map((item) => {
            const fact = facts.get(item.key);
            return (
              <div className="cl-inline-question" key={item.key}>
                <span>{item.question}</span>
                {fact && (
                  <QuestionControl
                    fact={fact}
                    value={answers[item.key]}
                    onChange={(value) => onAnswer(item.key, value)}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {open && (
        <div className="cl-row-details">
          <p>
            <strong>Why:</strong> {row.reason}
          </p>
          {row.clause_summary && (
            <p>
              <strong>What the clause says:</strong> {row.clause_summary}
            </p>
          )}
          <p className="cl-row-meta">
            {row.instrument_title ?? "Source document"} · {verificationNote(row.verification_status)}
            {row.version_id ? ` · ${row.version_id}` : ""}
          </p>
          {row.source_url && (
            <a href={row.source_url} target="_blank" rel="noreferrer">
              Open the official source text ↗
            </a>
          )}
        </div>
      )}
    </article>
  );
}

export default function Checklist({
  geminiConfigured,
  modelName,
}: {
  geminiConfigured: boolean;
  modelName?: string;
}) {
  const [facts, setFacts] = useState<FactDefinition[]>([]);
  const [groupLabels, setGroupLabels] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState("");

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [description, setDescription] = useState("");
  const [referenceDate, setReferenceDate] = useState(todayIso());
  const [regulator, setRegulator] = useState<"" | "RBI" | "SEBI">("");
  const [apiKey, setApiKey] = useState("");
  const [showKeyField, setShowKeyField] = useState(false);

  const [answers, setAnswers] = useState<Answers>({});
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState("");
  const [extractNote, setExtractNote] = useState("");

  const [result, setResult] = useState<ChecklistResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const [questionFilter, setQuestionFilter] = useState("");
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const [expandedBuckets, setExpandedBuckets] = useState<Record<string, boolean>>({});
  const [openBuckets, setOpenBuckets] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(BUCKET_META.map((item) => [item.bucket, item.openByDefault])),
  );

  useEffect(() => {
    listFacts()
      .then((payload) => {
        setFacts(payload.facts);
        setGroupLabels(payload.groups);
        const firstGroup = payload.facts[0]?.group;
        if (firstGroup) setOpenGroups({ [firstGroup]: true });
      })
      .catch((error: unknown) =>
        setLoadError(error instanceof Error ? error.message : "Could not load the question list."),
      );
  }, []);

  const factMap = useMemo(
    () => new Map(facts.map((fact) => [fact.key, fact])),
    [facts],
  );

  const grouped = useMemo(() => {
    const needle = questionFilter.trim().toLowerCase();
    const buckets = new Map<string, FactDefinition[]>();
    for (const fact of facts) {
      if (needle && !fact.question.toLowerCase().includes(needle) && !fact.key.includes(needle)) {
        continue;
      }
      const list = buckets.get(fact.group) ?? [];
      list.push(fact);
      buckets.set(fact.group, list);
    }
    return [...buckets.entries()];
  }, [facts, questionFilter]);

  const answeredCount = Object.keys(answers).length;

  const setAnswer = useCallback((key: string, value: AnswerValue | undefined) => {
    setAnswers((prior) => {
      const next = { ...prior };
      if (value === undefined) delete next[key];
      else next[key] = value;
      return next;
    });
  }, []);

  const run = useCallback(
    async (nextAnswers: Answers, date: string, reg: "" | "RBI" | "SEBI") => {
      setRunning(true);
      setRunError("");
      try {
        setResult(
          await runChecklist({
            entity_profile: nextAnswers,
            reference_date: date,
            regulator: reg === "" ? null : reg,
          }),
        );
      } catch (error) {
        setRunError(error instanceof Error ? error.message : "Could not build the checklist.");
      } finally {
        setRunning(false);
      }
    },
    [],
  );

  // On step 3 the checklist follows the answers: change one and it refreshes.
  const firstRender = useRef(true);
  useEffect(() => {
    if (step !== 3) return;
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    const timer = setTimeout(() => void run(answers, referenceDate, regulator), 350);
    return () => clearTimeout(timer);
  }, [answers, referenceDate, regulator, step, run]);

  async function handleExtract() {
    const text = description.trim();
    if (!text) {
      setExtractError("Please describe your organisation first, or skip to the questions.");
      return;
    }
    setExtracting(true);
    setExtractError("");
    setExtractNote("");
    try {
      const key = apiKey.trim();
      const payload = await extractFacts(key ? { description: text, api_key: key } : { description: text });
      setAnswers((prior) => ({ ...prior, ...(payload.facts as Answers) }));
      setEvidence((prior) => ({ ...prior, ...payload.evidence }));
      const filled = Object.keys(payload.facts).length;
      const skipped = payload.rejected.length + payload.unrecognised.length;
      setExtractNote(
        filled === 0
          ? "Your text did not clearly state any of the questions below, so nothing was filled in. Please answer them yourself."
          : `Filled in ${filled} answer${filled === 1 ? "" : "s"} from your text.`
            + (skipped > 0 ? ` ${skipped} guess${skipped === 1 ? " was" : "es were"} dropped as unsupported.` : "")
            + " Please check each one before continuing.",
      );
      const touched = Object.keys(payload.facts)
        .map((key2) => factMap.get(key2)?.group)
        .filter((group): group is string => Boolean(group));
      setOpenGroups((prior) => ({
        ...prior,
        ...Object.fromEntries(touched.map((group) => [group, true])),
      }));
      setStep(2);
    } catch (error) {
      setExtractError(error instanceof Error ? error.message : "Autofill could not be completed.");
    } finally {
      setExtracting(false);
    }
  }

  async function showChecklist() {
    setStep(3);
    firstRender.current = true;
    await run(answers, referenceDate, regulator);
  }

  function startOver() {
    setStep(1);
    setAnswers({});
    setEvidence({});
    setResult(null);
    setDescription("");
    setExtractNote("");
    setExtractError("");
    setRunError("");
  }

  function downloadChecklist() {
    if (!result) return;
    const lines: string[] = [
      "TAARR checklist",
      `Date checked against: ${result.reference_date}`,
      `Answers given: ${result.answered_fact_count}`,
      "",
    ];
    for (const meta of BUCKET_META) {
      const rows = result.groups[meta.bucket] ?? [];
      if (rows.length === 0) continue;
      lines.push(`## ${meta.title} (${rows.length})`);
      for (const row of rows) {
        lines.push(`- [${row.regulator ?? "—"} ${row.clause_id ?? ""}] ${modalityLine(row)}`);
        if (row.missing.length > 0) {
          lines.push(`    Still needed: ${row.missing.map((item) => item.question).join(" ")}`);
        }
        if (row.source_url) lines.push(`    Source: ${row.source_url}`);
      }
      lines.push("");
    }
    lines.push(result.notice);
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `taarr-checklist-${result.reference_date}.txt`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  const topQuestions = (result?.next_questions ?? []).slice(0, 6);

  return (
    <section className="workspace">
      <div className="workspace-heading">
        <div>
          <div className="eyebrow">GUIDED CHECK</div>
          <h2>Which rules apply to me?</h2>
          <p>
            Describe your organisation in your own words, check the answers, and get a plain-English
            checklist of RBI KYC and SEBI LODR obligations. Nothing is guessed: what you leave blank
            stays unknown.
          </p>
        </div>
      </div>

      {loadError && (
        <div className="notice error-notice">
          <strong>Could not load the questions</strong>
          <p>{loadError}</p>
        </div>
      )}

      <ol className="cl-steps" aria-label="Steps">
        {["Describe", "Check answers", "Your checklist"].map((label, index) => {
          const number = (index + 1) as 1 | 2 | 3;
          const state = step === number ? "active" : step > number ? "done" : "";
          return (
            <li key={label} className={state}>
              <button
                type="button"
                disabled={number > step}
                onClick={() => setStep(number)}
              >
                <span>{number}</span> {label}
              </button>
            </li>
          );
        })}
      </ol>

      {step === 1 && (
        <div className="cl-pane">
          <label className="field-label" htmlFor="cl-description">
            Tell us about your organisation
          </label>
          <textarea
            id="cl-description"
            className="text-input cl-textarea"
            rows={6}
            placeholder="For example: We are an NBFC regulated by the RBI. We onboard individual customers through our app without meeting them, and some are high risk."
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
          <div className="cl-example-row">
            <span className="cl-example-label">Try an example:</span>
            {EXAMPLES.map((example) => (
              <button
                key={example.label}
                type="button"
                className="cl-chip"
                onClick={() => setDescription(example.text)}
              >
                {example.label}
              </button>
            ))}
          </div>

          <div className="cl-grid-two">
            <div>
              <label className="field-label" htmlFor="cl-date">
                Which date should we check against?
              </label>
              <input
                id="cl-date"
                className="text-input"
                type="date"
                value={referenceDate}
                onChange={(event) => setReferenceDate(event.target.value)}
              />
              <p className="form-footnote">
                Rules come into force and change over time, so the answer depends on the date.
                Today is filled in for you.
              </p>
            </div>
            <div>
              <label className="field-label" htmlFor="cl-regulator">
                Which rule book?
              </label>
              <select
                id="cl-regulator"
                className="text-input"
                value={regulator}
                onChange={(event) => setRegulator(event.target.value as "" | "RBI" | "SEBI")}
              >
                <option value="">Both (RBI KYC and SEBI LODR)</option>
                <option value="RBI">RBI KYC only</option>
                <option value="SEBI">SEBI LODR only</option>
              </select>
              <p className="form-footnote">
                Pick one if you already know which regulator you fall under.
              </p>
            </div>
          </div>

          {!geminiConfigured && (
            <div className="cl-key-block">
              <button type="button" className="cl-link-button" onClick={() => setShowKeyField((v) => !v)}>
                {showKeyField ? "Hide the key box" : "Have a Gemini API key? Use it to autofill"}
              </button>
              {showKeyField && (
                <input
                  className="text-input"
                  type="password"
                  autoComplete="off"
                  placeholder="Paste your Gemini API key (used for this request only)"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                />
              )}
            </div>
          )}

          {extractError && (
            <div className="notice error-notice" role="alert">
              <strong>Autofill did not work</strong>
              <p>{extractError}</p>
              <p>You can still answer the questions yourself — the result is exactly the same.</p>
            </div>
          )}

          <div className="cl-actions">
            <button
              type="button"
              className="primary-button"
              disabled={extracting || (!geminiConfigured && !apiKey.trim())}
              onClick={() => void handleExtract()}
            >
              {extracting ? <span className="spinner" /> : null}
              {extracting ? "Reading your description…" : "Autofill the answers"}
              <span>→</span>
            </button>
            <button type="button" className="cl-secondary-button" onClick={() => setStep(2)}>
              Answer the questions myself
            </button>
          </div>
          <p className="form-footnote">
            Autofill only fills in this form from your own words, and must quote you for every
            answer it gives. It never decides whether a rule applies — the rule engine does that.
            {modelName ? <> Model: <code>{modelName}</code>.</> : null}
          </p>
        </div>
      )}

      {step === 2 && (
        <div className="cl-pane">
          {extractNote && (
            <div className="notice info-notice">
              <strong>Check these answers</strong>
              <p>{extractNote}</p>
            </div>
          )}
          <div className="cl-answers-top">
            <div>
              <strong>{answeredCount}</strong> of {facts.length} questions answered
              <p className="form-footnote">
                Answer only what you know. "Not sure" is a real answer here: the rule will be listed
                as needing more information instead of being wrongly ruled out.
              </p>
            </div>
            <input
              className="text-input cl-search"
              type="search"
              placeholder="Find a question…"
              value={questionFilter}
              onChange={(event) => setQuestionFilter(event.target.value)}
            />
          </div>

          {grouped.map(([group, groupFacts]) => {
            const open = openGroups[group] ?? false;
            const answeredHere = groupFacts.filter((fact) => fact.key in answers).length;
            return (
              <div className={open ? "cl-group open" : "cl-group"} key={group}>
                <button
                  type="button"
                  className="cl-group-head"
                  onClick={() => setOpenGroups((prior) => ({ ...prior, [group]: !open }))}
                >
                  <span>
                    {groupLabels[group] ?? group}
                    <small>
                      {answeredHere} of {groupFacts.length} answered
                    </small>
                  </span>
                  <span className="cl-caret">{open ? "−" : "+"}</span>
                </button>
                {open && (
                  <div className="cl-question-list">
                    {groupFacts.map((fact) => (
                      <div className="cl-question" key={fact.key}>
                        <div className="cl-question-text">
                          <p>{fact.question}</p>
                          {evidence[fact.key] && (
                            <small className="cl-evidence">From your text: “{evidence[fact.key]}”</small>
                          )}
                        </div>
                        <QuestionControl
                          fact={fact}
                          value={answers[fact.key]}
                          onChange={(value) => setAnswer(fact.key, value)}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}

          <div className="cl-sticky-bar">
            <span>
              <strong>{answeredCount}</strong> answered · checking against {referenceDate}
            </span>
            <div className="cl-actions">
              <button type="button" className="cl-secondary-button" onClick={() => setStep(1)}>
                Back
              </button>
              <button
                type="button"
                className="primary-button"
                disabled={running}
                onClick={() => void showChecklist()}
              >
                {running ? <span className="spinner" /> : null}
                Show my checklist <span>→</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="cl-pane">
          {runError && (
            <div className="notice error-notice" role="alert">
              <strong>Could not build the checklist</strong>
              <p>{runError}</p>
            </div>
          )}

          {result && (
            <>
              <div className="cl-tiles">
                <div className="cl-tile applies">
                  <strong>{result.counts.applies}</strong>
                  <span>Applies to you</span>
                </div>
                <div className="cl-tile unknown">
                  <strong>{result.counts.need_more_info}</strong>
                  <span>Need one more answer</span>
                </div>
                <div className="cl-tile no">
                  <strong>{result.counts.does_not_apply + result.counts.dropped}</strong>
                  <span>Does not apply</span>
                </div>
                {result.counts.conflict > 0 && (
                  <div className="cl-tile conflict">
                    <strong>{result.counts.conflict}</strong>
                    <span>Conflicting</span>
                  </div>
                )}
                <div className="cl-tile plain">
                  <strong>{result.answered_fact_count}</strong>
                  <span>Answers used</span>
                </div>
              </div>

              <div className="cl-run-row">
                <span className="date-chip">As of {result.reference_date}</span>
                {running && <span className="cl-updating"><span className="spinner dark" /> updating…</span>}
                <div className="cl-actions">
                  <button type="button" className="cl-secondary-button" onClick={() => setStep(2)}>
                    Change my answers
                  </button>
                  <button type="button" className="cl-secondary-button" onClick={downloadChecklist}>
                    Download
                  </button>
                  <button type="button" className="cl-secondary-button" onClick={startOver}>
                    Start over
                  </button>
                </div>
              </div>

              {topQuestions.length > 0 && (
                <div className="cl-unlock">
                  <h3>Answer these to settle more rules</h3>
                  <p className="form-footnote">
                    Each answer updates the checklist straight away. Leave anything you do not know.
                  </p>
                  <div className="cl-question-list">
                    {topQuestions.map((question) => (
                      <div className="cl-question" key={question.key}>
                        <div className="cl-question-text">
                          <p>{question.question}</p>
                          <small>
                            Settles {question.unblocks} rule{question.unblocks === 1 ? "" : "s"} ·{" "}
                            {question.group_label}
                          </small>
                        </div>
                        <QuestionControl
                          fact={question}
                          value={answers[question.key]}
                          onChange={(value) => setAnswer(question.key, value)}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {BUCKET_META.map((meta) => {
                const rows = result.groups[meta.bucket] ?? [];
                if (rows.length === 0) return null;
                const open = openBuckets[meta.bucket] ?? false;
                return (
                  <div className={`cl-bucket ${meta.tone}`} key={meta.bucket}>
                    <button
                      type="button"
                      className="cl-group-head"
                      onClick={() =>
                        setOpenBuckets((prior) => ({ ...prior, [meta.bucket]: !open }))
                      }
                    >
                      <span>
                        {meta.title} ({rows.length})<small>{meta.blurb}</small>
                      </span>
                      <span className="cl-caret">{open ? "−" : "+"}</span>
                    </button>
                    {open && (
                      <div className="cl-row-list">
                        {(expandedBuckets[meta.bucket] ? rows : rows.slice(0, ROW_PREVIEW)).map((row) => (
                          <ResultRow
                            key={row.obligation_id}
                            row={row}
                            facts={factMap}
                            answers={answers}
                            onAnswer={setAnswer}
                          />
                        ))}
                        {rows.length > ROW_PREVIEW && (
                          <button
                            type="button"
                            className="cl-secondary-button cl-show-all"
                            onClick={() =>
                              setExpandedBuckets((prior) => ({
                                ...prior,
                                [meta.bucket]: !prior[meta.bucket],
                              }))
                            }
                          >
                            {expandedBuckets[meta.bucket]
                              ? "Show fewer"
                              : `Show all ${rows.length}`}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              <div className="notice info-notice">
                <strong>Please read</strong>
                <p>{result.notice}</p>
              </div>
            </>
          )}

          {!result && !runError && (
            <div className="empty-state">
              <div className="empty-icon">…</div>
              <h3>Building your checklist</h3>
              <p>Running all {facts.length ? "60" : ""} obligations against your answers.</p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
