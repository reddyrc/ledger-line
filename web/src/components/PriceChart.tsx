import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Brush,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { brushProps, useBrushZoom } from "../hooks/useBrushZoom";
import type { OhlcvBar } from "../types/api";
import { fmtPrice } from "../lib/format";

type Props = {
  bars: OhlcvBar[];
};

export function PriceChart({ bars }: Props) {
  const data = useMemo(
    () =>
      bars.map((b) => ({
        date: b.date,
        price: b.adj_close ?? b.close,
      })),
    [bars],
  );

  const seriesKey = `${data[0]?.date ?? ""}:${data[data.length - 1]?.date ?? ""}:${data.length}`;
  const { viewData, brush, onBrushChange, resetZoom, isZoomed, rangeLabel } =
    useBrushZoom(data, seriesKey);

  if (!data.length) {
    return <div className="empty-panel">No price history for this range.</div>;
  }

  return (
    <div className="chart-wrap fade-in">
      <div className="chart-zoom-bar">
        <span className="muted small">
          {isZoomed
            ? `Zoomed · ${rangeLabel}`
            : "Drag the brush below to zoom a date range"}
        </span>
        {isZoomed && (
          <button type="button" className="btn-text" onClick={resetZoom}>
            Reset zoom
          </button>
        )}
      </div>
      <ResponsiveContainer width="100%" height={360}>
        <AreaChart
          data={viewData}
          margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
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
            domain={["auto", "auto"]}
            tick={{ fill: "var(--muted)", fontSize: 11 }}
            tickFormatter={(v: number) => fmtPrice(v)}
            width={56}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "var(--panel)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              color: "var(--text)",
            }}
            formatter={(value) => [fmtPrice(Number(value)), "Adj close"]}
            labelFormatter={(l) => String(l)}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke="var(--accent)"
            fill="url(#priceFill)"
            strokeWidth={2}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Full-series brush navigator */}
      <ResponsiveContainer width="100%" height={56}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: 56, bottom: 0 }}>
          <XAxis dataKey="date" hide />
          <YAxis hide domain={["auto", "auto"]} />
          <Area
            type="monotone"
            dataKey="price"
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
            endIndex={brush?.endIndex ?? Math.max(0, data.length - 1)}
            onChange={onBrushChange}
            tickFormatter={(d: string) => String(d).slice(0, 7)}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
