const TYPE_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  animal:           { bg: "rgba(210,153,34,.2)",  color: "var(--animal)", label: "Animal" },
  person:           { bg: "rgba(248,81,73,.2)",   color: "var(--person)", label: "Person" },
  motion:           { bg: "rgba(63,185,80,.2)",   color: "var(--motion)", label: "Motion" },
  loitering:        { bg: "rgba(210,153,34,.25)", color: "var(--animal)", label: "Loitering" },
  zone_crossing:    { bg: "rgba(88,166,255,.2)",  color: "var(--accent)", label: "Zone Crossing" },
  abnormal_activity:{ bg: "rgba(248,81,73,.25)",  color: "var(--person)", label: "Abnormal" },
  unknown:          { bg: "var(--bg3)",            color: "var(--muted)",  label: "Unknown" },
};

export function TypePill({ type }: { type: string }) {
  const s = TYPE_STYLES[type] ?? TYPE_STYLES.unknown;
  return (
    <span
      className="inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide"
      style={{ background: s.bg, color: s.color }}
    >
      {s.label}
    </span>
  );
}

export function typeColor(type: string): string {
  return TYPE_STYLES[type]?.color ?? "var(--muted)";
}

export function typeIcon(type: string): string {
  const icons: Record<string, string> = {
    animal: "🐾", person: "🚶", motion: "⚠️",
    loitering: "⏱️", zone_crossing: "🚧", abnormal_activity: "🏃",
  };
  return icons[type] ?? "❓";
}
