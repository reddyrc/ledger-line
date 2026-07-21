import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MacroObservation } from "../types/api";

type Props = {
  observations: MacroObservation[];
  seriesId: string;
};

export function MacroChart({ observations, seriesId }: Props) {
  const data = observations.map((o) => ({ date: o.date, value: o.value }));
  if (!data.length) {
    return <div className="empty-panel">No observations for {seriesId}.</div>;
  }

  return (
    <div className="chart-wrap fade-in">
      <ResponsiveContainer width="100%" height={360}>
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="macroFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent-2)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="var(--accent-2)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "var(--muted)", fontSize: 11 }}
            tickFormatter={(d: string) => d.slice(0, 7)}
            minTickGap={56}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "var(--muted)", fontSize: 11 }}
            width={48}
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
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--accent-2)"
            fill="url(#macroFill)"
            strokeWidth={2}
            isAnimationActive
            animationDuration={700}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
