/** Typed browser client for the PayLens HTTP API. */
import { clearSession, SESSION_KEY } from "./session";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEV_API_KEY = process.env.NEXT_PUBLIC_PAYLENS_DEV_API_KEY ?? "";

function authHeaders(): HeadersInit {
  // Production uses a short-lived Cognito token; the development key is local-only fallback.
  const token = typeof window !== "undefined" ? window.sessionStorage.getItem(SESSION_KEY) : null;
  if (token) return { Authorization: `Bearer ${token}` };
  return DEV_API_KEY ? { "X-PayLens-Dev-Key": DEV_API_KEY } : {};
}

const requestOptions = (headers: HeadersInit = {}): RequestInit => ({ headers, credentials: "include" });

export type AnalysisSummary = {
  analysis_id: string;
  status: "COMPLETED";
  filename: string;
  file_size: number;
  transaction_count: number;
  insight_count: number;
  currencies: string[];
  comparison_period: { current_start: string; current_end: string; baseline: string };
  performance: Record<string, number>;
};

export type OverallMetrics = {
  transaction_count: number;
  successful_transaction_count: number;
  failed_transaction_count: number;
  success_rate: string;
  failure_rate: string;
  refund_rate: string;
  dispute_rate: string;
};

export type CurrencyMetrics = {
  attempted_value: string;
  successful_value: string;
  failed_attempted_value: string;
  average_transaction_value: string;
  refund_amount: string;
  dispute_amount: string;
  processing_fees: string;
  provider_fees: string;
  other_costs: string;
  total_cost: string;
  effective_cost_rate: string | null;
};

export type KpiResponse = {
  analysis_id: string;
  overall: OverallMetrics;
  currencies: Record<string, CurrencyMetrics>;
};

export type Insight = {
  insight_id: string;
  type: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  segment: Record<string, string>;
  metric: string;
  baseline: string | null;
  current: string;
  absolute_difference: string | null;
  relative_change: string | null;
  affected_attempted_value: Record<string, string>;
  affected_refund_amount: Record<string, string>;
  affected_dispute_amount: Record<string, string>;
  affected_payment_cost: Record<string, string>;
  transaction_count: number;
  affected_transaction_count: number;
  confidence: string;
  supporting_metrics: Record<string, string | number>;
  /** Included in dashboards so expanding a finding needs no second request. */
  explanation?: Explanation;
};

