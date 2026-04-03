import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, CartesianGrid,
} from "recharts";
import { incidentsApi } from "../api/client";
import { TrendingUp, AlertTriangle, Clock, MapPin } from "lucide-react";

const COLORS: Record<string, string> = {
  animal:            "#d29922",
  person:            "#f85149",
  motion:            "#3fb950",
  loitering:         "#e3b341",
  zone_crossing:     "#58a6ff",
  abnormal_activity: "#db6d28",
  unknown:           "#8b949e",
};

const HOURS_OPTIONS = [
  { label: "24h",  value: 24  },
  { label: "48h",  value: 48  },
  { label: "7d",   value: 168 },
  { label: "30d",  value: 720 },
];

const TOOLTIP_STYLE = {
  contentStyle: {
    background: "var(--bg2)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    color: "var(--text)",
    fontSize: 12,
    boxShadow: "0 8px 24px rgba(0,0,0,.4)",
  },
  itemStyle: { color: "var(--text)" },
  labelStyle: { color: "var(--muted)", marginBottom: 4 },
};

// ── Reusable insight card ─────────────────────────────────────────────────────
function InsightCard({
  icon: Icon, title, value, sub, color,
}: {
  icon: React.ElementType; title: string; value: string | number; sub?: string; color: string;
}) {
  return (
    <div
      className="rounded-xl p-4 flex items-start gap-3"
      style={{
        background: "var(--bg2)",
        border: "1px solid var(--border)",
        borderLeft: `3px solid ${color}`,
      }}
    >
      <div
        className="p-2 rounded-lg mt-0.5 shrink-0"
        style={{ background: `${color}22` }}
      >
        <Icon size={16} style={{ color }} />
      </div>
      <div className="min-w-0">
        <p className="text-xs" style={{ color: "var(--muted)" }}>{title}</p>
        <p className="text-xl font-bold mt-0.5" style={{ color: "var(--text)" }}>{value}</p>
        {sub && <p className="text-xs mt-0.5 truncate" style={{ color: "var(--muted)" }}>{sub}</p>}
      </div>
    </div>
  );
}

// ── Section wrapper ───────────────────────────────────────────────────────────
function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}
    >
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--bg3)" }}
      >
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
          {title}
        </span>
        {action}
      </div>
      {children}
    </div>
  );
}

