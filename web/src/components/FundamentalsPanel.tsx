import type { FundamentalsResponse } from "../types/api";
import { fmtCompact, fmtNum, fmtPct, fmtPrice } from "../lib/format";

type Props = {
  data?: FundamentalsResponse;
  loading?: boolean;
};

const RATIO_LABELS: Record<string, string> = {
  pe: "P/E",
  pb: "P/B",
  roe: "ROE",
  roa: "ROA",
  gross_margin: "Gross margin",
  net_margin: "Net margin",
  debt_to_assets: "Debt / assets",
  price: "Price",
  market_cap_approx: "Mkt cap (approx)",
};

function formatRatio(key: string, v: number | null | undefined): string {
  if (key === "price") return fmtPrice(v);
  if (key === "market_cap_approx") return fmtCompact(v);
  if (["roe", "roa", "gross_margin", "net_margin", "debt_to_assets"].includes(key)) {
    return fmtPct(v);
  }
  return fmtNum(v);
}

export function FundamentalsPanel({ data, loading }: Props) {
  if (loading) {
    return (
      <div className="panel skeleton-block">
        <h3>Fundamentals</h3>
        <p className="muted">Loading SEC EDGAR facts…</p>
      </div>
    );
  }

  if (!data || data.error) {
    return (
      <div className="panel">
        <h3>Fundamentals</h3>
        <p className="muted">{data?.error ?? "No fundamentals loaded."}</p>
      </div>
    );
  }

  const revenue = data.growth?.Revenue ?? [];

  return (
    <div className="panel fade-in">
      <div className="panel-head">
        <h3>Fundamentals</h3>
        <span className="muted small">SEC EDGAR</span>
      </div>
      <div className="ratio-grid">
        {Object.entries(RATIO_LABELS).map(([key, label]) => (
          <div key={key} className="ratio-cell">
            <span className="metric-label">{label}</span>
            <span className="metric-value mono">
              {formatRatio(key, data.ratios?.[key] ?? null)}
            </span>
          </div>
        ))}
      </div>
      {revenue.length > 0 && (
        <div className="growth-table-wrap">
          <h4>Revenue history</h4>
          <table className="data-table">
            <thead>
              <tr>
                <th>Period end</th>
                <th>Value</th>
                <th>YoY</th>
                <th>Form</th>
              </tr>
            </thead>
            <tbody>
              {[...revenue].reverse().slice(0, 8).map((row) => (
                <tr key={`${row.end_date}-${row.form}`}>
                  <td className="mono">{row.end_date}</td>
                  <td className="mono">{fmtCompact(row.value)}</td>
                  <td className="mono">{fmtPct(row.yoy)}</td>
                  <td>{row.form ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.disclaimer && <p className="disclaimer">{data.disclaimer}</p>}
    </div>
  );
}
