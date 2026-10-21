export type Outcome = "Applicable" | "Not applicable" | "Indeterminate" | "Conflict";

export interface HealthResponse {
  status: string;
  service: string;
  policy_configured: boolean;
  policy_required: boolean;
  gemini_api_key_configured: boolean;
  gemini_model?: string;
  env_file_found?: boolean;
  catalog: {
    obligations: number;
    versions: number;
    clauses: number;
  };
}

export interface ObligationSummary {
  obligation_id: string;
  instrument_id?: string | null;
  instrument_title?: string | null;
  regulator?: string | null;
  clause_id?: string | null;
  clause_summary?: string | null;
  version_count: number;
  verification_status?: string | null;
}

export interface EvidenceRecord {
  kind?: string;
  clause_id?: string;
  version_id?: string;
  obligation_id?: string;
  source_url?: string;
  verification_status?: string;
  effective_from?: string;
  effective_to?: string | null;
  selected?: boolean;
  relation_id?: string;
  [key: string]: unknown;
}

export interface Resolution {
  obligation_id: string;
  outcome: Outcome | null;
  reason: string;
  reference_date: string;
  version_id?: string | null;
  clause_id?: string | null;
  source_url?: string | null;
  missing_facts?: string[];
  evidence: EvidenceRecord[];
  dependencies?: Resolution[];
  retrieval_score?: number;
}

export interface QueryResponse {
  query: string;
  reference_date: string;
  entity_profile: Record<string, unknown>;
  policy: {
    no_version: string;
    missing_facts: string;
    unknown_precedence: string;
  };
  retrieved_count: number;
  outcomes: Resolution[];
  notice: string;
}

export interface ClauseHistoryResponse {
  clause_id: string;
  version_count: number;
  versions: Array<Record<string, unknown>>;
}

export interface BenchmarkMetric {
  n: number;
  accuracy: number | null;
  macro_f1: number | null;
  per_outcome: Record<
    Outcome,
    { support: number; precision: number; recall: number; f1: number }
  >;
  dropped_predictions: number;
}

export interface BenchmarkResponse {
  system_config: string;
  policy: Record<string, string>;
  metrics: BenchmarkMetric;
  items: Array<Record<string, unknown>>;
  message: string;
}

export interface ObligationListResponse {
  count: number;
  items: ObligationSummary[];
}

export interface ExemptionsResponse {
  clause_id: string;
  reference_date: string | null;
  count: number;
  exemptions: Array<Record<string, unknown>>;
}

export interface LlmCrossCheckItem {
  benchmark_item_id: string;
  target_obligation_id: string;
  gold_outcome: Outcome;
  llm_outcome: Outcome | null;
  agrees_with_gold: boolean;
  llm_raw_text: string;
  error: string | null;
}

export interface LlmCrossCheckResponse {
  model: string;
  api_calls?: number;
  n: number;
  agreement_with_gold: BenchmarkMetric;
  items: LlmCrossCheckItem[];
  notice: string;
}

export type FactType = "boolean" | "enum" | "number";

export interface FactDefinition {
  key: string;
  group: string;
  type: FactType;
  question: string;
  values?: string[];
  unit?: string;
  min?: number;
  max?: number;
}

export interface FactListResponse {
  groups: Record<string, string>;
  facts: FactDefinition[];
}

export interface FactExtractionResponse {
  facts: Record<string, unknown>;
  evidence: Record<string, string>;
  rejected: Array<{ key: string; reason: string }>;
  unrecognised: string[];
  model?: string;
  notice: string;
}

export interface ChecklistRow {
  obligation_id: string;
  regulator?: string | null;
  instrument_id?: string | null;
  instrument_title?: string | null;
  circular_url?: string | null;
  effective_from?: string | null;
  decided_by: string[];
  clause_id?: string | null;
  clause_summary?: string | null;
  action?: string | null;
  modality?: string | null;
  deadline?: string | null;
  verification_status?: string | null;
  outcome: Outcome | null;
  reason: string;
  source_url?: string | null;
  version_id?: string | null;
  missing: Array<{ key: string; question: string }>;
  evidence: EvidenceRecord[];
  dependencies?: Resolution[];
}

export type ChecklistBucket =
  | "applies"
  | "does_not_apply"
  | "need_more_info"
  | "conflict"
  | "dropped";

export interface ChecklistNextQuestion extends FactDefinition {
  unblocks: number;
  unblocks_obligation_ids: string[];
  group_label: string;
}

export interface ChecklistResponse {
  reference_date: string;
  regulator: "RBI" | "SEBI" | null;
  policy: Record<string, string>;
  answered_fact_count: number;
  counts: Record<ChecklistBucket, number>;
  total: number;
  groups: Record<ChecklistBucket, ChecklistRow[]>;
  next_questions: ChecklistNextQuestion[];
  notice: string;
}
