import { Link } from "react-router-dom";
import type { Holding } from "../api/types";
import { money, pct, plClass, qty } from "../utils/format";

export default function HoldingsTable({ holdings }: { holdings: Holding[] }) {
  if (!holdings.length)
    return (
      <div className="rounded-xl border border-dashed border-slate-800 p-8 text-center text-slate-500">
        No positions yet. Search a symbol and place your first paper trade.
      </div>
    );

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full text-sm">
        <thead className="bg-slate-900 text-left text-xs uppercase tracking-wide text-slate-400">
          <tr>
            <th className="px-4 py-3">Symbol</th>
            <th className="px-4 py-3 text-right">Qty</th>
            <th className="px-4 py-3 text-right">Avg cost</th>
            <th className="px-4 py-3 text-right">Price</th>
            <th className="px-4 py-3 text-right">Market value</th>
            <th className="px-4 py-3 text-right">Today's gain</th>
            <th className="px-4 py-3 text-right">Total gain</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {holdings.map((h) => (
            <tr key={h.symbol} className="hover:bg-slate-900/50">
              <td className="px-4 py-3 font-semibold">
                <Link to={`/stock/${h.symbol}`} className="text-emerald-400 hover:underline">
                  {h.symbol}
                </Link>
                {h.quantity < 0 && (
                  <span className="ml-2 rounded bg-red-500/15 px-1.5 py-0.5 text-xs font-medium text-red-400">
                    Short
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-right">{qty(h.quantity)}</td>
              <td className="px-4 py-3 text-right">{money(h.avg_cost)}</td>
              <td className="px-4 py-3 text-right">{money(h.current_price)}</td>
              <td className="px-4 py-3 text-right">{money(h.market_value)}</td>
              <td className={`px-4 py-3 text-right ${plClass(h.todays_pl)}`}>
                {money(h.todays_pl)}{" "}
                <span className="text-xs">({pct(h.todays_pl_percent)})</span>
              </td>
              <td className={`px-4 py-3 text-right ${plClass(h.unrealized_pl)}`}>
                {money(h.unrealized_pl)}{" "}
                <span className="text-xs">({pct(h.unrealized_pl_percent)})</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
