import type { MetricsPayload } from "../types/api";
import { fmtNum, fmtPct, fmtPrice } from "../lib/format";

type Props = {
  metrics?: MetricsPayload;
  loading?: boolean;
  benchmark?: string;
};

const ITEMS: Array<{
  key: keyof MetricsPayload;
  label: string;
  format: (v: number | null | undefined) => string;
  vsBenchmark?: boolean;
}> = [
  { key: "last_price", label: "Last", format: fmtPrice },
  { key: "cumulative_return", label: "Total return", format: (v) => fmtPct(v) },
  { key: "sharpe", label: "Sharpe", format: (v) => fmtNum(v) },
  { key: "sortino", label: "Sortino", format: (v) => fmtNum(v) },
  {
    key: "realized_volatility_ann",
    label: "Vol (ann.)",
    format: (v) => fmtPct(v),
  },
  { key: "max_drawdown", label: "Max DD", format: (v) => fmtPct(v) },
  { key: "beta", label: "Beta", format: (v) => fmtNum(v), vsBenchmark: true },
  {
    key: "correlation_to_benchmark",
    label: "Corr",
    format: (v) => fmtNum(v),
    vsBenchmark: true,
  },
];

export function MetricStrip({ metrics, loading, benchmark }: Props) {
  const bench = metrics?.benchmark ?? benchmark ?? "SPY";

  if (loading) {
    return (
      <div className="metric-strip">
        {ITEMS.map((item) => (
          <div key={item.key} className="metric-cell skeleton-block">
            <span className="metric-label">{item.label}</span>
            <span className="metric-value">···</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="metric-strip">
      {ITEMS.map((item) => {
        const raw = metrics?.[item.key];
        const num = typeof raw === "number" ? raw : null;
        const negative = typeof num === "number" && num < 0;
        return (
          <div
            key={item.key}
            className={`metric-cell${item.vsBenchmark ? " metric-cell-bench" : ""}`}
            title={
              item.vsBenchmark
                ? `Measured against benchmark ${bench} over the selected range`
                : undefined
            }
          >
            <span className="metric-label">
              {item.label}
              {item.vsBenchmark && (
                <span className="bench-tag mono"> vs {bench}</span>
              )}
            </span>
            <span className={`metric-value mono ${negative ? "neg" : ""}`}>
              {item.format(num)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
