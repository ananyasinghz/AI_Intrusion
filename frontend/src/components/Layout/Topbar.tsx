import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut, Wifi, WifiOff } from "lucide-react";
import toast from "react-hot-toast";
import { authApi } from "../../api/client";
import { useAuthStore } from "../../store/authStore";

interface TopbarProps {
  connected: boolean;
}

export default function Topbar({ connected }: TopbarProps) {
  const [time, setTime] = useState(new Date().toLocaleTimeString());
  const { clearAuth } = useAuthStore();
  const navigate = useNavigate();

  useEffect(() => {
    const id = setInterval(() => setTime(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(id);
  }, []);

  const handleLogout = () => {
    // Optimistic logout: clear local state immediately for instant UX,
    // then revoke the refresh token on the server in the background.
    const refresh = localStorage.getItem("refresh_token");
    clearAuth();
    navigate("/login");
    toast.success("Logged out");
    if (refresh) authApi.logout(refresh).catch(() => {});
  };

  return (
    <header
      className="flex items-center justify-between px-5 py-3 shrink-0"
      style={{ background: "var(--bg2)", borderBottom: "1px solid var(--border)" }}
    >
      <div />
      <div className="flex items-center gap-3">
        {/* WS status */}
        <span
          className="flex items-center gap-1.5 text-xs px-3 py-1 rounded-full"
          style={{
            background: "var(--bg3)",
            border: "1px solid var(--border)",
            color: connected ? "var(--motion)" : "var(--person)",
          }}
        >
          {connected ? <Wifi size={12} /> : <WifiOff size={12} />}
          {connected ? "Live" : "Disconnected"}
        </span>

        {/* Clock */}
        <span
          className="text-xs font-mono px-3 py-1 rounded-full"
          style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--muted)" }}
        >
          {time}
        </span>

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="flex items-center gap-1.5 text-xs px-3 py-1 rounded-full transition-colors hover:opacity-80"
          style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--muted)" }}
        >
          <LogOut size={12} />
          Logout
        </button>
      </div>
    </header>
  );
}
