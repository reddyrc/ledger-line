import type { ReactNode } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useRolling } from "../api/hooks";
import type { DateBounds } from "../api/hooks";
import { fmtNum, fmtPct } from "../lib/format";

type Props = {
  symbol: string;
  bounds: DateBounds;
  window?: number;
  rangeControls?: ReactNode;
};

const TIPS = {
  cumReturn:
    "Running total return from the start of the selected date range to that day. Shows how much the stock is up or down over the chart window — not a rolling window.",
  rollVol:
    "Recent price jumpiness: standard deviation of about the last 21 trading days of daily returns, scaled to an annual %. Higher means the stock has been swinging harder lately.",
  rollSharpe:
    "Return per unit of risk over the last ~3 months (63 trading days). Roughly: average daily return ÷ daily volatility, annualized. Above ~1 is strong; near 0 is flat; negative means a rough ride relative to how much it wiggled.",
};

export function RollingRiskPanel({
  symbol,
  bounds,
  window = 63,
  rangeControls,
}: Props) {
  const rolling = useRolling(symbol, bounds, window);
  const series = rolling.data?.series ?? [];
  const latest = series.length ? series[series.length - 1] : null;

  const chartData = series.map((p) => ({
    date: p.date,
    vol: p.rolling_vol_ann == null ? null : p.rolling_vol_ann * 100,
    cum: p.cumulative_return == null ? null : p.cumulative_return * 100,
    sharpe: p.rolling_sharpe,
  }));

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Rolling risk</h3>
        {rangeControls}
      </div>
      <p className="muted small panel-sub">
        How risky and rewarding this stock has been <em>lately</em>, day by day —
        not a single forever number. Each point looks only at a recent window of
        daily returns (~1 month for vol, ~{window} trading days for Sharpe).
      </p>
      <ul className="muted small panel-howto">
        <li>
          <strong>Vol rising</strong> — swings got bigger; options often get
          richer and the stock is harder to hold.
        </li>
        <li>
          <strong>Sharpe rising</strong> — you were better paid for that risk
          (more return per unit of noise).
        </li>
        <li>
          <strong>Cum return up, Sharpe flat/down</strong> — you made money, but
          it was a choppy ride.
        </li>
      </ul>

      {rolling.isLoading && <div className="chart-skeleton skeleton-block" />}

      {latest && (
        <div className="chip-row valuation-stats">
          <span className="chip" data-tip={TIPS.cumReturn} tabIndex={0}>
            Cum return {fmtPct(latest.cumulative_return)}
          </span>
          <span className="chip" data-tip={TIPS.rollVol} tabIndex={0}>
            Roll vol {fmtPct(latest.rolling_vol_ann)}
          </span>
          <span className="chip" data-tip={TIPS.rollSharpe} tabIndex={0}>
            Roll Sharpe {fmtNum(latest.rolling_sharpe, 2)}
          </span>
        </div>
      )}

      {!rolling.isLoading && series.length === 0 && (
        <div className="empty-panel">No rolling series for this range.</div>
      )}

      {series.length > 0 && (
        <div className="chart-wrap fade-in">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData}>
              <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fill: "var(--muted)", fontSize: 11 }}
                tickFormatter={(d: string) => d.slice(0, 7)}
                minTickGap={48}
              />
              <YAxis
                yAxisId="pct"
                tick={{ fill: "var(--muted)", fontSize: 11 }}
                width={44}
                tickFormatter={(v) => `${Number(v).toFixed(0)}%`}
              />
              <YAxis
                yAxisId="sharpe"
                orientation="right"
                tick={{ fill: "var(--muted)", fontSize: 11 }}
                width={36}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--panel)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                }}
                formatter={(value, name) => {
                  const n = Number(value);
                  if (name === "Sharpe") return [fmtNum(n, 2), "Sharpe"];
                  if (name === "Roll vol") return [`${n.toFixed(1)}%`, "Roll vol"];
                  return [`${n.toFixed(1)}%`, "Cum return"];
                }}
              />
              <Legend />
              <Line
                yAxisId="pct"
                type="monotone"
                dataKey="cum"
                name="Cum return"
                stroke="var(--accent)"
                dot={false}
                strokeWidth={2}
              />
              <Line
                yAxisId="pct"
                type="monotone"
                dataKey="vol"
                name="Roll vol"
                stroke="var(--accent-2)"
                dot={false}
                strokeWidth={2}
                strokeDasharray="4 3"
              />
              <Line
                yAxisId="sharpe"
                type="monotone"
                dataKey="sharpe"
                name="Sharpe"
                stroke="var(--muted)"
                dot={false}
                strokeWidth={1.5}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
