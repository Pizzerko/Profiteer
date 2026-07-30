import { useEffect, useState } from "react";
import { api, errorMessage } from "../api/client";
import type { OptionChain, OptionContract } from "../api/types";
import { num, pct } from "../utils/format";

type Side = "call" | "put";

/**
 * Live option chain for a symbol: an expiration picker + a calls/puts toggle. Clicking a row
 * selects that contract (the parent renders the trade form for it).
 */
export default function OptionChainTable({
  symbol,
  selectedOcc,
  onSelect,
}: {
  symbol: string;
  selectedOcc?: string | null;
  onSelect: (contract: OptionContract, expiration: string) => void;
}) {
  const [expirations, setExpirations] = useState<string[]>([]);
  const [expiration, setExpiration] = useState<string>("");
  const [chain, setChain] = useState<OptionChain | null>(null);
  const [side, setSide] = useState<Side>("call");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load available expirations once per symbol; default to the nearest.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setChain(null);
    api
      .get<string[]>(`/options/${symbol}/expirations`)
      .then((r) => {
        if (cancelled) return;
        setExpirations(r.data);
        setExpiration(r.data[0] ?? "");
        if (r.data.length === 0) setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(errorMessage(err));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  // Load the chain whenever the chosen expiration changes.
  useEffect(() => {
    if (!expiration) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get<OptionChain>(`/options/${symbol}/chain`, { params: { expiration } })
      .then((r) => {
        if (!cancelled) setChain(r.data);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, expiration]);

  const rows = side === "call" ? chain?.calls ?? [] : chain?.puts ?? [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={expiration}
          onChange={(e) => setExpiration(e.target.value)}
          disabled={expirations.length === 0}
          title="Expiration"
          className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs font-medium text-sky-300 outline-none focus:border-sky-500 disabled:opacity-50"
        >
          {expirations.length === 0 && <option>No expirations</option>}
          {expirations.map((e) => (
            <option key={e} value={e} className="text-slate-200">
              {e}
            </option>
          ))}
        </select>
        <div className="flex gap-1">
          {(["call", "put"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSide(s)}
              className={`rounded-md px-3 py-1 text-xs font-medium capitalize transition ${
                side === s
                  ? "bg-sky-500 text-slate-950"
                  : "border border-slate-700 text-slate-300 hover:bg-slate-800"
              }`}
            >
              {s}s
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      {loading ? (
        <p className="text-sm text-slate-500">Loading chain…</p>
      ) : expirations.length === 0 ? (
        <p className="text-sm text-slate-500">No options available for {symbol}.</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-slate-500">No {side}s for this expiration.</p>
      ) : (
        <div className="max-h-80 overflow-y-auto rounded-xl border border-slate-800">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-slate-900 text-left uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-3 py-2">Strike</th>
                <th className="px-3 py-2 text-right">Bid</th>
                <th className="px-3 py-2 text-right">Ask</th>
                <th className="px-3 py-2 text-right">Mark</th>
                <th className="px-3 py-2 text-right">%Chg</th>
                <th className="px-3 py-2 text-right">Vol</th>
                <th className="px-3 py-2 text-right">OI</th>
                <th className="px-3 py-2 text-right">IV</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {rows.map((c) => {
                const selected = c.occ_symbol === selectedOcc;
                return (
                  <tr
                    key={c.occ_symbol}
                    onClick={() => onSelect(c, expiration)}
                    className={`cursor-pointer ${
                      selected
                        ? "bg-emerald-500/15"
                        : c.in_the_money
                          ? "bg-sky-500/5 hover:bg-slate-800/60"
                          : "hover:bg-slate-800/60"
                    }`}
                  >
                    <td className="px-3 py-2 font-semibold text-slate-100">
                      {num(c.strike)}
                      {c.in_the_money && (
                        <span className="ml-1.5 text-[10px] text-sky-400">ITM</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">{num(c.bid)}</td>
                    <td className="px-3 py-2 text-right">{num(c.ask)}</td>
                    <td className="px-3 py-2 text-right font-medium text-slate-100">
                      {num(c.mark)}
                    </td>
                    <td className={`px-3 py-2 text-right ${(c.percent_change ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {c.percent_change == null ? "—" : pct(c.percent_change)}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-400">
                      {c.volume == null ? "—" : c.volume.toLocaleString("en-US")}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-400">
                      {c.open_interest == null ? "—" : c.open_interest.toLocaleString("en-US")}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-400">
                      {c.implied_volatility == null
                        ? "—"
                        : `${(c.implied_volatility * 100).toFixed(1)}%`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
