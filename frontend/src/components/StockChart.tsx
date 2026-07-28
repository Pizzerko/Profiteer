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

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/**
 * Pull the wall-clock components straight out of the ISO string
 * (e.g. "2026-07-21T09:30:00-04:00"). We intentionally ignore the timezone
 * offset and use the exchange-local wall clock, so intraday times line up with
 * US market hours regardless of the viewer's browser timezone.
 */
function parseWall(iso: string) {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) {
    const d = new Date(iso);
    return { y: d.getFullYear(), mo: d.getMonth(), d: d.getDate(), h: d.getHours(), mi: d.getMinutes() };
  }
  return { y: +m[1], mo: +m[2] - 1, d: +m[3], h: +m[4], mi: +m[5] };
}

function timeLabel(h: number, mi: number): string {
  const ampm = h < 12 ? "AM" : "PM";
  let hr = h % 12;
  if (hr === 0) hr = 12;
  return mi === 0 ? `${hr} ${ampm}` : `${hr}:${String(mi).padStart(2, "0")} ${ampm}`;
}

export default function StockChart({
  points,
  up,
  range,
  seriesLabel = "Price",
}: {
  points: HistoryPoint[];
  up: boolean;
  range: string;
  seriesLabel?: string;
}) {
  if (!points.length)
    return (
      <div className="flex h-64 items-center justify-center text-slate-500">
        No price history available.
      </div>
    );

  const color = up ? "#34d399" : "#f87171";
  const singleDay = range === "1d";
  const showTime = range === "1d" || range === "5d";

  // For 1d, x is minutes-since-midnight (exchange local) so the axis spans the
  // full day; otherwise x is the array index so weekend/overnight gaps collapse.
  const data = points.map((p, i) => {
    const w = parseWall(p.date);
    return { i, close: p.close, w, x: singleDay ? w.h * 60 + w.mi : i };
  });

  let xDomain: [number, number];
  let xTicks: number[];

  if (singleDay) {
    // US extended session: 4:00 AM pre-market open → 8:00 PM after-hours close
    // (no overnight trading), so clamp the axis to that window.
    xDomain = [240, 1200];
    xTicks = [240, 480, 720, 960, 1200]; // 4AM, 8AM, 12PM, 4PM, 8PM
  } else {
    xDomain = [0, data.length - 1];
    if (range === "5d") {
      // One tick at the first bar of each distinct trading day.
      const seen = new Set<string>();
      xTicks = [];
      for (const d of data) {
        const key = `${d.w.y}-${d.w.mo}-${d.w.d}`;
        if (!seen.has(key)) {
          seen.add(key);
          xTicks.push(d.i);
        }
      }
    } else {
      // ~6 evenly spaced ticks across the range.
      const n = data.length;
      const count = Math.min(6, n);
      xTicks = Array.from({ length: count }, (_, k) =>
        Math.round((k * (n - 1)) / Math.max(1, count - 1)),
      );
    }
  }

  const xTickFormatter = (v: number): string => {
    if (singleDay) return timeLabel(Math.floor(v / 60), v % 60);
    const d = data[Math.round(v)];
    if (!d) return "";
    // Long, coarse ranges are sampled monthly — label them Month Year, not Month Day.
    const coarse = range === "5y" || range === "all" || range === "max";
    return coarse ? `${MONTHS[d.w.mo]} ${d.w.y}` : `${MONTHS[d.w.mo]} ${d.w.d}`;
  };

  const tooltipLabelFormatter = (v: number): string => {
    if (singleDay) return timeLabel(Math.floor(v / 60), v % 60);
    const d = data[Math.round(v)];
    if (!d) return "";
    const { w } = d;
    const date = `${MONTHS[w.mo]} ${w.d}, ${w.y}`;
    return showTime ? `${date} ${timeLabel(w.h, w.mi)}` : date;
  };

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
            dataKey="x"
            type="number"
            domain={xDomain}
            ticks={xTicks}
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            minTickGap={20}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => xTickFormatter(v as number)}
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
            labelFormatter={(v) => tooltipLabelFormatter(v as number)}
            formatter={(v) => [money(v as number), seriesLabel]}
          />
          <Area
            type="monotone"
            dataKey="close"
            stroke={color}
            strokeWidth={2}
            fill="url(#fill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
