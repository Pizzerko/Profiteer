import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import PositionCard from "../components/PositionCard";
import StockChart from "../components/StockChart";
import TradeForm from "../components/TradeForm";
import type {
  HistoryResponse,
  NewsItem,
  Portfolio,
  Quote,
  WatchlistItem,
} from "../api/types";
import { money, pct, plClass, signedMoney } from "../utils/format";

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
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [range, setRange] = useState("1mo");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [inWatchlist, setInWatchlist] = useState(false);

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
    // News is best-effort; don't block the page on it.
    api
      .get<NewsItem[]>(`/market/news/${sym}`)
      .then((r) => setNews(r.data))
      .catch(() => setNews([]));
  }

  useEffect(() => {
    loadCore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sym]);

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

  // Gain/loss over the selected chart range (first vs last close).
  const pts = history?.points ?? [];
  const firstClose = pts[0]?.close ?? null;
  const lastClose = pts[pts.length - 1]?.close ?? null;
  const rangeChange =
    firstClose != null && lastClose != null ? lastClose - firstClose : null;
  const rangeChangePct =
    rangeChange != null && firstClose ? (rangeChange / firstClose) * 100 : null;
  const up = (rangeChange ?? quote.change ?? 0) >= 0;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
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
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
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
          <StockChart points={history?.points ?? []} up={up} range={range} />
        </div>

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

      <div className="space-y-6 lg:col-span-1">
        {holding && <PositionCard holding={holding} />}
        <TradeForm
          symbol={sym}
          price={quote.effective_price ?? quote.price}
          priceLabel={isExtended ? STATE_LABEL[quote.market_state!] ?? "Extended-hours" : undefined}
          cash={portfolio?.cash_balance ?? null}
          tradingOpen={tradingOpen}
          onTraded={() => loadCore()}
        />
      </div>
    </div>
  );
}
