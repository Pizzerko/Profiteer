import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import Avatar from "../components/Avatar";
import CompetitionBadge from "../components/CompetitionBadge";
import type { PublicProfile } from "../api/types";
import { pct, plClass } from "../utils/format";

/**
 * Someone's public profile at /u/:username — including your own.
 *
 * Everything here comes from the public projection: symbols, portfolio weights and return
 * percentages. Cash, position sizes and dollar totals are never sent by the API, so there is
 * nothing to hide in the UI.
 */
export default function Profile() {
  const { username = "" } = useParams();
  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get<PublicProfile>(`/users/${username}`);
      setProfile(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [username]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleFollow() {
    if (!profile) return;
    setBusy(true);
    try {
      const { data } = profile.is_following
        ? await api.delete<PublicProfile>(`/users/${profile.username}/follow`)
        : await api.post<PublicProfile>(`/users/${profile.username}/follow`);
      // The follow endpoints return the refreshed public user; keep the profile-only fields.
      setProfile((p) => (p ? { ...p, ...data } : p));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-slate-400">Loading profile…</p>;
  if (error && !profile) return <p className="text-red-400">{error}</p>;
  if (!profile) return null;

  return (
    <div className="space-y-6">
      {error && <p className="text-red-400">{error}</p>}

      <div className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:flex-row sm:items-center">
        <Avatar username={profile.username} displayName={profile.display_name} size="lg" />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold">{profile.display_name || profile.username}</h1>
          <div className="text-sm text-slate-400">@{profile.username}</div>
          {profile.bio && <p className="mt-2 text-sm text-slate-300">{profile.bio}</p>}
          <div className="mt-3 flex gap-4 text-sm text-slate-400">
            <span>
              <span className="font-semibold text-slate-200">{profile.follower_count}</span>{" "}
              {profile.follower_count === 1 ? "follower" : "followers"}
            </span>
            <span>
              <span className="font-semibold text-slate-200">{profile.following_count}</span>{" "}
              following
            </span>
          </div>
        </div>
        {profile.is_me ? (
          <Link
            to="/settings/profile"
            className="shrink-0 rounded-md border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition hover:bg-slate-800"
          >
            Edit profile
          </Link>
        ) : (
          <button
            onClick={toggleFollow}
            disabled={busy}
            className={`shrink-0 rounded-md px-4 py-2 text-sm font-semibold transition disabled:opacity-50 ${
              profile.is_following
                ? "border border-slate-700 text-slate-300 hover:bg-slate-800"
                : "bg-emerald-500 text-slate-950 hover:bg-emerald-400"
            }`}
          >
            {profile.is_following ? "Following" : "Follow"}
          </button>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">
            {profile.portfolio_name ?? "Portfolio"}
            <span className="ml-2 text-xs font-normal uppercase tracking-wide text-slate-500">
              total return
            </span>
          </h2>
          <span className={`text-2xl font-bold ${plClass(profile.total_return_percent)}`}>
            {pct(profile.total_return_percent)}
          </span>
        </div>

        {profile.portfolio_name == null ? (
          <p className="mt-3 text-sm text-slate-500">
            {profile.is_me
              ? "You haven't published a portfolio. Choose one under Edit profile."
              : "This trader hasn't published a portfolio."}
          </p>
        ) : profile.holdings.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">No open positions.</p>
        ) : (
          <table className="mt-4 w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="pb-2">Symbol</th>
                <th className="pb-2 text-right">Weight</th>
                <th className="pb-2 text-right">Return</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {profile.holdings.map((h) => (
                <tr key={h.symbol}>
                  <td className="py-2">
                    <Link
                      to={`/stock/${h.symbol.split(" ")[0]}`}
                      className="font-semibold text-emerald-400 hover:underline"
                    >
                      {h.symbol}
                    </Link>
                  </td>
                  <td className="py-2 text-right text-slate-300">
                    {h.weight_percent == null ? "—" : `${h.weight_percent.toFixed(1)}%`}
                  </td>
                  <td className={`py-2 text-right font-medium ${plClass(h.unrealized_pl_percent)}`}>
                    {pct(h.unrealized_pl_percent)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Competitions</h2>
        {profile.competitions.length === 0 ? (
          <p className="text-sm text-slate-500">Hasn't entered any competitions yet.</p>
        ) : (
          <ul className="divide-y divide-slate-800 overflow-hidden rounded-xl border border-slate-800">
            {profile.competitions.map((c) => (
              <li key={c.competition_id}>
                <Link
                  to={`/competitions/${c.competition_id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-slate-900/50"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{c.name}</span>
                    <CompetitionBadge status={c.status} />
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    <span className="text-slate-400">
                      {c.rank == null ? "—" : `#${c.rank} of ${c.entrants}`}
                    </span>
                    <span className={`font-semibold ${plClass(c.return_percent)}`}>
                      {pct(c.return_percent)}
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
