import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { usePortfolios } from "../portfolio/PortfolioContext";

export default function NavBar() {
  const { user, logout } = useAuth();
  const { portfolios, activeId, setActiveId, refresh } = usePortfolios();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    const term = q.trim();
    if (term) navigate(`/search?q=${encodeURIComponent(term)}`);
  }

  async function createPortfolio() {
    const name = window.prompt("Name your new portfolio:");
    if (!name || !name.trim()) return;
    const cashStr = window.prompt("Starting cash:", "100000");
    if (cashStr === null) return;
    const starting_cash = parseFloat(cashStr);
    setBusy(true);
    try {
      const { data } = await api.post<{ id: number }>("/portfolios", {
        name: name.trim(),
        starting_cash: Number.isFinite(starting_cash) && starting_cash > 0 ? starting_cash : undefined,
      });
      await refresh();
      setActiveId(data.id);
      navigate("/");
    } catch (err) {
      window.alert(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function deleteActive() {
    if (activeId == null) return;
    const p = portfolios.find((x) => x.id === activeId);
    if (!window.confirm(`Delete portfolio "${p?.name ?? ""}"? This can't be undone.`)) return;
    setBusy(true);
    try {
      await api.delete(`/portfolios/${activeId}`);
      await refresh();
      navigate("/");
    } catch (err) {
      window.alert(errorMessage(err));
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
          {portfolios.length > 0 && (
            <div className="flex items-center gap-1">
              <select
                value={activeId ?? ""}
                onChange={(e) => setActiveId(Number(e.target.value))}
                disabled={busy}
                title="Switch portfolio"
                className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-emerald-500"
              >
                {portfolios.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <button
                onClick={createPortfolio}
                disabled={busy}
                title="New portfolio"
                className="rounded-md border border-slate-700 px-2 py-1.5 text-slate-300 hover:bg-slate-800 disabled:opacity-50"
              >
                ＋
              </button>
              {portfolios.length > 1 && (
                <button
                  onClick={deleteActive}
                  disabled={busy}
                  title="Delete this portfolio"
                  className="rounded-md border border-slate-700 px-2 py-1.5 text-slate-400 hover:bg-slate-800 hover:text-red-400 disabled:opacity-50"
                >
                  🗑
                </button>
              )}
            </div>
          )}
          <Link to="/" className="text-slate-300 hover:text-white">
            Dashboard
          </Link>
          <Link to="/markets" className="text-slate-300 hover:text-white">
            Markets
          </Link>
          <span className="hidden text-slate-500 sm:inline">{user?.username}</span>
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
    </header>
  );
}
