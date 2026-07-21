import { type FormEvent, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Brush,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { brushProps, useBrushZoom } from "../hooks/useBrushZoom";
import type { OhlcvBar } from "../types/api";
import { fmtPct, fmtPrice, normalizeTicker } from "../lib/format";

export type CompareSeries = {
  symbol: string;
  bars: OhlcvBar[];
};

type Props = {
  symbol: string;
  bars: OhlcvBar[];
  compare?: CompareSeries[];
  compareTickers?: string[];
  onCompareChange?: (tickers: string[]) => void;
  compareLoading?: boolean;
};

const SERIES_COLORS = [
  "var(--accent)",
  "var(--accent-2)",
  "#c45c26",
  "#2a9d8f",
  "#d4a017",
  "#4a6fa5",
];

const MAX_COMPARE = 5;

function barPrice(b: OhlcvBar): number | null {
  const v = b.adj_close ?? b.close;
  return v == null || Number.isNaN(v) ? null : v;
}

function priceMap(bars: OhlcvBar[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const b of bars) {
    const p = barPrice(b);
    if (p != null) m.set(b.date, p);
  }
  return m;
}

/** Rebase each series to % change from its first price in the window. */
function buildRelativeRows(
  primarySymbol: string,
  primaryBars: OhlcvBar[],
  compare: CompareSeries[],
): { rows: Array<Record<string, string | number | null>>; keys: string[] } {
  const series = [
    { symbol: primarySymbol, bars: primaryBars },
    ...compare.filter((c) => c.symbol !== primarySymbol),
  ];
  const maps = series.map((s) => ({
    symbol: s.symbol,
    prices: priceMap(s.bars),
  }));
  const dates = Array.from(
    new Set(maps.flatMap((s) => Array.from(s.prices.keys()))),
  ).sort();

  const bases = new Map<string, number>();
  for (const s of maps) {
    for (const d of dates) {
      const p = s.prices.get(d);
      if (p != null && p !== 0) {
        bases.set(s.symbol, p);
        break;
      }
    }
  }

  const keys = maps.map((s) => s.symbol);
  const rows = dates.map((date) => {
    const row: Record<string, string | number | null> = { date };
    for (const s of maps) {
      const base = bases.get(s.symbol);
      const px = s.prices.get(date);
      row[s.symbol] =
        base != null && px != null ? (px / base - 1) * 100 : null;
    }
    return row;
  });
  return { rows, keys };
}

function ComparePicker({
  tickers,
  primary,
  onChange,
}: {
  tickers: string[];
  primary: string;
  onChange: (next: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function add(e: FormEvent) {
    e.preventDefault();
    const t = normalizeTicker(draft);
    if (!t || t === primary) {
      setDraft("");
      return;
    }
    if (tickers.includes(t) || tickers.length >= MAX_COMPARE) {
      setDraft("");
      return;
    }
    onChange([...tickers, t]);
    setDraft("");
  }

  return (
    <div className="price-compare-bar">
      <form className="price-compare-form" onSubmit={add}>
        <label className="options-exp-label">
          Compare
          <input
            className="strategy-capital-input mono"
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            placeholder="Add ticker"
            aria-label="Add ticker to compare"
            maxLength={12}
          />
        </label>
        <button
          type="submit"
          className="btn-secondary"
          disabled={tickers.length >= MAX_COMPARE}
        >
          Add
        </button>
      </form>
      <div className="chip-row">
        {tickers.map((t, i) => (
          <button
            key={t}
            type="button"
            className="chip peer-custom-chip mono"
            style={{
              borderColor: SERIES_COLORS[(i + 1) % SERIES_COLORS.length],
            }}
            onClick={() => onChange(tickers.filter((x) => x !== t))}
            title={`Remove ${t}`}
          >
            {t} ×
          </button>
        ))}
      </div>
      {tickers.length > 0 && (
        <p className="muted small">
          Chart shows % change from the start of the selected range (max{" "}
          {MAX_COMPARE} overlays).
        </p>
      )}
    </div>
  );
}

export function PriceChart({
  symbol,
  bars,
  compare = [],
  compareTickers = [],
  onCompareChange,
  compareLoading = false,
}: Props) {
  const comparing = compareTickers.length > 0;

  const { rows: relativeRows, keys: relativeKeys } = useMemo(
    () =>
      comparing
        ? buildRelativeRows(symbol, bars, compare)
        : { rows: [] as Array<Record<string, string | number | null>>, keys: [] },
    [comparing, symbol, bars, compare],
  );

  const absoluteData = useMemo(
    () =>
      bars.map((b) => ({
        date: b.date,
        price: barPrice(b),
      })),
    [bars],
  );

  const chartData = comparing ? relativeRows : absoluteData;
  const seriesKey = comparing
    ? `rel:${symbol}:${compareTickers.join(",")}:${chartData[0]?.date ?? ""}:${chartData.length}`
    : `abs:${symbol}:${absoluteData[0]?.date ?? ""}:${absoluteData.length}`;

  const { viewData, brush, onBrushChange, resetZoom, isZoomed, rangeLabel } =
    useBrushZoom(chartData, seriesKey);

  if (!bars.length) {
    return <div className="empty-panel">No price history for this range.</div>;
  }

  return (
    <div className="chart-wrap fade-in">
      {onCompareChange && (
        <ComparePicker
          tickers={compareTickers}
          primary={symbol}
          onChange={onCompareChange}
        />
      )}

      <div className="chart-zoom-bar">
        <span className="muted small">
          {compareLoading
            ? "Loading compare tickers…"
            : isZoomed
              ? `Zoomed · ${rangeLabel}`
              : comparing
                ? "Relative performance · drag the brush to zoom"
                : "Drag the brush below to zoom a date range"}
        </span>
        {isZoomed && (
          <button type="button" className="btn-text" onClick={resetZoom}>
            Reset zoom
          </button>
        )}
      </div>

      <ResponsiveContainer width="100%" height={360}>
        {comparing ? (
          <LineChart
            data={viewData}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
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
              domain={["auto", "auto"]}
              tick={{ fill: "var(--muted)", fontSize: 11 }}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              width={52}
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
              formatter={(value, name) => [
                `${Number(value) >= 0 ? "+" : ""}${fmtPct(Number(value) / 100)}`,
                String(name),
              ]}
              labelFormatter={(l) => String(l)}
            />
            <Legend />
            {relativeKeys.map((key, i) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                name={key}
                stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                strokeWidth={key === symbol ? 2.5 : 1.75}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        ) : (
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
        )}
      </ResponsiveContainer>

      <ResponsiveContainer width="100%" height={56}>
        <AreaChart
          data={chartData}
          margin={{ top: 4, right: 8, left: 56, bottom: 0 }}
        >
          <XAxis dataKey="date" hide />
          <YAxis hide domain={["auto", "auto"]} />
          <Area
            type="monotone"
            dataKey={comparing ? symbol : "price"}
            stroke="var(--muted)"
            fill="color-mix(in srgb, var(--accent) 15%, transparent)"
            strokeWidth={1}
            isAnimationActive={false}
            dot={false}
            connectNulls
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
  );
}