export type InsightsResponse = { analysis_id: string; count: number; insights: Insight[] };
export type SegmentResult = { segment: Record<string, string>; overall: OverallMetrics; currencies: Record<string, CurrencyMetrics> };
export type SegmentsResponse = { analysis_id: string; dimensions: string[]; segments: SegmentResult[] };
export type MonthlyFlowPeriod = {
  period: string;
  currency: string;
  transaction_count: number;
  attempted_value: string;
  gross_inflow: string;
  refunds: string;
  disputed_value: string;
  processing_fees: string;
  provider_fees: string;
  other_costs: string;
  service_charges: string;
  money_out: string;
  total_reductions: string;
  net_inflow: string;
};
export type ProviderCostPeriod = MonthlyFlowPeriod & { provider: string };
export type CashFlowTotal = Omit<MonthlyFlowPeriod, "period">;
export type GbpCashFlowSummary = {
  reporting_currency: "GBP";
  gross_inflow: string;
  money_out: string;
  service_charges: string;
  total_reductions: string;
  net_inflow: string;
  cash_activity_transaction_count: number;
  included_transaction_count: number;
  excluded_transaction_count: number;
  native_gbp_transaction_count: number;
  provider_converted_transaction_count: number;
  conversion_coverage_rate: string;
  excluded_currencies: string[];
  is_complete: boolean;
};
export type MonthlyCashFlow = {
  definitions: {
    gross_inflow: string;
    money_out: string;
    service_charges: string;
    net_inflow: string;
    currency_policy: string;
    gbp_policy: string;
    provider_fee_note: string;
  };
  gbp_summary: GbpCashFlowSummary;
  totals: CashFlowTotal[];
  periods: MonthlyFlowPeriod[];
  provider_costs: ProviderCostPeriod[];
};
export type DashboardResponse = {
  summary: AnalysisSummary;
  kpis: KpiResponse;
  insights: InsightsResponse;
  monthly_cash_flow: MonthlyCashFlow;
  performance: Record<string, SegmentsResponse>;
};
export type Explanation = { what_happened: string; why_it_matters: string; what_to_investigate: string };
export type InsightDetailResponse = { analysis_id: string; insight: Insight; explanation: Explanation };
export type ProviderConnection = {
  id?: string;
  provider: "STRIPE";
  status: "NOT_CONNECTED" | "PENDING" | "CONNECTED" | "ERROR" | "DISCONNECTED";
  configured: boolean;
  connection_mode?: "OAUTH" | "SANDBOX_KEY" | null;
  provider_account_id?: string | null;
  last_sync_at?: string | null;
  transactions_imported?: number;
  webhook_status?: string;
};
export type ProviderStatusResponse = { providers: ProviderConnection[] };
export type SyncJob = {
  id: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "PARTIAL" | "FAILED";
  records_received: number;
  records_normalised: number;
  analysis_id: string | null;
  errors: string[];
};
export type AsyncJob = {
  id: string;
  type: "PROVIDER_SYNC" | "ANALYSIS" | "WEBHOOK";
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  result: {
    analysis_id?: string;
    sync_job_id?: string;
    transaction_count?: number;
    records_received?: number;
    records_normalised?: number;
    status?: string;
  };
  error_code: string | null;
};
export type JobResponse = { job: AsyncJob };
export type OperationalJob = {
  id: string;
  type: AsyncJob["type"];
  status: AsyncJob["status"];
  attempts: number;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  retryable: boolean;
};
export type StripeDiagnostics = {
  provider: "STRIPE";
  pipeline_status: "NOT_CONNECTED" | "HEALTHY" | "PROCESSING" | "DEGRADED";
  connection_status: ProviderConnection["status"];
  webhook_status: string;
  last_sync_at: string | null;
  transactions_imported: number;
  canonical_transaction_count: number;
  latest_sync: SyncJob | null;
  latest_webhook: {
    event_id: string;
    event_type: string;
    received_at: string;
    processed_at: string | null;
  } | null;
  recent_jobs: OperationalJob[];
  delivery_protection: { automatic_attempts: number; dead_letter_queue: boolean };
};
export type StripeDiagnosticsResponse = { diagnostics: StripeDiagnostics };

export class PayLensApiError extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  // Read text first because gateways and load balancers can return an HTML error page
  // while the application normally returns JSON. Calling response.json() directly in
  // that situation exposes a confusing "Unexpected token '<'" browser error.
  const rawBody = await response.text();
  if (response.status === 401 && typeof window !== "undefined") {
    clearSession();
    throw new PayLensApiError("SESSION_EXPIRED", "Your session expired. Sign in again to continue.");
  }
  let body: unknown = null;
  try {
    body = rawBody ? JSON.parse(rawBody) : null;
  } catch {
    const contentType = response.headers.get("content-type") ?? "";
    const transient = response.status >= 500 || response.status === 0 || contentType.includes("text/html");
    throw new PayLensApiError(
      transient ? "UPSTREAM_UNAVAILABLE" : "INVALID_API_RESPONSE",
      transient
        ? "PayLens is temporarily unavailable. Please refresh and try again."
        : "PayLens received an invalid server response. Please sign in again or try later.",
    );
  }

  // Convert the API's stable error envelope into one exception shape for all UI callers.
  if (!response.ok) {
    const errorBody = body as { error?: { code?: string; message?: string } } | null;
    throw new PayLensApiError(errorBody?.error?.code ?? "API_ERROR", errorBody?.error?.message ?? "PayLens request failed.");
  }
  return body as T;
}

