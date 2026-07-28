import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { money, signedMoney } from "../utils/format";

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const UP = "#34d399";
const DOWN = "#f87171";

export interface DailyPnL {
  /** Day, "YYYY-MM-DD". */
  date: string;
  /** Total realized P/L locked in that day. */
  pnl: number;
}

function parseDay(iso: string) {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) {
    const d = new Date(iso);
    return { y: d.getFullYear(), mo: d.getMonth(), d: d.getDate() };
  }
  return { y: +m[1], mo: +m[2] - 1, d: +m[3] };
}

/**
 * One bar per day that had a realized gain or loss: green above the zero line
 * for a profitable day, red extending below it for a losing day. Days with no
 * sell simply have no bar — this is a chart of realized P/L, not portfolio value.
 */
export default function RealizedPnLChart({
  days,
  coarse,
}: {
  days: DailyPnL[];
  coarse: boolean;
}) {
  if (!days.length)
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-500">
        No realized profit or loss in this range yet.
      </div>
    );

  const bars = days.map((d, i) => ({ i, pnl: d.pnl, w: parseDay(d.date) }));
  // Aim for ~6 axis labels regardless of how many bars there are.
  const interval = Math.max(0, Math.ceil(bars.length / 6) - 1);

  const xTickFormatter = (v: number): string => {
    const b = bars[v];
    if (!b) return "";
    return coarse ? `${MONTHS[b.w.mo]} ${b.w.y}` : `${MONTHS[b.w.mo]} ${b.w.d}`;
  };

  const tooltipLabelFormatter = (v: number): string => {
    const b = bars[v];
    if (!b) return "";
    return `${MONTHS[b.w.mo]} ${b.w.d}, ${b.w.y}`;
  };

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={bars} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <XAxis
            dataKey="i"
            type="category"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            interval={interval}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => xTickFormatter(v as number)}
          />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            width={60}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => money(v as number)}
          />
          <Tooltip
            cursor={{ fill: "rgba(148,163,184,0.1)" }}
            contentStyle={{
              background: "#0f172a",
              border: "1px solid #334155",
              borderRadius: 8,
              color: "#e2e8f0",
            }}
            labelFormatter={(v) => tooltipLabelFormatter(v as number)}
            formatter={(v) => [signedMoney(v as number), "Realized P/L"]}
          />
          <ReferenceLine y={0} stroke="#475569" />
          <Bar dataKey="pnl" isAnimationActive={false} radius={[2, 2, 0, 0]}>
            {bars.map((b) => (
              <Cell key={b.i} fill={b.pnl >= 0 ? UP : DOWN} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
