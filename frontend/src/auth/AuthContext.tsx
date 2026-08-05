import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, getToken, setToken } from "../api/client";
import type { User } from "../api/types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  signup: (email: string, username: string, password: string) => Promise<void>;
  logout: () => void;
  /** Re-read /auth/me after a profile edit, without flashing the loading screen. */
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>(null!);

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadUser() {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get<User>("/auth/me");
      setUser(data);
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUser();
  }, []);

  async function login(identifier: string, password: string) {
    const form = new URLSearchParams();
    form.set("username", identifier);
    form.set("password", password);
    const { data } = await api.post<{ access_token: string }>("/auth/login", form);
    setToken(data.access_token);
    await loadUser();
  }

  async function signup(email: string, username: string, password: string) {
    const { data } = await api.post<{ access_token: string }>("/auth/signup", {
      email,
      username,
      password,
    });
    setToken(data.access_token);
    await loadUser();
  }

  function logout() {
    setToken(null);
    setUser(null);
  }

  async function refreshUser() {
    if (!getToken()) return;
    try {
      const { data } = await api.get<User>("/auth/me");
      setUser(data);
    } catch {
      // Keep the current user; the response interceptor already handles a dead token.
    }
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}
