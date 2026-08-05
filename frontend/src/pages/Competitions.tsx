import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import CompetitionBadge from "../components/CompetitionBadge";
import type { Competition } from "../api/types";
import { usePortfolios } from "../portfolio/PortfolioContext";
import { dateTime, money, timeUntil } from "../utils/format";

/** `datetime-local` wants "YYYY-MM-DDTHH:mm" in the browser's own timezone. */
function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

const NOW = new Date();
const IN_A_WEEK = new Date(NOW.getTime() + 7 * 24 * 60 * 60 * 1000);

export default function Competitions() {
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [startingCash, setStartingCash] = useState("100000");
  const [startsAt, setStartsAt] = useState(toLocalInput(NOW));
  const [endsAt, setEndsAt] = useState(toLocalInput(IN_A_WEEK));
  const [creating, setCreating] = useState(false);

  // Joining and leaving create/remove an entry portfolio, so the switcher has to refresh too.
  const { refresh: refreshPortfolios } = usePortfolios();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get<Competition[]>("/competitions");
      setCompetitions(data);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const cash = parseFloat(startingCash);
      await api.post<Competition>("/competitions", {
        name: name.trim(),
        description: description.trim() || null,
        starting_cash: Number.isFinite(cash) && cash > 0 ? cash : 100000,
        // Send UTC — the inputs are local time.
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
      });
      setName("");
      setDescription("");
      setShowForm(false);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  async function join(c: Competition) {
    setBusyId(c.id);
    setError(null);
    try {
      await api.post(`/competitions/${c.id}/join`);
      await Promise.all([load(), refreshPortfolios()]);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function leave(c: Competition) {
    if (!window.confirm(`Leave "${c.name}"? Your entry and its trades will be discarded.`)) return;
    setBusyId(c.id);
    setError(null);
    try {
      await api.delete(`/competitions/${c.id}/leave`);
      await Promise.all([load(), refreshPortfolios()]);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Competitions</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition hover:bg-slate-800"
        >
          {showForm ? "Cancel" : "Host a competition"}
        </button>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {showForm && (
        <form onSubmit={onCreate} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div>
            <label htmlFor="c-name" className="mb-1 block text-sm text-slate-300">
              Name
            </label>
            <input
              id="c-name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              placeholder="Summer Cup"
              className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none placeholder:text-slate-500 focus:border-emerald-500"
            />
          </div>
          <div>
            <label htmlFor="c-desc" className="mb-1 block text-sm text-slate-300">
              Description <span className="text-slate-500">(optional)</span>
            </label>
            <input
              id="c-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={500}
              className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-emerald-500"
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="c-cash" className="mb-1 block text-sm text-slate-300">
                Starting cash
              </label>
              <input
                id="c-cash"
                type="number"
                min="1"
                step="1000"
                value={startingCash}
                onChange={(e) => setStartingCash(e.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-emerald-500"
              />
            </div>
            <div>
              <label htmlFor="c-start" className="mb-1 block text-sm text-slate-300">
                Starts
              </label>
              <input
                id="c-start"
                type="datetime-local"
                required
                value={startsAt}
                onChange={(e) => setStartsAt(e.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-emerald-500"
              />
            </div>
            <div>
              <label htmlFor="c-end" className="mb-1 block text-sm text-slate-300">
                Ends
              </label>
              <input
                id="c-end"
                type="datetime-local"
                required
                value={endsAt}
                onChange={(e) => setEndsAt(e.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-emerald-500"
              />
            </div>
          </div>
          <p className="text-xs text-slate-500">
            Every entrant gets a fresh portfolio with the same starting cash, so standings rank on
            return alone. Trading is only possible between the start and end times.
          </p>
          <button
            type="submit"
            disabled={creating}
            className="rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create"}
          </button>
        </form>
      )}

      {loading ? (
        <p className="text-slate-400">Loading competitions…</p>
      ) : competitions.length === 0 ? (
        <p className="text-sm text-slate-500">
          No competitions yet. Host one and invite the traders you follow.
        </p>
      ) : (
        <ul className="space-y-3">
          {competitions.map((c) => (
            <li
              key={c.id}
              className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900 p-4 sm:flex-row sm:items-center"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Link to={`/competitions/${c.id}`} className="font-semibold hover:underline">
                    {c.name}
                  </Link>
                  <CompetitionBadge status={c.status} />
                  {c.joined && (
                    <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-300">
                      Joined
                    </span>
                  )}
                </div>
                {c.description && (
                  <p className="mt-1 truncate text-sm text-slate-400">{c.description}</p>
                )}
                <div className="mt-1 text-xs text-slate-500">
                  {money(c.starting_cash)} start · {c.entrants}{" "}
                  {c.entrants === 1 ? "entrant" : "entrants"} · hosted by @{c.creator_username}
                  {c.status === "upcoming" && ` · starts ${timeUntil(c.starts_at)}`}
                  {c.status === "active" && ` · ends ${dateTime(c.ends_at)}`}
                  {c.status === "ended" && ` · ended ${dateTime(c.ends_at)}`}
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                <Link
                  to={`/competitions/${c.id}`}
                  className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition hover:bg-slate-800"
                >
                  Standings
                </Link>
                {c.joined ? (
                  c.status !== "ended" && (
                    <button
                      onClick={() => leave(c)}
                      disabled={busyId === c.id}
                      className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-red-400 disabled:opacity-50"
                    >
                      Leave
                    </button>
                  )
                ) : (
                  c.status !== "ended" && (
                    <button
                      onClick={() => join(c)}
                      disabled={busyId === c.id}
                      className="rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
                    >
                      Join
                    </button>
                  )
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
