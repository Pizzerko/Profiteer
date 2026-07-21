import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import type { SearchResult } from "../api/types";

export default function SearchPage() {
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!q) return;
    setLoading(true);
    setError(null);
    api
      .get<SearchResult[]>("/market/search", { params: { q } })
      .then((r) => setResults(r.data))
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }, [q]);

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">
        Results for <span className="text-emerald-400">“{q}”</span>
      </h1>
      {loading && <p className="text-slate-400">Searching…</p>}
      {error && <p className="text-red-400">{error}</p>}
      {!loading && !error && results.length === 0 && (
        <p className="text-slate-500">No matches found.</p>
      )}
      <ul className="divide-y divide-slate-800 overflow-hidden rounded-xl border border-slate-800">
        {results.map((r) => (
          <li key={r.symbol}>
            <Link
              to={`/stock/${r.symbol}`}
              className="flex items-center justify-between px-4 py-3 hover:bg-slate-900/50"
            >
              <div>
                <span className="font-semibold text-emerald-400">{r.symbol}</span>
                <span className="ml-2 text-sm text-slate-300">{r.name}</span>
              </div>
              <span className="text-xs text-slate-500">
                {r.exchange} {r.type ? `· ${r.type}` : ""}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
