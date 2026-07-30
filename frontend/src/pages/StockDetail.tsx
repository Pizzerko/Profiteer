import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import OptionChainTable from "../components/OptionChainTable";
import OptionOrdersTable from "../components/OptionOrdersTable";
import OptionPositionsTable from "../components/OptionPositionsTable";
import OptionTradeForm from "../components/OptionTradeForm";
import OrdersTable from "../components/OrdersTable";
import PositionCard from "../components/PositionCard";
import StockChart from "../components/StockChart";
import TradeForm from "../components/TradeForm";
import type {
  Fundamentals,
  HistoryResponse,
  NewsItem,
  OptionContract,
  OptionOrder,
  Order,
  Portfolio,
  Quote,
  WatchlistItem,
} from "../api/types";
import { usePortfolios } from "../portfolio/PortfolioContext";
import { compact, money, num, pct, plClass, signedMoney } from "../utils/format";

const RANGES = ["1d", "5d", "1mo", "6mo", "1y", "5y"];

const STATE_LABEL: Record<string, string> = {
  PRE: "Pre-market",
  POST: "After hours",
};

function EyeIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" fill={filled ? "var(--color-slate-900, #0f172a)" : "none"} />
    </svg>
  );
}

export default function StockDetail() {
  const { symbol = "" } = useParams();
  const sym = symbol.toUpperCase();

  const [quote, setQuote] = useState<Quote | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [fundamentals, setFundamentals] = useState<Fundamentals | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [optionOrders, setOptionOrders] = useState<OptionOrder[]>([]);
  const [range, setRange] = useState("1mo");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [inWatchlist, setInWatchlist] = useState(false);
  const [showOptions, setShowOptions] = useState(false);
  const [selectedContract, setSelectedContract] = useState<OptionContract | null>(null);
  const [selectedExpiration, setSelectedExpiration] = useState<string>("");
  const { activeId } = usePortfolios();

  async function loadCore() {
    setLoading(true);
    setError(null);
    try {
      const [q, p, w] = await Promise.all([
        api.get<Quote>(`/market/quote/${sym}`),
        api.get<Portfolio>("/portfolio"),
        api.get<WatchlistItem[]>("/watchlist"),
      ]);
      setQuote(q.data);
      setPortfolio(p.data);
      setInWatchlist(w.data.some((item) => item.symbol === sym));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
    // News and fundamentals are best-effort; don't block the page on them.
    api
      .get<NewsItem[]>(`/market/news/${sym}`)
      .then((r) => setNews(r.data))
      .catch(() => setNews([]));
    api
      .get<Fundamentals>(`/market/fundamentals/${sym}`)
      .then((r) => setFundamentals(r.data))
      .catch(() => setFundamentals(null));
    api
      .get<Order[]>("/orders", { params: { status: "open" } })
      .then((r) => setOrders(r.data))
      .catch(() => setOrders([]));
    api
      .get<OptionOrder[]>("/option-orders", { params: { status: "open" } })
      .then((r) => setOptionOrders(r.data))
      .catch(() => setOptionOrders([]));
  }

  useEffect(() => {
    loadCore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sym, activeId]);

  useEffect(() => {
    // 1d shows the full day incl. pre/after-hours; multi-day ranges use regular hours.
    const prepost = range === "1d";
    api
      .get<HistoryResponse>(`/market/history/${sym}`, { params: { range, prepost } })
      .then((r) => setHistory(r.data))
      .catch(() => setHistory(null));
  }, [sym, range]);

  async function toggleWatch() {
    const next = !inWatchlist;
    setInWatchlist(next); // optimistic
    try {
      if (next) await api.post("/watchlist", { symbol: sym });
      else await api.delete(`/watchlist/${sym}`);
    } catch (err) {
      setInWatchlist(!next); // revert
      setError(errorMessage(err));
    }
  }

  if (loading) return <p className="text-slate-400">Loading {sym}…</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!quote) return null;

  const isExtended = quote.market_state === "PRE" || quote.market_state === "POST";
  const showExtended = isExtended && quote.extended_price != null;
  const tradingOpen = ["PRE", "REGULAR", "POST"].includes(quote.market_state ?? "");
  const holding = portfolio?.holdings.find((h) => h.symbol === sym) ?? null;
  const symbolOrders = orders.filter((o) => o.symbol === sym);
  const symbolOptions =
    portfolio?.option_positions.filter((p) => p.underlying === sym) ?? [];
  const symbolOptionOrders = optionOrders.filter((o) => o.underlying === sym);

  // Gain/loss over the selected chart range. For 1d the header must match the quote card, which is
  // anchored to the prior regular-session close — not the first intraday bar (a 4:00 AM pre-market
  // print when prepost=true), which would hide any overnight gap. Other ranges use first vs last.
  const pts = history?.points ?? [];
  const isIntraday = range === "1d";
  const firstClose = pts[0]?.close ?? null;
  const lastClose = pts[pts.length - 1]?.close ?? null;
  const rangeChange = isIntraday
    ? quote.change ?? null
    : firstClose != null && lastClose != null
      ? lastClose - firstClose
      : null;
  const rangeChangePct = isIntraday
    ? quote.change_percent ?? null
    : rangeChange != null && firstClose
      ? (rangeChange / firstClose) * 100
      : null;
  const up = (rangeChange ?? quote.change ?? 0) >= 0;

  return (
    <div className="space-y-6">
      {/* Top row: price + chart on the left, the trade panel on the right. The left column is a
          flex stack so the chart card grows to fill the height, keeping both columns level. */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-2xl font-bold">{quote.symbol}</h1>
                <p className="text-sm text-slate-400">{quote.name}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={toggleWatch}
                  aria-label={inWatchlist ? "Remove from watchlist" : "Add to watchlist"}
                  title={inWatchlist ? "Remove from watchlist" : "Add to watchlist"}
                  className={`rounded-md p-1.5 transition-colors ${
                    inWatchlist
                      ? "text-emerald-400 hover:text-emerald-300"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  <EyeIcon filled={inWatchlist} />
                </button>
                {quote.market_state && (
                  <span className="rounded-full border border-slate-700 px-2 py-1 text-xs text-slate-400">
                    {quote.market_state}
                  </span>
                )}
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-3">
              <span className="text-3xl font-bold">{money(quote.price)}</span>
              <span className={`text-sm font-medium ${plClass(quote.change)}`}>
                {money(quote.change)} ({pct(quote.change_percent)})
              </span>
            </div>
            {showExtended && (
              <div className="mt-1 flex items-baseline gap-2 text-sm">
                <span className="text-slate-400">
                  {STATE_LABEL[quote.market_state!] ?? "Extended"}:
                </span>
                <span className="font-semibold text-slate-100">
                  {money(quote.extended_price)}
                </span>
                <span className={plClass(quote.extended_change)}>
                  {money(quote.extended_change)} ({pct(quote.extended_change_percent)})
                </span>
              </div>
            )}
            {fundamentals &&
              (fundamentals.day_high != null ||
                fundamentals.day_low != null ||
                fundamentals.volume != null) && (
                <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 border-t border-slate-800 pt-3 text-xs text-slate-400">
                  <span>
                    Day high{" "}
                    <span className="font-medium text-slate-100">
                      {money(fundamentals.day_high)}
                    </span>
                  </span>
                  <span>
                    Day low{" "}
                    <span className="font-medium text-slate-100">
                      {money(fundamentals.day_low)}
                    </span>
                  </span>
                  <span>
                    Volume{" "}
                    <span className="font-medium text-slate-100">
                      {compact(fundamentals.volume)}
                    </span>
                  </span>
                </div>
              )}
          </div>

          <div className="flex flex-1 flex-col rounded-xl border border-slate-800 bg-slate-900 p-5">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              {RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                    range === r
                      ? "bg-emerald-500 text-slate-950"
                      : "border border-slate-700 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  {r}
                </button>
              ))}
              {rangeChange != null && (
                <div className="ml-auto text-right text-sm font-medium">
                  <span className={plClass(rangeChange)}>
                    {signedMoney(rangeChange)} ({pct(rangeChangePct)})
                  </span>
                  <span className="ml-1 text-xs text-slate-500">{range}</span>
                </div>
              )}
            </div>
            <StockChart
              points={history?.points ?? []}
              up={up}
              range={range}
              heightClass="min-h-[16rem] flex-1"
            />
          </div>
        </div>

        <div className="space-y-6 lg:col-span-1">
          {holding && <PositionCard holding={holding} />}
          <TradeForm
            symbol={sym}
            price={quote.effective_price ?? quote.price}
            priceLabel={isExtended ? STATE_LABEL[quote.market_state!] ?? "Extended-hours" : undefined}
            cash={portfolio?.buying_power ?? null}
            tradingOpen={tradingOpen}
            locked={portfolio?.locked ?? false}
            onTraded={() => loadCore()}
            onOrdered={() => loadCore()}
          />

          {symbolOrders.length > 0 && (
            <div>
              <h2 className="mb-3 text-sm font-semibold text-slate-300">Open orders</h2>
              <OrdersTable orders={symbolOrders} onChanged={loadCore} showSymbol={false} />
            </div>
          )}
        </div>
      </div>

      {/* Options — full-width band: the chain is wide (calls/puts × 8 columns), so it gets the
          whole row, with the trade form sitting alongside it. */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <button
          type="button"
          onClick={() => setShowOptions((v) => !v)}
          className="flex w-full items-center justify-between text-sm font-semibold text-slate-300"
        >
          <span>Options</span>
          <span className="text-xs text-slate-500">{showOptions ? "Hide ▲" : "Show ▼"}</span>
        </button>
        {showOptions && (
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <OptionChainTable
                symbol={sym}
                selectedOcc={selectedContract?.occ_symbol}
                onSelect={(c, exp) => {
                  setSelectedContract(c);
                  setSelectedExpiration(exp);
                }}
              />
            </div>
            {selectedContract ? (
              <OptionTradeForm
                contract={selectedContract}
                underlying={sym}
                expiration={selectedExpiration}
                marketState={quote.market_state}
                ownedShares={holding && holding.quantity > 0 ? holding.quantity : 0}
                locked={portfolio?.locked ?? false}
                onTraded={() => loadCore()}
                onOrdered={() => loadCore()}
              />
            ) : (
              <div className="flex items-center justify-center rounded-xl border border-dashed border-slate-800 p-8 text-center text-sm text-slate-500">
                Select a contract from the chain to trade.
              </div>
            )}
          </div>
        )}
        {symbolOptions.length > 0 && (
          <div className="mt-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Your {sym} option positions
            </h3>
            <OptionPositionsTable positions={symbolOptions} />
          </div>
        )}
        {symbolOptionOrders.length > 0 && (
          <div className="mt-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Open {sym} option orders
            </h3>
            <OptionOrdersTable orders={symbolOptionOrders} onChanged={loadCore} />
          </div>
        )}
      </div>

      {/* Reference data below the trading surface. */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {fundamentals &&
            (() => {
              const rows: [string, string][] = [
                ["Market cap", compact(fundamentals.market_cap)],
                ["P/E (TTM)", num(fundamentals.pe_ratio)],
                ["Forward P/E", num(fundamentals.forward_pe)],
                ["EPS (TTM)", money(fundamentals.eps)],
                [
                  "Div yield",
                  fundamentals.dividend_yield == null
                    ? "—"
                    : `${num(fundamentals.dividend_yield)}%`,
                ],
                ["Beta", num(fundamentals.beta)],
                ["52W high", money(fundamentals.fifty_two_week_high)],
                ["52W low", money(fundamentals.fifty_two_week_low)],
                ["Day high", money(fundamentals.day_high)],
                ["Day low", money(fundamentals.day_low)],
                ["Open", money(fundamentals.open)],
                ["Prev close", money(fundamentals.previous_close)],
                ["Volume", compact(fundamentals.volume)],
                ["Avg volume", compact(fundamentals.avg_volume)],
              ];
              return (
                <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <h2 className="mb-3 text-sm font-semibold text-slate-300">
                    Key statistics
                  </h2>
                  {(fundamentals.sector || fundamentals.industry) && (
                    <p className="mb-3 text-xs text-slate-400">
                      {[fundamentals.sector, fundamentals.industry]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  )}
                  <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
                    {rows.map(([label, value]) => (
                      <div
                        key={label}
                        className="flex items-center justify-between border-b border-slate-800/60 pb-1"
                      >
                        <dt className="text-xs text-slate-400">{label}</dt>
                        <dd className="text-sm font-medium text-slate-100">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              );
            })()}

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">News</h2>
            {news.length === 0 ? (
              <p className="text-sm text-slate-500">No recent news.</p>
            ) : (
              <ul className="space-y-3">
                {news.slice(0, 8).map((n, i) => (
                  <li key={i}>
                    <a
                      href={n.link ?? "#"}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm text-slate-200 hover:text-emerald-400"
                    >
                      {n.title}
                    </a>
                    {n.publisher && (
                      <span className="ml-2 text-xs text-slate-500">{n.publisher}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
