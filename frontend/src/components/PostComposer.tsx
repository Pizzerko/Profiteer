import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, errorMessage } from "../api/client";
import type { AttachableTrade, Post } from "../api/types";
import { money, qty, timeAgo } from "../utils/format";
import { splitCashtags } from "../utils/cashtags";

const BODY_LIMIT = 1000;
/** Mirrors `PostCreate.trade_refs`' max_length — the server rejects more than this. */
const MAX_ATTACHMENTS = 5;

/** Two arrows passing in opposite directions — the "attach one of my trades" affordance. */
function ExchangeIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M4 8h13" />
      <path d="M13 4l4 4-4 4" />
      <path d="M20 16H7" />
      <path d="M11 12l-4 4 4 4" />
    </svg>
  );
}

/**
 * Write a post, and optionally publish some of your own fills with it.
 *
 * Mounted only once the reader has asked to write something (the feed owns the "+" that opens it),
 * so the page leads with posts rather than with an empty box.
 *
 * The recent-trades list is loaded lazily, the first time you open it: most posts carry no trades,
 * and the endpoint reads both trade ledgers across every portfolio you own.
 */
export default function PostComposer({
  onPosted,
  onClose,
}: {
  onPosted: (post: Post) => void;
  onClose: () => void;
}) {
  const [body, setBody] = useState("");
  const [attaching, setAttaching] = useState(false);
  const [available, setAvailable] = useState<AttachableTrade[] | null>(null);
  const [loadingTrades, setLoadingTrades] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  // Opening the composer is an explicit act, so put the caret where the reader is already looking.
  useEffect(() => {
    bodyRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!attaching || available !== null) return;
    let cancelled = false;
    setLoadingTrades(true);
    api
      .get<AttachableTrade[]>("/community/attachable-trades")
      .then(({ data }) => {
        if (!cancelled) setAvailable(data);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoadingTrades(false);
      });
    return () => {
      cancelled = true;
    };
  }, [attaching, available]);

  function toggle(ref: string) {
    setSelected((current) =>
      current.includes(ref)
        ? current.filter((r) => r !== ref)
        : current.length >= MAX_ATTACHMENTS
          ? current
          : [...current, ref],
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setPosting(true);
    setError(null);
    try {
      const { data } = await api.post<Post>("/community/posts", {
        body: body.trim(),
        trade_refs: selected,
      });
      setBody("");
      setSelected([]);
      setAttaching(false);
      // Drop the cached list: this post may have been about a fill, and the next one probably
      // isn't — but more importantly a new trade could have happened while this form was open.
      setAvailable(null);
      onPosted(data);
      // Fold back down to the "+" — the post is now in the feed above, which is the confirmation.
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPosting(false);
    }
  }

  // Preview the tickers the server will file this under, using the same parse the feed renders
  // with — so "which stock is this about" is answered before posting, not after.
  const symbols = [
    ...new Set(splitCashtags(body).flatMap((s) => (s.kind === "cashtag" ? [s.symbol] : []))),
  ];

  return (
    <form onSubmit={onSubmit} className="space-y-3 rounded-xl border border-slate-800 bg-slate-900 p-4">
      <textarea
        ref={bodyRef}
        value={body}
        onChange={(e) => setBody(e.target.value.slice(0, BODY_LIMIT))}
        onKeyDown={(e) => {
          // Escape backs out, but only from an empty draft — silently discarding typed text on a
          // stray keypress would be worse than making the reader click Cancel.
          if (e.key === "Escape" && !body.trim()) onClose();
        }}
        rows={3}
        placeholder="What's your take? Mention a ticker with $AAPL."
        className="w-full resize-y rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none placeholder:text-slate-500 focus:border-emerald-500"
      />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        {symbols.length > 0 && (
          <span className="text-slate-500">
            About{" "}
            {symbols.map((s) => (
              <span key={s} className="mr-1 font-semibold text-emerald-400">
                ${s}
              </span>
            ))}
          </span>
        )}
        <span className="ml-auto text-slate-500">
          {body.length}/{BODY_LIMIT}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setAttaching((v) => !v)}
          aria-pressed={attaching}
          aria-label="Attach a trade"
          title={attaching ? "Hide my trades" : "Attach a trade"}
          className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 transition ${
            attaching || selected.length > 0
              ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300"
              : "border-slate-700 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          }`}
        >
          <ExchangeIcon />
          {selected.length > 0 && (
            <span className="text-xs font-semibold tabular-nums">{selected.length}</span>
          )}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="ml-auto rounded-md px-3 py-1.5 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={posting || !body.trim()}
          className="rounded-md bg-emerald-500 px-4 py-1.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
        >
          {posting ? "Posting…" : "Post"}
        </button>
      </div>

      {attaching && (
        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
          <p className="mb-2 text-xs text-slate-500">
            Attaching a trade publishes its size and fill price — the only thing on Profiteer that
            does. Pick up to {MAX_ATTACHMENTS}.
          </p>
          {loadingTrades ? (
            <p className="text-sm text-slate-400">Loading your trades…</p>
          ) : available && available.length === 0 ? (
            <p className="text-sm text-slate-500">You haven't made any trades yet.</p>
          ) : (
            <ul className="max-h-64 space-y-1 overflow-y-auto">
              {available?.map((t) => {
                const checked = selected.includes(t.ref);
                const bought = t.side === "buy";
                const unit = t.kind === "option" ? "contract" : "share";
                return (
                  <li key={t.ref}>
                    <label
                      className={`flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-2 text-sm transition ${
                        checked
                          ? "border-emerald-500/50 bg-emerald-500/10"
                          : "border-transparent hover:bg-slate-800/60"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggle(t.ref)}
                        disabled={!checked && selected.length >= MAX_ATTACHMENTS}
                        className="h-4 w-4 shrink-0 rounded border-slate-600 bg-slate-800 text-emerald-500 focus:ring-0 disabled:opacity-40"
                      />
                      <span className={`font-semibold ${bought ? "text-emerald-400" : "text-red-400"}`}>
                        {bought ? "Bought" : "Sold"}
                      </span>
                      <span className="min-w-0 truncate text-slate-200">
                        {qty(t.quantity)} {unit}
                        {t.quantity === 1 ? "" : "s"} {t.label}
                      </span>
                      <span className="shrink-0 text-slate-400">@ {money(t.price)}</span>
                      <span className="ml-auto shrink-0 text-xs text-slate-500">
                        {t.portfolio_name} · {timeAgo(t.executed_at)}
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}
    </form>
  );
}
