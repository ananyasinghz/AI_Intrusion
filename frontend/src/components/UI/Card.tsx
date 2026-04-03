import { ReactNode } from "react";

interface CardProps {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Card({ title, action, children, className = "" }: CardProps) {
  return (
    <div
      className={`rounded-xl overflow-hidden ${className}`}
      style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}
    >
      {title && (
        <div
          className="flex items-center justify-between px-4 py-3"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
            {title}
          </span>
          {action && <div>{action}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

interface StatCardProps {
  value: number | string;
  label: string;
  color?: string;
}

export function StatCard({ value, label, color }: StatCardProps) {
  return (
    <div
      className="rounded-xl p-4 text-center"
      style={{
        background: "var(--bg2)",
        border: "1px solid var(--border)",
        borderTop: color ? `3px solid ${color}` : undefined,
      }}
    >
      <div className="text-3xl font-bold mb-1" style={{ color: "var(--text)" }}>{value}</div>
      <div className="text-xs" style={{ color: "var(--muted)" }}>{label}</div>
    </div>
  );
}
