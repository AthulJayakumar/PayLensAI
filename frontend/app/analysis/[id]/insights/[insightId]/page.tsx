"use client";

/** Drill-down route for the evidence and explanation attached to one insight. */

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AppHeader } from "../../../../../components/AppHeader";
import { InsightDetailView } from "../../../../../components/InsightDetailView";
import { fetchInsightDetail, InsightDetailResponse } from "../../../../../lib/api";

export default function InsightDetailPage() {
  const params = useParams<{ id: string; insightId: string }>();
  const [detail, setDetail] = useState<InsightDetailResponse | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    fetchInsightDetail(params.id, params.insightId).then(setDetail).catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Insight could not be loaded."));
  }, [params.id, params.insightId]);
  return (
    <main className="app-shell detail-shell">
      <AppHeader analysisId={params.id} />
      {error && <div className="page-state error-banner" role="alert"><h2>Insight unavailable</h2><p>{error}</p></div>}
      {!error && !detail && <div className="page-state loading-state"><span className="loading-ring" /><h2>Loading insight</h2></div>}
      {detail && <InsightDetailView detail={detail} />}
    </main>
  );
}
