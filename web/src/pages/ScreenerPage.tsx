import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type { ScreenQuery } from "../api/client";
import { useRefreshScreen, useScreen, useScreenSectors } from "../api/hooks";
import { fmtCompact, fmtNum, fmtPct, fmtPrice } from "../lib/format";

type SortKey =
  | "ticker"
  | "price"
  | "market_cap"
  | "pe"
  | "pb"
  | "ps"
  | "roe"
  | "net_margin"
  | "momentum_3m"
  | "momentum_12m"
  | "vol_ann"
  | "max_drawdown_1y";

function parseOptionalNumber(raw: string): number | undefined {
  const t = raw.trim();
  if (!t) return undefined;
  const n = Number(t);
  return Number.isFinite(n) ? n : undefined;
}

export function ScreenerPage() {
  const [q, setQ] = useState("");
  const [sector, setSector] = useState("");
  const [peMax, setPeMax] = useState("");
  const [roeMin, setRoeMin] = useState("");
  const [momoMin, setMomoMin] = useState("");
  const [sort, setSort] = useState<SortKey>("momentum_12m");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [refreshLimit, setRefreshLimit] = useState("25");

  const query: ScreenQuery = useMemo(
    () => ({
      q: q.trim() || undefined,
      sector: sector || undefined,
      pe_max: parseOptionalNumber(peMax),
      roe_min: parseOptionalNumber(roeMin),
      momentum_12m_min: parseOptionalNumber(momoMin),
      sort,
      order,
      limit: 100,
      offset: 0,
    }),
    [q, sector, peMax, roeMin, momoMin, sort, order],
  );

  const screen = useScreen(query);
  const sectors = useScreenSectors();
  const refresh = useRefreshScreen();

  function toggleSort(col: SortKey) {
    if (sort === col) {
      setOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSort(col);
      setOrder(col === "ticker" ? "asc" : "desc");
    }
  }

  const rows = screen.data?.rows ?? [];
  const snapshotCount = screen.data?.snapshot_count ?? 0;

  return (
    <div className="screener-page fade-in">
      <div className="symbol-header">
        <div>
          <h1 className="page-title">Screener</h1>
          <p className="muted">
            S&P 500 snapshots from free price + EDGAR data.{" "}
            {snapshotCount > 0
              ? `${snapshotCount.toLocaleString()} tickers cached.`
              : "No snapshots yet — run a refresh."}
          </p>
        </div>
        <div className="controls">
          <label className="bench-label">
            Batch
            <input
              className="bench-input mono"
              value={refreshLimit}
              onChange={(e) => setRefreshLimit(e.target.value)}
              title="How many tickers to refresh this run"
            />
          </label>
          <button
            type="button"
            className="btn-secondary"
            disabled={refresh.isPending}
            onClick={() =>
              refresh.mutate({
                limit: parseOptionalNumber(refreshLimit) ?? 25,
                sleep: 0.2,
              })
            }
          >
            {refresh.isPending ? "Refreshing…" : "Refresh batch"}
          </button>
        </div>
      </div>

      {refresh.isSuccess && (
        <div className="banner ok">
          Processed {refresh.data.processed}: ok {refresh.data.ok}, failed{" "}
          {refresh.data.failed}
          {refresh.data.errors?.length
            ? ` · sample errors: ${refresh.data.errors
                .slice(0, 3)
                .map((e) => e.ticker)
                .join(", ")}`
            : ""}
        </div>
      )}
      {refresh.isError && (
        <div className="banner error">{(refresh.error as Error).message}</div>
      )}

      <div className="panel screener-filters">
        <div className="filter-grid">
          <label>
            Search
            <input
              value={q}
              onChange={(e) => setQ(e.target.value.toUpperCase())}
              placeholder="AAPL / Apple"
              autoComplete="off"
            />
          </label>
          <label>
            Sector
            <select value={sector} onChange={(e) => setSector(e.target.value)}>
              <option value="">All</option>
              {(sectors.data?.sectors ?? []).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label>
            Max P/E
            <input
              className="mono"
              value={peMax}
              onChange={(e) => setPeMax(e.target.value)}
              placeholder="e.g. 25"
            />
          </label>
          <label>
            Min ROE
            <input
              className="mono"
              value={roeMin}
              onChange={(e) => setRoeMin(e.target.value)}
              placeholder="e.g. 0.15"
            />
          </label>
          <label>
            Min 12M mom.
            <input
              className="mono"
              value={momoMin}
              onChange={(e) => setMomoMin(e.target.value)}
              placeholder="e.g. 0.1"
            />
          </label>
        </div>
      </div>

      <div className="panel screener-table-wrap">
        {screen.isLoading ? (
          <div className="chart-skeleton skeleton-block" />
        ) : screen.isError ? (
          <div className="banner error">{(screen.error as Error).message}</div>
        ) : snapshotCount === 0 ? (
          <div className="empty-panel">
            Screener cache is empty. Click <strong>Refresh batch</strong> to
            pull the first tickers (start small — full S&P 500 takes a while on
            free APIs).
          </div>
        ) : rows.length === 0 ? (
          <div className="empty-panel">No rows match these filters.</div>
        ) : (
          <>
            <p className="muted small">
              Showing {rows.length} of {screen.data?.total.toLocaleString()}{" "}
              matches
            </p>
            <div className="table-scroll">
              <table className="data-table screener-table">
                <thead>
                  <tr>
                    {(
                      [
                        ["ticker", "Ticker"],
                        ["price", "Price"],
                        ["market_cap", "Mkt cap"],
                        ["pe", "P/E"],
                        ["pb", "P/B"],
                        ["ps", "P/S"],
                        ["roe", "ROE"],
                        ["net_margin", "Net mgn"],
                        ["momentum_3m", "3M"],
                        ["momentum_12m", "12M"],
                        ["vol_ann", "Vol"],
                        ["max_drawdown_1y", "Max DD"],
                      ] as Array<[SortKey, string]>
                    ).map(([key, label]) => (
                      <th key={key}>
                        <button
                          type="button"
                          className="sort-btn"
                          onClick={() => toggleSort(key)}
                        >
                          {label}
                          {sort === key ? (order === "asc" ? " ↑" : " ↓") : ""}
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.ticker}>
                      <td>
                        <Link className="mono ticker-link" to={`/s/${r.ticker}`}>
                          {r.ticker}
                        </Link>
                        {r.name && (
                          <div className="muted small screener-name">{r.name}</div>
                        )}
                      </td>
                      <td className="mono">{fmtPrice(r.price)}</td>
                      <td className="mono">{fmtCompact(r.market_cap)}</td>
                      <td className="mono">{fmtNum(r.pe)}</td>
                      <td className="mono">{fmtNum(r.pb)}</td>
                      <td className="mono">{fmtNum(r.ps)}</td>
                      <td className="mono">{fmtPct(r.roe)}</td>
                      <td className="mono">{fmtPct(r.net_margin)}</td>
                      <td className="mono">{fmtPct(r.momentum_3m)}</td>
                      <td className="mono">{fmtPct(r.momentum_12m)}</td>
                      <td className="mono">{fmtPct(r.vol_ann)}</td>
                      <td className="mono">{fmtPct(r.max_drawdown_1y)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
