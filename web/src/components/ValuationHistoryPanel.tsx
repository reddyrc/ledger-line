import { useMemo, useState, type ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { brushProps, useBrushZoom } from "../hooks/useBrushZoom";
import type {
  EarningsPoint,
  ValuationHistoryResponse,
  ValuationMetricKey,
} from "../types/api";
import { fmtCompact, fmtNum, fmtPct } from "../lib/format";

type Props = {
  data?: ValuationHistoryResponse;
  loading?: boolean;
  rangeControls?: ReactNode;
};

const METRICS: Array<{ key: ValuationMetricKey; label: string }> = [
  { key: "pe", label: "P/E" },
  { key: "pb", label: "P/B" },
  { key: "ps", label: "P/S" },
  { key: "market_cap", label: "Mkt cap" },
];

const POST_EARNINGS_HORIZONS: Array<{
  key: "ret_1d" | "ret_3d" | "ret_5d" | "ret_1m";
  label: string;
}> = [
  { key: "ret_1d", label: "+1d" },
  { key: "ret_3d", label: "+3d" },
  { key: "ret_5d", label: "+5d" },
  { key: "ret_1m", label: "+1mo" },
];

function formatMetric(key: ValuationMetricKey, v: number | null | undefined): string {
  if (key === "market_cap") return fmtCompact(v);
  return fmtNum(v);
}

function retClass(v: number | null | undefined): string {
  if (v == null) return "";
  return v > 0 ? "pos" : v < 0 ? "neg" : "";
}

/** Friendly names for the index proxy ETFs used in post-earnings returns. */
const INDEX_LABELS: Record<string, { label: string; title: string }> = {
  SPY: { label: "S&P", title: "S&P 500 (SPY)" },
  DIA: { label: "Dow", title: "Dow Jones Industrial Average (DIA)" },
  QQQ: { label: "Nasdaq", title: "Nasdaq-100 (QQQ)" },
};

function EarningsTooltip({
  active,
  payload,
  label,
  symbol,
  benchmarks,
}: {
  active?: boolean;
  payload?: Array<{ payload?: EarningsPoint }>;
  label?: string | number;
  symbol?: string;
  benchmarks?: string[];
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;

  const bits = [String(label ?? row.date)];
  if (row.form) bits.push(row.form);
  if (row.fp) bits.push(row.fp);

  const reportNote = row.report_date
    ? `After earnings report (${row.report_date})`
    : "Earnings report date unavailable";

  const indexReturns = row.index_returns ?? {};
  const indexSyms = (benchmarks ?? Object.keys(indexReturns)).filter((sym) =>
    POST_EARNINGS_HORIZONS.some((h) => indexReturns[sym]?.[h.key] != null),
  );
  const cols = { gridTemplateColumns: `2.4rem repeat(${indexSyms.length + 1}, 1fr)` };

  return (
    <div className="earnings-tooltip">
      <div className="earnings-tooltip-head">{bits.join(" · ")}</div>
      <div className="earnings-tooltip-eps">
        EPS <span className="mono">{fmtNum(row.eps, 3)}</span>
      </div>
      <div className="earnings-tooltip-sub muted small">{reportNote}</div>
      <div className="earnings-tooltip-returns">
        {indexSyms.length > 0 && (
          <div className="earnings-tooltip-row earnings-tooltip-cols" style={cols}>
            <span />
            <span className="mono muted">{symbol ?? "Stock"}</span>
            {indexSyms.map((sym) => (
              <span
                key={sym}
                className="mono muted"
                title={INDEX_LABELS[sym]?.title ?? sym}
              >
                {INDEX_LABELS[sym]?.label ?? sym}
              </span>
            ))}
          </div>
        )}
        {POST_EARNINGS_HORIZONS.map((h) => {
          const v = row[h.key];
          if (indexSyms.length === 0) {
            return (
              <div key={h.key} className="earnings-tooltip-row">
                <span>{h.label}</span>
                <span className={`mono ${retClass(v)}`}>{fmtPct(v, 1)}</span>
              </div>
            );
          }
          return (
            <div
              key={h.key}
              className="earnings-tooltip-row earnings-tooltip-cols"
              style={cols}
            >
              <span>{h.label}</span>
              <span className={`mono ${retClass(v)}`}>{fmtPct(v, 1)}</span>
              {indexSyms.map((sym) => {
                const bv = indexReturns[sym]?.[h.key];
                return (
                  <span key={sym} className={`mono ${retClass(bv)}`}>
                    {fmtPct(bv, 1)}
                  </span>
                );
              })}
            </div>
          );
        })}
      </div>
      {!row.report_date && (
        <div className="earnings-tooltip-note muted small">
          Returns are not calculated from the fiscal period end. Refresh to
          retrieve the actual earnings report date.
        </div>
      )}
    </div>
  );
}

function localStats(values: Array<number | null | undefined>) {
  const nums = values.filter((v): v is number => v != null && Number.isFinite(v));
  if (!nums.length) return { avg: null as number | null, median: null as number | null };
  const sorted = [...nums].sort((a, b) => a - b);
  const avg = nums.reduce((a, b) => a + b, 0) / nums.length;
  const mid = Math.floor(sorted.length / 2);
  const median =
    sorted.length % 2 === 0
      ? (sorted[mid - 1] + sorted[mid]) / 2
      : sorted[mid];
  return { avg, median };
}

export function ValuationHistoryPanel({ data, loading, rangeControls }: Props) {
  const [metric, setMetric] = useState<ValuationMetricKey>("pe");

  const chartData = useMemo(() => {
    if (!data?.series?.length) return [];
    const series = data.series;
    const step = Math.max(1, Math.ceil(series.length / 500));
    return series
      .filter((_, i) => i % step === 0 || i === series.length - 1)
      .map((p) => ({
        date: p.date,
        value: p[metric],
      }));
  }, [data?.series, metric]);

  const seriesKey = `${metric}:${chartData[0]?.date ?? ""}:${chartData.length}`;
  const { viewData, brush, onBrushChange, resetZoom, isZoomed, rangeLabel } =
    useBrushZoom(chartData, seriesKey);

  const zoomStats = useMemo(
    () => localStats(viewData.map((d) => d.value)),
    [viewData],
  );

  const stats = data?.summary?.[metric];
  const displayAvg = isZoomed ? zoomStats.avg : stats?.avg ?? null;
  const displayMedian = isZoomed ? zoomStats.median : stats?.median ?? null;
  const earnings = data?.earnings ?? [];

  if (loading) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Valuation history</h3>
          {rangeControls}
        </div>
        <div className="chart-skeleton skeleton-block" />
      </div>
    );
  }

  if (!data || data.error) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Valuation history</h3>
          {rangeControls}
        </div>
        <p className="muted">{data?.error ?? "No valuation history available."}</p>
      </div>
    );
  }

  if (!data.series.length) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Valuation history</h3>
          {rangeControls}
        </div>
        <div className="empty-panel">No valuation points for this range.</div>
      </div>
    );
  }

  return (
    <div className="panel fade-in valuation-panel">
      <div className="panel-head">
        <h3>Valuation history</h3>
        <div className="segmented" role="group" aria-label="Valuation metric">
          {METRICS.map((m) => (
            <button
              key={m.key}
              type="button"
              className={metric === m.key ? "active" : ""}
              onClick={() => setMetric(m.key)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {rangeControls && (
        <div className="section-range-row">{rangeControls}</div>
      )}

      <div className="chip-row valuation-stats">
        <span className="chip">
          Latest {formatMetric(metric, stats?.latest)}
        </span>
        <span className="chip chip-avg">
          {isZoomed ? "Zoom avg" : "Avg"}{" "}
          {formatMetric(metric, displayAvg)}
        </span>
        <span className="chip chip-median">
          {isZoomed ? "Zoom med" : "Median"}{" "}
          {formatMetric(metric, displayMedian)}
        </span>
        <span className="chip muted-chip">
          {(isZoomed ? viewData.length : stats?.count)?.toLocaleString() ?? 0}{" "}
          pts
        </span>
      </div>

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

      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart
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
              domain={["auto", "auto"]}
              tick={{ fill: "var(--muted)", fontSize: 11 }}
              width={56}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) =>
                metric === "market_cap" ? fmtCompact(v) : fmtNum(v, 1)
              }
            />
            <Tooltip
              contentStyle={{
                background: "var(--panel)",
                border: "1px solid var(--border)",
                borderRadius: 8,
              }}
              formatter={(value) => [
                formatMetric(metric, Number(value)),
                METRICS.find((m) => m.key === metric)?.label ?? metric,
              ]}
              labelFormatter={(l) => String(l)}
            />
            {displayAvg != null && (
              <ReferenceLine
                y={displayAvg}
                stroke="var(--accent)"
                strokeDasharray="6 4"
                strokeWidth={1.25}
                label={{
                  value: "avg",
                  fill: "var(--accent)",
                  fontSize: 11,
                  position: "insideTopRight",
                }}
              />
            )}
            {displayMedian != null && (
              <ReferenceLine
                y={displayMedian}
                stroke="var(--accent-2)"
                strokeDasharray="2 4"
                strokeWidth={1.25}
                label={{
                  value: "med",
                  fill: "var(--accent-2)",
                  fontSize: 11,
                  position: "insideBottomRight",
                }}
              />
            )}
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--text)"
              dot={false}
              strokeWidth={1.6}
              connectNulls
              isAnimationActive={false}
            />
          </LineChart>
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
              dataKey="value"
              stroke="var(--muted)"
              fill="color-mix(in srgb, var(--accent) 15%, transparent)"
              strokeWidth={1}
              connectNulls
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

      <div className="earnings-block">
        <div className="panel-head">
          <h4>Earnings (EPS)</h4>
          <span className="muted small">
            Diluted EPS · hover a bar for post-earnings returns
            {(data.benchmarks?.length ?? 0) > 0 ? " (vs S&P, Dow, Nasdaq)" : ""}
          </span>
        </div>
        {earnings.length === 0 ? (
          <div className="empty-panel">No earnings points in range.</div>
        ) : (
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={160}>
              <BarChart
                data={earnings.map((e) => ({
                  date: e.date,
                  eps: e.eps,
                  form: e.form,
                  fp: e.fp,
                  fy: e.fy,
                  filed: e.filed,
                  report_datetime: e.report_datetime,
                  report_date: e.report_date,
                  anchor: e.anchor,
                  ret_1d: e.ret_1d,
                  ret_3d: e.ret_3d,
                  ret_5d: e.ret_5d,
                  ret_1m: e.ret_1m,
                  index_returns: e.index_returns,
                }))}
                margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
              >
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "var(--muted)", fontSize: 11 }}
                  tickFormatter={(d: string) => d.slice(0, 7)}
                  minTickGap={40}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: "var(--muted)", fontSize: 11 }}
                  width={44}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v: number) => fmtNum(v, 2)}
                />
                <Tooltip
                  content={
                    <EarningsTooltip
                      symbol={data.symbol}
                      benchmarks={data.benchmarks}
                    />
                  }
                  cursor={{ fill: "color-mix(in srgb, var(--accent-2) 12%, transparent)" }}
                />
                <Bar
                  dataKey="eps"
                  fill="var(--accent-2)"
                  opacity={0.85}
                  radius={[3, 3, 0, 0]}
                  isAnimationActive
                  animationDuration={500}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {data.disclaimer && <p className="disclaimer">{data.disclaimer}</p>}
    </div>
  );
}
