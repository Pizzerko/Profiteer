import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HistoryPoint } from "../api/types";
import { money } from "../utils/format";

export default function StockChart({
  points,
  up,
}: {
  points: HistoryPoint[];
  up: boolean;
}) {
  if (!points.length)
    return (
      <div className="flex h-64 items-center justify-center text-slate-500">
        No price history available.
      </div>
    );

  const color = up ? "#34d399" : "#f87171";
  const data = points.map((p) => ({
    date: p.date,
    close: p.close,
    label: new Date(p.date).toLocaleDateString(),
  }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="label"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            minTickGap={40}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            width={60}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => money(v as number)}
          />
          <Tooltip
            contentStyle={{
              background: "#0f172a",
              border: "1px solid #334155",
              borderRadius: 8,
              color: "#e2e8f0",
            }}
            formatter={(v) => [money(v as number), "Close"]}
          />
          <Area
            type="monotone"
            dataKey="close"
            stroke={color}
            strokeWidth={2}
            fill="url(#fill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
