import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";

import { useAuthStore } from "./store/authStore";
import { authApi } from "./api/client";

import Layout from "./components/Layout/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Incidents from "./pages/Incidents";
import Analytics from "./pages/Analytics";
import Zones from "./pages/Zones";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";
import Users from "./pages/Users";
import ApprovedPersons from "./pages/ApprovedPersons";

const qc = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 10_000 },
  },
});

function ProtectedRoute({ children, adminOnly = false }: { children: React.ReactNode; adminOnly?: boolean }) {
  const { user, accessToken, isLoading } = useAuthStore();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg)" }}>
        <span style={{ color: "var(--muted)" }}>Loading…</span>
      </div>
    );
  }

  if (!accessToken || !user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/" replace />;

  return <>{children}</>;
}

export default function App() {
  const { setAuth, clearAuth, setLoading, accessToken } = useAuthStore();

  // Validate stored token on mount
  useEffect(() => {
    if (!accessToken) {
      setLoading(false);
      return;
    }
    authApi.me()
      .then((res) => {
        const token = localStorage.getItem("access_token") ?? "";
        const refresh = localStorage.getItem("refresh_token") ?? "";
        setAuth(res.data, token, refresh);
      })
      .catch(() => {
        clearAuth();
      });
  }, []);

  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="incidents" element={<Incidents />} />
            <Route path="analytics" element={<Analytics />} />
            <Route
              path="zones"
              element={<ProtectedRoute><Zones /></ProtectedRoute>}
            />
            <Route
              path="reports"
              element={<ProtectedRoute><Reports /></ProtectedRoute>}
            />
            <Route
              path="settings"
              element={<ProtectedRoute><Settings /></ProtectedRoute>}
            />
            <Route
              path="users"
              element={
                <ProtectedRoute adminOnly>
                  <Users />
                </ProtectedRoute>
              }
            />
            <Route
              path="approved-persons"
              element={
                <ProtectedRoute adminOnly>
                  <ApprovedPersons />
                </ProtectedRoute>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: "var(--bg2)",
            color: "var(--text)",
            border: "1px solid var(--border)",
            fontSize: "13px",
          },
        }}
      />
    </QueryClientProvider>
  );
}
