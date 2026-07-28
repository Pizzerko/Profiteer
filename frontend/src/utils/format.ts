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
