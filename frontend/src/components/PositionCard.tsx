import type { Holding } from "../api/types";
import { money, pct, plClass, qty } from "../utils/format";

export default function PositionCard({ holding }: { holding: Holding }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300">Your position</h3>
        <span className="text-xs text-slate-500">{qty(holding.quantity)} shares</span>
      </div>
      <div className="space-y-2 text-sm">
        <Row label="Avg cost" value={money(holding.avg_cost)} />
        <Row label="Current price" value={money(holding.current_price)} />
        <Row label="Market value" value={money(holding.market_value)} />
        <Row label="Cost basis" value={money(holding.cost_basis)} />
        <div className="my-2 border-t border-slate-800" />
        <div className="flex items-center justify-between">
          <span className="text-slate-400">Unrealized P/L</span>
          <span className={`font-semibold ${plClass(holding.unrealized_pl)}`}>
            {money(holding.unrealized_pl)}{" "}
            <span className="text-xs">({pct(holding.unrealized_pl_percent)})</span>
          </span>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-400">{label}</span>
      <span className="text-slate-100">{value}</span>
    </div>
  );
}
