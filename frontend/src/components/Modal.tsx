import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * The overlay every in-page dialog sits in — the replacement for `window.confirm`/`prompt`.
 *
 * Rendered through a portal onto `document.body` rather than in place: the nav bar's
 * `backdrop-blur` establishes a containing block, so a dialog opened from there would otherwise be
 * clipped by the header instead of covering the page.
 *
 * Escape and a backdrop click both dismiss, matching what the browser dialogs did.
 */
export default function Modal({
  open,
  onClose,
  labelledBy,
  children,
}: {
  open: boolean;
  onClose: () => void;
  /** Id of the element naming this dialog, for screen readers. */
  labelledBy?: string;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    // Hold the page still underneath, so scrolling can't drift the content behind the dialog.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className="relative w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-2xl"
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
