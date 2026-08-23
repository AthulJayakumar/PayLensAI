/** Reusable comparison table for any API-provided segment dimension. */

import { SegmentResult } from "../lib/api";
import { formatInteger, formatRate, segmentLabel } from "../lib/format";

export function PerformanceTable({ title, segments }: { title: string; segments: SegmentResult[] }) {
  return (
    <section className="panel performance-panel">
      <div className="section-heading"><h3>{title}</h3><span>{segments.length} segments</span></div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Segment</th><th>Attempts</th><th>Success</th><th>Failure</th></tr></thead>
          <tbody>
            {segments.map((item) => (
              <tr key={JSON.stringify(item.segment)}>
                <td><strong>{segmentLabel(item.segment)}</strong></td>
                <td>{formatInteger(item.overall.transaction_count)}</td>
                <td className="positive">{formatRate(item.overall.success_rate)}</td>
                <td className="negative">{formatRate(item.overall.failure_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
