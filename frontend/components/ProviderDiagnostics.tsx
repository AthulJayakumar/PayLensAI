"use client";

/** Safe operational visibility for the authenticated merchant's Stripe pipeline. */

import { useEffect, useState } from "react";
import {
  fetchStripeDiagnostics,
  retryJob,
  StripeDiagnostics,
  StripeDiagnosticsResponse,
} from "../lib/api";

type Props = {
  loader?: () => Promise<StripeDiagnosticsResponse>;
  retry?: (jobId: string) => Promise<unknown>;
};

function timestamp(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "Not recorded yet";
}

export function ProviderDiagnostics({ loader = fetchStripeDiagnostics, retry = retryJob }: Props) {
  const [diagnostics, setDiagnostics] = useState<StripeDiagnostics | null>(null);
  const [error, setError] = useState("");
  const [busyJob, setBusyJob] = useState<string | null>(null);

  async function refresh() {
    setError("");
    try {
      setDiagnostics((await loader()).diagnostics);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Operational diagnostics are unavailable.");
    }
  }

  useEffect(() => {
    let active = true;
    loader()
      .then((result) => { if (active) setDiagnostics(result.diagnostics); })
      .catch((cause) => {
        if (active) setError(cause instanceof Error ? cause.message : "Operational diagnostics are unavailable.");
      });
    return () => { active = false; };
  }, [loader]);

  async function retryFailedJob(jobId: string) {
    setBusyJob(jobId); setError("");
    try {
      await retry(jobId);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The job could not be retried.");
    } finally {
      setBusyJob(null);
    }
  }

  if (!diagnostics && !error) return <section className="diagnostics-panel">Loading pipeline diagnostics…</section>;
  if (!diagnostics) return <section className="diagnostics-panel provider-error" role="alert">
    <strong>{error.includes("session expired") ? "Session expired" : "Diagnostics unavailable"}</strong>
    <p>{error}</p>
    {error.toLowerCase().includes("session expired")
      ? <a className="primary-button compact" href="/login?reason=session-expired">Sign in again</a>
      : <button className="primary-button compact" onClick={refresh}>Retry</button>}
  </section>;

  const webhookState = diagnostics.latest_webhook
    ? diagnostics.latest_webhook.processed_at ? "Processed" : "Processing"
    : "Awaiting first event";
  return <section className="diagnostics-panel" aria-label="Stripe pipeline diagnostics">
    <div className="diagnostics-heading">
      <div><p className="eyebrow">Operational diagnostics</p><h2>Stripe pipeline</h2></div>
      <div className="diagnostics-actions">
        <span className={`pipeline-pill ${diagnostics.pipeline_status.toLowerCase()}`}>{diagnostics.pipeline_status.replace("_", " ")}</span>
        <button className="secondary-button compact" onClick={refresh}>Refresh</button>
      </div>
    </div>
    <dl className="diagnostics-grid">
      <div><dt>Canonical transactions</dt><dd>{diagnostics.canonical_transaction_count.toLocaleString("en-GB")}</dd></div>
      <div><dt>Last successful sync</dt><dd>{timestamp(diagnostics.last_sync_at)}</dd></div>
      <div><dt>Latest webhook</dt><dd>{webhookState}</dd></div>
      <div><dt>Webhook event</dt><dd>{diagnostics.latest_webhook?.event_type ?? "Not received"}</dd></div>
    </dl>
    {diagnostics.latest_webhook && <p className="diagnostics-reference">
      Event <code>{diagnostics.latest_webhook.event_id}</code> received {timestamp(diagnostics.latest_webhook.received_at)}
      {diagnostics.latest_webhook.processed_at && <> and processed {timestamp(diagnostics.latest_webhook.processed_at)}</>}.
    </p>}
    <div className="delivery-note">
      Automatic delivery attempts: <strong>{diagnostics.delivery_protection.automatic_attempts}</strong>
      <span>Dead-letter queue: <strong>{diagnostics.delivery_protection.dead_letter_queue ? "Enabled" : "Disabled"}</strong></span>
    </div>
    <h3>Recent background jobs</h3>
    {diagnostics.recent_jobs.length === 0 ? <p className="empty-jobs">No background jobs recorded yet.</p> :
      <div className="diagnostics-table-wrap"><table><thead><tr><th>Job</th><th>Type</th><th>Status</th><th>Attempts</th><th>Updated</th><th></th></tr></thead><tbody>
        {diagnostics.recent_jobs.map((job) => <tr key={job.id}>
          <td><code>{job.id}</code></td><td>{job.type.replaceAll("_", " ")}</td><td><span className={`job-status ${job.status.toLowerCase()}`}>{job.status}</span></td>
          <td>{job.attempts}</td><td>{timestamp(job.updated_at)}</td><td>{job.retryable && <button className="text-button" disabled={busyJob === job.id} onClick={() => retryFailedJob(job.id)}>{busyJob === job.id ? "Retrying…" : "Retry"}</button>}</td>
        </tr>)}
      </tbody></table></div>}
    {error && <div className="error-banner" role="alert">{error}</div>}
  </section>;
}
