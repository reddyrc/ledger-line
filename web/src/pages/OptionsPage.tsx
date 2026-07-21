import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useHistory, useOptionsChain, useOptionsContract } from "../api/hooks";
import type { DateBounds } from "../api/hooks";
import { IvEarningsChips, TermStructureTable } from "../components/IvEarningsChips";
import { IvHistoryPanel } from "../components/IvHistoryPanel";
import { StrategyIdeasPanel } from "../components/StrategyIdeasPanel";
import type { OptionContract } from "../types/api";
import { fmtNum, fmtPct, fmtPrice, normalizeTicker } from "../lib/format";
import { OPTION_TIPS } from "../lib/optionsGlossary";

type Selected = {
  side: "call" | "put";
  contract: OptionContract;
};

function formatExpiry(
  expiration: string | null | undefined,
  dte: number | null | undefined,
): string {
  if (!expiration) return "—";
  const date = String(expiration).slice(0, 10);
  let days = dte;
  if (days == null) {
    const exp = new Date(`${date}T00:00:00`);
    if (!Number.isNaN(exp.getTime())) {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      days = Math.round((exp.getTime() - today.getTime()) / 86_400_000);
    }
  }
  if (days == null) return date;
  return `${date} (${days <= 0 ? "expires today" : `${days}d`})`;
}

function historyBounds(period: string): DateBounds {
  const now = new Date();
  if (period === "max") return {};
  if (period === "ytd") {
    return { start: `${now.getFullYear()}-01-01` };
  }

  const months: Record<string, number> = {
    "1mo": 1,
    "3mo": 3,
    "6mo": 6,
    "1y": 12,
  };
  now.setMonth(now.getMonth() - (months[period] ?? 3));
  return { start: now.toISOString().slice(0, 10) };
}

