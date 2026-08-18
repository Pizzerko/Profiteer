import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Post, PostLikeResult, PostTrade } from "../api/types";
import { money, qty, timeAgo } from "../utils/format";
import { splitCashtags } from "../utils/cashtags";
import Avatar from "./Avatar";

/** A post body with its cashtags turned into filter links. Whitespace is preserved as typed. */
function Body({ body }: { body: string }) {
  return (
    <p className="whitespace-pre-wrap break-words text-sm text-slate-200">
      {splitCashtags(body).map((seg, i) =>
        seg.kind === "text" ? (
          <span key={i}>{seg.value}</span>
        ) : (
          <Link
            key={i}
            to={`/community?symbol=${encodeURIComponent(seg.symbol)}`}
            className="font-semibold text-emerald-400 hover:underline"
          >
            {seg.value}
          </Link>
        ),
      )}
    </p>
  );
}

/**
 * An attached fill — the one place the app shows someone else's position size, because its author
 * chose to publish it. Reads as a receipt: "bought 25 shares @ $203.40".
 */
function AttachedTrade({ trade }: { trade: PostTrade }) {
  const bought = trade.side === "buy";
  const unit = trade.kind === "option" ? "contract" : "share";
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-sm">
      <span className={`font-semibold ${bought ? "text-emerald-400" : "text-red-400"}`}>
        {bought ? "Bought" : "Sold"}
      </span>
      <span className="text-slate-200">
        {qty(trade.quantity)} {unit}
        {trade.quantity === 1 ? "" : "s"}
      </span>
      <Link
        to={`/stock/${trade.symbol}`}
        className="font-medium text-slate-200 hover:underline"
      >
        {trade.label}
      </Link>
      <span className="text-slate-400">@ {money(trade.price)}</span>
      {trade.kind === "option" && (
        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">
          option
        </span>
      )}
      <span className="ml-auto text-xs text-slate-500">{timeAgo(trade.executed_at)}</span>
    </div>
  );
}

/** A heart that fills in when you've liked the post, with the count beside it. */
function Heart({ filled }: { filled: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1L12 21l7.7-7.6 1.1-1a5.5 5.5 0 0 0 0-7.8z" />
    </svg>
  );
}

export default function PostCard({
  post,
  onDelete,
  onLikeChange,
}: {
  post: Post;
  onDelete?: (post: Post) => void;
  /** Lets the feed keep its copy in step, so a toggle survives a re-render or a tab switch. */
  onLikeChange?: (postId: number, like_count: number, liked_by_me: boolean) => void;
}) {
  // The toggle is applied locally first and reconciled with the server's count on the way back:
  // a like should feel instant, and the server is the authority on the total.
  const [liked, setLiked] = useState(post.liked_by_me);
  const [count, setCount] = useState(post.like_count);
  const [pending, setPending] = useState(false);

  // Adopt the server's numbers whenever the feed hands down new ones — switching tabs or reloading
  // reuses this component for the same post id, so without this the heart could go stale. An
  // optimistic toggle doesn't trip this: it changes local state, not these props.
  useEffect(() => {
    setLiked(post.liked_by_me);
    setCount(post.like_count);
  }, [post.id, post.liked_by_me, post.like_count]);

  async function toggleLike() {
    if (pending) return;
    const next = !liked;
    const rollbackLiked = liked;
    const rollbackCount = count;
    setLiked(next);
    setCount((c) => c + (next ? 1 : -1));
    setPending(true);
    try {
      const { data } = next
        ? await api.put<PostLikeResult>(`/community/posts/${post.id}/like`)
        : await api.delete<PostLikeResult>(`/community/posts/${post.id}/like`);
      setLiked(data.liked_by_me);
      setCount(data.like_count);
      onLikeChange?.(post.id, data.like_count, data.liked_by_me);
    } catch {
      // Put the button back the way the reader found it rather than showing a banner: a like
      // that didn't take is self-evident once the heart un-fills.
      setLiked(rollbackLiked);
      setCount(rollbackCount);
    } finally {
      setPending(false);
    }
  }

  return (
    <article className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="flex gap-3">
        <Avatar username={post.username} displayName={post.display_name} size="sm" />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <Link to={`/u/${post.username}`} className="truncate font-semibold hover:underline">
              {post.display_name || post.username}
            </Link>
            <span className="truncate text-xs text-slate-500">@{post.username}</span>
            <span className="shrink-0 text-xs text-slate-500">· {timeAgo(post.created_at)}</span>
            {post.is_mine && onDelete && (
              <button
                onClick={() => onDelete(post)}
                title="Delete this post"
                className="ml-auto shrink-0 rounded px-1.5 text-xs text-slate-500 transition hover:bg-slate-800 hover:text-red-400"
              >
                Delete
              </button>
            )}
          </div>

          <div className="mt-1.5">
            <Body body={post.body} />
          </div>

          {post.trades.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {post.trades.map((t, i) => (
                <AttachedTrade key={i} trade={t} />
              ))}
            </div>
          )}

          <div className="mt-3 flex items-center gap-3">
            <button
              onClick={toggleLike}
              disabled={pending}
              aria-pressed={liked}
              title={liked ? "Unlike" : "Like"}
              className={`flex items-center gap-1.5 rounded-full px-2 py-1 text-xs transition disabled:opacity-60 ${
                liked
                  ? "text-rose-400 hover:bg-rose-500/10"
                  : "text-slate-500 hover:bg-slate-800 hover:text-rose-400"
              }`}
            >
              <Heart filled={liked} />
              {count > 0 && <span className="font-semibold tabular-nums">{count}</span>}
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
