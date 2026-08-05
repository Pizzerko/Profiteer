const STYLES: Record<string, string> = {
  active: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  upcoming: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  ended: "border-slate-700 bg-slate-800 text-slate-400",
};

const LABELS: Record<string, string> = {
  active: "Live",
  upcoming: "Upcoming",
  ended: "Ended",
};

/** Status pill for a competition. Status is derived server-side from the contest's window. */
export default function CompetitionBadge({ status }: { status?: string | null }) {
  if (!status) return null;
  const style = STYLES[status] ?? STYLES.ended;
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${style}`}
    >
      {LABELS[status] ?? status}
    </span>
  );
}
