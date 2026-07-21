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
