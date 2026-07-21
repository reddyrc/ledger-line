import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import type { FundamentalsResponse } from "../types/api";
import { fmtCompact, fmtNum, fmtPct, fmtPrice } from "../lib/format";
import { tipFor } from "../lib/fundamentalsGlossary";

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
  current_ratio: "Current ratio",
  price: "Price",
  market_cap_approx: "Mkt cap (approx)",
};

const SECTION_LABELS: Record<string, string> = {
  assets: "Assets",
  liabilities: "Liabilities",
  equity: "Equity",
};

function formatRatio(key: string, v: number | null | undefined): string {
  if (key === "price") return fmtPrice(v);
  if (key === "market_cap_approx") return fmtCompact(v);
  if (
    [
      "roe",
      "roa",
      "gross_margin",
      "net_margin",
      "debt_to_assets",
    ].includes(key)
  ) {
    return fmtPct(v);
  }
  return fmtNum(v);
}

/** Portal-based tooltip so bubbles aren't clipped by scrollable tables. */
function TipLabel({ tipKey, children }: { tipKey: string; children: string }) {
  const tip = tipFor(tipKey);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);

  if (!tip) {
    return <span className="metric-label">{children}</span>;
  }

  function show(el: HTMLElement) {
    const r = el.getBoundingClientRect();
    // Clamp horizontally so the ~280px bubble stays inside the viewport
    const half = 150;
    const x = Math.min(
      Math.max(r.left + r.width / 2, half),
      window.innerWidth - half,
    );
    setPos({ x, y: r.top });
  }

  return (
    <span
      className="has-tip metric-label"
      tabIndex={0}
      onMouseEnter={(e) => show(e.currentTarget)}
      onMouseLeave={() => setPos(null)}
      onFocus={(e) => show(e.currentTarget)}
      onBlur={() => setPos(null)}
    >
      {children}
      {pos &&
        createPortal(
          <span
            className="floating-tip"
            role="tooltip"
            style={{ left: pos.x, top: pos.y }}
          >
            {tip}
          </span>,
          document.body,
        )}
    </span>
  );
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
  const bs = data.balance_sheet;
  const periods = bs?.history?.periods ?? [];
  const historyRows = bs?.history?.rows ?? [];
  const latestLines = bs?.lines ?? [];

  return (
    <div className="panel fade-in fundamentals-panel">
      <div className="panel-head">
        <h3>Fundamentals</h3>
        <span className="muted small">SEC EDGAR</span>
      </div>
      <div className="ratio-grid">
        {Object.entries(RATIO_LABELS).map(([key, label]) => (
          <div key={key} className="ratio-cell">
            <TipLabel tipKey={key}>{label}</TipLabel>
            <span className="metric-value mono">
              {formatRatio(key, data.ratios?.[key] ?? null)}
            </span>
          </div>
        ))}
      </div>

      {latestLines.length > 0 && (
        <div className="balance-sheet-wrap">
          <div className="panel-head">
            <h4>Balance sheet</h4>
            <span className="muted small mono">
              {bs?.as_of ?? "—"}
              {bs?.form ? ` · ${bs.form}` : ""}
            </span>
          </div>
          <p className="muted small panel-sub">
            Hover any line for a plain-English explanation. Refresh the ticker
            to pull newly added SEC tags.
          </p>
          <div className="table-scroll">
            <table className="data-table balance-sheet-table">
              <thead>
                <tr>
                  <th>Line</th>
                  <th>Value</th>
                  <th>YoY</th>
                </tr>
              </thead>
              <tbody>
                {(["assets", "liabilities", "equity"] as const).map((section) => {
                  const rows = latestLines.filter((l) => l.section === section);
                  if (!rows.length) return null;
                  return (
                    <SectionRows
                      key={section}
                      section={section}
                      rows={rows.map((l) => (
                        <tr key={l.key}>
                          <td>
                            <TipLabel tipKey={l.key}>{l.label}</TipLabel>
                          </td>
                          <td className="mono">{fmtCompact(l.value)}</td>
                          <td className="mono">{fmtPct(l.yoy)}</td>
                        </tr>
                      ))}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {periods.length > 0 && historyRows.length > 0 && (
        <div className="growth-table-wrap balance-sheet-history">
          <h4>Balance sheet history</h4>
          <p className="muted small panel-sub">
            Prefer annual 10-K periods when available (oldest → newest)
          </p>
          <div className="table-scroll">
            <table className="data-table balance-sheet-history-table">
              <thead>
                <tr>
                  <th>Line</th>
                  {periods.map((p) => (
                    <th key={p} className="mono">
                      {p.slice(0, 4)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(["assets", "liabilities", "equity"] as const).map((section) => {
                  const rows = historyRows.filter((r) => r.section === section);
                  if (!rows.length) return null;
                  return (
                    <SectionRows
                      key={`h-${section}`}
                      section={section}
                      colSpan={periods.length + 1}
                      rows={rows.map((r) => (
                        <tr key={r.key}>
                          <td>
                            <TipLabel tipKey={r.key}>{r.label}</TipLabel>
                          </td>
                          {r.values.map((v, i) => (
                            <td key={`${r.key}-${periods[i]}`} className="mono">
                              {fmtCompact(v)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

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

function SectionRows({
  section,
  rows,
  colSpan = 3,
}: {
  section: string;
  rows: ReactNode[];
  colSpan?: number;
}) {
  return (
    <>
      <tr className="bs-section-row">
        <td colSpan={colSpan} className="bs-section-label">
          {SECTION_LABELS[section] ?? section}
        </td>
      </tr>
      {rows}
    </>
  );
}
