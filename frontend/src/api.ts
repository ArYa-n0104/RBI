import type {
  BenchmarkResponse,
  ClauseHistoryResponse,
  ExemptionsResponse,
  HealthResponse,
  LlmCrossCheckResponse,
  ObligationListResponse,
  QueryResponse,
} from "./types";

const API_BASE = (import.meta.env.VITE_TAARR_API_BASE_URL as string | undefined) ?? "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new Error("TAARR API is unreachable. Start the FastAPI backend on port 8000.");
  }

  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const maybeObject = payload as { detail?: unknown };
    const detail = maybeObject?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail !== undefined
          ? JSON.stringify(detail)
          : `Request failed with HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export function getHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/api/v1/health");
}

export function listObligations(): Promise<ObligationListResponse> {
  return requestJson<ObligationListResponse>("/api/v1/obligations");
}

export function runQuery(input: {
  query: string;
  reference_date: string;
  entity_profile: Record<string, unknown>;
}): Promise<QueryResponse> {
  return requestJson<QueryResponse>("/api/v1/query", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getClause(clauseId: string): Promise<ClauseHistoryResponse> {
  return requestJson<ClauseHistoryResponse>(
    `/api/v1/clause/${encodeURIComponent(clauseId)}`,
  );
}

export function getExemptions(
  clauseId: string,
  referenceDate?: string,
): Promise<ExemptionsResponse> {
  const params = referenceDate
    ? `?reference_date=${encodeURIComponent(referenceDate)}`
    : "";
  return requestJson<ExemptionsResponse>(
    `/api/v1/clause/${encodeURIComponent(clauseId)}/exemptions${params}`,
  );
}

export function runBenchmark(): Promise<BenchmarkResponse> {
  return requestJson<BenchmarkResponse>("/api/v1/benchmark/run", {
    method: "POST",
    body: JSON.stringify({ system_config: "TAARR" }),
  });
}

export function runLlmCrossCheck(input: {
  api_key?: string;
  limit: number;
  model?: string;
}): Promise<LlmCrossCheckResponse> {
  return requestJson<LlmCrossCheckResponse>("/api/v1/baseline/llm-crosscheck", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
