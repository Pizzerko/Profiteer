import axios from "axios";

const baseURL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export const api = axios.create({ baseURL });

const TOKEN_KEY = "profiteer_token";
const ACTIVE_PORTFOLIO_KEY = "profiteer_active_portfolio";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getActivePortfolioId(): number | null {
  const s = localStorage.getItem(ACTIVE_PORTFOLIO_KEY);
  return s ? Number(s) : null;
}

export function setActivePortfolioId(id: number | null): void {
  if (id != null) localStorage.setItem(ACTIVE_PORTFOLIO_KEY, String(id));
  else localStorage.removeItem(ACTIVE_PORTFOLIO_KEY);
}

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // Scope portfolio-aware endpoints to the active portfolio. Endpoints that don't use it (auth,
  // market data, watchlist) simply ignore the extra query param. Any explicit portfolio_id wins.
  const pid = getActivePortfolioId();
  if (pid != null) {
    const params = config.params ?? {};
    if (params.portfolio_id == null) params.portfolio_id = pid;
    config.params = params;
  }
  return config;
});

// On expired/invalid tokens, clear and bounce to login (but not for auth calls themselves).
api.interceptors.response.use(
  (res) => res,
  (error) => {
    const url: string = error?.config?.url ?? "";
    if (error?.response?.status === 401 && !url.includes("/auth/")) {
      setToken(null);
      if (window.location.pathname !== "/login") window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

/** Extract a human-readable message from an axios error / FastAPI error body. */
export function errorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
    return err.message;
  }
  return "Something went wrong.";
}
