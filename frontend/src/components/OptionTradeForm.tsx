import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../api/client";
import type { OptionContract, OptionOrder, OptionTrade } from "../api/types";
import { money, num } from "../utils/format";

const MULTIPLIER = 100;

type OrderType = "market" | "limit" | "stop" | "trailing_stop";

const ORDER_TYPES: { key: OrderType; label: string }[] = [
  { key: "market", label: "Market" },
  { key: "limit", label: "Limit" },
  { key: "stop", label: "Stop" },
  { key: "trailing_stop", label: "Trailing" },
];

/**
 * Buy/sell a single selected option contract. Market orders fill immediately during regular hours;
 * limit/stop/trailing orders rest and are filled by the poller when the contract mark crosses the
 * trigger (allowed to be placed even while the market is closed). The server enforces the 0DTE-cutoff
 * and no-naked collateral rules; we surface them.
 */
export default function OptionTradeForm({
  contract,
  underlying,
  expiration,
  marketState,
  ownedShares,
  locked = false,
  onTraded,
  onOrdered,
}: {
  contract: OptionContract;
  underlying: string;
  expiration: string;
  marketState?: string | null;
  ownedShares: number;
  locked?: boolean;
  onTraded: (trade: OptionTrade) => void;
  // Fired after a resting order (limit/stop/trailing) is placed, so the caller can refresh its list.
  onOrdered?: (order: OptionOrder) => void;
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

  const qtyNum = parseInt(quantity, 10);
  const mark = contract.mark ?? null;
  const notional = mark != null && qtyNum > 0 ? mark * MULTIPLIER * qtyNum : null;
  const isRegular = marketState === "REGULAR";
  const isMarket = orderType === "market";

  // Collateral hint for writes (sell to open). Covered call needs shares; CSP reserves cash.
  const collateral =
    side === "sell"
      ? contract.option_type === "put"
        ? { kind: "Cash-secured put", need: money(contract.strike * MULTIPLIER * (qtyNum || 0)) }
        : {
            kind: "Covered call",
            need: `${MULTIPLIER * (qtyNum || 0)} sh (you own ${ownedShares})`,
          }
      : null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setOk(null);
    if (locked) return setError("Portfolio is locked. Reset it to trade again.");
    if (!(qtyNum > 0)) return setError("Enter a whole number of contracts.");

    if (isMarket) {
      // Market option orders fill immediately, so they require a regular session.
      if (!isRegular)
        return setError("Options trade only during regular market hours (9:30 AM–4:00 PM ET).");
      setSubmitting(true);
      try {
        const { data } = await api.post<OptionTrade>("/options/orders", {
          occ_symbol: contract.occ_symbol,
          underlying,
          expiration,
          option_type: contract.option_type,
          strike: contract.strike,
          side,
          quantity: qtyNum,
        });
        setOk(
          `${data.action === "buy" ? "Bought" : "Sold"} ${data.quantity} ${underlying} ${num(
            data.strike,
          )} ${data.option_type} @ ${money(data.price)}`,
        );
        onTraded(data);
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setSubmitting(false);
      }
      return;
    }

    // Resting order (limit / stop / trailing) on the contract mark. Allowed while the market is
    // closed — the poller fills it once the next regular session opens.
    const body: Record<string, unknown> = {
      occ_symbol: contract.occ_symbol,
      underlying,
      expiration,
      option_type: contract.option_type,
      strike: contract.strike,
      side,
      quantity: qtyNum,
      order_type: orderType,
    };
    if (orderType === "limit") {
      const v = parseFloat(limitPrice);
      if (!(v > 0)) return setError("Enter a limit price (per share).");
      body.limit_price = v;
    } else if (orderType === "stop") {
      const v = parseFloat(stopPrice);
      if (!(v > 0)) return setError("Enter a stop price (per share).");
      body.stop_price = v;
    } else {
      const v = parseFloat(trailPercent);
      if (!(v > 0 && v < 100)) return setError("Enter a trail percent between 0 and 100.");
      body.trail_percent = v;
    }

    setSubmitting(true);
    try {
      const { data } = await api.post<OptionOrder>("/option-orders", body);
      setOk(
        `Order placed: ${data.side} ${data.quantity} ${underlying} ${num(data.strike)} ${
          data.option_type
        } (${orderType.replace("_", " ")}).`,
      );
      onOrdered?.(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-emerald-500";

  return (
    <form onSubmit={submit} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-300">
            {underlying} {num(contract.strike)} {contract.option_type.toUpperCase()}
          </h3>
          <p className="text-xs text-slate-500">
            Exp {expiration} · {contract.occ_symbol}
          </p>
        </div>
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
          Portfolio locked — reset it from the dashboard to trade again.
        </div>
      )}

      {isMarket && !isRegular && (
        <div className="mb-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          Options trade only during regular market hours (9:30 AM–4:00 PM ET). Place a limit, stop,
          or trailing order to queue it for the next session.
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

      <label className="mb-1 block text-xs text-slate-400">Contracts</label>
      <input
        type="number"
        step="1"
        min="1"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        className={`mb-3 ${inputClass}`}
      />

      {orderType === "limit" && (
        <>
          <label className="mb-1 block text-xs text-slate-400">Limit price (per share)</label>
          <input
            type="number"
            step="any"
            min="0"
            value={limitPrice}
            onChange={(e) => setLimitPrice(e.target.value)}
            placeholder={mark != null ? money(mark) : ""}
            className={`mb-3 ${inputClass}`}
          />
        </>
      )}
      {orderType === "stop" && (
        <>
          <label className="mb-1 block text-xs text-slate-400">Stop price (per share)</label>
          <input
            type="number"
            step="any"
            min="0"
            value={stopPrice}
            onChange={(e) => setStopPrice(e.target.value)}
            placeholder={mark != null ? money(mark) : ""}
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
          <span>Mark (per share)</span>
          <span className="text-slate-200">{money(mark)}</span>
        </div>
        {isMarket && (
          <div className="flex justify-between">
            <span>{side === "buy" ? "Estimated cost" : "Premium received"}</span>
            <span className="text-slate-200">{money(notional)}</span>
          </div>
        )}
        <div className="text-[11px] text-slate-500">×100 shares per contract</div>
        {collateral && (
          <div className="flex justify-between border-t border-slate-800 pt-1">
            <span>{collateral.kind} collateral</span>
            <span className="text-slate-200">{collateral.need}</span>
          </div>
        )}
      </div>

      {error && <p className="mb-2 text-xs text-red-400">{error}</p>}
      {ok && <p className="mb-2 text-xs text-emerald-400">{ok}</p>}

      <button
        type="submit"
        disabled={submitting || locked || mark == null || (isMarket && !isRegular)}
        className="w-full rounded-md bg-emerald-500 px-3 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isMarket && !isRegular
          ? "Market closed for options"
          : submitting
            ? isMarket
              ? "Placing…"
              : "Placing order…"
            : isMarket
              ? `${side === "buy" ? "Buy" : "Sell"} ${qtyNum || ""} contract${qtyNum === 1 ? "" : "s"}`
              : `Place ${side} order`}
      </button>
    </form>
  );
}