export default function Analytics() {
  const [hours, setHours] = useState(24);

  const { data: stats } = useQuery({
    queryKey: ["stats", hours],
    queryFn: () => incidentsApi.stats(hours).then((r) => r.data),
    refetchInterval: 60_000,
  });

  const { data: hourlyGrid } = useQuery({
    queryKey: ["hourlyGrid", hours],
    queryFn: () => incidentsApi.hourlyHeatmap(hours).then((r) => r.data),
  });

  // Timeline
  const timelineData = (stats?.hourly ?? []).map((h: any) => ({
    time: h.hour.slice(11, 16),
    animal: h.animal ?? 0,
    person: h.person ?? 0,
    motion: h.motion ?? 0,
    loitering: h.loitering ?? 0,
    abnormal_activity: h.abnormal_activity ?? 0,
  }));

  // Donut
  const byType = stats?.by_type ?? {};
  const donutData = Object.entries(byType)
    .filter(([, v]) => (v as number) > 0)
    .map(([k, v]) => ({ name: k, value: v as number }));

  // Zone comparison
  const byZone = stats?.by_zone ?? {};
  const zoneData = Object.entries(byZone)
    .map(([zone, count]) => ({ zone, count: count as number }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);

  // Loitering avg
  const loiteringAvg = stats?.avg_loitering_seconds ?? {};
  const loiteringData = Object.entries(loiteringAvg)
    .map(([zone, avg]) => ({ zone, avg: Math.round(avg as number) }));

  // Insights
  const peakHour = timelineData.reduce(
    (best: any, h: any) => {
      const total = (h.animal || 0) + (h.person || 0) + (h.motion || 0) + (h.loitering || 0);
      return total > (best?.total ?? 0) ? { ...h, total } : best;
    },
    null,
  );
  const topZone = zoneData[0];
  const total = stats?.total ?? 0;
  // Hour-of-day heatmap
  const zones = Object.keys(hourlyGrid ?? {});
  const HOURS_ARR = Array.from({ length: 24 }, (_, i) => i);

  function heatCell(zone: string, hour: number) {
    const val = hourlyGrid?.[zone]?.[hour] ?? 0;
    const allVals = zones.flatMap((z) => HOURS_ARR.map((h) => hourlyGrid?.[z]?.[h] ?? 0));
    const max = Math.max(1, ...allVals);
    const r = val / max;
    if (r === 0) return { bg: "var(--bg3)", opacity: 1 };
    if (r < 0.2)  return { bg: "#58a6ff", opacity: 0.25 };
    if (r < 0.45) return { bg: "#d29922", opacity: 0.5 };
    if (r < 0.7)  return { bg: "#f85149", opacity: 0.65 };
    return { bg: "#f85149", opacity: 1 };
  }

  return (
    <div className="space-y-5">

      {/* Period tabs */}
      <div className="flex items-center gap-1.5 p-1 rounded-xl w-fit"
           style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
        {HOURS_OPTIONS.map((o) => (
          <button
            key={o.value}
            onClick={() => setHours(o.value)}
            className="px-4 py-1.5 rounded-lg text-sm font-medium transition-all"
            style={{
              background: hours === o.value ? "var(--accent)" : "transparent",
              color: hours === o.value ? "#000" : "var(--muted)",
              fontWeight: hours === o.value ? 600 : 400,
            }}
          >
            {o.label}
          </button>
        ))}
      </div>

      {/* Insight cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <InsightCard
          icon={AlertTriangle} title="Total Incidents"
          value={total} color="var(--accent)"
          sub={`Last ${hours < 48 ? hours + " hours" : Math.round(hours / 24) + " days"}`}
        />
        <InsightCard
          icon={TrendingUp} title="Top Detection"
          value={donutData[0]?.name ?? "—"}
          color={COLORS[donutData[0]?.name ?? ""] ?? "var(--muted)"}
          sub={donutData[0] ? `${donutData[0].value} events` : "No data"}
        />
        <InsightCard
          icon={MapPin} title="Busiest Zone"
          value={topZone?.zone ?? "—"}
          color="var(--animal)"
          sub={topZone ? `${topZone.count} incidents` : "No data"}
        />
        <InsightCard
          icon={Clock} title="Peak Hour"
          value={peakHour ? `${peakHour.time}` : "—"}
          color="var(--person)"
          sub={peakHour ? `${peakHour.total} events` : "No data"}
        />
      </div>

      {/* Timeline + Donut */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <Section title="Activity Timeline" action={
          <span className="text-xs" style={{ color: "var(--muted)" }}>{timelineData.length} hour buckets</span>
        }>
          <div className="p-4 h-64">
            {timelineData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm" style={{ color: "var(--muted)" }}>
                No incidents in this period.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={timelineData} barCategoryGap="30%">
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" vertical={false} />
                  <XAxis dataKey="time" tick={{ fill: "var(--muted)", fontSize: 10 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: "var(--muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Legend wrapperStyle={{ fontSize: 11, color: "var(--muted)", paddingTop: 8 }} />
                  <Bar dataKey="animal" stackId="a" fill={COLORS.animal} name="Animal" radius={[0,0,0,0]} />
                  <Bar dataKey="person" stackId="a" fill={COLORS.person} name="Person" />
                  <Bar dataKey="motion" stackId="a" fill={COLORS.motion} name="Motion" />
                  <Bar dataKey="loitering" stackId="a" fill={COLORS.loitering} name="Loitering" />
                  <Bar dataKey="abnormal_activity" stackId="a" fill={COLORS.abnormal_activity} name="Abnormal" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Section>

        <Section title="Detection Breakdown">
          <div className="p-4 h-64">
            {donutData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm" style={{ color: "var(--muted)" }}>
                No data yet.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={donutData}
                    cx="50%" cy="45%"
                    innerRadius="52%" outerRadius="78%"
                    dataKey="value" nameKey="name"
                    paddingAngle={3}
                    label={(props: any) => `${((props.percent ?? 0) * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {donutData.map((entry, i) => (
                      <Cell key={i} fill={COLORS[entry.name] ?? "#8b949e"} stroke="transparent" />
                    ))}
                  </Pie>
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Legend
                    wrapperStyle={{ fontSize: 11, color: "var(--muted)" }}
                    formatter={(value) => <span style={{ color: "var(--text)" }}>{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </Section>
      </div>

      {/* Zone comparison + loitering */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <Section title="Zone Activity Comparison">
          <div className="p-4 h-56">
            {zoneData.length === 0 ? (
              <p className="pt-16 text-center text-sm" style={{ color: "var(--muted)" }}>No zone data.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={zoneData} layout="vertical" barCategoryGap="25%">
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" horizontal={false} />
                  <XAxis type="number" tick={{ fill: "var(--muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis dataKey="zone" type="category" width={110} tick={{ fill: "var(--text)", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Bar dataKey="count" name="Incidents" radius={[0,4,4,0]}>
                    {zoneData.map((_, i) => (
                      <Cell key={i} fill={`hsl(${210 + i * 22}, 70%, ${55 - i * 3}%)`} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Section>

        <Section title="Avg Loitering Duration by Zone (seconds)">
          <div className="p-4 h-56">
            {loiteringData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm" style={{ color: "var(--muted)" }}>
                No loitering events in this period.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={loiteringData} barCategoryGap="30%">
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" vertical={false} />
                  <XAxis dataKey="zone" tick={{ fill: "var(--text)", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "var(--muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Bar dataKey="avg" name="Avg seconds" fill={COLORS.loitering} radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Section>
      </div>

      {/* Hour-of-day × zone heatmap */}
      <Section
        title="Activity Heatmap — Hour of Day × Zone"
        action={
          <div className="flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
            <span>Low</span>
            {["rgba(88,166,255,.25)","rgba(210,153,34,.5)","rgba(248,81,73,.65)","rgba(248,81,73,1)"].map((bg, i) => (
              <div key={i} className="w-4 h-4 rounded" style={{ background: bg, border: "1px solid var(--border)" }} />
            ))}
            <span>High</span>
          </div>
        }
      >
        <div className="p-4 overflow-x-auto">
          {zones.length === 0 ? (
            <p className="text-sm py-4" style={{ color: "var(--muted)" }}>No data yet.</p>
          ) : (
            <table className="text-xs w-full">
              <thead>
                <tr>
                  <th className="pr-4 text-left font-medium py-1" style={{ color: "var(--muted)", minWidth: 110 }}>Zone</th>
                  {HOURS_ARR.map((h) => (
                    <th key={h} className="text-center font-normal" style={{ color: "var(--muted)", width: 28 }}>
                      {h.toString().padStart(2, "0")}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {zones.map((zone) => (
                  <tr key={zone}>
                    <td className="py-1 pr-4 font-medium whitespace-nowrap" style={{ color: "var(--text)" }}>{zone}</td>
                    {HOURS_ARR.map((h) => {
                      const val = hourlyGrid?.[zone]?.[h] ?? 0;
                      const { bg, opacity } = heatCell(zone, h);
                      return (
                        <td key={h} className="p-0.5">
                          <div
                            className="w-6 h-6 rounded flex items-center justify-center font-semibold transition-colors"
                            style={{
                              background: bg,
                              opacity,
                              color: val > 0 ? "var(--text)" : "transparent",
                              fontSize: 9,
                              border: val > 0 ? "1px solid rgba(255,255,255,.1)" : "1px solid var(--border)",
                            }}
                            title={`${zone} at ${h}:00 — ${val} events`}
                          >
                            {val || ""}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Section>
    </div>
  );
}

