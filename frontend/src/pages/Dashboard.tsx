import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import HoldingsTable from "../components/HoldingsTable";
import OptionOrdersTable from "../components/OptionOrdersTable";
import OptionPositionsTable from "../components/OptionPositionsTable";
import OrdersTable from "../components/OrdersTable";
import StockChart from "../components/StockChart";
import TradesTable from "../components/TradesTable";
import type {
  OptionOrder,
  Order,
  PortfolioHistoryResponse,
  Portfolio,
  Quote,
  Trade,
  WatchlistItem,
} from "../api/types";
import { usePortfolios } from "../portfolio/PortfolioContext";
import { money, pct, plClass, signedMoney } from "../utils/format";

const STATE_LABEL: Record<string, string> = {
  PRE: "Pre-market",
  POST: "After hours",
};

// Backend range key -> button label, in display order.
const PERF_RANGES: { key: string; label: string }[] = [
  { key: "1d", label: "1D" },
  { key: "1w", label: "1W" },
  { key: "1mo", label: "1M" },
  { key: "3mo", label: "3M" },
  { key: "ytd", label: "YTD" },
  { key: "1y", label: "1Y" },
  { key: "all", label: "All" },
];

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
  const [orders, setOrders] = useState<Order[]>([]);
  const [optionOrders, setOptionOrders] = useState<OptionOrder[]>([]);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [history, setHistory] = useState<PortfolioHistoryResponse | null>(null);
  const [perfRange, setPerfRange] = useState("1mo");
  const [showBenchmark, setShowBenchmark] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { activeId, refresh: refreshPortfolios } = usePortfolios();

  async function load() {
    try {
      const [p, t, o, oo, w] = await Promise.all([
        api.get<Portfolio>("/portfolio"),
        api.get<Trade[]>("/portfolio/trades"),
        api.get<Order[]>("/orders", { params: { status: "open" } }),
        api.get<OptionOrder[]>("/option-orders", { params: { status: "open" } }),
        api.get<WatchlistItem[]>("/watchlist"),
      ]);
      setPortfolio(p.data);
      setTrades(t.data);
      setOrders(o.data);
      setOptionOrders(oo.data);
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

  async function resetPortfolio(startOver: boolean) {
    if (
      !startOver &&
      !window.confirm(
        "Reset this portfolio? All holdings, trades, and open orders will be cleared and your cash restored to the starting balance.",
      )
    )
      return;
    try {
      await api.post("/portfolio/reset");
      load();
      refreshPortfolios(); // keep the switcher's totals in sync
    } catch (err) {
      setError(errorMessage(err));
    }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  // Reconstructed portfolio value over the selected range (best-effort; don't block the page).
  useEffect(() => {
    api
      .get<PortfolioHistoryResponse>("/portfolio/history", {
        params: { range: perfRange, benchmark: showBenchmark },
      })
      .then((r) => setHistory(r.data))
      .catch(() => setHistory(null));
  }, [perfRange, showBenchmark, activeId]);

  if (loading) return <p className="text-slate-400">Loading portfolio…</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!portfolio) return null;

  return (
    <div className="space-y-6">
      {portfolio.locked && (
        <div className="flex flex-col gap-3 rounded-2xl border border-red-500/40 bg-red-500/10 p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-lg font-bold text-red-300">Your portfolio was wiped out</div>
            <p className="mt-1 text-sm text-red-200/80">
              Its total value hit zero. Trading is frozen until you start over — this restores your
              starting balance and clears all positions, trades, and orders.
            </p>
          </div>
          <button
            onClick={() => resetPortfolio(true)}
            className="shrink-0 rounded-md bg-red-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-red-400"
          >
            Start over
          </button>
        </div>
      )}

      {/* Total value — the headline number for the whole account. */}
      <div className="flex items-start justify-between rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-900/30 p-6">
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-400">Total value</div>
          <div className="mt-1 text-4xl font-bold sm:text-5xl">{money(portfolio.total_value)}</div>
          <div className="mt-1 text-xs text-slate-500">
            Buying power {money(portfolio.buying_power)}
            {portfolio.reserved_cash > 0 && (
              <> · {money(portfolio.reserved_cash)} reserved</>
            )}
          </div>
        </div>
        {!portfolio.locked && (
          <button
            onClick={() => resetPortfolio(false)}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-800"
          >
            Reset
          </button>
        )}
      </div>

      {(() => {
        const pts = history?.points ?? [];
        const first = pts[0]?.value ?? null;
        const last = pts[pts.length - 1]?.value ?? null;
        const changeVal = first != null && last != null ? last - first : null;
        const changePct = changeVal != null && first ? (changeVal / first) * 100 : null;
        const chartPoints = pts.map((p) => ({ date: p.date, close: p.value }));
        const benchmarkPoints = showBenchmark ? pts.map((p) => p.benchmark ?? null) : undefined;
        return (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">Performance</h2>
              {PERF_RANGES.map((r) => (
                <button
                  key={r.key}
                  onClick={() => setPerfRange(r.key)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                    perfRange === r.key
                      ? "bg-emerald-500 text-slate-950"
                      : "border border-slate-700 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  {r.label}
                </button>
              ))}
              <button
                onClick={() => setShowBenchmark((v) => !v)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                  showBenchmark
                    ? "bg-sky-500 text-slate-950"
                    : "border border-slate-700 text-slate-300 hover:bg-slate-800"
                }`}
              >
                vs S&P 500
              </button>
              {changeVal != null && (
                <div className="ml-auto text-right text-sm font-medium">
                  <span className={plClass(changeVal)}>
                    {signedMoney(changeVal)} ({pct(changePct)})
                  </span>
                  <span className="ml-1 text-xs text-slate-500">
                    {PERF_RANGES.find((r) => r.key === perfRange)?.label ?? perfRange}
                  </span>
                </div>
              )}
            </div>
            {chartPoints.length > 1 ? (
              <StockChart
                points={chartPoints}
                up={(changeVal ?? 0) >= 0}
                range={perfRange}
                seriesLabel="Value"
                benchmarkPoints={benchmarkPoints}
                benchmarkLabel="S&P 500"
              />
            ) : (
              <div className="flex h-64 items-center justify-center text-sm text-slate-500">
                Not enough history yet.
              </div>
            )}
          </div>
        );
      })()}

      {/* Open option orders sit directly below the performance chart. */}
      {optionOrders.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">Open option orders</h2>
          <OptionOrdersTable orders={optionOrders} onChanged={load} />
        </div>
      )}

      {/* Cash and holdings breakdown sit under the performance chart. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StatCard label="Cash" value={money(portfolio.cash_balance)} />
        <StatCard label="Holdings value" value={money(portfolio.holdings_value)} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Positions</h2>
        <HoldingsTable holdings={portfolio.holdings} />
      </div>

      {portfolio.option_positions.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">Options positions</h2>
          <OptionPositionsTable positions={portfolio.option_positions} />
        </div>
      )}

      {orders.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">Open orders</h2>
          <OrdersTable orders={orders} onChanged={load} showSymbol />
        </div>
      )}

      {/* Realized P/L — total profit locked in from sells; links to the full trade history. */}
      <Link
        to="/trades"
        className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900 p-4 transition hover:bg-slate-800/60"
      >
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-400">Realized P/L</div>
          <div className={`mt-1 text-2xl font-bold ${plClass(portfolio.realized_pl)}`}>
            {signedMoney(portfolio.realized_pl)}
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <span className="hidden sm:inline">Trade history</span>
          <span aria-hidden className="text-xl leading-none">→</span>
        </div>
      </Link>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent trades</h2>
          {trades.length > 5 && (
            <Link to="/trades" className="text-sm text-emerald-400 hover:underline">
              View all →
            </Link>
          )}
        </div>
        {trades.length === 0 ? (
          <p className="text-sm text-slate-500">No trades yet.</p>
        ) : (
          <TradesTable trades={trades.slice(0, 5)} />
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
