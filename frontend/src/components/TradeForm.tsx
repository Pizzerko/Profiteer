import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../api/client";
import type { Order, Trade } from "../api/types";
import { money } from "../utils/format";

type OrderType = "market" | "limit" | "stop" | "trailing_stop";

const ORDER_TYPES: { key: OrderType; label: string }[] = [
  { key: "market", label: "Market" },
  { key: "limit", label: "Limit" },
  { key: "stop", label: "Stop" },
  { key: "trailing_stop", label: "Trailing" },
];

export default function TradeForm({
  symbol,
  price,
  priceLabel,
  cash,
  tradingOpen = true,
  locked = false,
  onTraded,
  onOrdered,
}: {
  symbol: string;
  price?: number | null;
  priceLabel?: string;
  cash?: number | null;
  tradingOpen?: boolean;
  locked?: boolean;
  onTraded: (trade: Trade) => void;
  // Fired after a resting order (limit/stop/trailing) is placed, so the caller can refresh its list.
  onOrdered?: (order: Order) => void;
}) {
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [orderType, setOrderType] = useState<OrderType>("market");
  const [quantity, setQuantity] = useState("1");
  const [limitPrice, setLimitPrice] = useState("");
  const [stopPrice, setStopPrice] = useState("");
  const [trailPercent, setTrailPercent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const qtyNum = parseFloat(quantity);
  const estCost = price != null && qtyNum > 0 ? price * qtyNum : null;
  const isMarket = orderType === "market";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setOk(null);
    if (locked) {
      setError("Portfolio is locked. Reset it to trade again.");
      return;
    }
    if (!(qtyNum > 0)) {
      setError("Enter a quantity greater than zero.");
      return;
    }

    if (isMarket) {
      // Market orders fill immediately, so they require an open session.
      if (!tradingOpen) {
        setError("The market is closed. Market orders can't be placed right now.");
        return;
      }
      setSubmitting(true);
      try {
        const { data } = await api.post<Trade>("/trades", { symbol, side, quantity: qtyNum });
        setOk(
          `${data.side === "buy" ? "Bought" : "Sold"} ${data.quantity} ${data.symbol} @ ${money(data.price)}`,
        );
        onTraded(data);
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setSubmitting(false);
      }
      return;
    }

    // Resting order (limit / stop / trailing): validate its trigger field, then POST /orders.
    // These are allowed even while the market is closed — the poller fills them once it reopens.
    const body: Record<string, unknown> = { symbol, side, order_type: orderType, quantity: qtyNum };
    if (orderType === "limit") {
      const v = parseFloat(limitPrice);
      if (!(v > 0)) return setError("Enter a limit price.");
      body.limit_price = v;
    } else if (orderType === "stop") {
      const v = parseFloat(stopPrice);
      if (!(v > 0)) return setError("Enter a stop price.");
      body.stop_price = v;
    } else {
      const v = parseFloat(trailPercent);
      if (!(v > 0 && v < 100)) return setError("Enter a trail percent between 0 and 100.");
      body.trail_percent = v;
    }

    setSubmitting(true);
    try {
      const { data } = await api.post<Order>("/orders", body);
      setOk(`Order placed: ${data.side} ${data.quantity} ${data.symbol} (${orderType.replace("_", " ")}).`);
      onOrdered?.(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-emerald-500";
  const marketBlocked = isMarket && !tradingOpen;

  return (
    <form onSubmit={submit} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-300">Trade {symbol}</h3>
        <select
          value={orderType}
          onChange={(e) => setOrderType(e.target.value as OrderType)}
          title="Order type"
          className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs font-medium text-sky-300 outline-none focus:border-sky-500"
        >
          {ORDER_TYPES.map((t) => (
            <option key={t.key} value={t.key} className="text-slate-200">
              {t.label}
            </option>
          ))}
        </select>
      </div>

      {locked && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          Portfolio locked — it was wiped out. Reset it from the dashboard to trade again.
        </div>
      )}

      {marketBlocked && (
        <div className="mb-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          Market closed — place a limit, stop, or trailing order to queue it for the next session.
        </div>
      )}

      <div className="mb-3 grid grid-cols-2 gap-2">
        {(["buy", "sell"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSide(s)}
            className={`rounded-md px-3 py-2 text-sm font-medium capitalize transition ${
              side === s
                ? s === "buy"
                  ? "bg-emerald-500 text-slate-950"
                  : "bg-red-500 text-slate-950"
                : "border border-slate-700 text-slate-300 hover:bg-slate-800"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      <label className="mb-1 block text-xs text-slate-400">Quantity</label>
      <input
        type="number"
        step="any"
        min="0"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        className={`mb-3 ${inputClass}`}
      />

      {orderType === "limit" && (
        <>
          <label className="mb-1 block text-xs text-slate-400">Limit price</label>
          <input
            type="number"
            step="any"
            min="0"
            value={limitPrice}
            onChange={(e) => setLimitPrice(e.target.value)}
            placeholder={price != null ? money(price) : ""}
            className={`mb-3 ${inputClass}`}
          />
        </>
      )}
      {orderType === "stop" && (
        <>
          <label className="mb-1 block text-xs text-slate-400">Stop price</label>
          <input
            type="number"
            step="any"
            min="0"
            value={stopPrice}
            onChange={(e) => setStopPrice(e.target.value)}
            placeholder={price != null ? money(price) : ""}
            className={`mb-3 ${inputClass}`}
          />
        </>
      )}
      {orderType === "trailing_stop" && (
        <>
          <label className="mb-1 block text-xs text-slate-400">Trail percent</label>
          <input
            type="number"
            step="any"
            min="0"
            max="100"
            value={trailPercent}
            onChange={(e) => setTrailPercent(e.target.value)}
            placeholder="5"
            className={`mb-3 ${inputClass}`}
          />
        </>
      )}

      <div className="mb-3 space-y-1 text-xs text-slate-400">
        <div className="flex justify-between">
          <span>Price{priceLabel ? ` (${priceLabel})` : ""}</span>
          <span className="text-slate-200">{money(price)}</span>
        </div>
        {isMarket && (
          <div className="flex justify-between">
            <span>Estimated {side === "buy" ? "cost" : "proceeds"}</span>
            <span className="text-slate-200">{money(estCost)}</span>
          </div>
        )}
        {cash != null && (
          <div className="flex justify-between">
            <span>Buying power</span>
            <span className="text-slate-200">{money(cash)}</span>
          </div>
        )}
      </div>

      {error && <p className="mb-2 text-xs text-red-400">{error}</p>}
      {ok && <p className="mb-2 text-xs text-emerald-400">{ok}</p>}

      <button
        type="submit"
        disabled={submitting || locked || (isMarket && (price == null || !tradingOpen))}
        className="w-full rounded-md bg-emerald-500 px-3 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {marketBlocked
          ? "Market closed"
          : submitting
            ? isMarket
              ? "Placing…"
              : "Placing order…"
            : isMarket
              ? `${side === "buy" ? "Buy" : "Sell"} ${symbol}`
              : `Place ${side} order`}
      </button>
    </form>
  );
}
