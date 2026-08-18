import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import Modal from "./Modal";

export interface ConfirmOptions {
  title: string;
  /** The consequence, spelled out. Most of these actions discard something irreversibly. */
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Styles the action red and focuses Cancel instead. True for anything that destroys data. */
  danger?: boolean;
}

const ConfirmContext = createContext<(options: ConfirmOptions) => Promise<boolean>>(null!);

/**
 * `const confirm = useConfirm()` → `if (!(await confirm({ ... }))) return;`
 *
 * Promise-based on purpose: it keeps the guard at each call site a single line, exactly as
 * `window.confirm` did, so replacing the browser dialogs didn't mean restructuring the handlers
 * that used them into callback chains.
 */
// eslint-disable-next-line react-refresh/only-export-components
export const useConfirm = () => useContext(ConfirmContext);

/** Owns the one confirmation dialog the app renders, and the promise the caller is awaiting. */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<{
    options: ConfirmOptions;
    resolve: (value: boolean) => void;
  } | null>(null);

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => setPending({ options, resolve })),
    [],
  );

  // Settling always clears the dialog, so a dismissed prompt can't leave its caller awaiting
  // forever — closing resolves `false`, which reads the same as clicking Cancel.
  function settle(value: boolean) {
    if (!pending) return;
    pending.resolve(value);
    setPending(null);
  }

  const options = pending?.options;
  const danger = options?.danger ?? false;

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Modal open={pending !== null} onClose={() => settle(false)} labelledBy="confirm-title">
        <h2 id="confirm-title" className="text-base font-semibold text-white">
          {options?.title}
        </h2>
        {options?.message && (
          <div className="mt-2 text-sm text-slate-400">{options.message}</div>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => settle(false)}
            // Focused by default for destructive actions: Enter and Escape should both back out
            // of something that can't be undone.
            autoFocus={danger}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition hover:bg-slate-800"
          >
            {options?.cancelLabel ?? "Cancel"}
          </button>
          <button
            type="button"
            onClick={() => settle(true)}
            autoFocus={!danger}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold transition ${
              danger
                ? "bg-red-500 text-white hover:bg-red-400"
                : "bg-emerald-500 text-slate-950 hover:bg-emerald-400"
            }`}
          >
            {options?.confirmLabel ?? "Confirm"}
          </button>
        </div>
      </Modal>
    </ConfirmContext.Provider>
  );
}
