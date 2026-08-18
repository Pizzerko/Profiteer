/** The signed-in user's own record — the only shape carrying their email. */
export interface User {
  id: number;
  email: string;
  username: string;
  created_at: string;
  display_name?: string | null;
  bio?: string | null;
  /** Which portfolio is shown on their public profile; null ⇒ nothing published. */
  public_portfolio_id?: number | null;
  /** Whether their competition win record is visible to other traders. */
  show_competition_stats: boolean;
  /** Whether their trading stats (windowed P&L%, win rate) are visible to other traders. */
  show_trading_stats: boolean;
}

/** Another user, as the API exposes them. Deliberately has no email. */
export interface PublicUser {
  id: number;
  username: string;
  display_name?: string | null;
  bio?: string | null;
  created_at: string;
  follower_count: number;
  following_count: number;
  /** Whether *you* follow them. */
  is_following: boolean;
  is_me: boolean;
}

/** A position on a public profile: what they hold and how it's doing, never how much. */
export interface PublicHolding {
  symbol: string;
  /** Share of the portfolio's gross value — conveys concentration without dollar amounts. */
  weight_percent?: number | null;
  unrealized_pl_percent?: number | null;
}

export interface CompetitionRecord {
  competition_id: number;
  name: string;
  status: string; // "upcoming" | "active" | "ended"
  timeframe: Timeframe;
  ranked: boolean;
  return_percent?: number | null;
  rank?: number | null;
  entrants: number;
  /** Finished first in a ranked, ended contest that had someone to beat. */
  won: boolean;
}

/** First-place finishes in ranked competitions, split by contest length. */
export interface WinRecord {
  day: number;
  week: number;
  month: number;
}

/** Blended trading performance across a user's personal (non-competition) portfolios. */
export interface TradingStats {
  pnl_1d_percent?: number | null;
  pnl_3mo_percent?: number | null;
  pnl_1y_percent?: number | null;
  win_rate_percent?: number | null;
}

export interface PublicProfile extends PublicUser {
  portfolio_name?: string | null;
  total_return_percent?: number | null;
  holdings: PublicHolding[];
  competitions: CompetitionRecord[];
  /** null when this trader has hidden their record — distinct from a record of all zeroes. */
  wins?: WinRecord | null;
  show_competition_stats: boolean;
  /** null when this trader has hidden their trading stats. */
  trading_stats?: TradingStats | null;
  show_trading_stats: boolean;
}

/** A trade by someone you follow. Carries the fill price but never the size. */
export interface FeedItem {
  id: string;
  kind: string; // "stock" | "option"
  username: string;
  display_name?: string | null;
  symbol: string;
  label: string;
  side: string; // "buy" | "sell"
  price: number;
  executed_at: string;
}

/** The three contest lengths. Fixed spans, so wins in each are comparable. */
export type Timeframe = "day" | "week" | "month";
export type Visibility = "public" | "private";
export type InviteStatus = "pending" | "accepted" | "declined";

export interface Competition {
  id: number;
  name: string;
  description?: string | null;
  status: string; // "upcoming" | "active" | "ended"
  starting_cash: number;
  starts_at: string;
  /** Derived server-side from starts_at + timeframe; never sent when creating one. */
  ends_at: string;
  created_at: string;
  creator_username: string;
  entrants: number;
  visibility: Visibility;
  timeframe: Timeframe;
  /** Whether winning counts toward the winner's public record. */
  ranked: boolean;
  joined: boolean;
  entry_portfolio_id?: number | null;
  is_creator: boolean;
  /** Your own invite state for a private lobby; null if you were never invited. */
  invite_status?: InviteStatus | null;
  can_join: boolean;
}

/** One row of a host's guest list. */
export interface CompetitionInvite {
  id: number;
  username: string;
  display_name?: string | null;
  status: InviteStatus;
  created_at: string;
}

