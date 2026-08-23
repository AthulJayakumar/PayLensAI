/** Pure dashboard renderer: all network loading is handled by the route component. */

import { AnalysisSummary, Insight, KpiResponse, SegmentsResponse } from "../lib/api";
import { formatInteger, formatMoney, formatRate } from "../lib/format";
import { InsightsFeed } from "./InsightsFeed";
import { PerformanceTable } from "./PerformanceTable";

type DashboardViewProps = {
  summary: AnalysisSummary;
  kpis: KpiResponse;
  insights: Insight[];
  performance: Record<string, SegmentsResponse>;
  dashboardLoadMs?: number;
};

export function DashboardView({ summary, kpis, insights, performance, dashboardLoadMs }: DashboardViewProps) {
  return (
    <>
      <section className="dashboard-title">
        <div>
          <p className="eyebrow">Analysis complete</p>
          <h1>Payment performance</h1>
          <p>{summary.filename} · {formatInteger(summary.transaction_count)} transactions · {summary.currencies.join(", ")}</p>
        </div>
        <div className="window-card"><small>Current period</small><strong>{new Date(summary.comparison_period.current_start).toLocaleDateString("en-GB")} – {new Date(summary.comparison_period.current_end).toLocaleDateString("en-GB")}</strong>{dashboardLoadMs !== undefined && <span>Dashboard loaded in {dashboardLoadMs.toFixed(0)} ms</span>}</div>
      </section>

      <section className="metric-grid" aria-label="Overall payment metrics">
        <article className="metric-card"><span>Transactions</span><strong>{formatInteger(kpis.overall.transaction_count)}</strong><small>Payment attempts analysed</small></article>
        <article className="metric-card metric-positive"><span>Success rate</span><strong>{formatRate(kpis.overall.success_rate)}</strong><small>{formatInteger(kpis.overall.successful_transaction_count)} successful</small></article>
        <article className="metric-card metric-negative"><span>Failure rate</span><strong>{formatRate(kpis.overall.failure_rate)}</strong><small>{formatInteger(kpis.overall.failed_transaction_count)} failed attempts</small></article>
        <article className="metric-card"><span>Insights</span><strong>{formatInteger(insights.length)}</strong><small>Deterministic findings</small></article>
      </section>

      <section className="currency-section">
        <div className="section-heading"><div><p className="eyebrow">No currency mixing</p><h2>Currency performance</h2></div></div>
        <div className="currency-grid">
          {Object.entries(kpis.currencies).map(([currency, values]) => (
            <article className="currency-card" key={currency}>
              <div className="currency-title"><span>{currency}</span><small>Effective cost {formatRate(values.effective_cost_rate)}</small></div>
              <dl>
                <div><dt>Attempted value</dt><dd>{formatMoney(values.attempted_value, currency)}</dd></div>
                <div><dt>Successful value</dt><dd>{formatMoney(values.successful_value, currency)}</dd></div>
                <div><dt>Failed attempted value</dt><dd>{formatMoney(values.failed_attempted_value, currency)}</dd></div>
                <div><dt>Payment cost</dt><dd>{formatMoney(values.total_cost, currency)}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      </section>

      <InsightsFeed analysisId={summary.analysis_id} insights={insights} />

      <section className="performance-grid" aria-label="Segment performance">
        <PerformanceTable title="Provider performance" segments={performance.provider.segments} />
        <PerformanceTable title="Payment method performance" segments={performance.payment_method.segments} />
        <PerformanceTable title="Card network performance" segments={performance.card_network.segments} />
        <PerformanceTable title="Country performance" segments={performance.issuer_country.segments} />
      </section>
    </>
  );
}
