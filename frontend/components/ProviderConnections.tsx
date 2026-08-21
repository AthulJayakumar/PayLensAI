"use client";

import { useEffect, useState } from "react";
import {
  beginStripeConnection,
  disconnectStripe,
  fetchProviders,
  ProviderConnection,
  ProviderStatusResponse,
  syncStripe,
  SyncJob,
} from "../lib/api";

type Props = {
  loader?: () => Promise<ProviderStatusResponse>;
  connector?: () => Promise<{ authorization_url: string }>;
  synchronizer?: () => Promise<{ sync_job: SyncJob }>;
  disconnector?: () => Promise<void>;
};

export function ProviderConnections({
  loader = fetchProviders,
  connector = beginStripeConnection,
  synchronizer = syncStripe,
  disconnector = disconnectStripe,
}: Props) {
  const [stripe, setStripe] = useState<ProviderConnection | null>(null);
  const [syncJob, setSyncJob] = useState<SyncJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const result = await loader();
      setStripe(result.providers.find((item) => item.provider === "STRIPE") ?? null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Provider status is unavailable.");
    }
  }

  useEffect(() => {
    let active = true;
    loader()
      .then((result) => {
        if (active) setStripe(result.providers.find((item) => item.provider === "STRIPE") ?? null);
      })
      .catch((cause) => {
        if (active) setError(cause instanceof Error ? cause.message : "Provider status is unavailable.");
      });
    return () => { active = false; };
  }, [loader]);

  async function connect() {
    setBusy(true); setError("");
    try {
      const result = await connector();
      window.location.assign(result.authorization_url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Stripe connection could not start.");
      setBusy(false);
    }
  }

  async function sync() {
    setBusy(true); setError("");
    try {
      const result = await synchronizer();
      setSyncJob(result.sync_job);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Stripe synchronization failed.");
    } finally { setBusy(false); }
  }

  async function disconnect() {
    setBusy(true); setError("");
    try {
      await disconnector();
      setSyncJob(null);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Stripe could not be disconnected.");
    } finally { setBusy(false); }
  }

  if (!stripe) return <div className="provider-loading">Loading provider status…</div>;
  const connected = stripe.status === "CONNECTED";
  return (
    <section className="provider-card" aria-label="Stripe connection">
      <div className="provider-brand"><span className="stripe-mark">S</span><div><h2>Stripe</h2><p>PaymentIntents, fees, refunds and disputes</p></div></div>
      <span className={`connection-pill ${connected ? "connected" : ""}`}>{connected ? "Connected" : "Not connected"}</span>
      {connected ? (
        <div className="provider-details">
          <dl>
            <div><dt>Account</dt><dd>{stripe.provider_account_id ?? "Available after authorization"}</dd></div>
            <div><dt>Last sync</dt><dd>{stripe.last_sync_at ? new Date(stripe.last_sync_at).toLocaleString() : "Not synced yet"}</dd></div>
            <div><dt>Transactions imported</dt><dd>{stripe.transactions_imported ?? 0}</dd></div>
            <div><dt>Webhook</dt><dd>{stripe.webhook_status ?? "Not configured"}</dd></div>
          </dl>
          {syncJob && <div className={`sync-result ${syncJob.status.toLowerCase()}`} role="status">
            <strong>Sync {syncJob.status.toLowerCase()}</strong>
            <span>{syncJob.records_normalised} transactions normalised</span>
            {syncJob.analysis_id && <a href={`/analysis/${syncJob.analysis_id}`}>View analysis →</a>}
          </div>}
          <div className="provider-actions">
            <button className="primary-button compact" onClick={sync} disabled={busy}>Sync now</button>
            <button className="secondary-button danger" onClick={disconnect} disabled={busy}>Disconnect</button>
          </div>
        </div>
      ) : (
        <div className="provider-connect-copy">
          <p>Authorize PayLens through Stripe’s hosted install flow. PayLens never receives your Stripe password.</p>
          <button className="primary-button compact" onClick={connect} disabled={busy || !stripe.configured}>
            {busy ? "Opening Stripe…" : "Connect Stripe"}
          </button>
          {!stripe.configured && <small>Configure Stripe App sandbox variables in the backend to enable connection.</small>}
        </div>
      )}
      {error && <div className="error-banner" role="alert">{error}</div>}
    </section>
  );
}