export function OptionsPage() {
  const { symbol: raw } = useParams();
  const symbol = normalizeTicker(raw ?? "");
  const [expiration, setExpiration] = useState<string | undefined>(undefined);
  const [selected, setSelected] = useState<Selected | null>(null);
  const [period, setPeriod] = useState("3mo");
  const [showStock, setShowStock] = useState(false);

  const chain = useOptionsChain(symbol, expiration);

  useEffect(() => {
    setExpiration(undefined);
    setSelected(null);
  }, [symbol]);

  useEffect(() => {
    if (!expiration && chain.data?.expiration) {
      setExpiration(chain.data.expiration);
    }
  }, [expiration, chain.data?.expiration]);

  useEffect(() => {
    setSelected(null);
  }, [expiration]);

  const data = chain.data;
  const summary = data?.summary;
  const move = summary?.expected_move;
  const totals = summary?.totals;

  const strikeRows = useMemo(() => {
    const callBy = new Map(
      (data?.calls ?? [])
        .filter((c) => c.strike != null)
        .map((c) => [c.strike as number, c]),
    );
    const putBy = new Map(
      (data?.puts ?? [])
        .filter((p) => p.strike != null)
        .map((p) => [p.strike as number, p]),
    );
    const strikes = Array.from(
      new Set([...callBy.keys(), ...putBy.keys()]),
    ).sort((a, b) => a - b);
    return strikes.map((strike) => ({
      strike,
      call: callBy.get(strike) ?? null,
      put: putBy.get(strike) ?? null,
    }));
  }, [data?.calls, data?.puts]);

  const contractQuery = useOptionsContract(symbol, {
    contract: selected?.contract.contract_symbol,
    period,
    side: selected?.side,
    strike: selected?.contract.strike,
    day_low: selected?.contract.day_low,
    day_high: selected?.contract.day_high,
  });
  const stockBounds = useMemo(() => historyBounds(period), [period]);
  const stockQuery = useHistory(
    symbol,
    stockBounds,
    showStock && Boolean(selected),
  );
  const contractChartData = useMemo(() => {
    const series = contractQuery.data?.series ?? [];
    if (!showStock) return series;

    const stockByDate = new Map(
      (stockQuery.data?.bars ?? []).map((bar) => [
        bar.date,
        bar.adj_close ?? bar.close,
      ]),
    );
    return series.map((point) => ({
      ...point,
      stock: stockByDate.get(point.date) ?? null,
    }));
  }, [contractQuery.data?.series, showStock, stockQuery.data?.bars]);

  if (!symbol) {
    return <p className="muted">Enter a valid ticker.</p>;
  }

  return (
    <div className="options-page fade-in">
      <div className="symbol-header">
        <div>
          <p className="muted small">
            <Link to={`/s/${symbol}`}>← {symbol}</Link>
          </p>
          <h1 className="symbol-title mono">{symbol} options</h1>
          <p className="muted small">
            Spot {fmtPrice(data?.spot)}
            {data?.expiration ? ` · exp ${data.expiration}` : ""}
            {data?.freshness ? ` · ${data.freshness}` : ""}
          </p>
        </div>
        <div className="controls">
          <label className="options-exp-label">
            Expiration
            <select
              className="options-exp-select mono"
              value={expiration ?? data?.expiration ?? ""}
              onChange={(e) => setExpiration(e.target.value || undefined)}
              disabled={!data?.expirations?.length}
            >
              {(data?.expirations ?? []).map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {chain.isLoading && <div className="chart-skeleton skeleton-block" />}

      {data?.error && !summary && <p className="banner error">{data.error}</p>}
      {data?.warning && <p className="banner warn">{data.warning}</p>}

      {summary && (
        <div className="chip-row valuation-stats">
          <span className="chip" data-tip={OPTION_TIPS.maxPain}>
            Max pain {fmtNum(summary.max_pain, 2)}
          </span>
          <span className="chip" data-tip={OPTION_TIPS.expMove}>
            Exp move{" "}
            {move?.expected_move == null
              ? "—"
              : `±${fmtNum(move.expected_move, 2)} (${fmtPct(move.expected_move_pct)})`}
          </span>
          <span className="chip" data-tip={OPTION_TIPS.range}>
            Range{" "}
            {move?.price_low == null || move?.price_high == null
              ? "—"
              : `${fmtNum(move.price_low, 2)}–${fmtNum(move.price_high, 2)}`}
          </span>
          <span className="chip" data-tip={OPTION_TIPS.pcrOi}>
            PCR OI {fmtNum(totals?.pcr_oi, 2)}
          </span>
          <span className="chip" data-tip={OPTION_TIPS.pcrVol}>
            PCR vol {fmtNum(totals?.pcr_volume, 2)}
          </span>
          <span className="chip" data-tip={OPTION_TIPS.callPutOi}>
            Call OI {fmtNum(totals?.call_oi, 0)} · Put OI{" "}
            {fmtNum(totals?.put_oi, 0)}
          </span>
          <span className="chip" data-tip={OPTION_TIPS.callPutVol}>
            Call vol {fmtNum(totals?.call_volume, 0)} · Put vol{" "}
            {fmtNum(totals?.put_volume, 0)}
          </span>
          <IvEarningsChips
            iv={data?.iv_context ?? summary.iv_context}
            daysToEarnings={data?.days_to_earnings ?? summary.days_to_earnings}
            nextEarnings={data?.next_earnings ?? summary.next_earnings}
          />
        </div>
      )}

      {summary && (
        <TermStructureTable
          term={(data?.iv_context ?? summary.iv_context)?.term_structure}
        />
      )}

      <IvHistoryPanel
        symbol={symbol}
        expiration={expiration ?? data?.expiration ?? undefined}
      />

      {(data?.uoa?.length ?? 0) > 0 && (
        <div className="panel">
          <div className="panel-head">
            <h3>Unusual activity</h3>
            <p className="muted small panel-sub">
              Heuristic volume/OI vs chain median — not confirmed blocks
            </p>
          </div>
          <div className="table-scroll">
            <table className="data-table screener-table">
              <thead>
                <tr>
                  <th>Side</th>
                  <th>Strike</th>
                  <th title="Contract expiration date and days remaining until it expires.">
                    Expires
                  </th>
                  <th title={OPTION_TIPS.volume}>Vol</th>
                  <th title={OPTION_TIPS.oi}>OI</th>
                  <th title={OPTION_TIPS.volOi}>Vol/OI</th>
                  <th title={OPTION_TIPS.notional}>Notional</th>
                  <th title={OPTION_TIPS.uoaScore}>Score</th>
                  <th>Contract</th>
                </tr>
              </thead>
              <tbody>
                {(data?.uoa ?? []).slice(0, 12).map((row) => (
                  <tr key={String(row.contract_symbol)}>
                    <td className="mono">{row.side}</td>
                    <td className="mono">{fmtNum(row.strike, 2)}</td>
                    <td className="mono">
                      {formatExpiry(
                        row.expiration ?? data?.expiration,
                        row.dte,
                      )}
                    </td>
                    <td className="mono">{fmtNum(row.volume, 0)}</td>
                    <td className="mono">{fmtNum(row.open_interest, 0)}</td>
                    <td className="mono">{fmtNum(row.volume_oi, 2)}</td>
                    <td className="mono">{fmtNum(row.premium_notional, 0)}</td>
                    <td className="mono">{fmtNum(row.score, 0)}</td>
                    <td className="mono">
                      {row.contract_symbol &&
                      (row.side === "call" || row.side === "put") ? (
                        <button
                          type="button"
                          className="linkish mono"
                          onClick={() => {
                            const side = row.side as "call" | "put";
                            const list =
                              side === "call" ? data?.calls : data?.puts;
                            const found = (list ?? []).find(
                              (c) => c.contract_symbol === row.contract_symbol,
                            );
                            if (found) {
                              setSelected({ side, contract: found });
                            }
                          }}
                        >
                          {row.contract_symbol}
                        </button>
                      ) : (
                        row.contract_symbol ?? "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <StrategyIdeasPanel symbol={symbol} expiration={expiration ?? data?.expiration ?? undefined} />

      <div className="options-layout">
        <div className="panel">
          <div className="panel-head">
            <h3>Chain</h3>
            <p className="muted small panel-sub">
              Click a call or put mid to inspect the contract
            </p>
          </div>
          {strikeRows.length === 0 && !chain.isLoading ? (
            <div className="empty-panel">No strikes for this expiration.</div>
          ) : (
            <div className="table-scroll">
              <table className="data-table screener-table options-chain-table">
                <thead>
                  <tr>
                    <th title={`Call volume. ${OPTION_TIPS.volume}`}>C vol</th>
                    <th title={`Call open interest. ${OPTION_TIPS.oi}`}>
                      C OI
                    </th>
                    <th title={`Call implied volatility. ${OPTION_TIPS.iv}`}>
                      C IV
                    </th>
                    <th title={`Call mid price. ${OPTION_TIPS.mid}`}>C mid</th>
                    <th title="Call price change today (absolute and %).">
                      C day
                    </th>
                    <th title="Price at which the option can be exercised. Bold row ≈ at-the-money.">
                      Strike
                    </th>
                    <th title="Put price change today (absolute and %).">
                      P day
                    </th>
                    <th title={`Put mid price. ${OPTION_TIPS.mid}`}>P mid</th>
                    <th title={`Put implied volatility. ${OPTION_TIPS.iv}`}>
                      P IV
                    </th>
                    <th title={`Put open interest. ${OPTION_TIPS.oi}`}>P OI</th>
                    <th title={`Put volume. ${OPTION_TIPS.volume}`}>P vol</th>
                  </tr>
                </thead>
                <tbody>
                  {strikeRows.map((row) => {
                    const isAtm = row.strike === summary?.atm_strike;
                    const isPain = row.strike === summary?.max_pain;
                    return (
                      <tr
                        key={row.strike}
                        className={
                          isPain
                            ? "options-row-pain"
                            : isAtm
                              ? "options-row-atm"
                              : undefined
                        }
                      >
                        <td className="mono">{fmtNum(row.call?.volume, 0)}</td>
                        <td className="mono">
                          {fmtNum(row.call?.open_interest, 0)}
                        </td>
                        <td className="mono">
                          {fmtPct(row.call?.implied_volatility)}
                        </td>
                        <td className="mono">
                          {row.call?.contract_symbol ? (
                            <button
                              type="button"
                              className="linkish mono"
                              onClick={() =>
                                setSelected({ side: "call", contract: row.call! })
                              }
                            >
                              {fmtNum(row.call.mid)}
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="mono muted small">
                          {row.call?.day_low != null &&
                          row.call?.day_high != null
                            ? `${fmtNum(row.call.day_low)}–${fmtNum(row.call.day_high)}`
                            : "—"}
                        </td>
                        <td className="mono">
                          {fmtNum(row.strike, 2)}
                          {isPain ? " · pain" : isAtm ? " · ATM" : ""}
                        </td>
                        <td className="mono muted small">
                          {row.put?.day_low != null && row.put?.day_high != null
                            ? `${fmtNum(row.put.day_low)}–${fmtNum(row.put.day_high)}`
                            : "—"}
                        </td>
                        <td className="mono">
                          {row.put?.contract_symbol ? (
                            <button
                              type="button"
                              className="linkish mono"
                              onClick={() =>
                                setSelected({ side: "put", contract: row.put! })
                              }
                            >
                              {fmtNum(row.put.mid)}
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="mono">
                          {fmtPct(row.put?.implied_volatility)}
                        </td>
                        <td className="mono">
                          {fmtNum(row.put?.open_interest, 0)}
                        </td>
                        <td className="mono">{fmtNum(row.put?.volume, 0)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="panel options-detail">
          <div className="panel-head">
            <h3>Contract</h3>
            {selected && (
              <div className="strategy-filters">
                <button
                  type="button"
                  className={`chart-toggle-btn${showStock ? " active" : ""}`}
                  onClick={() => setShowStock((value) => !value)}
                  aria-pressed={showStock}
                >
                  {showStock ? "Hide stock" : "Show stock"}
                </button>
                <label className="options-exp-label">
                  Range
                  <select
                    className="options-exp-select mono"
                    value={period}
                    onChange={(e) => setPeriod(e.target.value)}
                  >
                    {["1mo", "3mo", "6mo", "1y", "ytd", "max"].map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}
          </div>

          {!selected && (
            <p className="muted">Select a call or put mid from the chain.</p>
          )}

          {selected && (
            <>
              <p className="mono">
                {selected.contract.contract_symbol} · {selected.side}{" "}
                {fmtNum(selected.contract.strike, 2)}
              </p>
              <div className="chip-row valuation-stats">
                <span className="chip" data-tip={OPTION_TIPS.mid}>
                  Mid {fmtNum(selected.contract.mid)}
                </span>
                <span className="chip" data-tip={OPTION_TIPS.bidAsk}>
                  Bid/Ask {fmtNum(selected.contract.bid)} /{" "}
                  {fmtNum(selected.contract.ask)}
                </span>
                <span className="chip" data-tip={OPTION_TIPS.last}>
                  Last {fmtNum(selected.contract.last)}
                </span>
                <span className="chip" data-tip={OPTION_TIPS.iv}>
                  IV {fmtPct(selected.contract.implied_volatility)}
                </span>
                <span className="chip" data-tip={OPTION_TIPS.oi}>
                  OI {fmtNum(selected.contract.open_interest, 0)}
                </span>
                <span className="chip" data-tip={OPTION_TIPS.volume}>
                  Vol {fmtNum(selected.contract.volume, 0)}
                </span>
                <span className="chip" data-tip={OPTION_TIPS.breakeven}>
                  Breakeven {fmtNum(selected.contract.breakeven)}
                </span>
                <span className="chip" data-tip={OPTION_TIPS.session}>
                  Session{" "}
                  {selected.contract.day_low != null &&
                  selected.contract.day_high != null
                    ? `${fmtNum(selected.contract.day_low)}–${fmtNum(selected.contract.day_high)}`
                    : "—"}
                </span>
                {(["delta", "gamma", "theta", "vega", "rho"] as const).map((g) =>
                  selected.contract[g] != null ? (
                    <span key={g} className="chip" data-tip={OPTION_TIPS[g]}>
                      {g} {fmtNum(selected.contract[g], 4)}
                    </span>
                  ) : null,
                )}
              </div>

              {contractQuery.isLoading && (
                <div className="chart-skeleton skeleton-block" />
              )}
              {showStock && stockQuery.isLoading && (
                <p className="muted small">Loading {symbol} price history…</p>
              )}
              {showStock && stockQuery.isError && (
                <p className="banner warn">
                  Unable to load {symbol} price history.
                </p>
              )}
              {contractQuery.data?.error && (
                <p className="muted">{contractQuery.data.error}</p>
              )}
              {contractQuery.data && !contractQuery.data.error && (
                <>
                  <div className="chip-row">
                    <span
                      className="chip chip-median"
                      data-tip={OPTION_TIPS.tradedLow}
                    >
                      Traded low {fmtNum(contractQuery.data.traded_low)}
                    </span>
                    <span
                      className="chip chip-median"
                      data-tip={OPTION_TIPS.tradedHigh}
                    >
                      Traded high {fmtNum(contractQuery.data.traded_high)}
                    </span>
                    <span className="chip" data-tip={OPTION_TIPS.tradedLast}>
                      Last close {fmtNum(contractQuery.data.traded_last)}
                    </span>
                  </div>
                  {contractChartData.length > 0 ? (
                    <div className="options-premium-chart">
                      <ResponsiveContainer width="100%" height={220}>
                        <LineChart data={contractChartData}>
                          <CartesianGrid
                            stroke="var(--grid)"
                            strokeDasharray="3 3"
                          />
                          <XAxis
                            dataKey="date"
                            tick={{ fill: "var(--muted)", fontSize: 11 }}
                            minTickGap={28}
                          />
                          <YAxis
                            yAxisId="premium"
                            tick={{ fill: "var(--muted)", fontSize: 11 }}
                            width={42}
                            domain={["auto", "auto"]}
                          />
                          {showStock && (
                            <YAxis
                              yAxisId="stock"
                              orientation="right"
                              tick={{ fill: "var(--muted)", fontSize: 11 }}
                              width={54}
                              domain={["auto", "auto"]}
                              tickFormatter={(value: number) =>
                                fmtPrice(value)
                              }
                            />
                          )}
                          <Tooltip
                            contentStyle={{
                              background: "var(--panel)",
                              border: "1px solid var(--border)",
                            }}
                          />
                          <Line
                            yAxisId="premium"
                            type="monotone"
                            dataKey="close"
                            stroke="var(--accent)"
                            dot={false}
                            strokeWidth={2}
                            name="Premium"
                          />
                          <Line
                            yAxisId="premium"
                            type="monotone"
                            dataKey="high"
                            stroke="var(--accent-2)"
                            dot={false}
                            strokeWidth={1}
                            strokeDasharray="4 4"
                            name="High"
                          />
                          <Line
                            yAxisId="premium"
                            type="monotone"
                            dataKey="low"
                            stroke="var(--muted)"
                            dot={false}
                            strokeWidth={1}
                            strokeDasharray="4 4"
                            name="Low"
                          />
                          {showStock && (
                            <Line
                              yAxisId="stock"
                              type="monotone"
                              dataKey="stock"
                              stroke="var(--danger)"
                              dot={false}
                              strokeWidth={2}
                              name={`${symbol} stock`}
                              connectNulls
                            />
                          )}
                        </LineChart>
                      </ResponsiveContainer>
                      <div className="chart-legend muted small">
                        <span className="chart-legend-item">
                          <span className="legend-swatch legend-solid legend-accent" />
                          Daily closing premium
                        </span>
                        <span className="chart-legend-item">
                          <span className="legend-swatch legend-dashed legend-accent-2" />
                          Daily high premium
                        </span>
                        <span className="chart-legend-item">
                          <span className="legend-swatch legend-dashed legend-muted" />
                          Daily low premium
                        </span>
                        {showStock && (
                          <span className="chart-legend-item">
                            <span className="legend-swatch legend-solid legend-danger" />
                            {symbol} stock close (right axis)
                          </span>
                        )}
                      </div>
                    </div>
                  ) : (
                    <p className="muted">No premium history for this contract.</p>
                  )}
                  {contractQuery.data.disclaimer && (
                    <p className="disclaimer">{contractQuery.data.disclaimer}</p>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>

      {data?.disclaimer && <p className="disclaimer">{data.disclaimer}</p>}
    </div>
  );
}
