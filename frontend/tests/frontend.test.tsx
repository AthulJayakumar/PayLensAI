import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DashboardView } from "../components/DashboardView";
import { InsightDetailView } from "../components/InsightDetailView";
import { InsightsFeed } from "../components/InsightsFeed";
import { UploadPanel } from "../components/UploadPanel";
import { ProviderConnections } from "../components/ProviderConnections";
import { ProviderDiagnostics } from "../components/ProviderDiagnostics";
import LoginPage from "../app/login/page";
import { PayLensApiError } from "../lib/api";
import type { AnalysisSummary, Insight, InsightDetailResponse, KpiResponse, SegmentsResponse } from "../lib/api";

const summary: AnalysisSummary = {
  analysis_id: "analysis_test",
  status: "COMPLETED",
  filename: "payments.csv",
  file_size: 1000,
  transaction_count: 100,
  insight_count: 1,
  currencies: ["GBP", "USD"],
  comparison_period: { current_start: "2026-06-16T00:00:00Z", current_end: "2026-07-01T00:00:00Z", baseline: "earlier" },
  performance: {},
};

const currency = (attempted: string) => ({
  attempted_value: attempted,
  successful_value: "900.00",
  failed_attempted_value: "100.00",
  average_transaction_value: "10.00",
  refund_amount: "20.00",
  dispute_amount: "5.00",
  processing_fees: "10.00",
  provider_fees: "5.00",
  other_costs: "1.00",
  total_cost: "16.00",
  effective_cost_rate: "0.017778",
});

const kpis: KpiResponse = {
  analysis_id: "analysis_test",
  overall: { transaction_count: 100, successful_transaction_count: 90, failed_transaction_count: 10, success_rate: "0.9", failure_rate: "0.1", refund_rate: "0.02", dispute_rate: "0.005" },
  currencies: { GBP: currency("1000.00"), USD: currency("2000.00") },
};

const insight: Insight = {
  insight_id: "ins_test",
  type: "FAILURE_SPIKE",
  severity: "HIGH",
  segment: { card_network: "MASTERCARD", issuer_country: "US" },
  metric: "failure_rate",
  baseline: "0.04",
  current: "0.12",
  absolute_difference: "0.08",
  relative_change: "2.0",
  affected_attempted_value: { GBP: "500.00" },
  affected_refund_amount: {},
  affected_dispute_amount: {},
  affected_payment_cost: {},
  transaction_count: 300,
  affected_transaction_count: 36,
  confidence: "0.85",
  supporting_metrics: {},
};

const segments: SegmentsResponse = {
  analysis_id: "analysis_test",
  dimensions: ["provider"],
  segments: [{ segment: { provider: "STRIPE" }, overall: kpis.overall, currencies: kpis.currencies }],
};

