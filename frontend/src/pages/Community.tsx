import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import { useConfirm } from "../components/ConfirmProvider";
import PostCard from "../components/PostCard";
import PostComposer from "../components/PostComposer";
import type { FeedMode, Post } from "../api/types";

const PAGE_SIZE = 30;

const TABS: { mode: FeedMode; label: string }[] = [
  { mode: "popular", label: "Popular" },
  { mode: "following", label: "Following" },
];

/**
 * The community feed: everyone's posts, ranked or chronological, filterable to one ticker.
 *
 * Both the feed mode and the ticker filter live in the URL (`/community?feed=following`,
 * `/community?symbol=AAPL`) rather than in state, so a cashtag anywhere in the app is an ordinary
 * link and any view can be shared, bookmarked, or reloaded.
 */
export default function Community() {
  const confirm = useConfirm();
  const [params, setParams] = useSearchParams();
  const symbol = params.get("symbol")?.toUpperCase() || null;
  // Anything unrecognised in the URL reads as the default rather than as an error.
  const feed: FeedMode = params.get("feed") === "following" ? "following" : "popular";

  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  // Only meaningful once a full page has come back; a short page means we've hit the end.
  const [exhausted, setExhausted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);

  function setFeed(next: FeedMode) {
    const updated = new URLSearchParams(params);
    // "popular" is the default, so it stays out of the URL rather than appearing as noise.
    if (next === "popular") updated.delete("feed");
    else updated.set("feed", next);
    setParams(updated);
  }

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get<Post[]>("/community/posts", {
        params: { feed, symbol: symbol ?? undefined, limit: PAGE_SIZE },
      });
      setPosts(data);
      setExhausted(data.length < PAGE_SIZE);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [feed, symbol]);

  useEffect(() => {
    load();
  }, [load]);

  async function loadMore() {
    const oldest = posts[posts.length - 1];
    if (!oldest) return;
    setLoadingMore(true);
    try {
      const { data } = await api.get<Post[]>("/community/posts", {
        params: {
          feed,
          symbol: symbol ?? undefined,
          limit: PAGE_SIZE,
          // Popular is ranked by a computed score, so it pages by offset; the chronological feeds
          // page by id, which can't skip or repeat when someone posts mid-scroll.
          ...(feed === "popular" ? { offset: posts.length } : { before_id: oldest.id }),
        },
      });
      // Popular's offset can drift by a post you added yourself mid-scroll, so drop anything
      // already on screen rather than rendering it (and its React key) twice.
      setPosts((current) => {
        const seen = new Set(current.map((p) => p.id));
        return [...current, ...data.filter((p) => !seen.has(p.id))];
      });
      setExhausted(data.length < PAGE_SIZE);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoadingMore(false);
    }
  }

  function onPosted(post: Post) {
    // Only prepend when it belongs in what's on screen: posting "thoughts on $MSFT" while filtered
    // to $AAPL shouldn't make it look like an $AAPL post.
    if (symbol && !post.symbols.includes(symbol)) return;
    setPosts((current) => [post, ...current]);
  }

  // Keep the page's copy in step with a card's optimistic toggle, so switching tabs and coming
  // back doesn't show a stale heart.
  function onLikeChange(postId: number, like_count: number, liked_by_me: boolean) {
    setPosts((current) =>
      current.map((p) => (p.id === postId ? { ...p, like_count, liked_by_me } : p)),
    );
  }

  async function onDelete(post: Post) {
    const ok = await confirm({
      title: "Delete this post?",
      message: "It disappears from the feed for everyone, along with any trades attached to it.",
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.delete(`/community/posts/${post.id}`);
      setPosts((current) => current.filter((p) => p.id !== post.id));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const emptyMessage = symbol
    ? `Nobody has posted about $${symbol} yet. Be the first.`
    : feed === "following"
      ? "Nothing here yet — follow some traders and their posts will show up in this tab."
      : "No posts yet. Share what you're watching — mention a ticker with $AAPL and people can filter to it.";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">Community</h1>
        {symbol && (
          <div className="flex items-center gap-2 text-sm">
            <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-0.5 font-semibold text-emerald-300">
              ${symbol}
            </span>
            <Link to={`/stock/${symbol}`} className="text-slate-400 hover:text-white">
              View {symbol} →
            </Link>
            <button
              onClick={() => {
                const updated = new URLSearchParams(params);
                updated.delete("symbol");
                setParams(updated);
              }}
              className="rounded-md border border-slate-700 px-2.5 py-1 text-slate-300 transition hover:bg-slate-800"
            >
              Clear filter
            </button>
          </div>
        )}
      </div>

      <div className="flex items-center gap-1 border-b border-slate-800">
        {TABS.map((tab) => (
          <button
            key={tab.mode}
            onClick={() => setFeed(tab.mode)}
            aria-current={feed === tab.mode ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${
              feed === tab.mode
                ? "border-emerald-400 text-white"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
        {!composing && (
          <button
            onClick={() => setComposing(true)}
            aria-label="Write a post"
            title="Write a post"
            className="mb-1.5 ml-auto flex h-8 w-8 items-center justify-center rounded-md border border-slate-700 text-lg leading-none text-slate-300 transition hover:border-emerald-500/50 hover:bg-emerald-500/10 hover:text-emerald-300"
          >
            +
          </button>
        )}
      </div>

      {composing && <PostComposer onPosted={onPosted} onClose={() => setComposing(false)} />}

      {error && <p className="text-sm text-red-400">{error}</p>}

      {loading ? (
        <p className="text-slate-400">Loading posts…</p>
      ) : posts.length === 0 ? (
        <p className="text-sm text-slate-500">{emptyMessage}</p>
      ) : (
        <>
          <div className="space-y-3">
            {posts.map((p) => (
              <PostCard
                key={p.id}
                post={p}
                onDelete={onDelete}
                onLikeChange={onLikeChange}
              />
            ))}
          </div>
          {!exhausted && (
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="w-full rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-300 transition hover:bg-slate-800 disabled:opacity-50"
            >
              {loadingMore ? "Loading…" : "Load more"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
