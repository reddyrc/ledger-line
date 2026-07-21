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

import { useOptionsIvHistory } from "../api/hooks";
import { fmtNum, fmtPct } from "../lib/format";
import { OPTION_TIPS } from "../lib/optionsGlossary";
import type { EarningsCrushEvent, IvHistoryPoint } from "../types/api";

type Props = {
  symbol: string;
  /** Optional pin to the page's selected expiration */
  expiration?: string;
};

function pctVol(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function EarningsCrushTable({ rows }: { rows: EarningsCrushEvent[] }) {
  if (!rows.length) {
    return (
      <p className="muted small">
        No earnings events in range yet — crush/move stats fill in as IV
        snapshots accumulate around reports.
      </p>
    );
  }
  return (
    <div className="table-scroll">
      <table className="data-table screener-table">
        <thead>
          <tr>
            <th>Date</th>
            <th title={OPTION_TIPS.earningsActualMove}>Actual</th>
            <th title={OPTION_TIPS.earningsExpectedMove}>Exp 1d</th>
            <th title="Whether |actual move| met or exceeded the 1-session IV-implied move.">
              Hit?
            </th>
            <th title={OPTION_TIPS.atmIv}>IV pre</th>
            <th title={OPTION_TIPS.atmIv}>IV post</th>
            <th title={OPTION_TIPS.earningsCrush}>Crush</th>
            <th title="EPS surprise vs estimate.">Surprise</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.report_date}>
              <td className="mono">{r.report_date}</td>
              <td className="mono">{fmtPct(r.actual_move_pct)}</td>
              <td className="mono">
                {r.expected_move_pct == null
                  ? "—"
                  : `±${fmtPct(r.expected_move_pct)}`}
              </td>
              <td className="mono">
                {r.hit_expected == null ? "—" : r.hit_expected ? "yes" : "no"}
              </td>
              <td className="mono">{pctVol(r.iv_before)}</td>
              <td className="mono">{pctVol(r.iv_after)}</td>
              <td className="mono">
                {r.iv_crush == null
                  ? "—"
                  : `${r.iv_crush > 0 ? "+" : ""}${(r.iv_crush * 100).toFixed(1)}pt`}
              </td>
              <td className="mono">{fmtPct(r.surprise_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function IvHistoryPanel({ symbol, expiration }: Props) {
  const hist = useOptionsIvHistory(symbol, {});
  const data = hist.data;
  const series = data?.series ?? [];
  const latest = data?.latest;
  const hasIv = series.some((p) => p.atm_iv != null);
  const hasHv = series.some((p) => p.hv_20 != null);
  const hasPcr = series.some((p) => p.pcr_oi != null);

  const chartData = series.map((p: IvHistoryPoint) => ({
    date: p.date,
    atm_iv: p.atm_iv == null ? null : p.atm_iv * 100,
    hv_20: p.hv_20 == null ? null : p.hv_20 * 100,
    hv_10: p.hv_10 == null ? null : p.hv_10 * 100,
    pcr_oi: p.pcr_oi,
    total_oi: p.total_oi,
  }));

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>IV vs HV</h3>
        <p className="muted small panel-sub">
          ATM implied vs 20-day realized — PCR/OI from chain snapshots
          {expiration ? ` · page exp ${expiration}` : ""}
        </p>
      </div>

      {hist.isLoading && <div className="chart-skeleton skeleton-block" />}

      {data && (
        <div className="chip-row valuation-stats">
          <span className="chip" data-tip={OPTION_TIPS.atmIv}>
            ATM IV {pctVol(latest?.atm_iv)}
          </span>
          <span className="chip" data-tip={OPTION_TIPS.hv20}>
            HV 20d {pctVol(latest?.hv_20)}
          </span>
          <span className="chip" data-tip={OPTION_TIPS.ivHvPremium}>
            IV − HV{" "}
            {latest?.iv_hv_premium == null
              ? "—"
              : `${latest.iv_hv_premium > 0 ? "+" : ""}${(latest.iv_hv_premium * 100).toFixed(1)}pt`}
          </span>
          <span className="chip" data-tip={OPTION_TIPS.pcrOi}>
            PCR OI {fmtNum(latest?.pcr_oi, 2)}
          </span>
          <span className="chip" data-tip={OPTION_TIPS.totalOi}>
            Total OI {fmtNum(latest?.total_oi, 0)}
          </span>
          <span
            className="chip"
            data-tip={OPTION_TIPS.ivRank}
          >
            {data.building_history
              ? `Building IV history (${data.sample_count})`
              : `${data.sample_count} IV samples`}
          </span>
        </div>
      )}

      {!hist.isLoading && !hasIv && !hasHv && (
        <p className="muted">
          No IV snapshots yet. Open the chain (or run the IV snapshot job) to
          start collecting history; HV appears once price history is cached.
        </p>
      )}

      {(hasIv || hasHv) && (
        <div className="options-premium-chart">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fill: "var(--muted)", fontSize: 11 }}
                tickFormatter={(d: string) => d.slice(5)}
                minTickGap={40}
              />
              <YAxis
                yAxisId="vol"
                tick={{ fill: "var(--muted)", fontSize: 11 }}
                width={42}
                tickFormatter={(v) => `${Number(v).toFixed(0)}%`}
              />
              {hasPcr && (
                <YAxis
                  yAxisId="pcr"
                  orientation="right"
                  tick={{ fill: "var(--muted)", fontSize: 11 }}
                  width={36}
                />
              )}
              <Tooltip
                contentStyle={{
                  background: "var(--panel)",
                  border: "1px solid var(--border)",
                }}
                formatter={(value, name) => {
                  const n = Number(value);
                  if (name === "pcr_oi") return [fmtNum(n, 2), "PCR OI"];
                  if (name === "total_oi") return [fmtNum(n, 0), "Total OI"];
                  return [`${n.toFixed(1)}%`, String(name).toUpperCase()];
                }}
              />
              <Legend />
              {hasIv && (
                <Line
                  yAxisId="vol"
                  type="monotone"
                  dataKey="atm_iv"
                  name="ATM IV"
                  stroke="var(--accent)"
                  dot={false}
                  strokeWidth={2}
                  connectNulls
                />
              )}
              {hasHv && (
                <Line
                  yAxisId="vol"
                  type="monotone"
                  dataKey="hv_20"
                  name="HV 20d"
                  stroke="var(--accent-2)"
                  dot={false}
                  strokeWidth={2}
                  strokeDasharray="4 3"
                  connectNulls
                />
              )}
              {hasPcr && (
                <Line
                  yAxisId="pcr"
                  type="monotone"
                  dataKey="pcr_oi"
                  name="PCR OI"
                  stroke="var(--muted)"
                  dot={false}
                  strokeWidth={1.5}
                  connectNulls
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="panel-head" style={{ marginTop: "1rem" }}>
        <h3>Earnings moves</h3>
        <p className="muted small panel-sub">
          Actual close-to-close vs 1-session IV-implied move; IV crush when
          pre/post snapshots exist
        </p>
      </div>
      <EarningsCrushTable rows={data?.earnings_history ?? []} />

      {data?.disclaimer && <p className="disclaimer">{data.disclaimer}</p>}
    </div>
  );
}
