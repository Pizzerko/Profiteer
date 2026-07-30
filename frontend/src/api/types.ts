export interface User {
  id: number;
  email: string;
  username: string;
  created_at: string;
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
