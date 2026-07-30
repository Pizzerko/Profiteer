import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Order } from "../api/types";
import { money, num, qty } from "../utils/format";

const STATUS_CLASS: Record<string, string> = {
  open: "text-sky-400",
  filled: "text-emerald-400",
  cancelled: "text-slate-500",
  rejected: "text-red-400",
};

const TYPE_LABEL: Record<string, string> = {
  limit: "Limit",
  stop: "Stop",
  trailing_stop: "Trailing",
};

function trigger(o: Order): string {
  if (o.order_type === "limit") return money(o.limit_price);
  if (o.order_type === "stop") return money(o.stop_price);
  if (o.order_type === "trailing_stop") return `−${num(o.trail_percent)}%`;
  return "—";
}

/**
 * Resting orders (limit/stop/trailing). Used symbol-scoped on StockDetail and account-wide on the
 * Dashboard. `onChanged` refetches after a cancel. `showSymbol` adds a linked symbol column.
 */
export default function OrdersTable({
  orders,
  onChanged,
  showSymbol = true,
}: {
  orders: Order[];
  onChanged?: () => void;
  showSymbol?: boolean;
}) {
  const [busyId, setBusyId] = useState<number | null>(null);

  async function cancel(id: number) {
    setBusyId(id);
    try {
      await api.delete(`/orders/${id}`);
      onChanged?.();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full text-sm">
        <thead className="bg-slate-900 text-left text-xs uppercase tracking-wide text-slate-400">
          <tr>
            <th className="px-4 py-3">Created</th>
            {showSymbol && <th className="px-4 py-3">Symbol</th>}
            <th className="px-4 py-3">Side</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3 text-right">Qty</th>
            <th className="px-4 py-3 text-right">Trigger</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3 text-right"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {orders.map((o) => (
            <tr key={o.id} className="hover:bg-slate-900/50">
              <td className="px-4 py-3 text-slate-400">
                {new Date(o.created_at).toLocaleString()}
              </td>
              {showSymbol && (
                <td className="px-4 py-3 font-semibold">
                  <Link to={`/stock/${encodeURIComponent(o.symbol)}`} className="text-emerald-400 hover:underline">
                    {o.symbol}
                  </Link>
                </td>
              )}
              <td
                className={`px-4 py-3 capitalize ${
                  o.side === "buy" ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {o.side}
              </td>
              <td className="px-4 py-3 text-slate-300">{TYPE_LABEL[o.order_type] ?? o.order_type}</td>
              <td className="px-4 py-3 text-right">{qty(o.quantity)}</td>
              <td className="px-4 py-3 text-right">{trigger(o)}</td>
              <td className={`px-4 py-3 capitalize ${STATUS_CLASS[o.status] ?? "text-slate-300"}`}>
                {o.status}
                {o.status === "rejected" && o.note && (
                  <span className="ml-1 text-xs text-slate-500" title={o.note}>
                    ⓘ
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-right">
                {o.status === "open" && (
                  <button
                    onClick={() => cancel(o.id)}
                    disabled={busyId === o.id}
                    className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                  >
                    {busyId === o.id ? "…" : "Cancel"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
