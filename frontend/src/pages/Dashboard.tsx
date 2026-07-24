import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import HoldingsTable from "../components/HoldingsTable";
import StockChart from "../components/StockChart";
import type {
  PortfolioHistoryResponse,
  Portfolio,
  Quote,
  Trade,
  WatchlistItem,
} from "../api/types";
import { money, pct, plClass, qty, signedMoney } from "../utils/format";

const STATE_LABEL: Record<string, string> = {
  PRE: "Pre-market",
  POST: "After hours",
};

const PERF_RANGES = ["1mo", "3mo", "6mo", "1y", "5y"];

function StatCard({
  label,
  value,
  sub,
  className = "",
}: {
  label: string;
  value: string;
  sub?: string;
  className?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${className}`}>{value}</div>
      {sub && <div className={`text-sm ${className}`}>{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [history, setHistory] = useState<PortfolioHistoryResponse | null>(null);
  const [perfRange, setPerfRange] = useState("1mo");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const [p, t, w] = await Promise.all([
        api.get<Portfolio>("/portfolio"),
        api.get<Trade[]>("/portfolio/trades"),
        api.get<WatchlistItem[]>("/watchlist"),
      ]);
      setPortfolio(p.data);
      setTrades(t.data);
      setWatchlist(w.data.map((item) => item.symbol));
      loadQuotes(w.data.map((item) => item.symbol));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  // Best-effort per-symbol quotes for the watchlist — quote fetches are slow cold calls,
  // so fill each row's price as its request resolves rather than blocking the page.
  async function loadQuotes(symbols: string[]) {
    const results = await Promise.allSettled(
      symbols.map((s) => api.get<Quote>(`/market/quote/${s}`)),
    );
    const next: Record<string, Quote> = {};
    results.forEach((r, i) => {
      if (r.status === "fulfilled") next[symbols[i]] = r.value.data;
    });
    setQuotes((prev) => ({ ...prev, ...next }));
  }

  async function removeFromWatchlist(symbol: string) {
    const prev = watchlist;
    setWatchlist((w) => w.filter((s) => s !== symbol)); // optimistic
    try {
      await api.delete(`/watchlist/${symbol}`);
    } catch (err) {
      setWatchlist(prev); // revert
      setError(errorMessage(err));
    }
  }

  useEffect(() => {
    load();
  }, []);

  // Reconstructed portfolio value over the selected range (best-effort; don't block the page).
  useEffect(() => {
    api
      .get<PortfolioHistoryResponse>("/portfolio/history", { params: { range: perfRange } })
      .then((r) => setHistory(r.data))
      .catch(() => setHistory(null));
  }, [perfRange]);

  if (loading) return <p className="text-slate-400">Loading portfolio…</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!portfolio) return null;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total value" value={money(portfolio.total_value)} />
        <StatCard label="Cash" value={money(portfolio.cash_balance)} />
        <StatCard label="Holdings value" value={money(portfolio.holdings_value)} />
        <StatCard
          label="Total P/L"
          value={money(portfolio.total_pl)}
          sub={pct(portfolio.total_pl_percent)}
          className={plClass(portfolio.total_pl)}
        />
      </div>

      {(() => {
        const pts = history?.points ?? [];
        const first = pts[0]?.value ?? null;
        const last = pts[pts.length - 1]?.value ?? null;
        const changeVal = first != null && last != null ? last - first : null;
        const changePct = changeVal != null && first ? (changeVal / first) * 100 : null;
        const chartPoints = pts.map((p) => ({ date: p.date, close: p.value }));
        return (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">Performance</h2>
              {PERF_RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => setPerfRange(r)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                    perfRange === r
                      ? "bg-emerald-500 text-slate-950"
                      : "border border-slate-700 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  {r}
                </button>
              ))}
              {changeVal != null && (
                <div className="ml-auto text-right text-sm font-medium">
                  <span className={plClass(changeVal)}>
                    {signedMoney(changeVal)} ({pct(changePct)})
                  </span>
                  <span className="ml-1 text-xs text-slate-500">{perfRange}</span>
                </div>
              )}
            </div>
            {chartPoints.length > 1 ? (
              <StockChart
                points={chartPoints}
                up={(changeVal ?? 0) >= 0}
                range={perfRange}
                seriesLabel="Value"
              />
            ) : (
              <div className="flex h-64 items-center justify-center text-sm text-slate-500">
                Not enough history yet.
              </div>
            )}
          </div>
        );
      })()}

      <div>
        <h2 className="mb-3 text-lg font-semibold">Positions</h2>
        <HoldingsTable holdings={portfolio.holdings} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Recent trades</h2>
        {trades.length === 0 ? (
          <p className="text-sm text-slate-500">No trades yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-left text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3">Time</th>
                  <th className="px-4 py-3">Symbol</th>
                  <th className="px-4 py-3">Side</th>
                  <th className="px-4 py-3 text-right">Qty</th>
                  <th className="px-4 py-3 text-right">Price</th>
                  <th className="px-4 py-3 text-right">Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {trades.slice(0, 15).map((t) => (
                  <tr key={t.id} className="hover:bg-slate-900/50">
                    <td className="px-4 py-3 text-slate-400">
                      {new Date(t.executed_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-semibold">{t.symbol}</td>
                    <td
                      className={`px-4 py-3 capitalize ${
                        t.side === "buy" ? "text-emerald-400" : "text-red-400"
                      }`}
                    >
                      {t.side}
                    </td>
                    <td className="px-4 py-3 text-right">{qty(t.quantity)}</td>
                    <td className="px-4 py-3 text-right">{money(t.price)}</td>
                    <td className="px-4 py-3 text-right">{money(t.price * t.quantity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Watchlist</h2>
        {watchlist.length === 0 ? (
          <p className="text-sm text-slate-500">No symbols in your watchlist yet.</p>
        ) : (
          <ul className="divide-y divide-slate-800 overflow-hidden rounded-xl border border-slate-800">
            {watchlist.map((symbol) => {
              const q = quotes[symbol];
              const showExt =
                !!q &&
                (q.market_state === "PRE" || q.market_state === "POST") &&
                q.extended_price != null;
              return (
                <li
                  key={symbol}
                  className="flex items-center justify-between px-4 py-3 hover:bg-slate-900/50"
                >
                  <Link to={`/stock/${symbol}`} className="min-w-0 flex-1">
                    <span className="font-semibold text-emerald-400">{symbol}</span>
                    {q?.name && (
                      <span className="ml-2 text-sm text-slate-400">{q.name}</span>
                    )}
                  </Link>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      {q ? (
                        <>
                          <div className="text-sm font-medium">
                            {money(q.price)}{" "}
                            <span className={plClass(q.change_percent)}>
                              {pct(q.change_percent)}
                            </span>
                          </div>
                          {showExt && (
                            <div className="text-xs text-slate-400">
                              {STATE_LABEL[q.market_state!] ?? "Extended"}{" "}
                              {money(q.extended_price)}{" "}
                              <span className={plClass(q.extended_change)}>
                                {signedMoney(q.extended_change)} (
                                {pct(q.extended_change_percent)})
                              </span>
                            </div>
                          )}
                        </>
                      ) : (
                        <span className="text-xs text-slate-500">—</span>
                      )}
                    </div>
                    <button
                      onClick={() => removeFromWatchlist(symbol)}
                      aria-label={`Remove ${symbol} from watchlist`}
                      title="Remove from watchlist"
                      className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-800 hover:text-red-400"
                    >
                      ✕
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
