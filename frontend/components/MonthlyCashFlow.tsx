"use client";

/** Monthly money movement chart with exact values and provider charge evidence. */

import { useMemo, useState } from "react";
import { MonthlyCashFlow as MonthlyCashFlowData } from "../lib/api";
import { formatInteger, formatMoney, humanise } from "../lib/format";

function monthLabel(period: string): string {
  const [year, month] = period.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: "UTC" })
    .format(new Date(Date.UTC(year, month - 1, 1)));
}

export function MonthlyCashFlow({ data }: { data: MonthlyCashFlowData }) {
  const currencies = useMemo(() => [...new Set(data.periods.map((row) => row.currency))].sort(), [data.periods]);
  const [selectedCurrency, setSelectedCurrency] = useState(currencies[0] ?? "GBP");
  const periods = data.periods.filter((row) => row.currency === selectedCurrency);
  const providerCosts = data.provider_costs.filter((row) => row.currency === selectedCurrency);
  // Totals come from Python Decimal arithmetic; the browser only formats them.
  const totals = data.totals.find((row) => row.currency === selectedCurrency);
  const chartMaximum = Math.max(1, ...periods.flatMap((row) => [Number(row.gross_inflow), Number(row.total_reductions)]));
  const gbp = data.gbp_summary;

  if (!periods.length || !totals) return <p className="empty-flow">No monthly payment activity is available.</p>;

  return (
    <section className="cash-flow-panel" aria-labelledby="cash-flow-heading">
      <div className="section-heading cash-flow-heading">
        <div><p className="eyebrow">Monthly movement</p><h2 id="cash-flow-heading">Money in, money out and provider charges</h2></div>
        {currencies.length > 1 && <label className="currency-picker">Currency<select value={selectedCurrency} onChange={(event) => setSelectedCurrency(event.target.value)}>{currencies.map((currency) => <option key={currency}>{currency}</option>)}</select></label>}
      </div>

      <div className="gbp-overview" aria-label="Whole business cash flow in pounds">
        <div className="gbp-overview-heading">
          <div><p className="eyebrow">UK reporting view</p><h3>Whole business cash flow in GBP</h3></div>
          <span className={gbp.is_complete ? "coverage-complete" : "coverage-partial"}>
            {(Number(gbp.conversion_coverage_rate) * 100).toFixed(1)}% conversion coverage
          </span>
        </div>
        <div className="flow-summary">
          <article><span>Money in</span><strong>{formatMoney(gbp.gross_inflow, "GBP")}</strong><small>All supported currencies in pounds</small></article>
          <article><span>Money out</span><strong>{formatMoney(gbp.money_out, "GBP")}</strong><small>Refunds + disputed value</small></article>
          <article><span>Service charges</span><strong>{formatMoney(gbp.service_charges, "GBP")}</strong><small>Provider and processing costs</small></article>
          <article><span>Net after reductions</span><strong>{formatMoney(gbp.net_inflow, "GBP")}</strong><small>Money in − all reductions</small></article>
        </div>
        {!gbp.is_complete && (
          <p className="conversion-warning" role="alert">
            {formatInteger(gbp.excluded_transaction_count)} cash-affecting transaction(s) in {gbp.excluded_currencies.join(", ")} were excluded because no provider GBP conversion was available. Re-sync the provider to refresh settlement data.
          </p>
        )}
        <p className="flow-definition">{data.definitions.gbp_policy}</p>
      </div>

      <div className="flow-summary" aria-label={`${selectedCurrency} cash flow totals`}>
        <article><span>Money in</span><strong>{formatMoney(totals.gross_inflow, selectedCurrency)}</strong><small>Successful gross payments</small></article>
        <article><span>Money out</span><strong>{formatMoney(totals.money_out, selectedCurrency)}</strong><small>Refunds + disputed value</small></article>
        <article><span>Service charges</span><strong>{formatMoney(totals.service_charges, selectedCurrency)}</strong><small>Provider and processing costs</small></article>
        <article><span>Net after reductions</span><strong>{formatMoney(totals.net_inflow, selectedCurrency)}</strong><small>Money in − all reductions</small></article>
      </div>

      <div className="flow-chart" role="img" aria-label={`Monthly money in and total reductions in ${selectedCurrency}`}>
        <div className="flow-legend"><span className="legend-in">Money in</span><span className="legend-out">Total reductions</span></div>
        {periods.map((row) => (
          <div className="flow-chart-row" key={`${row.period}-${row.currency}`}>
            <strong>{monthLabel(row.period)}</strong>
            <div className="flow-bars">
              <div><span className="flow-bar flow-bar-in" style={{ width: `${(Number(row.gross_inflow) / chartMaximum) * 100}%` }} /><small>{formatMoney(row.gross_inflow, row.currency)}</small></div>
              <div><span className="flow-bar flow-bar-out" style={{ width: `${(Number(row.total_reductions) / chartMaximum) * 100}%` }} /><small>{formatMoney(row.total_reductions, row.currency)}</small></div>
            </div>
          </div>
        ))}
      </div>

      <div className="table-wrap flow-table-wrap">
        <table>
          <thead><tr><th>Month</th><th>Money in</th><th>Refunds</th><th>Disputed</th><th>Service charges</th><th>Net</th></tr></thead>
          <tbody>{periods.map((row) => <tr key={`${row.period}-${row.currency}-detail`}><td><strong>{monthLabel(row.period)}</strong><small>{formatInteger(row.transaction_count)} attempts</small></td><td>{formatMoney(row.gross_inflow, row.currency)}</td><td>{formatMoney(row.refunds, row.currency)}</td><td>{formatMoney(row.disputed_value, row.currency)}</td><td>{formatMoney(row.service_charges, row.currency)}</td><td className={Number(row.net_inflow) >= 0 ? "positive" : "negative"}>{formatMoney(row.net_inflow, row.currency)}</td></tr>)}</tbody>
        </table>
      </div>

      <div className="provider-cost-heading"><h3>Charges by payment provider</h3><p>{data.definitions.provider_fee_note}</p></div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Month</th><th>Provider</th><th>Processing fees</th><th>Provider fees</th><th>Other costs</th><th>Total charges</th></tr></thead>
          <tbody>{providerCosts.map((row) => <tr key={`${row.period}-${row.provider}-${row.currency}`}><td>{monthLabel(row.period)}</td><td><strong>{humanise(row.provider)}</strong></td><td>{formatMoney(row.processing_fees, row.currency)}</td><td>{formatMoney(row.provider_fees, row.currency)}</td><td>{formatMoney(row.other_costs, row.currency)}</td><td><strong>{formatMoney(row.service_charges, row.currency)}</strong></td></tr>)}</tbody>
        </table>
      </div>
      <p className="flow-definition">{data.definitions.money_out} {data.definitions.currency_policy}</p>
    </section>
  );
}
