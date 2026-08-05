// Initials avatar. There are no uploads, so the colour is derived from the username — the same
// person is always the same colour, which makes feed rows scannable.
const PALETTE = [
  "bg-emerald-500/20 text-emerald-300",
  "bg-sky-500/20 text-sky-300",
  "bg-violet-500/20 text-violet-300",
  "bg-amber-500/20 text-amber-300",
  "bg-rose-500/20 text-rose-300",
  "bg-teal-500/20 text-teal-300",
];

const SIZES = {
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-16 w-16 text-xl",
};

function initials(label: string): string {
  const words = label.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export default function Avatar({
  username,
  displayName,
  size = "md",
}: {
  username: string;
  displayName?: string | null;
  size?: keyof typeof SIZES;
}) {
  const hash = [...username].reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  const colour = PALETTE[hash % PALETTE.length];
  return (
    <div
      aria-hidden
      className={`flex shrink-0 items-center justify-center rounded-full font-semibold ${colour} ${SIZES[size]}`}
    >
      {initials(displayName || username)}
    </div>
  );
}
