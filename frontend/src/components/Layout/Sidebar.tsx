import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, AlertTriangle, BarChart2, Map,
  FileText, Settings, Users, ShieldAlert, UserCheck, MessageSquare,
} from "lucide-react";
import { useAuthStore } from "../../store/authStore";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/incidents", icon: AlertTriangle, label: "Incidents" },
  { to: "/analytics", icon: BarChart2, label: "Analytics" },
  { to: "/zones", icon: Map, label: "Zones" },
  { to: "/reports", icon: FileText, label: "Reports" },
];

const adminItems = [
  { to: "/approved-persons", icon: UserCheck, label: "Approved Persons" },
  { to: "/assistant", icon: MessageSquare, label: "Data assistant" },
  { to: "/settings", icon: Settings, label: "Settings" },
  { to: "/users", icon: Users, label: "Users" },
];

export default function Sidebar() {
  const user = useAuthStore((s) => s.user);

  return (
    <aside
      className="flex flex-col h-full w-56 shrink-0"
      style={{ background: "var(--bg2)", borderRight: "1px solid var(--border)" }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
        <ShieldAlert size={22} style={{ color: "var(--accent)" }} />
        <span className="font-semibold text-sm tracking-wide" style={{ color: "var(--text)" }}>
          Intrusion Monitor
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive ? "active-nav" : "hover-nav"
              }`
            }
            style={({ isActive }) => ({
              background: isActive ? "rgba(88,166,255,.12)" : "transparent",
              color: isActive ? "var(--accent)" : "var(--muted)",
            })}
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}

        {user?.role === "admin" && (
          <>
            <div className="pt-4 pb-1 px-3">
              <span className="text-xs uppercase tracking-wider" style={{ color: "var(--muted)" }}>Admin</span>
            </div>
            {adminItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={() => `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors`}
                style={({ isActive }) => ({
                  background: isActive ? "rgba(88,166,255,.12)" : "transparent",
                  color: isActive ? "var(--accent)" : "var(--muted)",
                })}
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </>
        )}
      </nav>

      {/* User badge */}
      {user && (
        <div className="px-4 py-3" style={{ borderTop: "1px solid var(--border)" }}>
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                 style={{ background: "var(--accent)", color: "#000" }}>
              {user.username[0].toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium truncate" style={{ color: "var(--text)" }}>{user.username}</p>
              <p className="text-xs capitalize" style={{ color: "var(--muted)" }}>{user.role}</p>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
