import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../api/client";
import type { Trade } from "../api/types";
import { money } from "../utils/format";

export default function TradeForm({
  symbol,
  price,
  priceLabel,
  cash,
  tradingOpen = true,
  onTraded,
}: {
  symbol: string;
  price?: number | null;
  priceLabel?: string;
  cash?: number | null;
  tradingOpen?: boolean;
  onTraded: (trade: Trade) => void;
}) {
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState("1");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const qtyNum = parseFloat(quantity);
  const estCost = price != null && qtyNum > 0 ? price * qtyNum : null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setOk(null);
    if (!tradingOpen) {
      setError("The market is closed. Orders can't be placed right now.");
      return;
    }
    if (!(qtyNum > 0)) {
      setError("Enter a quantity greater than zero.");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post<Trade>("/trades", {
        symbol,
        side,
        quantity: qtyNum,
      });
      setOk(
        `${data.side === "buy" ? "Bought" : "Sold"} ${data.quantity} ${data.symbol} @ ${money(data.price)}`,
      );
      onTraded(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <h3 className="mb-3 text-sm font-semibold text-slate-300">Trade {symbol}</h3>

      {!tradingOpen && (
        <div className="mb-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          Market closed — orders reopen in pre-market (4:00 AM ET).
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
        className="mb-3 w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-emerald-500"
      />

      <div className="mb-3 space-y-1 text-xs text-slate-400">
        <div className="flex justify-between">
          <span>Price{priceLabel ? ` (${priceLabel})` : ""}</span>
          <span className="text-slate-200">{money(price)}</span>
        </div>
        <div className="flex justify-between">
          <span>Estimated {side === "buy" ? "cost" : "proceeds"}</span>
          <span className="text-slate-200">{money(estCost)}</span>
        </div>
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
        disabled={submitting || price == null || !tradingOpen}
        className="w-full rounded-md bg-emerald-500 px-3 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {!tradingOpen
          ? "Market closed"
          : submitting
            ? "Placing…"
            : `${side === "buy" ? "Buy" : "Sell"} ${symbol}`}
      </button>
    </form>
  );
}
