import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import CompetitionBadge from "../components/CompetitionBadge";
import { useConfirm } from "../components/ConfirmProvider";
import type { Competition, Timeframe, Visibility } from "../api/types";
import { usePortfolios } from "../portfolio/PortfolioContext";
import { dateTime, money, timeUntil } from "../utils/format";

/** `datetime-local` wants "YYYY-MM-DDTHH:mm" in the browser's own timezone. */
function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

/**
 * Whether a local `datetime-local` value falls inside a regular US session.
 *
 * Mirrors the server's rule (Mon–Fri, 9:30–16:00 ET) so the host is told *before* submitting rather
 * than by a rejection. The server remains the authority — this only saves a round trip, and it uses
 * the same Intl timezone data the browser already ships, so it can't drift from ET as DST shifts.
 */
function isMarketHours(local: string): boolean {
  const d = new Date(local);
  if (Number.isNaN(d.getTime())) return false;
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  if (["Sat", "Sun"].includes(get("weekday"))) return false;
  const minutes = Number(get("hour")) * 60 + Number(get("minute"));
  return minutes >= 9 * 60 + 30 && minutes < 16 * 60;
}

/**
 * A sensible default start: now if the market is open, else the next time it is.
 *
 * Found by stepping forward in 15-minute jumps rather than by computing the next open directly —
 * the same `isMarketHours` predicate then decides both the default and the validation, so the two
 * can't disagree, and there's no second piece of ET/DST arithmetic to get wrong. The 9:30 boundary
 * is on a 15-minute grid, so stepping from a rounded start always lands on it exactly.
 */
function defaultStart(): string {
  const d = new Date();
  d.setSeconds(0, 0);
  d.setMinutes(Math.floor(d.getMinutes() / 15) * 15);
  // A week of quarter-hours is far more than enough to clear any weekend.
  for (let i = 0; i < 4 * 24 * 7; i++) {
    const candidate = toLocalInput(d);
    if (isMarketHours(candidate)) return candidate;
    d.setMinutes(d.getMinutes() + 15);
  }
  return toLocalInput(new Date());
}

const TIMEFRAMES: { value: Timeframe; label: string; hint: string }[] = [
  { value: "day", label: "1 day", hint: "24 hours from the start" },
  { value: "week", label: "1 week", hint: "7 days from the start" },
  { value: "month", label: "1 month", hint: "30 days from the start" },
];

const TABS: { value: Visibility; label: string; blurb: string }[] = [
  { value: "public", label: "Public", blurb: "Open contests anyone can enter." },
  {
    value: "private",
    label: "Private",
    blurb: "Invite-only lobbies you host or were invited to.",
  },
];