export interface AppNotification {
  id: number;
  kind: "competition_invite" | "competition_result" | "invite_accepted";
  title: string;
  body?: string | null;
  competition_id?: number | null;
  read: boolean;
  created_at: string;
  /** An invite still awaiting an answer — render Accept / Decline. */
  actionable: boolean;
}

export interface StandingRow {
  rank: number;
  username: string;
  display_name?: string | null;
  return_percent: number;
  is_me: boolean;
  /** True once the competition has ended and this result is frozen. */
  final: boolean;
}

export interface Quote {
  symbol: string;
  name?: string | null;
  price?: number | null;
  previous_close?: number | null;
  change?: number | null;
  change_percent?: number | null;
  currency?: string | null;
  market_state?: string | null;
  extended_price?: number | null;
  extended_change?: number | null;
  extended_change_percent?: number | null;
  effective_price?: number | null;
}

export interface HistoryPoint {
  date: string;
  close: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
}

export interface HistoryResponse {
  symbol: string;
  range: string;
  points: HistoryPoint[];
}

export interface Fundamentals {
  symbol: string;
  name?: string | null;
  exchange?: string | null;
  sector?: string | null;
  industry?: string | null;
  market_cap?: number | null;
  pe_ratio?: number | null;
  forward_pe?: number | null;
  eps?: number | null;
  dividend_yield?: number | null;
  beta?: number | null;
  fifty_two_week_high?: number | null;
  fifty_two_week_low?: number | null;
  day_high?: number | null;
  day_low?: number | null;
  open?: number | null;
  previous_close?: number | null;
  volume?: number | null;
  avg_volume?: number | null;
}

export interface MoverQuote {
  symbol: string;
  name?: string | null;
  price?: number | null;
  change?: number | null;
  change_percent?: number | null;
  market_state?: string | null;
}

export interface MarketOverview {
  indices: MoverQuote[];
  gainers: MoverQuote[];
  losers: MoverQuote[];
  etfs: MoverQuote[];
}

export interface NewsItem {
  title: string;
  publisher?: string | null;
  link?: string | null;
  published_at?: string | null;
}

export interface SearchResult {
  symbol: string;
  name?: string | null;
  exchange?: string | null;
  type?: string | null;
}

export interface Holding {
  symbol: string;
  quantity: number;
  avg_cost: number;
  current_price?: number | null;
  market_value?: number | null;
  cost_basis: number;
  unrealized_pl?: number | null;
  unrealized_pl_percent?: number | null;
  // Today's gain: the position's move since the prior regular-session close.
  todays_pl?: number | null;
  todays_pl_percent?: number | null;
}

export interface OptionContract {
  occ_symbol: string;
  option_type: string; // "call" | "put"
  strike: number;
  last_price?: number | null;
  bid?: number | null;
  ask?: number | null;
  mark?: number | null;
  change?: number | null;
  percent_change?: number | null;
  volume?: number | null;
  open_interest?: number | null;
  implied_volatility?: number | null;
  in_the_money?: boolean | null;
}

export interface OptionChain {
  underlying: string;
  expiration: string; // "YYYY-MM-DD"
  expirations: string[];
  calls: OptionContract[];
  puts: OptionContract[];
}

export interface OptionPosition {
  underlying: string;
  occ_symbol: string;
  option_type: string; // "call" | "put"
  strike: number;
  expiration: string; // "YYYY-MM-DD"
  quantity: number; // signed: + long, − written
  avg_price: number; // premium per share
  collateral_kind?: string | null; // "covered" | "cash_secured" | null
  current_price?: number | null;
  market_value?: number | null;
  cost_basis: number;
  unrealized_pl?: number | null;
  unrealized_pl_percent?: number | null;
  days_to_expiry?: number | null;
}

export interface OptionTrade {
  id: number;
  underlying: string;
  occ_symbol: string;
  option_type: string;
  strike: number;
  expiration: string;
  action: string; // "buy" | "sell" | "settle"
  quantity: number;
  price: number;
  realized_pl?: number | null;
  note?: string | null;
  executed_at: string;
}

