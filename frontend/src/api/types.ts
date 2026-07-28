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
  holdings: Holding[];
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

export interface PortfolioHistoryPoint {
  date: string;
  value: number;
}

export interface PortfolioHistoryResponse {
  range: string;
  points: PortfolioHistoryPoint[];
}
