import { useMemo, type ReactNode } from "react";
import {
  Area,
  AreaChart,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { brushProps, useBrushZoom } from "../hooks/useBrushZoom";
import type { ShortInterestResponse } from "../types/api";
import { fmtCompact, fmtNum, fmtPct } from "../lib/format";

type Props = {
  data?: ShortInterestResponse;
  loading?: boolean;
  rangeControls?: ReactNode;
};

export function ShortInterestPanel({ data, loading, rangeControls }: Props) {
  const chartData = useMemo(
    () =>
      (data?.series ?? []).map((p) => ({
        date: p.date,
        shares_short: p.shares_short,
        days_to_cover: p.days_to_cover,
        change_pct: p.change_pct,
      })),
    [data?.series],
  );

  const seriesKey = `${chartData[0]?.date ?? ""}:${chartData.length}`;
  const { viewData, brush, onBrushChange, resetZoom, isZoomed, rangeLabel } =
    useBrushZoom(chartData, seriesKey);

  const latest = data?.latest;

  if (loading) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Short interest</h3>
          {rangeControls}
        </div>
        <div className="chart-skeleton skeleton-block" />
      </div>
    );
  }

  if (data?.error && !chartData.length) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Short interest</h3>
          {rangeControls}
        </div>
        <p className="muted">{data.error}</p>
      </div>
    );
  }

  if (!chartData.length) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Short interest</h3>
          {rangeControls}
        </div>
        <div className="empty-panel">
          No FINRA short interest points for this range.
        </div>
      </div>
    );
  }

  return (
    <div className="panel fade-in">
      <div className="panel-head">
        <h3>Short interest</h3>
        {rangeControls}
      </div>

      {latest && (
        <div className="chip-row valuation-stats">
          <span className="chip">
            Shares {fmtCompact(latest.shares_short)}
          </span>
          <span className="chip">
            Days to cover {fmtNum(latest.days_to_cover, 1)}
          </span>
          <span className="chip">
            Δ prior{" "}
            {latest.change_pct == null
              ? "—"
              : `${latest.change_pct > 0 ? "+" : ""}${fmtNum(latest.change_pct, 1)}%`}
          </span>
          {latest.short_pct_float != null && (
            <span className="chip">
              Short % float {fmtPct(latest.short_pct_float, 1)}
            </span>
          )}
          <span className="chip muted-chip">
            Settled {latest.settlement_date}
          </span>
        </div>
      )}

      <div className="chart-zoom-bar">
        <span className="muted small">
          {isZoomed
            ? `Zoomed · ${rangeLabel}`
            : "Biweekly FINRA settlements · drag brush to zoom"}
        </span>
        {isZoomed && (
          <button type="button" className="btn-text" onClick={resetZoom}>
            Reset zoom
          </button>
        )}
      </div>

      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart
            data={viewData}
            margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
          >
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
              yAxisId="shares"
              tick={{ fill: "var(--muted)", fontSize: 11 }}
              width={56}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => fmtCompact(v)}
            />
            <YAxis
              yAxisId="dtc"
              orientation="right"
              tick={{ fill: "var(--muted)", fontSize: 11 }}
              width={40}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => fmtNum(v, 1)}
            />
            <Tooltip
              contentStyle={{
                background: "var(--panel)",
                border: "1px solid var(--border)",
                borderRadius: 8,
              }}
              formatter={(value, name) => {
                const n = Number(value);
                if (name === "shares_short") {
                  return [fmtCompact(n), "Shares short"];
                }
                if (name === "days_to_cover") {
                  return [fmtNum(n, 2), "Days to cover"];
                }
                return [fmtNum(n), String(name)];
              }}
              labelFormatter={(l) => String(l)}
            />
            <Area
              yAxisId="shares"
              type="monotone"
              dataKey="shares_short"
              stroke="var(--accent)"
              fill="color-mix(in srgb, var(--accent) 18%, transparent)"
              strokeWidth={1.75}
              isAnimationActive={false}
            />
            <Line
              yAxisId="dtc"
              type="monotone"
              dataKey="days_to_cover"
              stroke="var(--accent-2)"
              strokeWidth={1.5}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>

        <ResponsiveContainer width="100%" height={56}>
          <AreaChart
            data={chartData}
            margin={{ top: 4, right: 12, left: 56, bottom: 0 }}
          >
            <XAxis dataKey="date" hide />
            <YAxis hide domain={["auto", "auto"]} />
            <Area
              type="monotone"
              dataKey="shares_short"
              stroke="var(--muted)"
              fill="color-mix(in srgb, var(--accent) 15%, transparent)"
              strokeWidth={1}
              isAnimationActive={false}
              dot={false}
            />
            <Brush
              {...brushProps}
              dataKey="date"
              startIndex={brush?.startIndex ?? 0}
              endIndex={brush?.endIndex ?? Math.max(0, chartData.length - 1)}
              onChange={onBrushChange}
              tickFormatter={(d: string) => String(d).slice(0, 7)}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {data?.disclaimer && <p className="disclaimer">{data.disclaimer}</p>}
    </div>
  );
}
