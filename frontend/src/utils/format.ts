export const money = (n?: number | null): string =>
  n == null
    ? "—"
    : n.toLocaleString("en-US", { style: "currency", currency: "USD" });

export const pct = (n?: number | null): string =>
  n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;

export const signedMoney = (n?: number | null): string =>
  n == null ? "—" : `${n >= 0 ? "+" : "-"}${money(Math.abs(n))}`;

export const plClass = (n?: number | null): string =>
  n == null
    ? "text-slate-400"
    : n > 0
      ? "text-emerald-400"
      : n < 0
        ? "text-red-400"
        : "text-slate-300";

export const qty = (n: number): string =>
  Number.isInteger(n) ? n.toString() : n.toFixed(4).replace(/\.?0+$/, "");

// Abbreviate large numbers (market cap, volume): 3.21T, 45.6B, 12.3M, 987K.
export const compact = (n?: number | null): string => {
  if (n == null) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  const units: [number, string][] = [
    [1e12, "T"],
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "K"],
  ];
  for (const [size, suffix] of units) {
    if (abs >= size) return `${sign}${(abs / size).toFixed(2)}${suffix}`;
  }
  return `${sign}${abs.toLocaleString("en-US")}`;
};

// Plain fixed-decimal number, or — when null (for ratios like P/E, beta, EPS).
export const num = (n?: number | null, digits = 2): string =>
  n == null ? "—" : n.toFixed(digits);

// Compact relative time for feeds and competition windows: "just now", "4m ago", "3d ago".
export const timeAgo = (iso?: string | null): string => {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.floor((Date.now() - then) / 1000);
  if (secs < 0) return "just now";
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
};

// Absolute local date + time, for competition start/end stamps.
export const dateTime = (iso?: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
};

// How long until an ISO timestamp: "in 3d", "in 2h", or "" once it's past.
export const timeUntil = (iso?: string | null): string => {
  if (!iso) return "";
  const secs = Math.floor((new Date(iso).getTime() - Date.now()) / 1000);
  if (Number.isNaN(secs) || secs <= 0) return "";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `in ${Math.max(1, mins)}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `in ${hours}h`;
  return `in ${Math.floor(hours / 24)}d`;
};
