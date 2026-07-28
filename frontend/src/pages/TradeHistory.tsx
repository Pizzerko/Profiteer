import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import RealizedPnLChart, { type DailyPnL } from "../components/RealizedPnLChart";
import TradesTable from "../components/TradesTable";
import type { Trade } from "../api/types";
import { plClass, signedMoney } from "../utils/format";

// Range key -> button label, in display order. `days` is the lookback window in
// calendar days; null means "all time", "ytd" is special-cased.
const RANGES: { key: string; label: string; days: number | null }[] = [
  { key: "1w", label: "1W", days: 7 },
  { key: "1mo", label: "1M", days: 30 },
  { key: "3mo", label: "3M", days: 90 },
  { key: "ytd", label: "YTD", days: null },
  { key: "1y", label: "1Y", days: 365 },
  { key: "all", label: "All", days: null },
];

// Local "YYYY-MM-DD" for a Date (avoids UTC shifting the calendar day).
function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

// Every weekday (Mon–Fri) from start to end, inclusive. Markets are closed on
// weekends, so those never carry realized P/L — we skip them to keep the axis clean.
function weekdaysBetween(startISO: string, endISO: string): string[] {
  const out: string[] = [];
  const cur = new Date(`${startISO}T00:00:00`);
  const end = new Date(`${endISO}T00:00:00`);
  while (cur <= end) {
    const dow = cur.getDay();
    if (dow !== 0 && dow !== 6) out.push(isoOf(cur));
    cur.setDate(cur.getDate() + 1);
  }
  return out;
}

export default function TradeHistory() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [range, setRange] = useState("3mo");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<Trade[]>("/portfolio/trades")
      .then((r) => setTrades(r.data))
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  // A continuous weekday axis over the selected range, with each day's realized P/L
  // (0 where there was no sell). Only sells carry realized_pl, so gaps show as no bar.
  const days = useMemo<DailyPnL[]>(() => {
    const byDay = new Map<string, number>();
    for (const t of trades) {
      if (t.realized_pl == null) continue;
      const day = t.executed_at.slice(0, 10);
      byDay.set(day, (byDay.get(day) ?? 0) + t.realized_pl);
    }
    if (byDay.size === 0) return []; // nothing ever realized -> empty-state message

    const end = isoOf(new Date());
    let start: string;
    if (range === "ytd") {
      start = `${new Date().getFullYear()}-01-01`;
    } else if (range === "all") {
      start = [...byDay.keys()].sort()[0]; // first day with realized activity
    } else {
      const win = RANGES.find((r) => r.key === range)?.days ?? 0;
      const d = new Date();
      d.setDate(d.getDate() - win);
      start = isoOf(d);
    }
    if (start > end) start = end;

    return weekdaysBetween(start, end).map((day) => ({
      date: day,
      pnl: byDay.get(day) ?? 0,
    }));
  }, [trades, range]);

  const total = days.reduce((sum, d) => sum + d.pnl, 0);
  // Long spans get Month-Year axis labels; shorter ones get Month-Day.
  const spanDays =
    days.length > 1
      ? (new Date(days[days.length - 1].date).getTime() -
          new Date(days[0].date).getTime()) /
        86_400_000
      : 0;
  const coarse = spanDays > 180;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-sm text-slate-400 hover:text-white">
          ← Dashboard
        </Link>
        <h1 className="text-xl font-bold">Trade history</h1>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">Realized P/L</h2>
          {RANGES.map((r) => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                range === r.key
                  ? "bg-emerald-500 text-slate-950"
                  : "border border-slate-700 text-slate-300 hover:bg-slate-800"
              }`}
            >
              {r.label}
            </button>
          ))}
          {days.length > 0 && (
            <div className="ml-auto text-right text-sm font-medium">
              <span className={plClass(total)}>{signedMoney(total)}</span>
              <span className="ml-1 text-xs text-slate-500">
                {RANGES.find((r) => r.key === range)?.label ?? range}
              </span>
            </div>
          )}
        </div>
        <RealizedPnLChart days={days} coarse={coarse} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">All trades</h2>
        {loading ? (
          <p className="text-sm text-slate-500">Loading trades…</p>
        ) : error ? (
          <p className="text-sm text-red-400">{error}</p>
        ) : trades.length === 0 ? (
          <p className="text-sm text-slate-500">No trades yet.</p>
        ) : (
          <TradesTable trades={trades} />
        )}
      </div>
    </div>
  );
}
