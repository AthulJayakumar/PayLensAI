/** Prioritised findings expand in place; no route change or extra data fetch. */

import { Insight } from "../lib/api";
import { formatMoney, formatRate, humanise, segmentLabel } from "../lib/format";

function firstMoney(insight: Insight): [string, string] | null {
  const maps = [insight.affected_attempted_value, insight.affected_payment_cost, insight.affected_refund_amount, insight.affected_dispute_amount];
  for (const values of maps) {
    const first = Object.entries(values)[0];
    if (first) return first;
  }
  return null;
}

function moneyRows(insight: Insight) {
  const maps = [
    ["Affected attempted value", insight.affected_attempted_value],
    ["Affected payment cost", insight.affected_payment_cost],
    ["Refund amount", insight.affected_refund_amount],
    ["Disputed amount", insight.affected_dispute_amount],
  ] as const;
  return maps.flatMap(([label, values]) => Object.entries(values).map(([currency, value]) => ({ label, currency, value })));
}

export function InsightsFeed({ insights }: { insights: Insight[] }) {
  return (
    <section className="panel insights-panel" aria-labelledby="insights-heading">
      <div className="section-heading">
        <div><p className="eyebrow">Prioritised findings</p><h2 id="insights-heading">PayLens insights</h2></div>
        <span className="count-badge">{insights.length}</span>
      </div>
      <div className="insight-list">
        {insights.map((insight) => {
          const money = firstMoney(insight);
          return (
            <article className="insight-item" key={insight.insight_id}>
              <details>
                <summary className="insight-row">
                  <span className={`severity severity-${insight.severity.toLowerCase()}`}>{insight.severity}</span>
                  <span className="insight-copy">
                    <strong>{segmentLabel(insight.segment)}</strong>
                    <span>{humanise(insight.type)}</span>
                    <small>
                      {insight.baseline !== null ? `${formatRate(insight.baseline)} → ${formatRate(insight.current)}` : formatRate(insight.current)}
                      {money ? ` · ${formatMoney(money[1], money[0])} affected` : ""}
                    </small>
                  </span>
                  <span className="insight-toggle">Details <span aria-hidden="true">⌄</span></span>
                </summary>
                <div className="insight-expanded">
                  <section aria-label="Supporting metrics">
                    <h4>Supporting metrics</h4>
                    <dl className="evidence-list">
                      <div><dt>Baseline</dt><dd>{formatRate(insight.baseline)}</dd></div>
                      <div><dt>Current</dt><dd>{formatRate(insight.current)}</dd></div>
                      <div><dt>Relative change</dt><dd>{formatRate(insight.relative_change)}</dd></div>
                      <div><dt>Transactions in segment</dt><dd>{insight.transaction_count.toLocaleString("en-GB")}</dd></div>
                      <div><dt>Affected transactions</dt><dd>{insight.affected_transaction_count.toLocaleString("en-GB")}</dd></div>
                      <div><dt>Evidence confidence</dt><dd>{formatRate(insight.confidence)}</dd></div>
                      {moneyRows(insight).map((row) => <div key={`${row.label}-${row.currency}`}><dt>{row.label} · {row.currency}</dt><dd>{formatMoney(row.value, row.currency)}</dd></div>)}
                    </dl>
                  </section>
                  {insight.explanation && <section className="insight-explanation" aria-label="Explanation">
                    <div><h4>What happened?</h4><p>{insight.explanation.what_happened}</p></div>
                    <div><h4>Why it matters</h4><p>{insight.explanation.why_it_matters}</p></div>
                    <div><h4>What to investigate</h4><p>{insight.explanation.what_to_investigate}</p></div>
                  </section>}
                </div>
              </details>
            </article>
          );
        })}
      </div>
    </section>
  );
}
