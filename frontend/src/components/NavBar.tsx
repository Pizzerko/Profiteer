import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { usePortfolios } from "../portfolio/PortfolioContext";
import { useConfirm } from "./ConfirmProvider";
import NewPortfolioDialog from "./NewPortfolioDialog";
import NotificationBell from "./NotificationBell";

export default function NavBar() {
  const { user, logout } = useAuth();
  const { portfolios, activeId, setActiveId, refresh } = usePortfolios();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    const term = q.trim();
    if (term) navigate(`/search?q=${encodeURIComponent(term)}`);
  }

  // Throws on failure so the dialog can show the reason in the form it came from.
  async function createPortfolio(name: string, starting_cash: number) {
    setBusy(true);
    try {
      const { data } = await api.post<{ id: number }>("/portfolios", { name, starting_cash });
      await refresh();
      setActiveId(data.id);
      setCreating(false);
      navigate("/");
    } catch (err) {
      throw new Error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  // Competition entries live in their own group: they're portfolios you trade, but you can't
  // rename or delete them (you leave the competition instead).
  const ownPortfolios = portfolios.filter((p) => p.competition_id == null);
  const entries = portfolios.filter((p) => p.competition_id != null);
  const active = portfolios.find((p) => p.id === activeId);
  const canDeleteActive = active != null && active.competition_id == null && ownPortfolios.length > 1;

  async function deleteActive() {
    if (activeId == null) return;
    const p = portfolios.find((x) => x.id === activeId);
    const ok = await confirm({
      title: `Delete "${p?.name ?? ""}"?`,
      message: "Its holdings, trades, and open orders go with it. This can't be undone.",
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      await api.delete(`/portfolios/${activeId}`);
      await refresh();
      navigate("/");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
        <Link to="/" className="text-lg font-bold tracking-tight text-emerald-400">
          Profiteer
        </Link>
        <form onSubmit={onSearch} className="flex-1">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search a symbol or company (e.g. AAPL, Tesla)…"
            className="w-full max-w-md rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm outline-none placeholder:text-slate-500 focus:border-emerald-500"
          />
        </form>
        <nav className="flex items-center gap-3 text-sm">
          <Link to="/" className="text-slate-300 hover:text-white">
            Dashboard
          </Link>
          <Link to="/markets" className="text-slate-300 hover:text-white">
            Markets
          </Link>
          <Link to="/community" className="text-slate-300 hover:text-white">
            Community
          </Link>
          <Link to="/competitions" className="text-slate-300 hover:text-white">
            Competitions
          </Link>
          <NotificationBell />
          {user && (
            <Link
              to={`/u/${user.username}`}
              className="hidden text-slate-400 hover:text-white sm:inline"
              title="Your profile"
            >
              @{user.username}
            </Link>
          )}
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-slate-300 hover:bg-slate-800"
          >
            Log out
          </button>
        </nav>
      </div>

      {/*
        Portfolios read as tabs under the main bar rather than as a dropdown on the right: which
        book you're trading is persistent context for every page below, so it should be visible at
        a glance instead of one click away. The underline marks the one being displayed.
      */}
      {portfolios.length > 0 && (
        <div className="border-t border-slate-800/60">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-1 px-4">
            {/* Wraps onto a second line rather than scrolling: a horizontal scrollbar hides
                portfolios behind a gesture, and these are meant to be visible at a glance. */}
            <div className="flex flex-wrap items-center gap-1">
              {[...ownPortfolios, ...entries].map((p) => {
                const isActive = p.id === activeId;
                return (
                  <button
                    key={p.id}
                    onClick={() => setActiveId(p.id)}
                    disabled={busy}
                    aria-current={isActive ? "true" : undefined}
                    title={p.competition_id != null ? `Competition entry: ${p.name}` : p.name}
                    className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm transition disabled:opacity-50 ${
                      isActive
                        ? "border-emerald-400 font-semibold text-white"
                        : "border-transparent text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {p.competition_id != null && <span className="mr-1">🏆</span>}
                    {p.name}
                  </button>
                );
              })}
            </div>
            <button
              onClick={() => setCreating(true)}
              disabled={busy}
              aria-label="New portfolio"
              title="New portfolio"
              className="my-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-slate-700 text-base leading-none text-slate-300 transition hover:border-emerald-500/50 hover:bg-emerald-500/10 hover:text-emerald-300 disabled:opacity-50"
            >
              +
            </button>
            {canDeleteActive && (
              <button
                onClick={deleteActive}
                disabled={busy}
                aria-label={`Delete portfolio "${active?.name ?? ""}"`}
                title={`Delete "${active?.name ?? ""}"`}
                className="my-1 ml-auto flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-lg leading-none text-red-500/70 transition hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
              >
                ×
              </button>
            )}
          </div>
          {error && (
            <div className="mx-auto max-w-6xl px-4 pb-2">
              <p className="text-xs text-red-400">
                {error}{" "}
                <button
                  onClick={() => setError(null)}
                  className="underline transition hover:text-red-300"
                >
                  Dismiss
                </button>
              </p>
            </div>
          )}
        </div>
      )}

      <NewPortfolioDialog
        open={creating}
        busy={busy}
        onClose={() => setCreating(false)}
        onCreate={createPortfolio}
      />
    </header>
  );
}
