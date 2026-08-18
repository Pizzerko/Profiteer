import { useEffect, useState, type FormEvent } from "react";
import Modal from "./Modal";

const DEFAULT_CASH = "100000";

/**
 * Create a portfolio.
 *
 * Replaces two chained `window.prompt`s, which had no way to show what was wrong with an entry:
 * a non-numeric starting balance was silently swallowed, and cancelling the second prompt threw
 * away the name typed into the first. Both fields are visible at once here, and the server's
 * error comes back into the form rather than into an `alert`.
 */
export default function NewPortfolioDialog({
  open,
  busy,
  onClose,
  onCreate,
}: {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  /** Rejects with a message to display in the form; resolves once the portfolio exists. */
  onCreate: (name: string, startingCash: number) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [cash, setCash] = useState(DEFAULT_CASH);
  const [error, setError] = useState<string | null>(null);

  // Reopening should be a blank form, not the last attempt's leftovers.
  useEffect(() => {
    if (open) {
      setName("");
      setCash(DEFAULT_CASH);
      setError(null);
    }
  }, [open]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Give the portfolio a name.");
      return;
    }
    const startingCash = Number(cash);
    if (!Number.isFinite(startingCash) || startingCash <= 0) {
      setError("Starting cash must be a number greater than zero.");
      return;
    }
    setError(null);
    try {
      await onCreate(trimmed, startingCash);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <Modal open={open} onClose={onClose} labelledBy="new-portfolio-title">
      <form onSubmit={onSubmit}>
        <h2 id="new-portfolio-title" className="text-base font-semibold text-white">
          New portfolio
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          A separate book with its own cash, holdings, and trade history.
        </p>

        <label className="mt-4 block text-xs font-medium text-slate-400" htmlFor="portfolio-name">
          Name
        </label>
        <input
          id="portfolio-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          maxLength={60}
          placeholder="Swing trades"
          className="mt-1 w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none placeholder:text-slate-500 focus:border-emerald-500"
        />

        <label className="mt-3 block text-xs font-medium text-slate-400" htmlFor="portfolio-cash">
          Starting cash
        </label>
        <input
          id="portfolio-cash"
          value={cash}
          onChange={(e) => setCash(e.target.value)}
          inputMode="decimal"
          className="mt-1 w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-emerald-500"
        />

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
          >
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
