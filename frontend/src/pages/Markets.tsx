import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import type { MarketOverview, MoverQuote } from "../api/types";
import { money, pct, plClass, signedMoney } from "../utils/format";

function MoverList({ items }: { items: MoverQuote[] }) {
  if (!items.length) return <p className="text-sm text-slate-500">No data.</p>;
  return (
    <ul className="divide-y divide-slate-800 overflow-hidden rounded-xl border border-slate-800">
      {items.map((m) => (
        <li key={m.symbol}>
          <Link
            to={`/stock/${encodeURIComponent(m.symbol)}`}
            className="flex items-center justify-between px-4 py-3 hover:bg-slate-900/50"
          >
            <div className="min-w-0">
              <div className="font-semibold text-emerald-400">{m.symbol}</div>
              {m.name && <div className="truncate text-xs text-slate-400">{m.name}</div>}
            </div>
            <div className="text-right">
              <div className="text-sm font-medium">{money(m.price)}</div>
              <div className={`text-xs ${plClass(m.change_percent)}`}>
                {signedMoney(m.change)} ({pct(m.change_percent)})
              </div>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function Markets() {
  const [data, setData] = useState<MarketOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<MarketOverview>("/market/overview")
      .then((r) => setData(r.data))
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-slate-400">Loading markets…</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Markets</h1>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Indices</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {data.indices.map((m) => (
            <Link
              key={m.symbol}
              to={`/stock/${encodeURIComponent(m.symbol)}`}
              className="rounded-xl border border-slate-800 bg-slate-900 p-4 transition hover:bg-slate-800/60"
            >
              <div className="truncate text-sm font-semibold">{m.name ?? m.symbol}</div>
              <div className="text-xs text-slate-500">{m.symbol}</div>
              <div className="mt-2 text-lg font-bold">{money(m.price)}</div>
              <div className={`text-xs ${plClass(m.change_percent)}`}>{pct(m.change_percent)}</div>
            </Link>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-semibold">Top gainers</h2>
          <MoverList items={data.gainers} />
        </div>
        <div>
          <h2 className="mb-3 text-lg font-semibold">Top losers</h2>
          <MoverList items={data.losers} />
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Popular ETFs</h2>
        <MoverList items={data.etfs} />
      </div>
    </div>
  );
}