export default function Competitions() {
  const confirm = useConfirm();
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [tab, setTab] = useState<Visibility>("public");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [startingCash, setStartingCash] = useState("100000");
  const [startsAt, setStartsAt] = useState(defaultStart);
  const [timeframe, setTimeframe] = useState<Timeframe>("week");
  const [visibility, setVisibility] = useState<Visibility>("public");
  const [ranked, setRanked] = useState(true);
  const [creating, setCreating] = useState(false);

  // Joining and leaving create/remove an entry portfolio, so the switcher has to refresh too.
  const { refresh: refreshPortfolios } = usePortfolios();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get<Competition[]>("/competitions", {
        params: { visibility: tab },
      });
      setCompetitions(data);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    load();
  }, [load]);

  /** Opening the host form on the Private tab pre-selects a private lobby — that's why you're here. */
  function toggleForm() {
    if (!showForm) {
      setVisibility(tab);
      // Recompute the start: the default is time-sensitive, and a stale one from a form opened
      // before the bell would be rejected.
      setStartsAt(defaultStart());
    }
    setShowForm((v) => !v);
  }

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
        // Send UTC — the input is local time. No end date: the server derives it from the timeframe.
        starts_at: new Date(startsAt).toISOString(),
        timeframe,
        visibility,
        ranked,
      });
      setName("");
      setDescription("");
      setShowForm(false);
      // Land on the tab the new contest actually lives in, so it's visible straight away.
      if (visibility !== tab) setTab(visibility);
      else await load();
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
    const ok = await confirm({
      title: `Leave "${c.name}"?`,
      message: "Your entry and every trade you made in it will be discarded.",
      confirmLabel: "Leave",
      danger: true,
    });
    if (!ok) return;
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

  const startOk = isMarketHours(startsAt);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Competitions</h1>
        <button
          onClick={toggleForm}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition hover:bg-slate-800"
        >
          {showForm ? "Cancel" : "Host a competition"}
        </button>
      </div>

      <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-900 p-1">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition ${
              tab === t.value
                ? "bg-slate-800 text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {t.label}
          </button>
        ))}
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

          <div>
            <span className="mb-1 block text-sm text-slate-300">Who can join</span>
            <div className="grid grid-cols-2 gap-2">
              {TABS.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setVisibility(t.value)}
                  className={`rounded-md border px-3 py-2 text-left text-sm transition ${
                    visibility === t.value
                      ? "border-emerald-500 bg-emerald-500/10 text-emerald-200"
                      : "border-slate-700 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  <span className="block font-medium">{t.label}</span>
                  <span className="mt-0.5 block text-xs text-slate-500">
                    {t.value === "public" ? "Anyone can enter." : "Only people you invite."}
                  </span>
                </button>
              ))}
            </div>
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
                className={`w-full rounded-md border bg-slate-800 px-3 py-2 text-sm outline-none ${
                  startOk ? "border-slate-700 focus:border-emerald-500" : "border-red-500/60"
                }`}
              />
            </div>
            <div>
              <label htmlFor="c-timeframe" className="mb-1 block text-sm text-slate-300">
                Length
              </label>
              <select
                id="c-timeframe"
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value as Timeframe)}
                className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 outline-none focus:border-emerald-500"
              >
                {TIMEFRAMES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {!startOk && (
            <p className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
              Competitions can only start while the market is open — a weekday between 9:30 AM and
              4:00 PM ET.
            </p>
          )}

          <label className="flex cursor-pointer items-start gap-2">
            <input
              type="checkbox"
              checked={ranked}
              onChange={(e) => setRanked(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-800 text-emerald-500 focus:ring-0"
            />
            <span className="text-sm text-slate-300">
              Count the win on players' stats
              <span className="mt-0.5 block text-xs text-slate-500">
                The winner gets a {timeframe} win on their profile. Uncheck for a friendly that
                doesn't affect anyone's record.
              </span>
            </span>
          </label>

          <p className="text-xs text-slate-500">
            Every entrant gets a fresh portfolio with the same starting cash, so standings rank on
            return alone. The contest ends {TIMEFRAMES.find((t) => t.value === timeframe)?.hint},
            and trading is only possible in between.
          </p>
          <button
            type="submit"
            disabled={creating || !startOk}
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
          {tab === "public"
            ? "No public competitions yet. Host one and anyone can enter."
            : "No private lobbies. Host one and invite the traders you follow, or wait for an invite."}
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
                  {c.visibility === "private" && (
                    <span className="rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      🔒 Private
                    </span>
                  )}
                  {!c.ranked && (
                    <span className="rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Unranked
                    </span>
                  )}
                  {c.joined && (
                    <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-300">
                      Joined
                    </span>
                  )}
                  {!c.joined && c.invite_status === "pending" && (
                    <span className="rounded-full border border-sky-500/40 bg-sky-500/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-sky-300">
                      Invited
                    </span>
                  )}
                </div>
                {c.description && (
                  <p className="mt-1 truncate text-sm text-slate-400">{c.description}</p>
                )}
                <div className="mt-1 text-xs text-slate-500">
                  {money(c.starting_cash)} start · {c.timeframe}-long · {c.entrants}{" "}
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
                {c.joined
                  ? c.status !== "ended" && (
                      <button
                        onClick={() => leave(c)}
                        disabled={busyId === c.id}
                        className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-red-400 disabled:opacity-50"
                      >
                        Leave
                      </button>
                    )
                  : c.can_join && (
                      <button
                        onClick={() => join(c)}
                        disabled={busyId === c.id}
                        className="rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
                      >
                        {c.invite_status === "pending" ? "Accept invite" : "Join"}
                      </button>
                    )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
