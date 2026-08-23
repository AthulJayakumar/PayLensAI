/** Evidence-focused presentation for one deterministic insight. */

import { InsightDetailResponse } from "../lib/api";
import { formatMoney, formatRate, humanise, segmentLabel } from "../lib/format";

function valueRows(detail: InsightDetailResponse) {
  // Flatten currency maps so each monetary value has an explicit currency-labelled row.
  const insight = detail.insight;
  const maps = [
    ["Affected attempted value", insight.affected_attempted_value],
    ["Affected payment cost", insight.affected_payment_cost],
    ["Refund amount", insight.affected_refund_amount],
    ["Disputed amount", insight.affected_dispute_amount],
  ] as const;
  return maps.flatMap(([label, values]) => Object.entries(values).map(([currency, value]) => ({ label, currency, value })));
}

export function InsightDetailView({ detail }: { detail: InsightDetailResponse }) {
  const { insight, explanation } = detail;
  return (
    <>
      <nav className="breadcrumb"><a href={`/analysis/${detail.analysis_id}`}>← Back to analysis</a></nav>
      <section className="detail-hero">
        <span className={`severity severity-${insight.severity.toLowerCase()}`}>{insight.severity}</span>
        <p className="eyebrow">{humanise(insight.type)}</p>
        <h1>{segmentLabel(insight.segment)}</h1>
        <p>{explanation.what_happened}</p>
      </section>
      <div className="detail-grid">
        <section className="panel evidence-panel">
          <div className="section-heading"><h2>Supporting metrics</h2><span>{insight.transaction_count.toLocaleString("en-GB")} transactions</span></div>
          <div className="comparison-block">
            <div><span>Baseline</span><strong>{formatRate(insight.baseline)}</strong></div>
            <div className="comparison-arrow">→</div>
            <div><span>Current</span><strong>{formatRate(insight.current)}</strong></div>
          </div>
          <dl className="evidence-list">
            <div><dt>Relative change</dt><dd>{formatRate(insight.relative_change)}</dd></div>
            <div><dt>Affected transactions</dt><dd>{insight.affected_transaction_count.toLocaleString("en-GB")}</dd></div>
            <div><dt>Evidence confidence</dt><dd>{formatRate(insight.confidence)}</dd></div>
            {valueRows(detail).map((row) => <div key={`${row.label}-${row.currency}`}><dt>{row.label} · {row.currency}</dt><dd>{formatMoney(row.value, row.currency)}</dd></div>)}
          </dl>
        </section>
        <aside className="explanation-stack">
          <section className="explanation-card"><span>01</span><h2>What happened?</h2><p>{explanation.what_happened}</p></section>
          <section className="explanation-card"><span>02</span><h2>Why it matters</h2><p>{explanation.why_it_matters}</p></section>
          <section className="explanation-card accent"><span>03</span><h2>What to investigate</h2><p>{explanation.what_to_investigate}</p></section>
        </aside>
      </div>
    </>
  );
}
