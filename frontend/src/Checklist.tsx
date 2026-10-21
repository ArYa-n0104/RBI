import { useCallback, useEffect, useMemo, useState } from "react";
import { extractFacts, getClause, listFacts, runChecklist } from "./api";
import type {
  ChecklistBucket,
  ChecklistNextQuestion,
  ChecklistResponse,
  ChecklistRow,
  FactDefinition,
} from "./types";

type AnswerValue = boolean | string | number;
type Answers = Record<string, AnswerValue>;
type Regulator = "" | "RBI" | "SEBI";
type Row = ChecklistRow & { bucket: ChecklistBucket };

const ROW_PREVIEW = 8;
const TOP_QUESTIONS = 6;

function todayIso(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

function niceDate(iso?: string | null): string {
  if (!iso) return "";
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function circularName(title?: string | null): string {
  if (!title) return "Circular";
  if (/know your customer/i.test(title)) return "RBI KYC Master Direction, 2016";
  if (/listing obligations/i.test(title)) return "SEBI LODR Regulations, 2015";
  return title;
}

/** Natural sort for clause ids like paragraph-5A(b) < paragraph-10(1) < paragraph-38. */
function clauseSortKey(clause?: string | null): string {
  return (clause ?? "").replace(/\d+/g, (digits) => digits.padStart(4, "0"));
}

const EXAMPLES: Array<{ label: string; text: string }> = [
  {
    label: "NBFC onboarding over an app",
    text:
      "We are an NBFC regulated by the RBI. Our customer is an individual. We onboard customers "
      + "without meeting them face to face through our mobile app. We do not use video based "
      + "identification (V-CIP). The customer is rated high risk.",
  },
  {
    label: "Bank with V-CIP, small account",
    text:
      "We are a bank regulated by the RBI. The customer is an individual walk-in customer. We "
      + "onboard customers using video based identification (V-CIP). The account is a small "
      + "account. The customer is rated low risk.",
  },
  {
    label: "Cash transaction, walk-in",
    text:
      "We are a bank regulated by the RBI. The customer is an individual walk-in customer who is "
      + "not an account holder. The transaction amount is 60000 rupees in cash.",
  },
  {
    label: "Listed company, board questions",
    text:
      "We are a company listed on a stock exchange and we are in the top 2000 listed entities by "
      + "market capitalisation. Our chairperson is non-executive and is not related to the promoter. "
      + "Our paid up equity capital is 25 crore and our net worth is 600 crore.",
  },
];

function actionLine(row: ChecklistRow): string {
  const action = row.action?.trim();
  if (!action) return row.clause_summary ?? row.obligation_id;
  const modality = (row.modality ?? "").toLowerCase();
  if (modality === "must") return `You must: ${action}`;
  if (modality === "must_not") return `You must not: ${action}`;
  if (modality === "may") return `You may: ${action}`;
  return action;
}

function verdict(row: Row, referenceDate: string): { label: string; tone: string; text: string } {
  if (row.bucket === "applies") {
    return {
      label: "Applies to you",
      tone: "applies",
      text: `It is in force on ${niceDate(referenceDate)} and your answers meet its conditions.`,
    };
  }
  if (row.bucket === "need_more_info") {
    return {
      label: "Depends on your answer",
      tone: "unknown",
      text: "One fact is still unknown. Answer the question below and the result will update.",
    };
  }
  if (row.bucket === "conflict") {
    return {
      label: "Needs a human decision",
      tone: "conflict",
      text: "Two rules point in opposite directions for your answers.",
    };
  }
  if (row.bucket === "dropped" || /no recorded version/i.test(row.reason)) {
    return {
      label: "Not in force on this date",
      tone: "no",
      text: row.effective_from
        ? `This rule starts on ${niceDate(row.effective_from)}. Pick a later date to include it.`
        : "No version of this rule was in force on the date you picked.",
    };
  }
  return {
    label: "Does not apply to you",
    tone: "no",
    text: "Your answers rule it out, or an exemption covers your case.",
  };
}

/** Yes / No / Not sure chips, a choice list, or a number box. */
function QuestionControl({
  fact,
  value,
  onChange,
}: {
  fact: FactDefinition;
  value: AnswerValue | undefined;
  onChange: (value: AnswerValue | undefined) => void;
}) {
  if (fact.type === "boolean" || fact.type === "enum") {
    const options: Array<{ label: string; value: AnswerValue }> =
      fact.type === "boolean"
        ? [{ label: "Yes", value: true }, { label: "No", value: false }]
        : (fact.values ?? []).map((option) => ({ label: option, value: option }));
    return (
      <div className="cl-chips" role="group" aria-label={fact.question}>
        {options.map((option) => (
          <button
            key={String(option.value)}
            type="button"
            className={value === option.value ? "cl-chip active" : "cl-chip"}
            onClick={() => onChange(value === option.value ? undefined : option.value)}
          >
            {option.label}
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
        type="number"
        inputMode="decimal"
        min={fact.min}
        max={fact.max}
        placeholder="Leave blank if unknown"
        value={typeof value === "number" ? String(value) : ""}
        onChange={(event) => {
          const raw = event.target.value.trim();
          const parsed = Number(raw);
          onChange(raw && Number.isFinite(parsed) ? parsed : undefined);
        }}
      />
      {fact.unit && <span className="cl-unit">{fact.unit}</span>}
    </div>
  );
}

function QuestionRow({
  fact,
  answers,
  onAnswer,
  note,
}: {
  fact: FactDefinition;
  answers: Answers;
  onAnswer: (key: string, value: AnswerValue | undefined) => void;
  note?: string;
}) {
  return (
    <div className="cl-question">
      <div className="cl-question-text">
        <p>{fact.question}</p>
        {note && <small className={note.startsWith("From your text") ? "cl-evidence" : ""}>{note}</small>}
      </div>
      <QuestionControl
        fact={fact}
        value={answers[fact.key]}
        onChange={(value) => onAnswer(fact.key, value)}
      />
    </div>
  );
}

/** One rule in a list. The whole card opens the rule; the link opens the circular. */
function RuleCard({ row, onOpen, showNeeds }: { row: Row; onOpen: () => void; showNeeds?: boolean }) {
  return (
    <article className="cl-row clickable" onClick={onOpen}>
      <div className="cl-row-main">
        <div>
          <p className="cl-row-action">{actionLine(row)}</p>
          {row.clause_summary && row.action && <p className="cl-row-summary">{row.clause_summary}</p>}
          {showNeeds && row.missing.length > 0 && (
            <p className="cl-row-needs">Needs: {row.missing.map((item) => item.question).join(" ")}</p>
          )}
          <div className="cl-row-tags">
            <span className="cl-tag">{circularName(row.instrument_title)}</span>
            {row.clause_id && <span className="cl-tag mono">{row.clause_id}</span>}
            {row.deadline && <span className="cl-tag amber">Deadline {niceDate(row.deadline)}</span>}
          </div>
        </div>
        <div className="cl-row-buttons">
          <button
            type="button"
            className="cl-secondary-button small"
            onClick={(event) => {
              event.stopPropagation();
              onOpen();
            }}
          >
            Open rule
          </button>
          {row.circular_url && (
            <a
              className="cl-link-button"
              href={row.circular_url}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
            >
              Official circular ↗
            </a>
          )}
        </div>
      </div>
    </article>
  );
}

/** The rule page: what it says, your result, the questions that decide it, the circular. */
function RuleDialog({
  row,
  facts,
  answers,
  onAnswer,
  onClose,
  referenceDate,
  updating,
}: {
  row: Row;
  facts: Map<string, FactDefinition>;
  answers: Answers;
  onAnswer: (key: string, value: AnswerValue | undefined) => void;
  onClose: () => void;
  referenceDate: string;
  updating: boolean;
}) {
  const [clauseText, setClauseText] = useState<string | null>(null);
  const [showText, setShowText] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setClauseText(null);
    if (!row.clause_id) return;
    getClause(row.clause_id)
      .then((payload) => {
        if (cancelled) return;
        const match = payload.versions
          .filter((version) => version.obligation_id === row.obligation_id)
          .pop();
        const text = (match ?? payload.versions[payload.versions.length - 1])?.clause_text;
        setClauseText(typeof text === "string" ? text : "");
      })
      .catch(() => {
        if (!cancelled) setClauseText("");
      });
    return () => {
      cancelled = true;
    };
  }, [row.clause_id, row.obligation_id]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  const result = verdict(row, referenceDate);
  const deciding = row.decided_by
    .map((key) => facts.get(key))
    .filter((fact): fact is FactDefinition => Boolean(fact));

  return (
    <div className="cl-dialog-overlay" onClick={onClose}>
      <div
        className="cl-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cl-dialog-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="cl-dialog-head">
          <div className="cl-row-tags">
            <span className="cl-tag">{circularName(row.instrument_title)}</span>
            {row.clause_id && <span className="cl-tag mono">{row.clause_id}</span>}
          </div>
          <button type="button" className="cl-close" onClick={onClose} aria-label="Close" autoFocus>
            ×
          </button>
        </div>

        <h3 id="cl-dialog-title">{actionLine(row)}</h3>
        {row.clause_summary && <p className="cl-dialog-summary">{row.clause_summary}</p>}

        <div className={`cl-verdict ${result.tone}`}>
          <strong>
            <span className={`cl-dot ${result.tone}`} /> {result.label}
            {updating && <span className="cl-updating-inline"> · updating…</span>}
          </strong>
          <p>{result.text}</p>
        </div>

        {deciding.length > 0 && (
          <div className="cl-dialog-section">
            <h4>What decides this rule</h4>
            <p className="form-footnote">
              Change an answer and the result above updates straight away (and your checklist with it).
            </p>
            <div className="cl-question-list flush">
              {deciding.map((fact) => (
                <QuestionRow
                  key={fact.key}
                  fact={fact}
                  answers={answers}
                  onAnswer={onAnswer}
                  note={row.missing.some((item) => item.key === fact.key) ? "Still needed" : undefined}
                />
              ))}
            </div>
          </div>
        )}

        <div className="cl-dialog-section">
          <button type="button" className="cl-link-button" onClick={() => setShowText((value) => !value)}>
            {showText ? "Hide the exact clause text" : "Read the exact clause text"}
          </button>
          {showText && (
            <blockquote className="cl-clause-text">
              {clauseText === null ? "Loading…" : clauseText || "Clause text is not available."}
            </blockquote>
          )}
        </div>

        <div className="cl-dialog-foot">
          {row.circular_url && (
            <a className="primary-button cl-link-primary" href={row.circular_url} target="_blank" rel="noreferrer">
              Open the official circular <span>↗</span>
            </a>
          )}
          <p className="form-footnote">
            {row.instrument_title}
            {row.effective_from ? ` · In force from ${niceDate(row.effective_from)}` : ""}
            {row.deadline ? ` · Deadline ${niceDate(row.deadline)}` : ""}
          </p>
        </div>
      </div>
    </div>
  );
}

function CircularBrowser({ rows, onOpen }: { rows: Row[]; onOpen: (id: string) => void }) {
  const [search, setSearch] = useState("");
  const [openCircular, setOpenCircular] = useState<Record<string, boolean>>({});

  const circulars = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const byTitle = new Map<string, Row[]>();
    for (const row of rows) {
      const haystack = `${row.action ?? ""} ${row.clause_summary ?? ""} ${row.clause_id ?? ""}`.toLowerCase();
      if (needle && !haystack.includes(needle)) continue;
      const title = row.instrument_title ?? "Other";
      byTitle.set(title, [...(byTitle.get(title) ?? []), row]);
    }
    return [...byTitle.entries()].map(([title, list]) => ({
      title,
      rows: [...list].sort((a, b) => clauseSortKey(a.clause_id).localeCompare(clauseSortKey(b.clause_id))),
    }));
  }, [rows, search]);

  return (
    <div className="cl-pane">
      <p className="cl-lead">
        Pick a circular, then click any rule to see what it says, whether it applies to you, the
        questions that decide it, and a link to the official text.
      </p>
      <input
        type="search"
        className="cl-search wide"
        placeholder="Search rules — for example: high risk, PAN, V-CIP, chairperson"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {rows.length === 0 && <p className="form-footnote">Loading the circulars…</p>}
      {rows.length > 0 && circulars.length === 0 && <p className="form-footnote">No rule matches that search.</p>}
      {circulars.map(({ title, rows: list }) => {
        const open = search.trim() !== "" || (openCircular[title] ?? false);
        const applies = list.filter((row) => row.bucket === "applies").length;
        const url = list[0]?.circular_url;
        return (
          <div className={open ? "cl-group open" : "cl-group"} key={title}>
            <button
              type="button"
              className="cl-group-head"
              onClick={() => setOpenCircular((prior) => ({ ...prior, [title]: !open }))}
            >
              <span>
                {title}
                <small>
                  {list[0]?.regulator} · {list.length} rule{list.length === 1 ? "" : "s"} · {applies} apply to
                  you with your current answers
                </small>
              </span>
              <span className="cl-caret">{open ? "−" : "+"}</span>
            </button>
            {open && (
              <div className="cl-circular-body">
                {url && (
                  <a className="cl-link-button" href={url} target="_blank" rel="noreferrer">
                    Open the official circular ↗
                  </a>
                )}
                <ul className="cl-rule-index">
                  {list.map((row) => (
                    <li key={row.obligation_id}>
                      <button type="button" onClick={() => onOpen(row.obligation_id)}>
                        <span className={`cl-dot ${verdict(row, "").tone}`} />
                        <span className="cl-rule-index-clause">{row.clause_id}</span>
                        <span className="cl-rule-index-text">{actionLine(row)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        );
      })}
      <p className="form-footnote cl-legend">
        <span className="cl-dot applies" /> applies to you <span className="cl-dot unknown" /> depends on an
        answer <span className="cl-dot no" /> does not apply
      </p>
    </div>
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

  const [mode, setMode] = useState<"guided" | "browse">("guided");
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [description, setDescription] = useState("");
  const [referenceDate, setReferenceDate] = useState(todayIso());
  const [regulator, setRegulator] = useState<Regulator>("");

  const [answers, setAnswers] = useState<Answers>({});
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState("");
  const [extractNote, setExtractNote] = useState("");
  const [usedModel, setUsedModel] = useState("");

  const [result, setResult] = useState<ChecklistResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const [openRuleId, setOpenRuleId] = useState<string | null>(null);

  const [showAllQuestions, setShowAllQuestions] = useState(false);
  const [questionFilter, setQuestionFilter] = useState("");
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const [showAll, setShowAll] = useState<Record<string, boolean>>({});

  useEffect(() => {
    listFacts()
      .then((payload) => {
        setFacts(payload.facts);
        setGroupLabels(payload.groups);
      })
      .catch((error: unknown) =>
        setLoadError(error instanceof Error ? error.message : "Could not load the question list."),
      );
  }, []);

  // The checklist is local and deterministic (no Gemini), so it simply follows the answers.
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      setRunning(true);
      setRunError("");
      try {
        const payload = await runChecklist({ entity_profile: answers, reference_date: referenceDate });
        if (!cancelled) setResult(payload);
      } catch (error) {
        if (!cancelled) setRunError(error instanceof Error ? error.message : "Could not build the checklist.");
      } finally {
        if (!cancelled) setRunning(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [answers, referenceDate]);

  const factMap = useMemo(() => new Map(facts.map((fact) => [fact.key, fact])), [facts]);

  const allRows: Row[] = useMemo(() => {
    if (!result) return [];
    return (Object.keys(result.groups) as ChecklistBucket[]).flatMap((bucket) =>
      result.groups[bucket].map((row) => ({ ...row, bucket })),
    );
  }, [result]);

  const rows = useMemo(
    () => allRows.filter((row) => !regulator || row.regulator === regulator),
    [allRows, regulator],
  );

  const bucketRows = useCallback(
    (...buckets: ChecklistBucket[]) => rows.filter((row) => buckets.includes(row.bucket)),
    [rows],
  );

  const nextQuestions: ChecklistNextQuestion[] = useMemo(() => {
    if (!result) return [];
    const visible = new Set(rows.map((row) => row.obligation_id));
    return result.next_questions
      .map((question) => {
        const ids = question.unblocks_obligation_ids.filter((id) => visible.has(id));
        return { ...question, unblocks: ids.length, unblocks_obligation_ids: ids };
      })
      .filter((question) => question.unblocks > 0 && !(question.key in answers))
      .sort((a, b) => b.unblocks - a.unblocks);
  }, [result, rows, answers]);

  const openRow = openRuleId ? allRows.find((row) => row.obligation_id === openRuleId) ?? null : null;
  const closeRule = useCallback(() => setOpenRuleId(null), []);

  const setAnswer = useCallback((key: string, value: AnswerValue | undefined) => {
    setAnswers((prior) => {
      const next = { ...prior };
      if (value === undefined) delete next[key];
      else next[key] = value;
      return next;
    });
  }, []);

  async function handleExtract() {
    const text = description.trim();
    if (!text) {
      setExtractError("Please describe your organisation first, or answer the questions yourself.");
      return;
    }
    setExtracting(true);
    setExtractError("");
    setExtractNote("");
    try {
      // One click = one Gemini request. Key and model are read from .env on the server.
      const payload = await extractFacts({ description: text });
      if (payload.model) setUsedModel(payload.model);
      setAnswers((prior) => ({ ...prior, ...(payload.facts as Answers) }));
      setEvidence((prior) => ({ ...prior, ...payload.evidence }));
      const filled = Object.keys(payload.facts).length;
      setExtractNote(
        filled === 0
          ? "Your text did not clearly answer any question, so nothing was filled in. Please answer the questions below."
          : `Found ${filled} answer${filled === 1 ? "" : "s"} in your text. Check them, then see your checklist.`,
      );
      setStep(2);
    } catch (error) {
      setExtractError(error instanceof Error ? error.message : "Autofill could not be completed.");
    } finally {
      setExtracting(false);
    }
  }

  function startOver() {
    setStep(1);
    setAnswers({});
    setEvidence({});
    setDescription("");
    setExtractNote("");
    setExtractError("");
    setShowAllQuestions(false);
  }

  function downloadChecklist() {
    const sections: Array<[string, Row[]]> = [
      ["Applies to you", bucketRows("applies")],
      ["Depends on your situation", bucketRows("need_more_info")],
      ["Needs a human decision", bucketRows("conflict")],
      ["Does not apply", bucketRows("does_not_apply", "dropped")],
    ];
    const lines = [
      "TAARR checklist",
      `Date checked against: ${niceDate(referenceDate)}`,
      `Rule book: ${regulator || "RBI KYC and SEBI LODR"}`,
      "",
    ];
    for (const [title, list] of sections) {
      if (list.length === 0) continue;
      lines.push(`## ${title} (${list.length})`);
      for (const row of list) {
        lines.push(`- ${actionLine(row)}  [${circularName(row.instrument_title)}, ${row.clause_id ?? ""}]`);
        if (row.missing.length) lines.push(`    Needs: ${row.missing.map((item) => item.question).join(" ")}`);
        if (row.circular_url) lines.push(`    Circular: ${row.circular_url}`);
      }
      lines.push("");
    }
    if (result) lines.push(result.notice);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" }));
    link.download = `taarr-checklist-${referenceDate}.txt`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  const applies = bucketRows("applies");
  const depends = bucketRows("need_more_info");
  const conflict = bucketRows("conflict");
  const notApplies = bucketRows("does_not_apply", "dropped");
  const foundKeys = Object.keys(evidence).filter((key) => key in answers);
  const usefulQuestions = nextQuestions.slice(0, TOP_QUESTIONS);

  const groupedFacts = useMemo(() => {
    const needle = questionFilter.trim().toLowerCase();
    const groups = new Map<string, FactDefinition[]>();
    for (const fact of facts) {
      if (needle && !fact.question.toLowerCase().includes(needle)) continue;
      groups.set(fact.group, [...(groups.get(fact.group) ?? []), fact]);
    }
    return [...groups.entries()];
  }, [facts, questionFilter]);

  function renderRuleList(list: Row[], key: string, showNeeds = false) {
    const visible = showAll[key] ? list : list.slice(0, ROW_PREVIEW);
    return (
      <div className="cl-row-list">
        {visible.map((row) => (
          <RuleCard
            key={row.obligation_id}
            row={row}
            showNeeds={showNeeds}
            onOpen={() => setOpenRuleId(row.obligation_id)}
          />
        ))}
        {list.length > ROW_PREVIEW && (
          <button
            type="button"
            className="cl-secondary-button cl-show-all"
            onClick={() => setShowAll((prior) => ({ ...prior, [key]: !prior[key] }))}
          >
            {showAll[key] ? "Show fewer" : `Show all ${list.length}`}
          </button>
        )}
      </div>
    );
  }

  return (
    <section className="workspace">
      <div className="workspace-heading">
        <div>
          <div className="eyebrow">CHECK MY RULES</div>
          <h2>Which rules apply to me?</h2>
          <p>
            Describe your organisation, confirm a few answers, and get a plain-English list of the
            RBI KYC and SEBI LODR rules that apply — each one linked to its official circular.
          </p>
        </div>
      </div>

      <div className="cl-mode" role="tablist" aria-label="How do you want to start?">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "guided"}
          className={mode === "guided" ? "active" : ""}
          onClick={() => setMode("guided")}
        >
          Describe my organisation
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "browse"}
          className={mode === "browse" ? "active" : ""}
          onClick={() => setMode("browse")}
        >
          Browse circulars and rules
        </button>
      </div>

      {loadError && (
        <div className="notice error-notice cl-pane-notice">
          <strong>Could not load the questions</strong>
          <p>{loadError}</p>
        </div>
      )}
      {runError && (
        <div className="notice error-notice cl-pane-notice" role="alert">
          <strong>Could not build the checklist</strong>
          <p>{runError}</p>
        </div>
      )}

      {mode === "browse" && <CircularBrowser rows={allRows} onOpen={setOpenRuleId} />}

      {mode === "guided" && (
        <>
          <ol className="cl-steps" aria-label="Steps">
            {["Describe", "Confirm answers", "Your checklist"].map((label, index) => {
              const number = (index + 1) as 1 | 2 | 3;
              const state = step === number ? "active" : step > number ? "done" : "";
              return (
                <li key={label} className={state}>
                  <button type="button" onClick={() => setStep(number)}>
                    <span>{number}</span> {label}
                  </button>
                </li>
              );
            })}
          </ol>

          {step === 1 && (
            <div className="cl-pane">
              <label className="field-label" htmlFor="cl-description">
                Tell us about your organisation and customer
              </label>
              <textarea
                id="cl-description"
                className="cl-textarea"
                rows={5}
                placeholder="For example: We are an NBFC regulated by the RBI. Our customer is an individual. We onboard customers through our mobile app without meeting them. The customer is rated high risk."
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
              <div className="cl-example-row">
                <span className="cl-example-label">Or try an example:</span>
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
                    Check against which date?
                  </label>
                  <input
                    id="cl-date"
                    type="date"
                    value={referenceDate}
                    onChange={(event) => setReferenceDate(event.target.value || todayIso())}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="cl-regulator">
                    Which rule book?
                  </label>
                  <select
                    id="cl-regulator"
                    value={regulator}
                    onChange={(event) => setRegulator(event.target.value as Regulator)}
                  >
                    <option value="">Both (RBI KYC and SEBI LODR)</option>
                    <option value="RBI">RBI KYC only</option>
                    <option value="SEBI">SEBI LODR only</option>
                  </select>
                </div>
              </div>

              {!geminiConfigured && (
                <div className="notice info-notice">
                  <strong>Autofill needs a Gemini key in your .env file</strong>
                  <p>
                    Add <code>GEMINI_API_KEY=...</code> and <code>GEMINI_MODEL=...</code> to the{" "}
                    <code>.env</code> file in the project folder and save it — no restart needed. Or
                    answer the questions yourself.
                  </p>
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
                  disabled={extracting}
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
                Autofill only fills in answers your text clearly states, quoting you for each one. It
                never decides whether a rule applies — the rule engine does. One click is one Gemini
                request.
                {usedModel || modelName ? <> Model: <code>{usedModel || modelName}</code>.</> : null}
              </p>
            </div>
          )}

          {step === 2 && (
            <div className="cl-pane">
              {extractNote && <p className="cl-lead">{extractNote}</p>}

              {foundKeys.length > 0 && (
                <div className="cl-card">
                  <h3>Found in your text</h3>
                  <div className="cl-question-list flush">
                    {foundKeys.map((key) => {
                      const fact = factMap.get(key);
                      return fact ? (
                        <QuestionRow
                          key={key}
                          fact={fact}
                          answers={answers}
                          onAnswer={setAnswer}
                          note={`From your text: “${evidence[key]}”`}
                        />
                      ) : null;
                    })}
                  </div>
                </div>
              )}

              {usefulQuestions.length > 0 && (
                <div className="cl-card">
                  <h3>{foundKeys.length > 0 ? "Optional: a few more questions" : "Start with these questions"}</h3>
                  <p className="form-footnote">
                    These settle the most rules. Skip any you do not know — skipping never rules a rule out.
                  </p>
                  <div className="cl-question-list flush">
                    {usefulQuestions.map((question) => (
                      <QuestionRow
                        key={question.key}
                        fact={question}
                        answers={answers}
                        onAnswer={setAnswer}
                        note={`Settles ${question.unblocks} rule${question.unblocks === 1 ? "" : "s"}`}
                      />
                    ))}
                  </div>
                </div>
              )}

              <button
                type="button"
                className="cl-link-button cl-all-questions-toggle"
                onClick={() => setShowAllQuestions((value) => !value)}
              >
                {showAllQuestions ? "Hide the full question list" : `See all ${facts.length} questions`}
              </button>

              {showAllQuestions && (
                <div className="cl-all-questions">
                  <input
                    type="search"
                    className="cl-search"
                    placeholder="Find a question…"
                    value={questionFilter}
                    onChange={(event) => setQuestionFilter(event.target.value)}
                  />
                  {groupedFacts.map(([group, groupFacts]) => {
                    const open = questionFilter.trim() !== "" || (openGroups[group] ?? false);
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
                              <QuestionRow
                                key={fact.key}
                                fact={fact}
                                answers={answers}
                                onAnswer={setAnswer}
                                note={evidence[fact.key] ? `From your text: “${evidence[fact.key]}”` : undefined}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="cl-sticky-bar">
                <span>
                  {result ? (
                    <>
                      <strong>{applies.length}</strong> rule{applies.length === 1 ? "" : "s"} apply so far
                    </>
                  ) : (
                    "Working…"
                  )}
                </span>
                <div className="cl-actions">
                  <button type="button" className="cl-secondary-button" onClick={() => setStep(1)}>
                    Back
                  </button>
                  <button type="button" className="primary-button" onClick={() => setStep(3)}>
                    Show my checklist <span>→</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="cl-pane">
              {!result ? (
                <div className="empty-state">
                  <div className="empty-icon">…</div>
                  <h3>Building your checklist</h3>
                </div>
              ) : (
                <>
                  <p className="cl-lead big">
                    <strong>{applies.length}</strong> rule{applies.length === 1 ? "" : "s"} apply to you on{" "}
                    {niceDate(referenceDate)}.{" "}
                    {depends.length > 0 && <>{depends.length} more depend on your situation. </>}
                    {running && <span className="cl-updating-inline">Updating…</span>}
                  </p>

                  <div className="cl-tiles">
                    <div className="cl-tile applies">
                      <strong>{applies.length}</strong>
                      <span>Apply to you</span>
                    </div>
                    <div className="cl-tile unknown">
                      <strong>{depends.length}</strong>
                      <span>Depend on your situation</span>
                    </div>
                    <div className="cl-tile no">
                      <strong>{notApplies.length}</strong>
                      <span>Do not apply</span>
                    </div>
                    {conflict.length > 0 && (
                      <div className="cl-tile conflict">
                        <strong>{conflict.length}</strong>
                        <span>Need a human decision</span>
                      </div>
                    )}
                  </div>

                  <div className="cl-run-row">
                    <span className="date-chip">
                      {regulator ? `${regulator} only` : "RBI + SEBI"} · {niceDate(referenceDate)}
                    </span>
                    <div className="cl-actions">
                      <button type="button" className="cl-secondary-button" onClick={() => setStep(2)}>
                        Change my answers
                      </button>
                      <button type="button" className="cl-secondary-button" onClick={() => setMode("browse")}>
                        Browse circulars
                      </button>
                      <button type="button" className="cl-secondary-button" onClick={downloadChecklist}>
                        Download
                      </button>
                      <button type="button" className="cl-secondary-button" onClick={startOver}>
                        Start over
                      </button>
                    </div>
                  </div>

                  <div className="cl-bucket applies">
                    <div className="cl-bucket-title">
                      <h3>Apply to you ({applies.length})</h3>
                      <p>Click a rule to read it, see why it applies, and open its official circular.</p>
                    </div>
                    {applies.length === 0 ? (
                      <p className="form-footnote cl-bucket-empty">
                        None yet. Answer a few questions so the engine can decide.
                      </p>
                    ) : (
                      renderRuleList(applies, "applies")
                    )}
                  </div>

                  {conflict.length > 0 && (
                    <div className="cl-bucket conflict">
                      <div className="cl-bucket-title">
                        <h3>Need a human decision ({conflict.length})</h3>
                        <p>Two rules point in opposite directions for your answers.</p>
                      </div>
                      {renderRuleList(conflict, "conflict")}
                    </div>
                  )}

                  {depends.length > 0 && (
                    <div className="cl-bucket unknown">
                      <div className="cl-bucket-title">
                        <h3>Depend on your situation ({depends.length})</h3>
                        <p>
                          These apply only in particular cases — for example a trust customer or a foreign
                          student. Answer below if a case is relevant to you; otherwise you can ignore them.
                        </p>
                      </div>
                      {usefulQuestions.length > 0 && (
                        <div className="cl-question-list">
                          {usefulQuestions.map((question) => (
                            <QuestionRow
                              key={question.key}
                              fact={question}
                              answers={answers}
                              onAnswer={setAnswer}
                              note={`Settles ${question.unblocks} rule${question.unblocks === 1 ? "" : "s"}`}
                            />
                          ))}
                        </div>
                      )}
                      <details className="cl-details">
                        <summary>See the {depends.length} rules</summary>
                        {renderRuleList(depends, "depends", true)}
                      </details>
                    </div>
                  )}

                  {notApplies.length > 0 && (
                    <div className="cl-bucket no">
                      <details className="cl-details">
                        <summary>Do not apply to you ({notApplies.length})</summary>
                        {renderRuleList(notApplies, "no")}
                      </details>
                    </div>
                  )}

                  <p className="form-footnote cl-disclaimer">{result.notice}</p>
                </>
              )}
            </div>
          )}
        </>
      )}

      {openRow && (
        <RuleDialog
          row={openRow}
          facts={factMap}
          answers={answers}
          onAnswer={setAnswer}
          onClose={closeRule}
          referenceDate={referenceDate}
          updating={running}
        />
      )}
    </section>
  );
}
