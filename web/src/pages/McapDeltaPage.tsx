import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  boundsForSelection,
  defaultSelection,
  type DateBounds,
  type RangePreset,
  useMcapDelta,
} from "../api/hooks";
import { DateRangeControls } from "../components/DateRangeControls";
import {
  fmtCompact,
  fmtPct,
  fmtSignedCompact,
  normalizeTicker,
} from "../lib/format";
import { useSeo } from "../lib/seo";

const DEFAULT_WATCHLIST =
  "AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA,INTC";
const STORAGE_KEY = "ledgerline.mcap.watchlist";

function parseWatchlist(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((t) => normalizeTicker(t))
    .filter(Boolean)
    .filter((t, i, arr) => arr.indexOf(t) === i)
    .slice(0, 15);
}

export function McapDeltaPage() {
  useSeo(
    "Market cap delta",
    "Tally signed market-cap change for a watchlist over a selected period — end minus start, with a cumulative total.",
  );

  const [draft, setDraft] = useState(DEFAULT_WATCHLIST);
  const [watchlist, setWatchlist] = useState<string[]>(() =>
    parseWatchlist(DEFAULT_WATCHLIST),
  );
  const [mode, setMode] = useState<"preset" | "custom">("preset");
  const [preset, setPreset] = useState<RangePreset>("1Y");
  const [custom, setCustom] = useState<DateBounds>(() => {
    const sel = defaultSelection("1Y");
    return sel.custom;
  });
  const [wantRefresh, setWantRefresh] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        setDraft(saved);
        setWatchlist(parseWatchlist(saved));
      }
    } catch {
      /* ignore */
    }
  }, []);

  const bounds = useMemo(
    () => boundsForSelection(mode, preset, custom),
    [mode, preset, custom],
  );

  const query = useMcapDelta(
    {
      symbols: watchlist,
      start: bounds.start,
      end: bounds.end,
      refresh: wantRefresh,
    },
    watchlist.length > 0,
  );

  useEffect(() => {
    if (wantRefresh && !query.isFetching) {
      setWantRefresh(false);
    }
  }, [wantRefresh, query.isFetching]);

  function applyWatchlist(refresh = false) {
    const next = parseWatchlist(draft);
    setWatchlist(next);
    setDraft(next.join(","));
    if (refresh) setWantRefresh(true);
    try {
      localStorage.setItem(STORAGE_KEY, next.join(","));
    } catch {
      /* ignore */
    }
  }

  function selectPreset(next: RangePreset) {
    setMode("preset");
    setPreset(next);
    setCustom({ start: undefined, end: undefined });
  }

  const totals = query.data?.totals;
  const rows = query.data?.rows ?? [];

  return (
    <div className="mcap-delta-page fade-in">
      <div className="symbol-header">
        <div>
          <h1 className="page-title">Market cap Δ</h1>
          <p className="muted small">
            Signed change in market cap (end − start) for each ticker, using
            price × as-of EDGAR shares. Cumulative total sums the deltas.
          </p>
        </div>
        <div className="controls">
          <DateRangeControls
            mode={mode}
            preset={preset}
            custom={custom}
            onPreset={selectPreset}
            onCustomChange={setCustom}
            onModeCustom={() => setMode("custom")}
          />
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h3>Watchlist</h3>
        </div>
        <form
          className="strategy-watch-form"
          onSubmit={(e) => {
            e.preventDefault();
            applyWatchlist(false);
          }}
        >
          <input
            className="strategy-watch-input mono"
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            aria-label="Market cap watchlist"
            placeholder="AAPL, MSFT, NVDA…"
          />
          <button className="btn-secondary" type="submit" disabled={query.isFetching}>
            {query.isFetching ? "Loading…" : "Load"}
          </button>
          <button
            className="btn-secondary"
            type="button"
            disabled={query.isFetching}
            onClick={() => applyWatchlist(true)}
          >
            Refresh
          </button>
        </form>
      </div>

      {totals && (
        <div className="mcap-delta-summary panel">
          <div className="mcap-delta-summary-grid">
            <div>
              <p className="muted small">Cumulative Δ market cap</p>
              <p
                className={`mcap-delta-total mono${
                  (totals.delta_mcap ?? 0) < 0
                    ? " neg"
                    : (totals.delta_mcap ?? 0) > 0
                      ? " pos"
                      : ""
                }`}
              >
                {fmtSignedCompact(totals.delta_mcap)}
              </p>
            </div>
            <div>
              <p className="muted small">Sum start → end</p>
              <p className="mono">
                {fmtCompact(totals.start_mcap)} → {fmtCompact(totals.end_mcap)}
              </p>
            </div>
            <div>
              <p className="muted small">Included</p>
              <p className="mono">
                {totals.included}
                {totals.failed > 0 ? ` · ${totals.failed} failed` : ""}
              </p>
            </div>
          </div>
        </div>
      )}

      {query.isLoading && <div className="chart-skeleton skeleton-block" />}

      {query.isError && (
        <div className="banner error">
          {(query.error as Error).message || "Failed to load market-cap deltas."}
        </div>
      )}

      {!query.isLoading && rows.length > 0 && (
        <div className="panel">
          <div className="table-scroll">
            <table className="data-table screener-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Start</th>
                  <th>End</th>
                  <th>Start mcap</th>
                  <th>End mcap</th>
                  <th>Δ mcap</th>
                  <th>Δ %</th>
                  <th>Δ price</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.symbol}>
                    <td>
                      <Link className="ticker-link mono" to={`/s/${r.symbol}`}>
                        {r.symbol}
                      </Link>
                    </td>
                    {r.error ? (
                      <td className="muted small" colSpan={7}>
                        {r.error}
                      </td>
                    ) : (
                      <>
                        <td className="mono small">{r.start_date ?? "—"}</td>
                        <td className="mono small">{r.end_date ?? "—"}</td>
                        <td className="mono">{fmtCompact(r.start_mcap)}</td>
                        <td className="mono">{fmtCompact(r.end_mcap)}</td>
                        <td
                          className={`mono${
                            (r.delta_mcap ?? 0) < 0
                              ? " neg"
                              : (r.delta_mcap ?? 0) > 0
                                ? " pos"
                                : ""
                          }`}
                        >
                          {fmtSignedCompact(r.delta_mcap)}
                        </td>
                        <td
                          className={`mono${
                            (r.delta_mcap_pct ?? 0) < 0
                              ? " neg"
                              : (r.delta_mcap_pct ?? 0) > 0
                                ? " pos"
                                : ""
                          }`}
                        >
                          {fmtPct(r.delta_mcap_pct)}
                        </td>
                        <td className="mono">{fmtPct(r.delta_price_pct)}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {query.data?.disclaimer && (
            <p className="muted small" style={{ marginTop: "0.75rem" }}>
              {query.data.disclaimer}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