async function fetchReadOnly<T>(url: string): Promise<T> {
  // A GET is safe to repeat. Retry once when CloudFront or the load balancer returns
  // a temporary 5xx/HTML response; write operations are deliberately never retried.
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      return await parseResponse<T>(await fetch(url, requestOptions(authHeaders())));
    } catch (error) {
      if (!(error instanceof PayLensApiError) || error.code !== "UPSTREAM_UNAVAILABLE" || attempt === 1) throw error;
    }
  }
  throw new PayLensApiError("UPSTREAM_UNAVAILABLE", "PayLens is temporarily unavailable. Please refresh and try again.");
}

export async function uploadAnalysis(file: File): Promise<AnalysisSummary | JobResponse> {
  const form = new FormData();
  form.append("file", file);
  return parseResponse<AnalysisSummary>(await fetch(`${API_URL}/analysis/upload`, { method: "POST", headers: authHeaders(), body: form }));
}

export async function fetchJob(jobId: string): Promise<JobResponse> {
  return fetchReadOnly(`${API_URL}/jobs/${jobId}`);
}

export async function waitForJob(jobId: string, intervalMs = 1000): Promise<AsyncJob> {
  // Poll until the worker reaches a terminal state. The default delay avoids a tight request loop.
  for (;;) {
    const { job } = await fetchJob(jobId);
    if (job.status === "COMPLETED") return job;
    if (job.status === "FAILED") throw new PayLensApiError(job.error_code ?? "JOB_FAILED", "PayLens could not complete the queued job.");
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
  }
}

export async function fetchAnalysis(analysisId: string): Promise<AnalysisSummary> {
  return fetchReadOnly(`${API_URL}/analysis/${analysisId}`);
}

export async function fetchDashboard(analysisId: string): Promise<DashboardResponse> {
  // One server read replaces seven concurrent full-analysis database reads.
  return fetchReadOnly(`${API_URL}/analysis/${analysisId}/dashboard`);
}

export async function fetchKpis(analysisId: string): Promise<KpiResponse> {
  return fetchReadOnly(`${API_URL}/analysis/${analysisId}/kpis`);
}

export async function fetchSegments(analysisId: string, dimensions: string): Promise<SegmentsResponse> {
  const query = new URLSearchParams({ dimensions });
  return fetchReadOnly(`${API_URL}/analysis/${analysisId}/segments?${query}`);
}

export async function fetchInsights(analysisId: string): Promise<InsightsResponse> {
  return fetchReadOnly(`${API_URL}/analysis/${analysisId}/insights`);
}

export async function fetchInsightDetail(analysisId: string, insightId: string): Promise<InsightDetailResponse> {
  return fetchReadOnly(`${API_URL}/analysis/${analysisId}/insights/${insightId}`);
}

export async function fetchProviders(): Promise<ProviderStatusResponse> {
  return fetchReadOnly(`${API_URL}/providers`);
}

export async function beginStripeConnection(): Promise<{ authorization_url: string }> {
  return parseResponse(await fetch(`${API_URL}/providers/stripe/authorize`, { method: "POST", headers: authHeaders() }));
}

export async function connectStripeSandbox(): Promise<{ connection: ProviderConnection }> {
  return parseResponse(await fetch(`${API_URL}/providers/stripe/connect-sandbox`, { method: "POST", headers: authHeaders() }));
}

export async function syncStripe(): Promise<{ sync_job: SyncJob } | JobResponse> {
  return parseResponse(await fetch(`${API_URL}/providers/stripe/sync`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: "{}",
  }));
}

export async function fetchStripeDiagnostics(): Promise<StripeDiagnosticsResponse> {
  return fetchReadOnly(`${API_URL}/providers/stripe/diagnostics`);
}

export async function retryJob(jobId: string): Promise<JobResponse> {
  return parseResponse(await fetch(`${API_URL}/jobs/${jobId}/retry`, { method: "POST", headers: authHeaders() }));
}

export async function disconnectStripe(): Promise<void> {
  const response = await fetch(`${API_URL}/providers/stripe`, { method: "DELETE", headers: authHeaders() });
  if (!response.ok) await parseResponse(response);
}
