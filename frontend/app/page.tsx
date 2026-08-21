"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { UploadPanel } from "../components/UploadPanel";

export default function Home() {
  const router = useRouter();
  return (
    <main className="landing-shell">
      <header className="site-header">
        <Link className="brand" href="/" aria-label="PayLens home">
          <span className="brand-mark">P</span>
          <span>PAYLENS</span>
        </Link>
        <nav className="landing-nav">
          <Link className="secondary-button" href="/providers">Payment providers</Link>
          <span className="local-badge">Local prototype</span>
        </nav>
      </header>

      <section className="hero-grid">
        <div className="hero-copy">
          <p className="eyebrow">Payment intelligence, without changing checkout</p>
          <h1>See what is happening across every payment attempt.</h1>
          <p className="hero-lede">
            Upload a canonical payment CSV. PayLens validates the data, calculates
            currency-safe performance metrics, and surfaces the issues worth investigating.
          </p>
          <div className="trust-row" aria-label="Product principles">
            <span>Deterministic analytics</span>
            <span>Separate currencies</span>
            <span>No payment processing</span>
          </div>
        </div>
        <UploadPanel onComplete={(analysisId) => router.push(`/analysis/${analysisId}`)} />
      </section>

      <section className="process-strip" aria-label="How PayLens works">
        <div><b>01</b><span>Validate</span><small>Canonical transaction checks</small></div>
        <div><b>02</b><span>Analyse</span><small>Exact KPIs and segmentation</small></div>
        <div><b>03</b><span>Explain</span><small>Structured, actionable findings</small></div>
      </section>
    </main>
  );
}
