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

export function InsightsFeed({ analysisId, insights }: { analysisId: string; insights: Insight[] }) {
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
            <article className="insight-row" key={insight.insight_id}>
              <span className={`severity severity-${insight.severity.toLowerCase()}`}>{insight.severity}</span>
              <div className="insight-copy">
                <h3>{segmentLabel(insight.segment)}</h3>
                <p>{humanise(insight.type)}</p>
                <small>
                  {insight.baseline !== null ? `${formatRate(insight.baseline)} → ${formatRate(insight.current)}` : formatRate(insight.current)}
                  {money ? ` · ${formatMoney(money[1], money[0])} affected` : ""}
                </small>
              </div>
              <a className="text-link" href={`/analysis/${analysisId}/insights/${insight.insight_id}`}>View insight <span>→</span></a>
            </article>
          );
        })}
      </div>
    </section>
  );
}

