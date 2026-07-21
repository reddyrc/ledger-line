import type { ReactNode } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TechnicalsPoint, TechnicalsLatest } from "../types/api";
import { fmtNum, fmtPrice } from "../lib/format";

type Props = {
  series: TechnicalsPoint[];
  latest?: TechnicalsLatest;
  loading?: boolean;
  rangeControls?: ReactNode;
};

export function TechnicalsPanel({ series, latest, loading, rangeControls }: Props) {
  if (loading) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Technicals</h3>
          {rangeControls}
        </div>
        <div className="chart-skeleton skeleton-block" />
      </div>
    );
  }

  if (!series.length) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Technicals</h3>
          {rangeControls}
        </div>
        <div className="empty-panel">No technicals available.</div>
      </div>
    );
  }

  return (
    <div className="panel fade-in">
      <div className="panel-head">
        <h3>Technicals</h3>
        {latest && (
          <div className="chip-row">
            <span className="chip">RSI {fmtNum(latest.rsi, 1)}</span>
            <span className="chip">MACD {fmtNum(latest.macd)}</span>
            <span className="chip">SMA20 {fmtPrice(latest.sma_20)}</span>
            <span className="chip">SMA50 {fmtPrice(latest.sma_50)}</span>
          </div>
        )}
      </div>
      {rangeControls && (
        <div className="section-range-row">{rangeControls}</div>
      )}
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: "var(--muted)", fontSize: 11 }}
              tickFormatter={(d: string) => d.slice(0, 7)}
              minTickGap={48}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              yAxisId="price"
              tick={{ fill: "var(--muted)", fontSize: 11 }}
              width={52}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "var(--panel)",
                border: "1px solid var(--border)",
                borderRadius: 8,
              }}
            />
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="price"
              stroke="var(--text)"
              dot={false}
              strokeWidth={1.5}
            />
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="sma_20"
              stroke="var(--accent)"
              dot={false}
              strokeWidth={1.25}
            />
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="sma_50"
              stroke="var(--accent-2)"
              dot={false}
              strokeWidth={1.25}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