export interface Portfolio {
  id: number;
  name: string;
  cash_balance: number;
  starting_balance: number;
  holdings_value: number;
  total_value: number;
  total_pl: number;
  total_pl_percent: number;
  realized_pl: number;
  buying_power: number;
  reserved_cash: number;
  locked: boolean;
  holdings: Holding[];
  option_positions: OptionPosition[];
}

export interface PortfolioSummary {
  id: number;
  name: string;
  cash_balance: number;
  starting_balance: number;
  total_value: number;
  locked: boolean;
  /** Set when this portfolio is a competition entry rather than one the user created. */
  competition_id?: number | null;
  competition_name?: string | null;
  competition_status?: string | null;
}

export interface Trade {
  id: number;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  realized_pl?: number | null;
  executed_at: string;
}

export interface WatchlistItem {
  symbol: string;
  created_at: string;
}

export interface Order {
  id: number;
  symbol: string;
  side: string;
  order_type: string; // "limit" | "stop" | "trailing_stop"
  quantity: number;
  limit_price?: number | null;
  stop_price?: number | null;
  trail_percent?: number | null;
  peak_price?: number | null;
  status: string; // "open" | "filled" | "cancelled" | "rejected"
  note?: string | null;
  created_at: string;
  filled_at?: string | null;
  fill_price?: number | null;
  filled_trade_id?: number | null;
}

export interface OptionOrder {
  id: number;
  underlying: string;
  occ_symbol: string;
  option_type: string; // "call" | "put"
  strike: number;
  expiration: string; // "YYYY-MM-DD"
  side: string; // "buy" | "sell"
  order_type: string; // "limit" | "stop" | "trailing_stop"
  quantity: number;
  limit_price?: number | null;
  stop_price?: number | null;
  trail_percent?: number | null;
  peak_price?: number | null;
  status: string; // "open" | "filled" | "cancelled" | "rejected"
  note?: string | null;
  created_at: string;
  filled_at?: string | null;
  fill_price?: number | null;
  filled_option_trade_id?: number | null;
}

export interface PortfolioHistoryPoint {
  date: string;
  value: number;
  benchmark?: number | null;
}

export interface PortfolioHistoryResponse {
  range: string;
  points: PortfolioHistoryPoint[];
}

/**
 * A trade published alongside a community post.
 *
 * The only shape in this file that carries a position size, and only because its author attached
 * it by hand — see the module docstring of `backend/app/schemas/community.py`.
 */
export interface PostTrade {
  kind: string; // "stock" | "option"
  symbol: string;
  label: string; // "AAPL", or "AAPL $210 call 2026-09-18"
  side: string; // "buy" | "sell"
  /** Shares for a stock, contracts for an option. */
  quantity: number;
  price: number;
  executed_at: string;
}

/** One of your own recent fills, offered by the composer. `ref` is what you send back to attach it. */
export interface AttachableTrade extends PostTrade {
  ref: string; // "t<id>" | "o<id>"
  /** Which of your books it came from. Shown while choosing; never published with the post. */
  portfolio_name: string;
}

export interface Post {
  id: number;
  username: string;
  display_name?: string | null;
  body: string;
  /** Distinct tickers the body mentions, uppercased — the server's parse of its own cashtags. */
  symbols: string[];
  trades: PostTrade[];
  created_at: string;
  is_mine: boolean;
  /** How many distinct people have liked this. */
  like_count: number;
  /** Whether *you* have — resolved per request against the reader, never stored on the post. */
  liked_by_me: boolean;
}

/**
 * Which ordering the community feed is asked for.
 *
 * The mode also picks the paging cursor: "popular" is ranked by a computed score and so pages by
 * offset, while the two chronological modes page by `before_id`. See
 * `backend/app/services/community.py`.
 */
export type FeedMode = "popular" | "following" | "latest";

/** The like state of one post after liking or unliking it. */
export interface PostLikeResult {
  post_id: number;
  like_count: number;
  liked_by_me: boolean;
}