describe("upload workflow", () => {
  it("shows the selected file, loading state, and completion", async () => {
    let resolveUpload!: (value: AnalysisSummary) => void;
    const uploader = vi.fn(() => new Promise<AnalysisSummary>((resolve) => { resolveUpload = resolve; }));
    const onComplete = vi.fn();
    const user = userEvent.setup();
    render(<UploadPanel uploader={uploader} onComplete={onComplete} />);

    await user.upload(screen.getByLabelText("Payment CSV"), new File(["data"], "payments.csv", { type: "text/csv" }));
    expect(screen.getByText("payments.csv")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Analyse payments" }));
    expect(screen.getByRole("button", { name: /Validating and analysing/ })).toBeDisabled();
    resolveUpload(summary);
    await waitFor(() => expect(onComplete).toHaveBeenCalledWith("analysis_test"));
  });

  it("renders a clear API failure state", async () => {
    const user = userEvent.setup();
    render(<UploadPanel uploader={vi.fn().mockRejectedValue(new Error("The CSV is invalid."))} onComplete={vi.fn()} />);
    await user.upload(screen.getByLabelText("Payment CSV"), new File(["bad"], "bad.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "Analyse payments" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The CSV is invalid.");
  });
});

it("renders the dashboard with currencies kept separate", () => {
  render(<DashboardView summary={summary} kpis={kpis} insights={[insight]} performance={{ provider: segments, payment_method: segments, card_network: segments, issuer_country: segments }} />);
  expect(screen.getByText("Payment performance")).toBeInTheDocument();
  expect(screen.getAllByText("90.00%").length).toBeGreaterThan(0);
  expect(screen.getByText("£1,000.00")).toBeInTheDocument();
  expect(screen.getByText("US$2,000.00")).toBeInTheDocument();
  expect(screen.getAllByText("Provider performance").length).toBeGreaterThan(0);
});

it("renders a severity-ordered insight card with supporting values", () => {
  render(<InsightsFeed analysisId="analysis_test" insights={[insight]} />);
  expect(screen.getByText("HIGH")).toBeInTheDocument();
  expect(screen.getByText("US · Mastercard")).toBeInTheDocument();
  expect(screen.getByText(/4.00% → 12.00%/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /View insight/ })).toHaveAttribute("href", "/analysis/analysis_test/insights/ins_test");
});

it("renders insight detail and deterministic explanation", () => {
  const detail: InsightDetailResponse = {
    analysis_id: "analysis_test",
    insight,
    explanation: {
      what_happened: "US Mastercard failures increased.",
      why_it_matters: "GBP 500 of attempted payment value was affected.",
      what_to_investigate: "Review issuer-decline patterns.",
    },
  };
  render(<InsightDetailView detail={detail} />);
  expect(screen.getByText("Supporting metrics")).toBeInTheDocument();
  expect(screen.getAllByText("US Mastercard failures increased.").length).toBeGreaterThan(0);
  expect(screen.getByText("£500.00")).toBeInTheDocument();
  expect(screen.getByText("Review issuer-decline patterns.")).toBeInTheDocument();
});

it("renders Stripe as unavailable until sandbox configuration exists", async () => {
  render(<ProviderConnections loader={vi.fn().mockResolvedValue({ providers: [{ provider: "STRIPE", status: "NOT_CONNECTED", configured: false }] })} />);
  expect(await screen.findByText("Not connected")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Connect Stripe" })).toBeDisabled();
  expect(screen.getByText(/Configure private Stripe sandbox credentials/)).toBeInTheDocument();
});

it("connects a server-configured private Stripe sandbox without exposing its key", async () => {
  const disconnected = {
    provider: "STRIPE" as const,
    status: "NOT_CONNECTED" as const,
    configured: true,
    connection_mode: "SANDBOX_KEY" as const,
  };
  const connected = {
    ...disconnected,
    status: "CONNECTED" as const,
    provider_account_id: "acct_sandbox_test",
    webhook_status: "NOT_CONFIGURED",
  };
  const sandboxConnector = vi.fn().mockResolvedValue({ connection: connected });
  const user = userEvent.setup();

  render(
    <ProviderConnections
      loader={vi.fn().mockResolvedValue({ providers: [disconnected] })}
      sandboxConnector={sandboxConnector}
    />
  );

  await user.click(await screen.findByRole("button", { name: "Connect Stripe sandbox" }));
  expect(sandboxConnector).toHaveBeenCalledOnce();
  expect(await screen.findByText("Connected")).toBeInTheDocument();
  expect(screen.getByText("acct_sandbox_test")).toBeInTheDocument();
});

it("syncs a connected Stripe account and links to its analysis", async () => {
  const connection = {
    provider: "STRIPE" as const,
    status: "CONNECTED" as const,
    configured: true,
    provider_account_id: "acct_test",
    transactions_imported: 12,
    webhook_status: "CONFIGURED",
  };
  const loader = vi.fn().mockResolvedValue({ providers: [connection] });
  const synchronizer = vi.fn().mockResolvedValue({
    sync_job: { id: "sync_1", status: "COMPLETED", records_received: 12, records_normalised: 12, analysis_id: "analysis_stripe", errors: [] },
  });
  const user = userEvent.setup();
  render(<ProviderConnections loader={loader} synchronizer={synchronizer} />);
  expect(await screen.findByText("Connected")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Sync now" }));
  expect(await screen.findByText("12 transactions normalised")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /View analysis/ })).toHaveAttribute("href", "/analysis/analysis_stripe");
});

it("shows processed counts returned by an asynchronous Stripe sync job", async () => {
  const connection = {
    provider: "STRIPE" as const,
    status: "CONNECTED" as const,
    configured: true,
    provider_account_id: "acct_test",
    transactions_imported: 4743,
    webhook_status: "CONFIGURED",
  };
  const synchronizer = vi.fn().mockResolvedValue({
    job: { id: "job_1", type: "PROVIDER_SYNC", status: "QUEUED", result: {}, error_code: null },
  });
  const jobWaiter = vi.fn().mockResolvedValue({
    id: "job_1", type: "PROVIDER_SYNC", status: "COMPLETED", error_code: null,
    result: {
      sync_job_id: "sync_1", status: "COMPLETED", analysis_id: "analysis_stripe",
      records_received: 4743, records_normalised: 4743,
    },
  });
  const user = userEvent.setup();

  render(
    <ProviderConnections
      loader={vi.fn().mockResolvedValue({ providers: [connection] })}
      synchronizer={synchronizer}
      jobWaiter={jobWaiter}
    />
  );

  await user.click(await screen.findByRole("button", { name: "Sync now" }));
  expect(await screen.findByText("4,743 transactions normalised")).toBeInTheDocument();
  expect(jobWaiter).toHaveBeenCalledWith("job_1");
});

it("shows Stripe pipeline evidence and retries a failed background job", async () => {
  const failedJob = {
    id: "job_failed", type: "WEBHOOK" as const, status: "FAILED" as const, attempts: 4,
    error_code: "ProviderTimeout", created_at: "2026-09-02T10:00:00Z",
    updated_at: "2026-09-02T10:05:00Z", retryable: true,
  };
  const diagnostics = {
    provider: "STRIPE" as const, pipeline_status: "DEGRADED" as const,
    connection_status: "CONNECTED" as const, webhook_status: "CONFIGURED",
    last_sync_at: "2026-09-02T09:00:00Z", transactions_imported: 4743,
    canonical_transaction_count: 4744, latest_sync: null,
    latest_webhook: {
      event_id: "evt_end_to_end", event_type: "payment_intent.succeeded",
      received_at: "2026-09-02T10:00:00Z", processed_at: "2026-09-02T10:00:01Z",
    },
    recent_jobs: [failedJob], delivery_protection: { automatic_attempts: 4, dead_letter_queue: true },
  };
  const loader = vi.fn().mockResolvedValue({ diagnostics });
  const retry = vi.fn().mockResolvedValue({ job: { id: "job_retry", status: "QUEUED" } });
  const user = userEvent.setup();

  render(<ProviderDiagnostics loader={loader} retry={retry} />);

  expect(await screen.findByText("4,744")).toBeInTheDocument();
  expect(screen.getByText("payment_intent.succeeded")).toBeInTheDocument();
  expect(screen.getByText("evt_end_to_end")).toBeInTheDocument();
  expect(screen.getByText("Enabled")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(retry).toHaveBeenCalledWith("job_failed");
  await waitFor(() => expect(loader).toHaveBeenCalledTimes(2));
});

it("replaces the provider loading state with a session-expired action", async () => {
  render(<ProviderConnections loader={vi.fn().mockRejectedValue(
    new PayLensApiError("SESSION_EXPIRED", "Your session expired. Sign in again to continue.")
  )}/>);

  expect(await screen.findByText("Session expired")).toBeInTheDocument();
  expect(screen.queryByText("Loading provider status…")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute("href", "/login?reason=session-expired");
});

it("completes the Cognito forgot-password flow without exposing the new password", async () => {
  const requests: Array<{ target?: string; body?: string }> = [];
  const fetchMock = vi.fn().mockImplementation(async (_url: string, options?: RequestInit) => {
    requests.push({
      target: (options?.headers as Record<string, string> | undefined)?.["X-Amz-Target"],
      body: options?.body as string | undefined,
    });
    if (!options) return { ok: true, json: async () => ({ region: "eu-north-1", client_id: "client_test" }) };
    return { ok: true, json: async () => ({}) };
  });
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  render(<LoginPage/>);

  await user.click(screen.getByRole("button", { name: "Forgot password?" }));
  await user.type(screen.getByLabelText("Email"), "merchant@example.com");
  await user.click(screen.getByRole("button", { name: "Send verification code" }));
  expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeInTheDocument();

  await user.type(screen.getByLabelText("Verification code"), "123456");
  await user.type(screen.getByLabelText("New password"), "Safe-Test-Password-42!");
  await user.type(screen.getByLabelText("Confirm new password"), "Safe-Test-Password-42!");
  await user.click(screen.getByRole("button", { name: "Reset password" }));

  expect(await screen.findByText("Password reset complete. Sign in with your new password.")).toBeInTheDocument();
  expect(requests.some((request) => request.target?.endsWith("ForgotPassword"))).toBe(true);
  expect(requests.some((request) => request.target?.endsWith("ConfirmForgotPassword"))).toBe(true);
  vi.unstubAllGlobals();
});
