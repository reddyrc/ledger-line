import { Link } from "react-router-dom";
import { useState, type FormEvent } from "react";

import type { PeerComparisonResponse, PeerMetrics } from "../types/api";
import { fmtCompact, fmtNum, fmtPct, fmtPrice } from "../lib/format";

type Props = {
  data?: PeerComparisonResponse;
  loading?: boolean;
  customPeers?: string[];
  onCustomPeersChange?: (tickers: string[]) => void;
};

type MetricKey = keyof Pick<
  PeerMetrics,
  | "pe"
  | "pb"
  | "ps"
  | "roe"
  | "net_margin"
  | "momentum_3m"
  | "momentum_12m"
  | "vol_ann"
  | "max_drawdown_1y"
  | "market_cap"
>;

const COMPARE_METRICS: Array<{
  key: MetricKey;
  label: string;
  format: (v: number | null | undefined) => string;
}> = [
  { key: "pe", label: "P/E", format: (v) => fmtNum(v) },
  { key: "pb", label: "P/B", format: (v) => fmtNum(v) },
  { key: "ps", label: "P/S", format: (v) => fmtNum(v) },
  { key: "roe", label: "ROE", format: (v) => fmtPct(v) },
  { key: "net_margin", label: "Net mgn", format: (v) => fmtPct(v) },
  { key: "momentum_3m", label: "3M mom", format: (v) => fmtPct(v) },
  { key: "momentum_12m", label: "12M mom", format: (v) => fmtPct(v) },
  { key: "vol_ann", label: "Vol", format: (v) => fmtPct(v) },
  { key: "max_drawdown_1y", label: "Max DD", format: (v) => fmtPct(v) },
  { key: "market_cap", label: "Mkt cap", format: (v) => fmtCompact(v) },
];

function fmtPercentile(p: number | null | undefined): string {
  if (p == null || Number.isNaN(p)) return "—";
  return `P${Math.round(p * 100)}`;
}

