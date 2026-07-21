import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useOptionStrategies } from "../api/hooks";
import type { StrategyIdea } from "../types/api";
import { fmtNum, fmtPct } from "../lib/format";
import { OPTION_TIPS } from "../lib/optionsGlossary";

type FamilyFilter = "all" | "credit" | "debit" | "mispricing";

type Props = {
  symbol: string;
  expiration?: string;
};

const COLLAPSE_KEY = "ledgerline.options.strategiesCollapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(collapsed: boolean) {
  try {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
  } catch {
    /* ignore */
  }
}

function liquidityBadge(idea: StrategyIdea): string | null {
  const liq = idea.metrics.liquidity;
  if (!liq) return null;
  if (liq.max_spread_pct != null && liq.max_spread_pct > 0.2) return "wide spread";
  if (
    (liq.min_oi != null && liq.min_oi >= 100) ||
    (liq.min_volume != null && liq.min_volume >= 10)
  ) {
    return "liquid";
  }
  return null;
}

function IdeaCard({ idea, symbol }: { idea: StrategyIdea; symbol: string }) {
  const m = idea.metrics;
  const href = `/s/${symbol}/strategies/${idea.id}?expiration=${encodeURIComponent(idea.expiration)}`;
  const badge = liquidityBadge(idea);
  return (
    <Link to={href} className={`strategy-card family-${idea.family}`}>
      <div className="strategy-card-top">
        <span className="strategy-family mono">{idea.family}</span>
        <span className="strategy-score mono" title={OPTION_TIPS.edgeScore}>
          {fmtNum(m.edge_score, 0)}
        </span>
      </div>
      <div className="strategy-title">{idea.title}</div>
      <div className="strategy-meta muted small">
        {m.credit_or_debit != null && (
          <span title={OPTION_TIPS.creditDebit}>
            {m.credit_or_debit >= 0 ? "Credit" : "Debit"}{" "}
            {fmtNum(Math.abs(m.credit_or_debit))}
          </span>
        )}
        {m.max_loss != null && (
          <span title={OPTION_TIPS.maxLoss}>Max loss {fmtNum(m.max_loss)}</span>
        )}
        {m.pop_proxy != null && (
          <span title={OPTION_TIPS.pop}>POP~ {fmtPct(m.pop_proxy)}</span>
        )}
        {m.severity && <span>{m.severity}</span>}
        {badge && (
          <span
            className="strategy-liq-badge"
            title="Quick liquidity check from the legs' open interest, volume, and bid-ask spread."
          >
            {badge}
          </span>
        )}
        {m.days_to_earnings != null && m.days_to_earnings <= 7 && (
          <span className="strategy-earn-badge" title={OPTION_TIPS.earnings}>
            earn {m.days_to_earnings}d
          </span>
        )}
      </div>
      {m.notes?.[0] && <p className="muted small strategy-note">{m.notes[0]}</p>}
    </Link>
  );
}

export function StrategyIdeasPanel({ symbol, expiration }: Props) {
  const [family, setFamily] = useState<FamilyFilter>("all");
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [liqOn, setLiqOn] = useState(false);

  const filters = liqOn
    ? { min_oi: 100, min_volume: 10, max_spread_pct: 0.25 }
    : undefined;

  const strategies = useOptionStrategies(symbol, expiration, filters);
  const ideas = useMemo(() => {
    const all = strategies.data?.ideas ?? [];
    if (family === "all") return all;
    return all.filter((i) => i.family === family);
  }, [strategies.data?.ideas, family]);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      writeCollapsed(next);
      return next;
    });
  }

  return (
    <div
      className={`panel strategy-ideas-panel${collapsed ? " is-collapsed" : ""}`}
      id="strategies"
    >
      <div className="panel-head">
        <h3>Strategies</h3>
        <div className="strategy-filters">
          {!collapsed && (
            <>
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
              <button
                type="button"
                className={`chart-toggle-btn${liqOn ? " active" : ""}`}
                onClick={() => setLiqOn((v) => !v)}
                aria-pressed={liqOn}
              >
                Liquidity filter
              </button>
              <Link className="btn-secondary" to="/strategies">
                Scanner
              </Link>
            </>
          )}
          <button
            type="button"
            className="btn-secondary strategy-collapse-btn"
            onClick={toggleCollapsed}
            aria-expanded={!collapsed}
            aria-controls="strategies-body"
          >
            {collapsed ? "Expand" : "Collapse"}
          </button>
        </div>
      </div>

      {!collapsed && (
        <div id="strategies-body">
          <p className="muted small">
            Heuristic ranks from delayed Yahoo mids — not trade advice or
            guaranteed edge.
            {strategies.data?.days_to_earnings != null &&
              strategies.data.days_to_earnings <= 7 &&
              ` Earnings in ${strategies.data.days_to_earnings}d.`}
          </p>

          {strategies.isLoading && (
            <div className="chart-skeleton skeleton-block" />
          )}

          {strategies.data?.error && !ideas.length && (
            <p className="muted">{strategies.data.error}</p>
          )}

          {!strategies.isLoading &&
            ideas.length === 0 &&
            !strategies.data?.error && (
              <div className="empty-panel">
                No strategy ideas for this expiration
                {liqOn ? " with current liquidity filters" : ""}.
              </div>
            )}

          {ideas.length > 0 && (
            <div className="strategy-card-grid">
              {ideas.map((idea) => (
                <IdeaCard key={idea.id} idea={idea} symbol={symbol} />
              ))}
            </div>
          )}

          {strategies.data?.disclaimer && (
            <p className="disclaimer">{strategies.data.disclaimer}</p>
          )}
        </div>
      )}
    </div>
  );
}
