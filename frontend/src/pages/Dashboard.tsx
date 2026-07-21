import { useEffect, useState } from "react";
import { api, errorMessage } from "../api/client";
import HoldingsTable from "../components/HoldingsTable";
import type { Portfolio, Trade } from "../api/types";
import { money, pct, plClass, qty } from "../utils/format";

function StatCard({
  label,
  value,
  sub,
  className = "",
}: {
  label: string;
  value: string;
  sub?: string;
  className?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${className}`}>{value}</div>
      {sub && <div className={`text-sm ${className}`}>{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const [p, t] = await Promise.all([
        api.get<Portfolio>("/portfolio"),
        api.get<Trade[]>("/portfolio/trades"),
      ]);
      setPortfolio(p.data);
      setTrades(t.data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (loading) return <p className="text-slate-400">Loading portfolio…</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!portfolio) return null;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total value" value={money(portfolio.total_value)} />
        <StatCard label="Cash" value={money(portfolio.cash_balance)} />
        <StatCard label="Holdings value" value={money(portfolio.holdings_value)} />
        <StatCard
          label="Total P/L"
          value={money(portfolio.total_pl)}
          sub={pct(portfolio.total_pl_percent)}
          className={plClass(portfolio.total_pl)}
        />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Positions</h2>
        <HoldingsTable holdings={portfolio.holdings} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Recent trades</h2>
        {trades.length === 0 ? (
          <p className="text-sm text-slate-500">No trades yet.</p>
        ) : (
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
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {trades.slice(0, 15).map((t) => (
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
                    <td className="px-4 py-3 text-right">{money(t.price * t.quantity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