function fmtFetchedAt(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function freshnessLabel(data: PeerComparisonResponse): string {
  const when = fmtFetchedAt(data.fetched_at);
  if (data.stale || data.freshness === "stale") {
    return when ? `Stale · last updated ${when}` : "Stale cache";
  }
  if (data.freshness === "cached") {
    return when ? `Cached · updated ${when}` : "Cached";
  }
  if (data.freshness === "live") {
    return when ? `Live · updated ${when}` : "Live";
  }
  return when ? `Updated ${when}` : "";
}

function MetricCell({
  value,
  format,
}: {
  value: number | null | undefined;
  format: (v: number | null | undefined) => string;
}) {
  return <td className="mono">{format(value)}</td>;
}

function PeerPicker({
  tickers,
  onChange,
}: {
  tickers: string[];
  onChange?: (tickers: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function addTicker(event: FormEvent) {
    event.preventDefault();
    const ticker = draft
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9.-]/g, "")
      .slice(0, 12);
    if (!ticker || tickers.includes(ticker) || tickers.length >= 10) return;
    onChange?.([...tickers, ticker]);
    setDraft("");
  }

  return (
    <div className="peer-picker">
      <form className="peer-add-form" onSubmit={addTicker}>
        <input
          className="peer-add-input mono"
          value={draft}
          onChange={(event) => setDraft(event.target.value.toUpperCase())}
          placeholder="Add ticker"
          aria-label="Ticker to add to peer comparison"
          maxLength={12}
        />
        <button
          className="btn-secondary peer-add-btn"
          type="submit"
          disabled={!draft.trim() || tickers.length >= 10}
        >
          Add peer
        </button>
      </form>
      {tickers.length > 0 && (
        <div className="peer-custom-chips" aria-label="Custom peer tickers">
          {tickers.map((ticker) => (
            <button
              key={ticker}
              className="chip peer-custom-chip mono"
              type="button"
              onClick={() => onChange?.(tickers.filter((t) => t !== ticker))}
              title={`Remove ${ticker}`}
            >
              {ticker} ×
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function PeerComparisonPanel({
  data,
  loading,
  customPeers = [],
  onCustomPeersChange,
}: Props) {
  const picker = (
    <PeerPicker tickers={customPeers} onChange={onCustomPeersChange} />
  );

  if (loading) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Peer comparison</h3>
        </div>
        {picker}
        <div className="chart-skeleton skeleton-block" />
      </div>
    );
  }

  if (!data) {
    return null;
  }

  if (data.error && !data.subject) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Peer comparison</h3>
        </div>
        {picker}
        <p className="muted">{data.error}</p>
      </div>
    );
  }

  const subject = data.subject;
  const peers = (data.peers ?? []).filter(
    (p) => p.ticker !== subject?.ticker,
  );
  // Custom tickers directly under the subject, then automatic peers.
  const ordered = [
    ...peers.filter((p) => p.custom),
    ...peers.filter((p) => !p.custom),
  ];
  const rows: PeerMetrics[] = subject ? [subject, ...ordered] : ordered;

  const basis =
    data.basis_label ||
    (data.peer_basis === "sector" ? data.sector : data.industry) ||
    data.sector ||
    data.industry;
  const basisKind =
    data.peer_basis === "sector"
      ? "sector"
      : data.peer_basis === "industry"
        ? "industry"
        : null;
  const status = freshnessLabel(data);

  return (
    <div className="panel fade-in">
      <div className="panel-head">
        <h3>Peer comparison</h3>
        <p className="muted small panel-sub">
          {basis
            ? `${basisKind ? `${basisKind}: ` : ""}${basis} · ${
                data.peer_count ?? peers.length
              } peers`
            : "Live Yahoo peers"}
          {status ? ` · ${status}` : ""}
        </p>
      </div>

      {picker}

      {data.warning && <p className="banner warn">{data.warning}</p>}
      {data.error && <p className="muted">{data.error}</p>}

      {subject && (
        <div className="peer-stat-grid">
          {COMPARE_METRICS.map(({ key, label, format }) => {
            const stat = data.sector_stats?.[key];
            return (
              <div key={key} className="peer-stat">
                <div className="peer-stat-label">{label}</div>
                <div className="peer-stat-value mono">{format(stat?.subject)}</div>
                <div className="peer-stat-meta muted small">
                  peer med {format(stat?.median)} ·{" "}
                  {fmtPercentile(stat?.percentile)}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {rows.length > 0 && (
        <div className="table-scroll peer-table-wrap">
          <table className="data-table screener-table peer-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Price</th>
                <th>Mkt cap</th>
                <th>P/E</th>
                <th>P/B</th>
                <th>P/S</th>
                <th>ROE</th>
                <th>Net mgn</th>
                <th>3M</th>
                <th>12M</th>
                <th>Vol</th>
                <th>Max DD</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isSubject = r.ticker === data.symbol;
                return (
                  <tr
                    key={r.ticker ?? "row"}
                    className={isSubject ? "peer-row-subject" : undefined}
                  >
                    <td>
                      {r.ticker ? (
                        <Link
                          className="mono ticker-link"
                          to={`/s/${r.ticker}`}
                        >
                          {r.ticker}
                          {isSubject ? " · you" : ""}
                          {r.custom ? " · custom" : ""}
                        </Link>
                      ) : (
                        "—"
                      )}
                      {r.name && (
                        <div className="muted small screener-name">{r.name}</div>
                      )}
                    </td>
                    <MetricCell value={r.price} format={fmtPrice} />
                    <MetricCell value={r.market_cap} format={fmtCompact} />
                    <MetricCell value={r.pe} format={fmtNum} />
                    <MetricCell value={r.pb} format={fmtNum} />
                    <MetricCell value={r.ps} format={fmtNum} />
                    <MetricCell value={r.roe} format={fmtPct} />
                    <MetricCell value={r.net_margin} format={fmtPct} />
                    <MetricCell value={r.momentum_3m} format={fmtPct} />
                    <MetricCell value={r.momentum_12m} format={fmtPct} />
                    <MetricCell value={r.vol_ann} format={fmtPct} />
                    <MetricCell value={r.max_drawdown_1y} format={fmtPct} />
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {data.disclaimer && <p className="disclaimer">{data.disclaimer}</p>}
    </div>
  );
}
