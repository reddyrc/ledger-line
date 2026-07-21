import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useOptionStrategyDetail } from "../api/hooks";
import { fmtCompact, fmtNum, fmtPct, normalizeTicker } from "../lib/format";
import { useSeo } from "../lib/seo";
import { OPTION_TIPS } from "../lib/optionsGlossary";
import { sizeStrategy } from "../lib/strategySizing";

const CAPITAL_KEY = "ledgerline.strategies.capital";

function money(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

export function StrategyDetailPage() {
  const { symbol: raw, ideaId = "" } = useParams();
  const symbol = normalizeTicker(raw ?? "");
  useSeo(`${symbol} option strategy detail`);
  const [params] = useSearchParams();
  const expiration = params.get("expiration") ?? undefined;

  const [capitalDraft, setCapitalDraft] = useState(() => {
    try {
      return localStorage.getItem(CAPITAL_KEY) || "1000";
    } catch {
      return "1000";
    }
  });
  const [capital, setCapital] = useState(() => {
    const n = Number(capitalDraft);
    return Number.isFinite(n) && n > 0 ? n : 1000;
  });

  const detail = useOptionStrategyDetail(symbol, ideaId, expiration);
  const idea = detail.data?.idea;
  const m = idea?.metrics;

  const sizing = useMemo(() => {
    if (!idea || !m) return null;
    return sizeStrategy({
      family: idea.family,
      creditOrDebit: m.credit_or_debit,
      maxProfitPerShare: m.max_profit,
      maxLossPerShare: m.max_loss,
      breakevens: m.breakevens,
      capital,
    });
  }, [idea, m, capital]);

  const payoffScaled = useMemo(() => {
    const curve = detail.data?.payoff ?? [];
    const contracts = sizing?.contracts ?? 0;
    if (!contracts) return curve;
    return curve.map((p) => ({
      spot: p.spot,
      pnl: p.pnl == null ? null : p.pnl * 100 * contracts,
    }));
  }, [detail.data?.payoff, sizing?.contracts]);

  function commitCapital() {
    const n = Number(capitalDraft.replace(/[^0-9.]/g, ""));
    const next = Number.isFinite(n) && n > 0 ? n : 1000;
    setCapital(next);
    setCapitalDraft(String(next));
    try {
      localStorage.setItem(CAPITAL_KEY, String(next));
    } catch {
      /* ignore */
    }
  }

  if (!symbol || !ideaId) {
    return <p className="muted">Missing strategy reference.</p>;
  }

  return (
    <div className="strategy-detail-page fade-in">
      <div className="symbol-header">
        <div>
          <p className="muted small">
            <Link to={`/s/${symbol}/options`}>← {symbol} options</Link>
            {" · "}
            <Link to="/strategies">Scanner</Link>
          </p>
          <h1 className="symbol-title">
            {idea?.title ?? "Strategy detail"}
          </h1>
          <p className="muted small mono">
            {symbol}
            {idea?.expiration ? ` · ${idea.expiration}` : ""}
            {idea?.family ? ` · ${idea.family}` : ""}
            {idea?.kind ? ` · ${idea.kind}` : ""}
          </p>
        </div>
      </div>

      {detail.isLoading && <div className="chart-skeleton skeleton-block" />}

      {detail.data?.error && !idea && (
        <p className="banner error">{detail.data.error}</p>
      )}

      {idea && m && (
        <>
          <div className="banner warn">
            Heuristic screen only — delayed Yahoo mids ignore fills, fees, and
            assignment. Not trade advice.
          </div>

          <div className="panel strategy-capital-panel">
            <div className="panel-head">
              <h3>Position size</h3>
              <p className="muted small panel-sub">
                Capital budget vs defined max loss per contract
              </p>
            </div>
            <form
              className="strategy-capital-form"
              onSubmit={(e) => {
                e.preventDefault();
                commitCapital();
              }}
            >
              <label className="options-exp-label">
                Invest / risk budget ($)
                <input
                  className="strategy-capital-input mono"
                  value={capitalDraft}
                  onChange={(e) => setCapitalDraft(e.target.value)}
                  onBlur={commitCapital}
                  inputMode="decimal"
                  aria-label="Capital to invest or risk"
                />
              </label>
              <button className="btn-secondary" type="submit">
                Apply
              </button>
            </form>
            {sizing && (
              <div className="chip-row valuation-stats">
                <span className="chip" data-tip={OPTION_TIPS.contracts}>
                  Contracts {sizing.contracts || "0"}
                </span>
                <span className="chip" data-tip={OPTION_TIPS.capitalUsed}>
                  Capital used {money(sizing.capitalUsed)}
                </span>
                <span
                  className="chip chip-median"
                  data-tip="Best-case profit for the sized position at expiration."
                >
                  Max gain {money(sizing.maxProfit)}
                </span>
                <span
                  className="chip"
                  data-tip="Worst-case loss for the sized position at expiration."
                >
                  Max loss {money(sizing.maxLoss)}
                </span>
                <span className="chip" data-tip={OPTION_TIPS.netPremium}>
                  Net premium{" "}
                  {sizing.netPremium == null
                    ? "—"
                    : `${sizing.netPremium >= 0 ? "+" : ""}${money(sizing.netPremium)}`}
                </span>
                {sizing.breakevens.map((be, i) => (
                  <span
                    key={`${be}-${i}`}
                    className="chip"
                    data-tip="Stock price at expiration where this position neither makes nor loses money."
                  >
                    {sizing.breakevens.length > 1 ? `BE${i + 1}` : "Breakeven"}{" "}
                    {fmtNum(be, 2)}
                  </span>
                ))}
                {sizing.roiOnRisk != null && (
                  <span className="chip" data-tip={OPTION_TIPS.gainRisk}>
                    Gain / risk {fmtPct(sizing.roiOnRisk)}
                  </span>
                )}
              </div>
            )}
            {sizing && sizing.contracts === 0 && m.max_loss != null && (
              <p className="muted small">
                Need at least {money(m.max_loss * 100)} to open 1 contract at
                this max-loss estimate.
              </p>
            )}
            {idea.family === "mispricing" && (
              <p className="muted small">
                Mispricing flags are quote anomalies — sizing may be unavailable.
              </p>
            )}
          </div>

          <div className="chip-row valuation-stats">
            <span className="chip" data-tip={OPTION_TIPS.edgeScore}>
              Score {fmtNum(m.edge_score, 0)}
            </span>
            {m.credit_or_debit != null && (
              <span className="chip" data-tip={OPTION_TIPS.creditDebit}>
                {m.credit_or_debit >= 0 ? "Credit" : "Debit"}/sh{" "}
                {fmtNum(Math.abs(m.credit_or_debit))}
              </span>
            )}
            {m.max_profit != null && (
              <span className="chip" data-tip={OPTION_TIPS.maxProfit}>
                Max profit/sh {fmtNum(m.max_profit)}
              </span>
            )}
            {m.max_loss != null && (
              <span className="chip" data-tip={OPTION_TIPS.maxLoss}>
                Max loss/sh {fmtNum(m.max_loss)}
              </span>
            )}
            {m.pop_proxy != null && (
              <span className="chip" data-tip={OPTION_TIPS.pop}>
                POP~ {fmtPct(m.pop_proxy)}
              </span>
            )}
            {m.spot != null && (
              <span className="chip" data-tip={OPTION_TIPS.spot}>
                Spot {fmtNum(m.spot)}
              </span>
            )}
            {m.expected_move != null && (
              <span className="chip" data-tip={OPTION_TIPS.expMove}>
                Exp move ±{fmtNum(m.expected_move)}
              </span>
            )}
            {m.max_pain != null && (
              <span className="chip" data-tip={OPTION_TIPS.maxPain}>
                Max pain {fmtNum(m.max_pain)}
              </span>
            )}
            {m.severity && <span className="chip">{m.severity}</span>}
            {detail.data?.days_to_earnings != null && (
              <span className="chip" data-tip={OPTION_TIPS.earnings}>
                Earnings in {detail.data.days_to_earnings}d
              </span>
            )}
          </div>

          {detail.data?.greeks && (
            <div className="chip-row valuation-stats">
              <span className="chip" data-tip={OPTION_TIPS.netDelta}>
                Δ {fmtNum(detail.data.greeks.delta, 3)}
              </span>
              <span className="chip" data-tip={OPTION_TIPS.netGamma}>
                Γ {fmtNum(detail.data.greeks.gamma, 4)}
              </span>
              <span className="chip" data-tip={OPTION_TIPS.netTheta}>
                Θ {fmtNum(detail.data.greeks.theta, 3)}
              </span>
              <span className="chip" data-tip={OPTION_TIPS.netVega}>
                ν {fmtNum(detail.data.greeks.vega, 3)}
              </span>
              <span
                className="chip muted small"
                data-tip="Greeks estimated with the Black-Scholes model using each leg's mid-implied volatility."
              >
                BS from mid IV
              </span>
            </div>
          )}

          {(m.notes?.length ?? 0) > 0 && (
            <ul className="strategy-notes">
              {m.notes.map((n) => (
                <li key={n} className="muted">
                  {n}
                </li>
              ))}
            </ul>
          )}

          <div className="options-layout">
            <div className="panel">
              <div className="panel-head">
                <h3>Legs</h3>
              </div>
              <div className="table-scroll">
                <table className="data-table screener-table">
                  <thead>
                    <tr>
                      <th title="Buy (long) or sell (short) this leg.">
                        Action
                      </th>
                      <th title="Call or put.">Right</th>
                      <th title="Price at which the option can be exercised.">
                        Strike
                      </th>
                      <th title={OPTION_TIPS.mid}>Mid</th>
                      <th title={OPTION_TIPS.bidAsk}>Bid/Ask</th>
                      <th title={OPTION_TIPS.iv}>IV</th>
                      <th title={OPTION_TIPS.delta}>Δ</th>
                      <th title={OPTION_TIPS.theta}>Θ</th>
                      <th title={OPTION_TIPS.vega}>ν</th>
                      <th>Contract</th>
                    </tr>
                  </thead>
                  <tbody>
                    {idea.legs.map((lg, idx) => {
                      const gg = detail.data?.greeks?.legs?.find(
                        (x) =>
                          x.contract_symbol === lg.contract_symbol ||
                          (x.strike === lg.strike && x.right === lg.right),
                      );
                      return (
                        <tr key={`${lg.contract_symbol ?? idx}`}>
                          <td className="mono">{lg.action}</td>
                          <td className="mono">{lg.right}</td>
                          <td className="mono">{fmtNum(lg.strike, 2)}</td>
                          <td className="mono">{fmtNum(lg.mid)}</td>
                          <td className="mono">
                            {fmtNum(lg.bid)} / {fmtNum(lg.ask)}
                          </td>
                          <td className="mono">
                            {fmtPct(lg.implied_volatility)}
                          </td>
                          <td className="mono">{fmtNum(gg?.delta, 3)}</td>
                          <td className="mono">{fmtNum(gg?.theta, 3)}</td>
                          <td className="mono">{fmtNum(gg?.vega, 3)}</td>
                          <td className="mono small">
                            {lg.contract_symbol ?? "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="panel">
              <div className="panel-head">
                <h3>Expiration PnL</h3>
                <p className="muted small panel-sub">
                  {sizing && sizing.contracts > 0
                    ? `USD for ${sizing.contracts} contract${sizing.contracts === 1 ? "" : "s"}`
                    : "Per share, mid-based"}
                </p>
              </div>
              {payoffScaled.length > 0 ? (
                <div className="options-premium-chart">
                  <ResponsiveContainer width="100%" height={260}>
                    <LineChart data={payoffScaled}>
                      <CartesianGrid
                        stroke="var(--grid)"
                        strokeDasharray="3 3"
                      />
                      <XAxis
                        dataKey="spot"
                        tick={{ fill: "var(--muted)", fontSize: 11 }}
                        tickFormatter={(v) => Number(v).toFixed(0)}
                      />
                      <YAxis
                        tick={{ fill: "var(--muted)", fontSize: 11 }}
                        width={52}
                        tickFormatter={(v) => fmtCompact(Number(v))}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "var(--panel)",
                          border: "1px solid var(--border)",
                        }}
                        formatter={(value) => [
                          sizing && sizing.contracts > 0
                            ? money(Number(value))
                            : fmtNum(Number(value)),
                          "PnL",
                        ]}
                        labelFormatter={(label) =>
                          `Spot ${fmtNum(Number(label))}`
                        }
                      />
                      <ReferenceLine y={0} stroke="var(--border)" />
                      {m.spot != null && (
                        <ReferenceLine
                          x={m.spot}
                          stroke="var(--accent-2)"
                          strokeDasharray="4 4"
                        />
                      )}
                      {(sizing?.breakevens ?? []).map((be) => (
                        <ReferenceLine
                          key={be}
                          x={be}
                          stroke="var(--danger)"
                          strokeDasharray="3 3"
                        />
                      ))}
                      <Line
                        type="monotone"
                        dataKey="pnl"
                        stroke="var(--accent)"
                        dot={false}
                        strokeWidth={2}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="muted">No payoff curve available.</p>
              )}
            </div>
          </div>

          {detail.data?.scenarios?.grid &&
            detail.data.scenarios.grid.length > 0 && (
              <div className="panel">
                <div className="panel-head">
                  <h3>Scenario risk</h3>
                  <p className="muted small panel-sub">
                    Mark-to-model PnL / share under spot × IV shocks
                  </p>
                </div>
                <div className="table-scroll">
                  <table className="data-table screener-table scenario-grid">
                    <thead>
                      <tr>
                        <th>Spot \\ IV</th>
                        {(detail.data.scenarios.iv_shocks ?? [-0.2, 0, 0.2]).map(
                          (iv) => (
                            <th key={iv} className="mono">
                              {iv > 0 ? "+" : ""}
                              {(iv * 100).toFixed(0)}%
                            </th>
                          ),
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {(detail.data.scenarios.spot_shocks ?? []).map((sp) => (
                        <tr key={sp}>
                          <td className="mono">
                            {sp > 0 ? "+" : ""}
                            {(sp * 100).toFixed(0)}%
                          </td>
                          {(
                            detail.data!.scenarios!.iv_shocks ?? [-0.2, 0, 0.2]
                          ).map((iv) => {
                            const cell = detail.data!.scenarios!.grid.find(
                              (g) => g.spot_pct === sp && g.iv_pct === iv,
                            );
                            const pnl = cell?.pnl;
                            const tone =
                              pnl == null
                                ? ""
                                : pnl > 0
                                  ? "scenario-pos"
                                  : pnl < 0
                                    ? "scenario-neg"
                                    : "";
                            return (
                              <td key={`${sp}-${iv}`} className={`mono ${tone}`}>
                                {fmtNum(pnl)}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {detail.data.scenarios.note && (
                  <p className="disclaimer">{detail.data.scenarios.note}</p>
                )}
              </div>
            )}

          {(idea.disclaimer || detail.data?.disclaimer) && (
            <p className="disclaimer">
              {idea.disclaimer ?? detail.data?.disclaimer}
            </p>
          )}
        </>
      )}
    </div>
  );
}
