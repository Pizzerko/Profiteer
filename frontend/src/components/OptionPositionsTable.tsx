import { Link } from "react-router-dom";
import type { OptionPosition } from "../api/types";
import { money, num, pct, plClass, qty } from "../utils/format";

function badge(p: OptionPosition) {
  if (p.quantity < 0)
    return p.collateral_kind === "cash_secured"
      ? { label: "CSP", cls: "bg-sky-500/15 text-sky-400" }
      : { label: "Covered", cls: "bg-amber-500/15 text-amber-400" };
  return { label: "Long", cls: "bg-emerald-500/15 text-emerald-400" };
}

export default function OptionPositionsTable({
  positions,
  selectedOcc,
  onSelect,
}: {
  positions: OptionPosition[];
  /** occ_symbol of the position currently loaded into the trade form, if any. */
  selectedOcc?: string | null;
  /** Fired when a row is clicked, so the caller can load it into the trade form to close it. */
  onSelect?: (position: OptionPosition) => void;
}) {
  if (!positions.length)
    return (
      <div className="rounded-xl border border-dashed border-slate-800 p-8 text-center text-slate-500">
        No option positions yet.
      </div>
    );

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full text-sm">
        <thead className="bg-slate-900 text-left text-xs uppercase tracking-wide text-slate-400">
          <tr>
            <th className="px-4 py-3">Contract</th>
            <th className="px-4 py-3 text-right">Qty</th>
            <th className="px-4 py-3 text-right">Avg</th>
            <th className="px-4 py-3 text-right">Mark</th>
            <th className="px-4 py-3 text-right">Value</th>
            <th className="px-4 py-3 text-right">Unrealized P/L</th>
            <th className="px-4 py-3 text-right">Exp</th>
            {onSelect && <th className="px-4 py-3" />}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {positions.map((p) => {
            const b = badge(p);
            const selected = p.occ_symbol === selectedOcc;
            return (
              <tr
                key={p.occ_symbol}
                onClick={() => onSelect?.(p)}
                className={`${onSelect ? "cursor-pointer" : ""} ${
                  selected ? "bg-emerald-500/15" : "hover:bg-slate-900/50"
                }`}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Link
                      to={`/stock/${p.underlying}`}
                      onClick={(e) => e.stopPropagation()}
                      className="font-semibold text-emerald-400 hover:underline"
                    >
                      {p.underlying}
                    </Link>
                    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${b.cls}`}>
                      {b.label}
                    </span>
                  </div>
                  <div className="text-xs text-slate-500">
                    {num(p.strike)} {p.option_type}
                  </div>
                </td>
                <td className="px-4 py-3 text-right">{qty(p.quantity)}</td>
                <td className="px-4 py-3 text-right">{money(p.avg_price)}</td>
                <td className="px-4 py-3 text-right">{money(p.current_price)}</td>
                <td className="px-4 py-3 text-right">{money(p.market_value)}</td>
                <td className={`px-4 py-3 text-right ${plClass(p.unrealized_pl)}`}>
                  {money(p.unrealized_pl)}{" "}
                  <span className="text-xs">({pct(p.unrealized_pl_percent)})</span>
                </td>
                <td className="px-4 py-3 text-right text-xs text-slate-400">
                  {p.expiration}
                  {p.days_to_expiry != null && (
                    <span className="ml-1 text-slate-600">({p.days_to_expiry}d)</span>
                  )}
                </td>
                {onSelect && (
                  <td className="px-4 py-3 text-right text-xs font-medium text-sky-400">
                    {selected ? "Selected" : "Close ▸"}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
