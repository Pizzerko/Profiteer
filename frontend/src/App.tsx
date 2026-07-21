import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import NavBar from "./components/NavBar";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import SearchPage from "./pages/Search";
import Signup from "./pages/Signup";
import StockDetail from "./pages/StockDetail";
import type { ReactNode } from "react";

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="flex h-screen items-center justify-center text-slate-400">
        Loading…
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  return (
    <>
      <NavBar />
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </>
  );
}

export default function App() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/signup" element={user ? <Navigate to="/" replace /> : <Signup />} />
      <Route
        path="/"
        element={
          <Protected>
            <Dashboard />
          </Protected>
        }
      />
      <Route
        path="/search"
        element={
          <Protected>
            <SearchPage />
          </Protected>
        }
      />
      <Route
        path="/stock/:symbol"
        element={
          <Protected>
            <StockDetail />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
