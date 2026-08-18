import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import type { AppNotification } from "../api/types";
import { usePortfolios } from "../portfolio/PortfolioContext";
import { timeAgo } from "../utils/format";

/** How often the navbar re-checks the unread count. A single COUNT server-side. */
const POLL_MS = 60_000;

const ICONS: Record<AppNotification["kind"], string> = {
  competition_invite: "✉️",
  competition_result: "🏆",
  invite_accepted: "👤",
};

/**
 * The bell in the navbar: an unread badge, and a panel of recent notifications.
 *
 * Only the *count* is polled. The list itself is fetched when the panel opens, so the common case
 * — a user who never opens it — costs one cheap query a minute rather than a full projection.
 *
 * A pending invite is answered from here: Accept posts the same `/join` the competition page uses,
 * so acceptance goes through one code path no matter where the user clicks it.
 */
export default function NotificationBell() {
  const navigate = useNavigate();
  const { refresh: refreshPortfolios } = usePortfolios();

  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(0);
  const [items, setItems] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const loadCount = useCallback(async () => {
    try {
      const { data } = await api.get<{ count: number }>("/notifications/unread-count");
      setCount(data.count);
    } catch {
      // A failed count is not worth surfacing — the badge just stays as it was.
    }
  }, []);

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get<AppNotification[]>("/notifications");
      setItems(data);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCount();
    const t = setInterval(loadCount, POLL_MS);
    return () => clearInterval(t);
  }, [loadCount]);

  // Close on an outside click or Escape, so the panel behaves like every other dropdown.
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) loadItems();
  }

  async function markAllRead() {
    try {
      await api.post("/notifications/read-all");
      setItems((xs) => xs.map((x) => ({ ...x, read: true })));
      setCount(0);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  /** Mark read, close, and go wherever the notification points. */
  async function openNotification(n: AppNotification) {
    if (!n.read) {
      try {
        await api.post(`/notifications/${n.id}/read`);
        setCount((c) => Math.max(0, c - 1));
        setItems((xs) => xs.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
      } catch {
        // Navigating matters more than the read flag; a failure here is silent.
      }
    }
    if (n.competition_id != null) {
      setOpen(false);
      navigate(`/competitions/${n.competition_id}`);
    }
  }

  async function respond(n: AppNotification, accept: boolean) {
    if (n.competition_id == null) return;
    setBusyId(n.id);
    setError(null);
    try {
      if (accept) {
        await api.post(`/competitions/${n.competition_id}/join`);
        await refreshPortfolios(); // the entry portfolio shows up in the switcher
      } else {
        await api.post(`/competitions/${n.competition_id}/invites/decline`);
      }
      await Promise.all([loadItems(), loadCount()]);
      if (accept) {
        setOpen(false);
        navigate(`/competitions/${n.competition_id}`);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div ref={wrapRef} className="relative">
      <button
        onClick={toggle}
        title="Notifications"
        aria-label={count > 0 ? `Notifications (${count} unread)` : "Notifications"}
        className="relative rounded-md border border-slate-700 px-2 py-1.5 text-slate-300 transition hover:bg-slate-800"
      >
        🔔
        {count > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-emerald-500 px-1 text-[10px] font-bold text-slate-950">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            {items.some((x) => !x.read) && (
              <button
                onClick={markAllRead}
                className="text-xs text-slate-400 transition hover:text-emerald-400"
              >
                Mark all read
              </button>
            )}
          </div>

          {error && <p className="px-4 py-2 text-xs text-red-400">{error}</p>}

          <div className="max-h-96 overflow-y-auto">
            {loading ? (
              <p className="px-4 py-6 text-center text-sm text-slate-500">Loading…</p>
            ) : items.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-slate-500">Nothing yet.</p>
            ) : (
              <ul className="divide-y divide-slate-800">
                {items.map((n) => (
                  <li
                    key={n.id}
                    className={`px-4 py-3 ${n.read ? "" : "bg-emerald-500/5"}`}
                  >
                    <button
                      onClick={() => openNotification(n)}
                      className="flex w-full gap-2 text-left"
                    >
                      <span className="shrink-0" aria-hidden>
                        {ICONS[n.kind] ?? "🔔"}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium leading-snug">{n.title}</span>
                        {n.body && (
                          <span className="mt-0.5 block text-xs text-slate-400">{n.body}</span>
                        )}
                        <span className="mt-1 block text-[11px] text-slate-500">
                          {timeAgo(n.created_at)}
                        </span>
                      </span>
                      {!n.read && (
                        <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-emerald-400" />
                      )}
                    </button>

                    {n.actionable && (
                      <div className="mt-2 flex gap-2 pl-6">
                        <button
                          onClick={() => respond(n, true)}
                          disabled={busyId === n.id}
                          className="rounded-md bg-emerald-500 px-3 py-1 text-xs font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
                        >
                          Accept
                        </button>
                        <button
                          onClick={() => respond(n, false)}
                          disabled={busyId === n.id}
                          className="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-red-400 disabled:opacity-50"
                        >
                          Decline
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
