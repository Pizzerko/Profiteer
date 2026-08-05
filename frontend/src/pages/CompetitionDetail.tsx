import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import Avatar from "../components/Avatar";
import CompetitionBadge from "../components/CompetitionBadge";
import type { Competition, StandingRow } from "../api/types";
import { usePortfolios } from "../portfolio/PortfolioContext";
import { dateTime, money, pct, plClass, timeUntil } from "../utils/format";

const REFRESH_MS = 30_000;

const MEDALS = ["🥇", "🥈", "🥉"];

export default function CompetitionDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { setActiveId, refresh: refreshPortfolios } = usePortfolios();

  const [competition, setCompetition] = useState<Competition | null>(null);
  const [rows, setRows] = useState<StandingRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      // There's no single-competition endpoint; the list already carries the viewer's join state.
      const [list, standings] = await Promise.all([
        api.get<Competition[]>("/competitions"),
        api.get<StandingRow[]>(`/competitions/${id}/standings`),
      ]);
      setCompetition(list.data.find((c) => String(c.id) === id) ?? null);
      setRows(standings.data);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Keep a live contest's standings current; frozen results don't need polling.
  useEffect(() => {
    if (competition?.status !== "active") return;
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [competition?.status, load]);

  async function join() {
    setBusy(true);
    try {
      await api.post(`/competitions/${id}/join`);
      await Promise.all([load(), refreshPortfolios()]);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function leave() {
    if (!window.confirm("Leave this competition? Your entry and its trades will be discarded."))
      return;
    setBusy(true);
    try {
      await api.delete(`/competitions/${id}/leave`);
      await Promise.all([load(), refreshPortfolios()]);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm("Delete this competition? Every entry will be discarded.")) return;
    setBusy(true);
    try {
      await api.delete(`/competitions/${id}`);
      await refreshPortfolios();
      navigate("/competitions");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  /** Point the portfolio switcher at this entry and drop the user on the dashboard to trade it. */
  function tradeEntry() {
    if (competition?.entry_portfolio_id == null) return;
    setActiveId(competition.entry_portfolio_id);
    navigate("/");
  }

  if (loading) return <p className="text-slate-400">Loading competition…</p>;
  if (error && !competition) return <p className="text-red-400">{error}</p>;
  if (!competition) return <p className="text-slate-400">Competition not found.</p>;

  const ended = competition.status === "ended";

  return (
    <div className="space-y-6">
      <Link to="/competitions" className="text-sm text-slate-400 hover:text-white">
        ← All competitions
      </Link>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold">{competition.name}</h1>
          <CompetitionBadge status={competition.status} />
        </div>
        {competition.description && (
          <p className="mt-2 text-sm text-slate-300">{competition.description}</p>
        )}
        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Starting cash</dt>
            <dd className="mt-0.5 font-medium">{money(competition.starting_cash)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Starts</dt>
            <dd className="mt-0.5 font-medium">
              {dateTime(competition.starts_at)}
              {competition.status === "upcoming" && (
                <span className="ml-1 text-xs text-sky-300">{timeUntil(competition.starts_at)}</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Ends</dt>
            <dd className="mt-0.5 font-medium">{dateTime(competition.ends_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Entrants</dt>
            <dd className="mt-0.5 font-medium">{competition.entrants}</dd>
          </div>
        </dl>

        <div className="mt-5 flex flex-wrap gap-2">
          {competition.joined ? (
            <>
              {!ended && (
                <button
                  onClick={tradeEntry}
                  className="rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400"
                >
                  Trade my entry →
                </button>
              )}
              {!ended && (
                <button
                  onClick={leave}
                  disabled={busy}
                  className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-red-400 disabled:opacity-50"
                >
                  Leave
                </button>
              )}
            </>
          ) : (
            !ended && (
              <button
                onClick={join}
                disabled={busy}
                className="rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
              >
                Join competition
              </button>
            )
          )}
          {competition.is_creator && !ended && (
            <button
              onClick={remove}
              disabled={busy}
              className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-red-400 disabled:opacity-50"
            >
              Delete competition
            </button>
          )}
        </div>

        {ended && (
          <p className="mt-4 rounded-md border border-slate-700 bg-slate-800/60 px-3 py-2 text-xs text-slate-400">
            This competition is over. Final standings are frozen at the closing values and entries
            are read-only.
          </p>
        )}
        {competition.status === "upcoming" && competition.joined && (
          <p className="mt-4 rounded-md border border-sky-500/40 bg-sky-500/10 px-3 py-2 text-xs text-sky-200">
            You're in. Trading opens {dateTime(competition.starts_at)}.
          </p>
        )}
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">
          {ended ? "Final standings" : "Standings"}
          {!ended && rows.length > 0 && (
            <span className="ml-2 text-xs font-normal text-slate-500">
              ranked by return · refreshes automatically
            </span>
          )}
        </h2>
        {rows.length === 0 ? (
          <p className="text-sm text-slate-500">No entrants yet.</p>
        ) : (
          <ul className="divide-y divide-slate-800 overflow-hidden rounded-xl border border-slate-800">
            {rows.map((r) => (
              <li
                key={r.username}
                className={`flex items-center gap-3 px-4 py-3 ${
                  r.is_me ? "bg-emerald-500/5" : ""
                }`}
              >
                <span className="w-8 shrink-0 text-center text-sm font-semibold text-slate-400">
                  {r.rank <= 3 ? MEDALS[r.rank - 1] : `#${r.rank}`}
                </span>
                <Avatar username={r.username} displayName={r.display_name} size="sm" />
                <div className="min-w-0 flex-1">
                  <Link to={`/u/${r.username}`} className="text-sm font-medium hover:underline">
                    {r.display_name || r.username}
                  </Link>
                  {r.is_me && <span className="ml-2 text-xs text-emerald-400">you</span>}
                </div>
                <span className={`text-sm font-semibold ${plClass(r.return_percent)}`}>
                  {pct(r.return_percent)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
