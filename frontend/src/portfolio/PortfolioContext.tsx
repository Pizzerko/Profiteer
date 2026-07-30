import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, getActivePortfolioId, setActivePortfolioId } from "../api/client";
import type { PortfolioSummary } from "../api/types";
import { useAuth } from "../auth/AuthContext";

interface PortfolioContextValue {
  portfolios: PortfolioSummary[];
  activeId: number | null;
  setActiveId: (id: number) => void;
  refresh: () => Promise<void>;
}

const PortfolioContext = createContext<PortfolioContextValue>(null!);

// eslint-disable-next-line react-refresh/only-export-components
export const usePortfolios = () => useContext(PortfolioContext);

export function PortfolioProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [portfolios, setPortfolios] = useState<PortfolioSummary[]>([]);
  const [activeId, setActiveIdState] = useState<number | null>(getActivePortfolioId);

  const setActiveId = useCallback((id: number) => {
    setActiveIdState(id);
    setActivePortfolioId(id); // shared with the axios interceptor
  }, []);

  const refresh = useCallback(async () => {
    const { data } = await api.get<PortfolioSummary[]>("/portfolios");
    setPortfolios(data);
    setActiveIdState((cur) => {
      // Keep the current selection if it still exists, else fall back to the first portfolio.
      const next = cur && data.some((p) => p.id === cur) ? cur : data[0]?.id ?? null;
      setActivePortfolioId(next);
      return next;
    });
  }, []);

  useEffect(() => {
    if (user) {
      refresh().catch(() => {});
    } else {
      setPortfolios([]);
      setActiveIdState(null);
      setActivePortfolioId(null);
    }
  }, [user, refresh]);

  return (
    <PortfolioContext.Provider value={{ portfolios, activeId, setActiveId, refresh }}>
      {children}
    </PortfolioContext.Provider>
  );
}
