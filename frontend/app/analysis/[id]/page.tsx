"use client";

/** Analysis dashboard route that assembles summary, KPI, insight, and segment resources. */

import { useParams } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AppHeader } from "../../../components/AppHeader";
import { DashboardView } from "../../../components/DashboardView";
import { AnalysisSummary, fetchAnalysis, fetchInsights, fetchKpis, fetchSegments, Insight, KpiResponse, SegmentsResponse } from "../../../lib/api";

type DashboardData = { summary: AnalysisSummary; kpis: KpiResponse; insights: Insight[]; performance: Record<string, SegmentsResponse>; loadMs: number };

export default function AnalysisPage() {
  const params = useParams<{ id: string }>();
  const analysisId = params.id;
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    // Independent read endpoints are loaded together to minimize dashboard wait time.
    const started = performance.now();
    Promise.all([
      fetchAnalysis(analysisId), fetchKpis(analysisId), fetchInsights(analysisId),
      fetchSegments(analysisId, "provider"), fetchSegments(analysisId, "payment_method"),
      fetchSegments(analysisId, "card_network"), fetchSegments(analysisId, "issuer_country"),
    ]).then(([summary, kpis, insightResponse, provider, paymentMethod, cardNetwork, issuerCountry]) => {
      setData({ summary, kpis, insights: insightResponse.insights, performance: { provider, payment_method: paymentMethod, card_network: cardNetwork, issuer_country: issuerCountry }, loadMs: performance.now() - started });
    }).catch((requestError) => setError(requestError instanceof Error ? requestError.message : "The analysis could not be loaded."));
  }, [analysisId]);

  return (
    <main className="app-shell">
      <AppHeader analysisId={analysisId} />
      {error && <div className="page-state error-banner" role="alert"><h2>Analysis unavailable</h2><p>{error}</p><Link className="secondary-button" href="/">Return to upload</Link></div>}
      {!error && !data && <div className="page-state loading-state"><span className="loading-ring" /><h2>Loading payment intelligence</h2><p>Retrieving KPIs, segment performance, and insights…</p></div>}
      {data && <DashboardView {...data} dashboardLoadMs={data.loadMs} />}
    </main>
  );
}
