import type { Trade } from "../api/types";
import { money, plClass, qty, signedMoney } from "../utils/format";

/**
 * Trade log table shared by the dashboard (recent) and the full history page.
 * Value is signed by cash flow — buys spend cash (−), sells return cash (+).
 * P/L shows realized profit/loss on sells (green/loss red); buys have none (—).
 */
export default function TradesTable({ trades }: { trades: Trade[] }) {
  return (
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
            <th className="px-4 py-3 text-right">P/L</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {trades.map((t) => {
            const value = t.price * t.quantity;
            const signedValue = t.side === "buy" ? -value : value;
            return (
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
                <td className="px-4 py-3 text-right">{signedMoney(signedValue)}</td>
                <td className={`px-4 py-3 text-right ${plClass(t.realized_pl)}`}>
                  {t.realized_pl == null ? "—" : signedMoney(t.realized_pl)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
