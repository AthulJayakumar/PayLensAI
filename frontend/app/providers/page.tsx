/** Provider-management route; connector behavior lives in the testable client component. */

import { AppHeader } from "../../components/AppHeader";
import { ProviderConnections } from "../../components/ProviderConnections";

export default function ProvidersPage() {
  return (
    <main className="app-shell provider-page">
      <AppHeader />
      <section className="provider-hero">
        <p className="eyebrow">Payment providers</p>
        <h1>Bring Stripe data into PayLens.</h1>
        <p>Connect a Stripe sandbox or test account, import its payment history, and run the same deterministic analytics used for CSV data.</p>
      </section>
      <ProviderConnections />
      <aside className="provider-security-note">
        <strong>Read-oriented intelligence foundation</strong>
        <span>Provider credentials are encrypted at rest. Webhooks are signature verified and duplicate events are idempotent.</span>
      </aside>
    </main>
  );
}
