export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEV_API_KEY = process.env.NEXT_PUBLIC_PAYLENS_DEV_API_KEY ?? "";

function authHeaders(): HeadersInit {
  return DEV_API_KEY ? { "X-PayLens-Dev-Key": DEV_API_KEY } : {};
}

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
};

export type InsightsResponse = { analysis_id: string; count: number; insights: Insight[] };
export type SegmentResult = { segment: Record<string, string>; overall: OverallMetrics; currencies: Record<string, CurrencyMetrics> };
export type SegmentsResponse = { analysis_id: string; dimensions: string[]; segments: SegmentResult[] };
export type Explanation = { what_happened: string; why_it_matters: string; what_to_investigate: string };
export type InsightDetailResponse = { analysis_id: string; insight: Insight; explanation: Explanation };
export type ProviderConnection = {
  id?: string;
  provider: "STRIPE";
  status: "NOT_CONNECTED" | "PENDING" | "CONNECTED" | "ERROR" | "DISCONNECTED";
  configured: boolean;
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

export class PayLensApiError extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  const body = await response.json();
  if (!response.ok) {
    throw new PayLensApiError(body?.error?.code ?? "API_ERROR", body?.error?.message ?? "PayLens request failed.");
  }
  return body as T;
}

export async function uploadAnalysis(file: File): Promise<AnalysisSummary> {
  const form = new FormData();
  form.append("file", file);
  return parseResponse<AnalysisSummary>(await fetch(`${API_URL}/analysis/upload`, { method: "POST", headers: authHeaders(), body: form }));
}

export async function fetchAnalysis(analysisId: string): Promise<AnalysisSummary> {
  return parseResponse(await fetch(`${API_URL}/analysis/${analysisId}`, { headers: authHeaders() }));
}

export async function fetchKpis(analysisId: string): Promise<KpiResponse> {
  return parseResponse(await fetch(`${API_URL}/analysis/${analysisId}/kpis`, { headers: authHeaders() }));
}

export async function fetchSegments(analysisId: string, dimensions: string): Promise<SegmentsResponse> {
  const query = new URLSearchParams({ dimensions });
  return parseResponse(await fetch(`${API_URL}/analysis/${analysisId}/segments?${query}`, { headers: authHeaders() }));
}

export async function fetchInsights(analysisId: string): Promise<InsightsResponse> {
  return parseResponse(await fetch(`${API_URL}/analysis/${analysisId}/insights`, { headers: authHeaders() }));
}

export async function fetchInsightDetail(analysisId: string, insightId: string): Promise<InsightDetailResponse> {
  return parseResponse(await fetch(`${API_URL}/analysis/${analysisId}/insights/${insightId}`, { headers: authHeaders() }));
}

export async function fetchProviders(): Promise<ProviderStatusResponse> {
  return parseResponse(await fetch(`${API_URL}/providers`, { headers: authHeaders() }));
}

export async function beginStripeConnection(): Promise<{ authorization_url: string }> {
  return parseResponse(await fetch(`${API_URL}/providers/stripe/authorize`, { method: "POST", headers: authHeaders() }));
}

export async function syncStripe(): Promise<{ sync_job: SyncJob }> {
  return parseResponse(await fetch(`${API_URL}/providers/stripe/sync`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: "{}",
  }));
}

export async function disconnectStripe(): Promise<void> {
  const response = await fetch(`${API_URL}/providers/stripe`, { method: "DELETE", headers: authHeaders() });
  if (!response.ok) await parseResponse(response);
}
