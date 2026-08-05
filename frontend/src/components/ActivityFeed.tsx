import { Link } from "react-router-dom";
import type { FeedItem } from "../api/types";
import { money, timeAgo } from "../utils/format";
import Avatar from "./Avatar";

/** Trades by people you follow. Sizes are deliberately absent — the API never sends them. */
export default function ActivityFeed({ items }: { items: FeedItem[] }) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        Nothing here yet. Follow some traders to see what they're buying and selling.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-slate-800 overflow-hidden rounded-xl border border-slate-800">
      {items.map((item) => {
        const bought = item.side === "buy";
        return (
          <li key={item.id} className="flex items-center gap-3 px-4 py-3">
            <Avatar username={item.username} displayName={item.display_name} size="sm" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm">
                <Link to={`/u/${item.username}`} className="font-semibold hover:underline">
                  {item.display_name || item.username}
                </Link>{" "}
                <span className={bought ? "text-emerald-400" : "text-red-400"}>
                  {bought ? "bought" : "sold"}
                </span>{" "}
                <Link to={`/stock/${item.symbol}`} className="font-medium text-slate-200 hover:underline">
                  {item.label}
                </Link>
                {item.kind === "option" && (
                  <span className="ml-1.5 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">
                    option
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-500">
                at {money(item.price)} · {timeAgo(item.executed_at)}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
