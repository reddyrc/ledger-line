import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { useOptionStrategies } from "../api/hooks";
import type { StrategyIdea } from "../types/api";
import { fmtNum, fmtPct } from "../lib/format";
import { OPTION_TIPS } from "../lib/optionsGlossary";

type FamilyFilter = "all" | "credit" | "debit" | "collar" | "mispricing";

type Props = {
  symbol: string;
  expiration?: string;
};

const FAMILY_FILTERS: Array<{ key: FamilyFilter; label: string }> = [
  { key: "all", label: "all" },
  { key: "credit", label: "credit" },
  { key: "debit", label: "debit" },
  { key: "collar", label: "collars" },
  { key: "mispricing", label: "mispricing" },
];

const FAMILY_KEYS = new Set(FAMILY_FILTERS.map((f) => f.key));

const COLLAPSE_KEY = "ledgerline.options.strategiesCollapsed";
const MAX_LOSS_KEY = "ledgerline.options.collarMaxLoss";
/** Near-free options net (call bid − put ask), matches backend FREE_COLLAR_MAX_DEBIT. */
const NEAR_FREE_NET = -0.05;

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

function readMaxLossDraft(): string {
  try {
    return localStorage.getItem(MAX_LOSS_KEY) ?? "";
  } catch {
    return "";
  }
}

function parseFamily(raw: string | null): FamilyFilter {
  if (raw && FAMILY_KEYS.has(raw as FamilyFilter)) return raw as FamilyFilter;
  return "all";
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

/** Dollar P&L for one collar (100 shares) from a per-share metric. */
function collarDollars(perShare: number | null | undefined): number | null {
  if (perShare == null || Number.isNaN(perShare)) return null;
  return perShare * 100;
}

/** Reward / risk: max_gain ÷ max_loss (higher is better). */
function rewardRiskRatio(idea: StrategyIdea): number | null {
  const gain = idea.metrics.max_profit;
  const loss = idea.metrics.max_loss;
  if (gain == null || loss == null || Number.isNaN(gain) || Number.isNaN(loss)) {
    return null;
  }
  if (loss <= 0) return gain > 0 ? Number.POSITIVE_INFINITY : null;
  return gain / loss;
}

function sortByRewardRisk(ideas: StrategyIdea[]): StrategyIdea[] {
  return [...ideas].sort((a, b) => {
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
}

function IdeaCard({
  idea,
  symbol,
  returnTo,
}: {
  idea: StrategyIdea;
  symbol: string;
  returnTo: string;
}) {
  const m = idea.metrics;
  const href = `/s/${symbol}/strategies/${idea.id}?expiration=${encodeURIComponent(idea.expiration)}`;
  const badge = liquidityBadge(idea);
  const familyLabel = idea.family === "collar" ? "collar" : idea.family;
  const isCollar = idea.family === "collar";
  const lossDollars = isCollar ? collarDollars(m.max_loss) : null;
  const gainDollars = isCollar ? collarDollars(m.max_profit) : null;
  return (
    <Link
      to={href}
      state={{ returnTo }}
      className={`strategy-card family-${idea.family}`}
    >
      <div className="strategy-card-top">
        <span
          className="strategy-family mono"
          title={isCollar ? OPTION_TIPS.collar : undefined}
        >
          {familyLabel}
        </span>
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
        {gainDollars != null ? (
          <span title={OPTION_TIPS.maxProfit}>
            Max gain ~${fmtNum(gainDollars, 0)}
          </span>
        ) : (
          m.max_profit != null && (
            <span title={OPTION_TIPS.maxProfit}>
              Max gain {fmtNum(m.max_profit)}
            </span>
          )
        )}
        {lossDollars != null ? (
          <span title={OPTION_TIPS.collarMaxLoss}>
            Max loss ~${fmtNum(lossDollars, 0)}
          </span>
        ) : (
          m.max_loss != null && (
            <span title={OPTION_TIPS.maxLoss}>Max loss {fmtNum(m.max_loss)}</span>
          )
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
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [family, setFamily] = useState<FamilyFilter>(() =>
    parseFamily(searchParams.get("family")),
  );
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [liqOn, setLiqOn] = useState(false);
  const [maxLossDraft, setMaxLossDraft] = useState(readMaxLossDraft);

  useEffect(() => {
    const fromUrl = parseFamily(searchParams.get("family"));
    if (fromUrl !== family) setFamily(fromUrl);
    // Only re-sync when the URL changes (e.g. browser back).
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

  const maxLossBudget = useMemo(() => {
    const n = Number(maxLossDraft);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [maxLossDraft]);

  const returnTo = `${location.pathname}${location.search}#strategies`;

  const filters = liqOn
    ? { min_oi: 100, min_volume: 10, max_spread_pct: 0.25 }
    : undefined;

  const strategies = useOptionStrategies(symbol, expiration, filters);
  const ideas = useMemo(() => {
    const all = strategies.data?.ideas ?? [];
    let filtered: StrategyIdea[];
    if (family === "all") {
      filtered = all;
    } else if (family !== "collar") {
      filtered = all.filter((i) => i.family === family);
    } else {
      const collars = all.filter((i) => i.family === "collar");
      if (maxLossBudget != null) {
        filtered = collars.filter((i) => {
          const dollars = collarDollars(i.metrics.max_loss);
          return dollars != null && dollars <= maxLossBudget;
        });
      } else {
        filtered = collars.filter(
          (i) =>
            i.metrics.credit_or_debit != null &&
            i.metrics.credit_or_debit >= NEAR_FREE_NET,
        );
      }
    }
    return sortByRewardRisk(filtered);
  }, [strategies.data?.ideas, family, maxLossBudget]);

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

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      writeCollapsed(next);
      return next;
    });
  }

  const showCollarBudget = !collapsed && family === "collar";

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
              {FAMILY_FILTERS.map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  className={`sort-btn${family === key ? " active" : ""}`}
                  onClick={() => selectFamily(key)}
                >
                  {label}
                </button>
              ))}
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
            Heuristic ranks from delayed Yahoo quotes — not trade advice.
            Cards are sorted by max gain ÷ max loss (best reward/risk first).
            Collars are long stock + long put + short call. Leave the loss
            budget blank for near-zero options cost, or set a $ worst-case
            budget (per 100 shares) to include tighter debit puts.
            {strategies.data?.days_to_earnings != null &&
              strategies.data.days_to_earnings <= 7 &&
              ` Earnings in ${strategies.data.days_to_earnings}d.`}
          </p>

          {showCollarBudget && (
            <div className="collar-budget-row">
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
                  ? "Shows collars whose worst-case loss (100 sh) is within your budget."
                  : "Leave blank for near-zero options cost only. Enter a $ budget to include tighter puts."}
              </span>
              {maxLossDraft && (
                <button
                  type="button"
                  className="sort-btn"
                  onClick={() => setMaxLossDraft("")}
                >
                  clear
                </button>
              )}
            </div>
          )}

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
                {liqOn ? " with current liquidity filters" : ""}
                {family === "collar" && maxLossBudget != null
                  ? ` within a $${fmtNum(maxLossBudget, 0)} worst-case budget`
                  : ""}
                .
              </div>
            )}

          {ideas.length > 0 && (
            <div className="strategy-card-grid">
              {ideas.map((idea) => (
                <IdeaCard
                  key={idea.id}
                  idea={idea}
                  symbol={symbol}
                  returnTo={returnTo}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
