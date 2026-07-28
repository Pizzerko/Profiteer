import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  function onSearch(e: FormEvent) {
    e.preventDefault();
    const term = q.trim();
    if (term) navigate(`/search?q=${encodeURIComponent(term)}`);
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
        <nav className="flex items-center gap-4 text-sm">
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
