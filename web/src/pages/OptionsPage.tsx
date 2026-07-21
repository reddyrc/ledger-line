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

import { useOptionsChain, useOptionsContract } from "../api/hooks";
import type { OptionContract } from "../types/api";
import { fmtNum, fmtPct, fmtPrice, normalizeTicker } from "../lib/format";

type Selected = {
  side: "call" | "put";
  contract: OptionContract;
};

export function OptionsPage() {
  const { symbol: raw } = useParams();
  const symbol = normalizeTicker(raw ?? "");
  const [expiration, setExpiration] = useState<string | undefined>(undefined);
  const [selected, setSelected] = useState<Selected | null>(null);
  const [period, setPeriod] = useState("3mo");

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
          <span className="chip">Max pain {fmtNum(summary.max_pain, 2)}</span>
          <span className="chip">
            Exp move{" "}
            {move?.expected_move == null
              ? "—"
              : `±${fmtNum(move.expected_move, 2)} (${fmtPct(move.expected_move_pct)})`}
          </span>
          <span className="chip">
            Range{" "}
            {move?.price_low == null || move?.price_high == null
              ? "—"
              : `${fmtNum(move.price_low, 2)}–${fmtNum(move.price_high, 2)}`}
          </span>
          <span className="chip">PCR OI {fmtNum(totals?.pcr_oi, 2)}</span>
          <span className="chip">PCR vol {fmtNum(totals?.pcr_volume, 2)}</span>
          <span className="chip">
            Call OI {fmtNum(totals?.call_oi, 0)} · Put OI{" "}
            {fmtNum(totals?.put_oi, 0)}
          </span>
          <span className="chip">
            Call vol {fmtNum(totals?.call_volume, 0)} · Put vol{" "}
            {fmtNum(totals?.put_volume, 0)}
          </span>
        </div>
      )}

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
                    <th>C vol</th>
                    <th>C OI</th>
                    <th>C IV</th>
                    <th>C mid</th>
                    <th>C day</th>
                    <th>Strike</th>
                    <th>P day</th>
                    <th>P mid</th>
                    <th>P IV</th>
                    <th>P OI</th>
                    <th>P vol</th>
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
                <span className="chip">Mid {fmtNum(selected.contract.mid)}</span>
                <span className="chip">
                  Bid/Ask {fmtNum(selected.contract.bid)} /{" "}
                  {fmtNum(selected.contract.ask)}
                </span>
                <span className="chip">Last {fmtNum(selected.contract.last)}</span>
                <span className="chip">
                  IV {fmtPct(selected.contract.implied_volatility)}
                </span>
                <span className="chip">
                  OI {fmtNum(selected.contract.open_interest, 0)}
                </span>
                <span className="chip">
                  Vol {fmtNum(selected.contract.volume, 0)}
                </span>
                <span className="chip">
                  Breakeven {fmtNum(selected.contract.breakeven)}
                </span>
                <span className="chip">
                  Session{" "}
                  {selected.contract.day_low != null &&
                  selected.contract.day_high != null
                    ? `${fmtNum(selected.contract.day_low)}–${fmtNum(selected.contract.day_high)}`
                    : "—"}
                </span>
                {(["delta", "gamma", "theta", "vega", "rho"] as const).map((g) =>
                  selected.contract[g] != null ? (
                    <span key={g} className="chip">
                      {g} {fmtNum(selected.contract[g], 4)}
                    </span>
                  ) : null,
                )}
              </div>

              {contractQuery.isLoading && (
                <div className="chart-skeleton skeleton-block" />
              )}
              {contractQuery.data?.error && (
                <p className="muted">{contractQuery.data.error}</p>
              )}
              {contractQuery.data && !contractQuery.data.error && (
                <>
                  <div className="chip-row">
                    <span className="chip chip-median">
                      Traded low {fmtNum(contractQuery.data.traded_low)}
                    </span>
                    <span className="chip chip-median">
                      Traded high {fmtNum(contractQuery.data.traded_high)}
                    </span>
                    <span className="chip">
                      Last close {fmtNum(contractQuery.data.traded_last)}
                    </span>
                  </div>
                  {(contractQuery.data.series?.length ?? 0) > 0 ? (
                    <div className="options-premium-chart">
                      <ResponsiveContainer width="100%" height={220}>
                        <LineChart data={contractQuery.data.series}>
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
                            tick={{ fill: "var(--muted)", fontSize: 11 }}
                            width={42}
                            domain={["auto", "auto"]}
                          />
                          <Tooltip
                            contentStyle={{
                              background: "var(--panel)",
                              border: "1px solid var(--border)",
                            }}
                          />
                          <Line
                            type="monotone"
                            dataKey="close"
                            stroke="var(--accent)"
                            dot={false}
                            strokeWidth={2}
                            name="Premium"
                          />
                          <Line
                            type="monotone"
                            dataKey="high"
                            stroke="var(--accent-2)"
                            dot={false}
                            strokeWidth={1}
                            strokeDasharray="4 4"
                            name="High"
                          />
                          <Line
                            type="monotone"
                            dataKey="low"
                            stroke="var(--muted)"
                            dot={false}
                            strokeWidth={1}
                            strokeDasharray="4 4"
                            name="Low"
                          />
                        </LineChart>
                      </ResponsiveContainer>
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
