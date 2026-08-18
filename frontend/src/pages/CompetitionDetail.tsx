import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import Avatar from "../components/Avatar";
import CompetitionBadge from "../components/CompetitionBadge";
import type { Competition, CompetitionInvite, StandingRow } from "../api/types";
import { usePortfolios } from "../portfolio/PortfolioContext";
import { dateTime, money, pct, plClass, timeUntil } from "../utils/format";

const REFRESH_MS = 30_000;

const MEDALS = ["🥇", "🥈", "🥉"];

const INVITE_STYLES: Record<string, string> = {
  pending: "text-sky-300",
  accepted: "text-emerald-400",
  declined: "text-slate-500",
};

export default function CompetitionDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { setActiveId, refresh: refreshPortfolios } = usePortfolios();

  const [competition, setCompetition] = useState<Competition | null>(null);
  const [rows, setRows] = useState<StandingRow[]>([]);
  const [invites, setInvites] = useState<CompetitionInvite[]>([]);
  const [inviteName, setInviteName] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteNote, setInviteNote] = useState<string | null>(null);
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
      const found = list.data.find((c) => String(c.id) === id) ?? null;
      setCompetition(found);
      setRows(standings.data);
      setError(null);
      // The guest list is the host's alone — asking for it as anyone else would 403.
      if (found?.is_creator) {
        const { data } = await api.get<CompetitionInvite[]>(`/competitions/${id}/invites`);
        setInvites(data);
      } else {
        setInvites([]);
      }
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

  async function declineInvite() {
    setBusy(true);
    try {
      await api.post(`/competitions/${id}/invites/decline`);
      await load();
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

  async function sendInvite(e: FormEvent) {
    e.preventDefault();
    const username = inviteName.trim().replace(/^@/, "");
    if (!username) return;
    setInviting(true);
    setInviteError(null);
    setInviteNote(null);
    try {
      await api.post(`/competitions/${id}/invites`, { username });
      setInviteName("");
      setInviteNote(`Invited @${username}.`);
      await load();
    } catch (err) {
      setInviteError(errorMessage(err));
    } finally {
      setInviting(false);
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
  const isPrivate = competition.visibility === "private";

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
          {isPrivate && (
            <span className="rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              🔒 Private
            </span>
          )}
        </div>
        {competition.description && (
          <p className="mt-2 text-sm text-slate-300">{competition.description}</p>
        )}
        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-5">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Starting cash</dt>
            <dd className="mt-0.5 font-medium">{money(competition.starting_cash)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Length</dt>
            <dd className="mt-0.5 font-medium capitalize">1 {competition.timeframe}</dd>
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

        <p className="mt-4 text-xs text-slate-500">
          {competition.ranked
            ? `Winning counts toward the winner's ${competition.timeframe} record.`
            : "A friendly — the result won't affect anyone's record."}
        </p>

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
              <>
                {competition.can_join && (
                  <button
                    onClick={join}
                    disabled={busy}
                    className="rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
                  >
                    {competition.invite_status === "pending"
                      ? "Accept invite"
                      : "Join competition"}
                  </button>
                )}
                {competition.invite_status === "pending" && (
                  <button
                    onClick={declineInvite}
                    disabled={busy}
                    className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-red-400 disabled:opacity-50"
                  >
                    Decline
                  </button>
                )}
              </>
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
        {!competition.joined && isPrivate && competition.invite_status === "declined" && (
          <p className="mt-4 rounded-md border border-slate-700 bg-slate-800/60 px-3 py-2 text-xs text-slate-400">
            You declined this invite. The host can send another one.
          </p>
        )}
      </div>

      {competition.is_creator && isPrivate && !ended && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <h2 className="text-lg font-semibold">Invites</h2>
          <p className="mt-1 text-xs text-slate-500">
            This lobby is invite-only. Everyone you invite gets a notification they can accept from
            anywhere in the app.
          </p>

          <form onSubmit={sendInvite} className="mt-4 flex gap-2">
            <input
              value={inviteName}
              onChange={(e) => setInviteName(e.target.value)}
              placeholder="Username"
              maxLength={50}
              className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none placeholder:text-slate-500 focus:border-emerald-500"
            />
            <button
              type="submit"
              disabled={inviting || !inviteName.trim()}
              className="shrink-0 rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
            >
              {inviting ? "Sending…" : "Invite"}
            </button>
          </form>
          {inviteError && <p className="mt-2 text-sm text-red-400">{inviteError}</p>}
          {inviteNote && <p className="mt-2 text-sm text-emerald-400">{inviteNote}</p>}

          {invites.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">Nobody invited yet.</p>
          ) : (
            <ul className="mt-4 divide-y divide-slate-800 overflow-hidden rounded-lg border border-slate-800">
              {invites.map((i) => (
                <li key={i.id} className="flex items-center gap-3 px-3 py-2">
                  <Avatar username={i.username} displayName={i.display_name} size="sm" />
                  <Link
                    to={`/u/${i.username}`}
                    className="min-w-0 flex-1 truncate text-sm hover:underline"
                  >
                    {i.display_name || i.username}
                    <span className="ml-1 text-xs text-slate-500">@{i.username}</span>
                  </Link>
                  <span
                    className={`text-xs font-medium capitalize ${
                      INVITE_STYLES[i.status] ?? "text-slate-400"
                    }`}
                  >
                    {i.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

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
