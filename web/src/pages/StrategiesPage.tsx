import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useStrategiesScan } from "../api/hooks";
import type { StrategyIdea } from "../types/api";
import { fmtNum, fmtPct, normalizeTicker } from "../lib/format";
import { useSeo } from "../lib/seo";
import { OPTION_TIPS } from "../lib/optionsGlossary";

const DEFAULT_WATCHLIST =
  "SPY,QQQ,IWM,AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA";
const STORAGE_KEY = "ledgerline.strategies.watchlist";

type FamilyFilter = "all" | "credit" | "debit" | "mispricing";

function parseWatchlist(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((t) => normalizeTicker(t))
    .filter(Boolean)
    .filter((t, i, arr) => arr.indexOf(t) === i)
    .slice(0, 15);
}

export function StrategiesPage() {
  useSeo(
    "Options strategy screener",
    "Scan a watchlist for credit spreads, iron condors, and covered calls with liquidity filters, POP estimates, and earnings-risk annotations.",
  );
  const [draft, setDraft] = useState(DEFAULT_WATCHLIST);
  const [watchlist, setWatchlist] = useState<string[]>(() =>
    parseWatchlist(DEFAULT_WATCHLIST),
  );
  const [family, setFamily] = useState<FamilyFilter>("all");
  const [minOi, setMinOi] = useState("100");
  const [minVol, setMinVol] = useState("10");
  const [maxSpread, setMaxSpread] = useState("25");

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

  const liqFilters = useMemo(() => {
    const oi = Number(minOi);
    const vol = Number(minVol);
    const spr = Number(maxSpread);
    return {
      min_oi: Number.isFinite(oi) ? oi : 100,
      min_volume: Number.isFinite(vol) ? vol : 10,
      max_spread_pct: Number.isFinite(spr) ? spr / 100 : 0.25,
    };
  }, [minOi, minVol, maxSpread]);

  const scan = useStrategiesScan(watchlist, "nearest", liqFilters);

  const ideas = useMemo(() => {
    const all = scan.data?.ideas ?? [];
    const filtered =
      family === "all" ? all : all.filter((i) => i.family === family);
    return [...filtered].sort(
      (a, b) => (b.metrics.edge_score ?? 0) - (a.metrics.edge_score ?? 0),
    );
  }, [scan.data?.ideas, family]);

  function applyWatchlist() {
    const next = parseWatchlist(draft);
    setWatchlist(next);
    setDraft(next.join(","));
    try {
      localStorage.setItem(STORAGE_KEY, next.join(","));
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="strategies-page fade-in">
      <div className="symbol-header">
        <div>
          <h1 className="symbol-title">Strategy scanner</h1>
          <p className="muted small">
            Cross-ticker heuristic ideas from live Yahoo chains. Not trade advice.
          </p>
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
            applyWatchlist();
          }}
        >
          <input
            className="strategy-watch-input mono"
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            placeholder="SPY, QQQ, AAPL…"
            aria-label="Strategy watchlist tickers"
          />
          <button className="btn-secondary" type="submit">
            Scan
          </button>
        </form>
        <div className="strategy-filters" style={{ marginTop: "0.75rem" }}>
          {(["all", "credit", "debit", "mispricing"] as FamilyFilter[]).map(
            (key) => (
              <button
                key={key}
                type="button"
                className={`sort-btn${family === key ? " active" : ""}`}
                onClick={() => setFamily(key)}
              >
                {key}
              </button>
            ),
          )}
        </div>
        <div className="liq-filter-row">
          <label className="options-exp-label">
            Min OI
            <input
              className="strategy-capital-input mono"
              value={minOi}
              onChange={(e) => setMinOi(e.target.value)}
            />
          </label>
          <label className="options-exp-label">
            Min vol
            <input
              className="strategy-capital-input mono"
              value={minVol}
              onChange={(e) => setMinVol(e.target.value)}
            />
          </label>
          <label className="options-exp-label">
            Max spread %
            <input
              className="strategy-capital-input mono"
              value={maxSpread}
              onChange={(e) => setMaxSpread(e.target.value)}
            />
          </label>
        </div>
      </div>

      {scan.isLoading && <div className="chart-skeleton skeleton-block" />}

      {(scan.data?.errors?.length ?? 0) > 0 && (
        <p className="muted small">
          Some symbols failed:{" "}
          {scan.data!.errors.map((e) => e.symbol).join(", ")}
        </p>
      )}

      {!scan.isLoading && ideas.length === 0 && (
        <div className="empty-panel">No ideas for this watchlist yet.</div>
      )}

      {ideas.length > 0 && (
        <div className="panel">
          <div className="table-scroll">
            <table className="data-table screener-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th title="Strategy family: credit (sell premium), debit (buy premium), or mispricing (quote anomaly).">
                    Family
                  </th>
                  <th>Idea</th>
                  <th title={OPTION_TIPS.edgeScore}>Score</th>
                  <th title={OPTION_TIPS.creditDebit}>Cr/Db</th>
                  <th title={OPTION_TIPS.maxLoss}>Max loss</th>
                  <th title={OPTION_TIPS.pop}>POP~</th>
                  <th title="Worst leg liquidity: lowest open interest / volume and widest bid-ask spread across the legs.">
                    Liq
                  </th>
                  <th title={OPTION_TIPS.earnings}>Earn</th>
                  <th title="Option expiration date.">Exp</th>
                </tr>
              </thead>
              <tbody>
                {ideas.map((idea: StrategyIdea) => (
                  <tr key={`${idea.symbol}-${idea.id}`}>
                    <td>
                      <Link
                        className="mono ticker-link"
                        to={`/s/${idea.symbol}/strategies/${idea.id}?expiration=${encodeURIComponent(idea.expiration)}`}
                      >
                        {idea.symbol}
                      </Link>
                    </td>
                    <td className="mono">{idea.family}</td>
                    <td>
                      <Link
                        className="ticker-link"
                        to={`/s/${idea.symbol}/strategies/${idea.id}?expiration=${encodeURIComponent(idea.expiration)}`}
                      >
                        {idea.title}
                      </Link>
                    </td>
                    <td className="mono">
                      {fmtNum(idea.metrics.edge_score, 0)}
                    </td>
                    <td className="mono">
                      {idea.metrics.credit_or_debit == null
                        ? "—"
                        : fmtNum(idea.metrics.credit_or_debit)}
                    </td>
                    <td className="mono">
                      {fmtNum(idea.metrics.max_loss)}
                    </td>
                    <td className="mono">
                      {fmtPct(idea.metrics.pop_proxy)}
                    </td>
                    <td className="mono small">
                      {idea.metrics.liquidity?.max_spread_pct != null &&
                      idea.metrics.liquidity.max_spread_pct > 0.2
                        ? "wide"
                        : idea.metrics.liquidity?.ok === false
                          ? "thin"
                          : "ok"}
                    </td>
                    <td className="mono small">
                      {idea.metrics.days_to_earnings == null
                        ? "—"
                        : `${idea.metrics.days_to_earnings}d`}
                    </td>
                    <td className="mono small">{idea.expiration}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {scan.data?.disclaimer && (
        <p className="disclaimer">{scan.data.disclaimer}</p>
      )}
    </div>
  );
}
