import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import Avatar from "../components/Avatar";
import type { PublicUser, SearchResult } from "../api/types";

export default function SearchPage() {
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const [results, setResults] = useState<SearchResult[]>([]);
  const [people, setPeople] = useState<PublicUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!q) return;
    setLoading(true);
    setError(null);
    // Symbols and traders are searched together; a failing people search shouldn't hide symbols.
    Promise.allSettled([
      api.get<SearchResult[]>("/market/search", { params: { q } }),
      api.get<PublicUser[]>("/users/search", { params: { q } }),
    ])
      .then(([symbols, users]) => {
        if (symbols.status === "fulfilled") setResults(symbols.value.data);
        else setError(errorMessage(symbols.reason));
        setPeople(users.status === "fulfilled" ? users.value.data : []);
      })
      .finally(() => setLoading(false));
  }, [q]);

  const nothingFound = !loading && !error && results.length === 0 && people.length === 0;

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">
        Results for <span className="text-emerald-400">“{q}”</span>
      </h1>
      {loading && <p className="text-slate-400">Searching…</p>}
      {error && <p className="text-red-400">{error}</p>}
      {nothingFound && <p className="text-slate-500">No matches found.</p>}

      {people.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Traders
          </h2>
          <ul className="divide-y divide-slate-800 overflow-hidden rounded-xl border border-slate-800">
            {people.map((u) => (
              <li key={u.id}>
                <Link
                  to={`/u/${u.username}`}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-slate-900/50"
                >
                  <Avatar username={u.username} displayName={u.display_name} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold">{u.display_name || u.username}</div>
                    <div className="truncate text-xs text-slate-500">
                      @{u.username}
                      {u.bio ? ` · ${u.bio}` : ""}
                    </div>
                  </div>
                  <span className="shrink-0 text-xs text-slate-500">
                    {u.follower_count} {u.follower_count === 1 ? "follower" : "followers"}
                    {u.is_following && <span className="ml-2 text-emerald-400">following</span>}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {results.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Symbols
          </h2>
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
      )}
    </div>
  );
}
