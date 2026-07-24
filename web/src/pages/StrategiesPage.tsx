import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { useStrategiesScan } from "../api/hooks";
import type { StrategyIdea } from "../types/api";
import { fmtNum, fmtPct, normalizeTicker } from "../lib/format";
import { useSeo } from "../lib/seo";
import { OPTION_TIPS } from "../lib/optionsGlossary";

const DEFAULT_WATCHLIST =
  "SPY,QQQ,IWM,AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA";
const STORAGE_KEY = "ledgerline.strategies.watchlist";
const MAX_LOSS_KEY = "ledgerline.options.collarMaxLoss";
const NEAR_FREE_NET = -0.05;

type FamilyFilter = "all" | "credit" | "debit" | "collar" | "mispricing";

const FAMILY_KEYS = new Set<FamilyFilter>([
  "all",
  "credit",
  "debit",
  "collar",
  "mispricing",
]);

function parseWatchlist(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((t) => normalizeTicker(t))
    .filter(Boolean)
    .filter((t, i, arr) => arr.indexOf(t) === i)
    .slice(0, 15);
}

function parseFamily(raw: string | null): FamilyFilter {
  if (raw && FAMILY_KEYS.has(raw as FamilyFilter)) return raw as FamilyFilter;
  return "all";
}

function collarMaxLossDollars(idea: StrategyIdea): number | null {
  const perShare = idea.metrics.max_loss;
  if (perShare == null || Number.isNaN(perShare)) return null;
  return perShare * 100;
}

function rewardRiskRatio(idea: StrategyIdea): number | null {
  const gain = idea.metrics.max_profit;
  const loss = idea.metrics.max_loss;
  if (gain == null || loss == null || Number.isNaN(gain) || Number.isNaN(loss)) {
    return null;
  }
  if (loss <= 0) return gain > 0 ? Number.POSITIVE_INFINITY : null;
  return gain / loss;
}

export function StrategiesPage() {
  useSeo(
    "Options strategy screener",
    "Scan a watchlist for credit spreads, iron condors, collars, and covered-style ideas with liquidity filters and earnings-risk annotations.",
  );
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState(DEFAULT_WATCHLIST);
  const [watchlist, setWatchlist] = useState<string[]>(() =>
    parseWatchlist(DEFAULT_WATCHLIST),
  );
  const [family, setFamily] = useState<FamilyFilter>(() =>
    parseFamily(searchParams.get("family")),
  );
  const [minOi, setMinOi] = useState("100");
  const [minVol, setMinVol] = useState("10");
  const [maxSpread, setMaxSpread] = useState("25");
  const [maxLossDraft, setMaxLossDraft] = useState(() => {
    try {
      return localStorage.getItem(MAX_LOSS_KEY) ?? "";
    } catch {
      return "";
    }
  });

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

  useEffect(() => {
    const fromUrl = parseFamily(searchParams.get("family"));
    if (fromUrl !== family) setFamily(fromUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    try {
      if (maxLossDraft.trim()) {
        localStorage.setItem(MAX_LOSS_KEY, maxLossDraft.trim());
      } else {
        localStorage.removeItem(MAX_LOSS_KEY);
      }
    } catch {
      /* ignore */
    }
  }, [maxLossDraft]);

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

  const maxLossBudget = useMemo(() => {
    const n = Number(maxLossDraft);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [maxLossDraft]);

  const returnTo = `${location.pathname}${location.search}`;

  const scan = useStrategiesScan(watchlist, "nearest", liqFilters);

  const ideas = useMemo(() => {
    const all = scan.data?.ideas ?? [];
    let filtered =
      family === "all" ? all : all.filter((i) => i.family === family);
    if (family === "collar") {
      if (maxLossBudget != null) {
        filtered = filtered.filter((i) => {
          const dollars = collarMaxLossDollars(i);
          return dollars != null && dollars <= maxLossBudget;
        });
      } else {
        filtered = filtered.filter(
          (i) =>
            i.metrics.credit_or_debit != null &&
            i.metrics.credit_or_debit >= NEAR_FREE_NET,
        );
      }
    }
    return [...filtered].sort((a, b) => {
      const ra = rewardRiskRatio(a);
      const rb = rewardRiskRatio(b);
      if (ra == null && rb == null) {
        return (b.metrics.edge_score ?? 0) - (a.metrics.edge_score ?? 0);
      }
      if (ra == null) return 1;
      if (rb == null) return -1;
      if (rb !== ra) return rb - ra;
      return (b.metrics.edge_score ?? 0) - (a.metrics.edge_score ?? 0);
    });
  }, [scan.data?.ideas, family, maxLossBudget]);

  function selectFamily(next: FamilyFilter) {
    setFamily(next);
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (next === "all") p.delete("family");
        else p.set("family", next);
        return p;
      },
      { replace: true },
    );
  }

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

  const ideaHref = (idea: StrategyIdea) =>
    `/s/${idea.symbol}/strategies/${idea.id}?expiration=${encodeURIComponent(idea.expiration)}`;

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
          {(
            [
              { key: "all", label: "all" },
              { key: "credit", label: "credit" },
              { key: "debit", label: "debit" },
              { key: "collar", label: "collars" },
              { key: "mispricing", label: "mispricing" },
            ] as Array<{ key: FamilyFilter; label: string }>
          ).map(({ key, label }) => (
            <button
              key={key}
              type="button"
              className={`sort-btn${family === key ? " active" : ""}`}
              onClick={() => selectFamily(key)}
            >
              {label}
            </button>
          ))}
        </div>
        {family === "collar" && (
          <div className="collar-budget-row" style={{ marginTop: "0.75rem" }}>
            <label className="options-exp-label" title={OPTION_TIPS.collarMaxLoss}>
              Willing to lose ≤ $
              <input
                className="strategy-capital-input mono"
                type="number"
                min={0}
                step={50}
                inputMode="decimal"
                placeholder="e.g. 500"
                value={maxLossDraft}
                onChange={(e) => setMaxLossDraft(e.target.value)}
                aria-label="Maximum collar loss in dollars for 100 shares"
              />
            </label>
            <span className="muted small">
              {maxLossBudget != null
                ? "Collars within this worst-case budget (100 sh)."
                : "Blank = near-zero options cost only."}
            </span>
          </div>
        )}
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
                  <th title="Strategy family: credit, debit, collar, or mispricing.">
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
                        to={ideaHref(idea)}
                        state={{ returnTo }}
                      >
                        {idea.symbol}
                      </Link>
                    </td>
                    <td className="mono">{idea.family}</td>
                    <td>
                      <Link
                        className="ticker-link"
                        to={ideaHref(idea)}
                        state={{ returnTo }}
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
