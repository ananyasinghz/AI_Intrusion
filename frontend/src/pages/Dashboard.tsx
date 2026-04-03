import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { incidentsApi, zonesApi, firePIR } from "../api/client";
import { useWebSocket } from "../hooks/useWebSocket";
import { useLiveEventsStore } from "../store/liveEventsStore";
import { Card, StatCard } from "../components/UI/Card";
import { TypePill, typeIcon } from "../components/UI/TypePill";
import { formatDistanceToNow } from "date-fns";
import toast from "react-hot-toast";

export default function Dashboard() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Separate selectors — object literals from Zustand cause a new snapshot each render
  // and trigger "Maximum update depth" with useSyncExternalStore (React 18).
  const events = useLiveEventsStore((s) => s.events);
  const setFrameHandler = useLiveEventsStore((s) => s.setFrameHandler);
  const { connected } = useWebSocket(20);
  const [selectedZone, setSelectedZone] = useState("");

  // Register a frame renderer for the shared websocket connection.
  // This prevents the event feed list from resetting on navigation.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const handler = (base64: string) => {
      const img = new Image();
      img.onload = () => {
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        ctx.drawImage(img, 0, 0);
      };
      img.src = `data:image/jpeg;base64,${base64}`;
    };

    setFrameHandler(handler);
    return () => setFrameHandler(null);
  }, [setFrameHandler]);


  const { data: stats, refetch: refetchStats } = useQuery({
    queryKey: ["stats", 24],
    queryFn: () => incidentsApi.stats(24).then((r) => r.data),
    refetchInterval: 30_000,
  });

  const { data: zones } = useQuery({
    queryKey: ["zones"],
    queryFn: () => zonesApi.list().then((r) => r.data),
  });

  const { data: heatmap } = useQuery({
    queryKey: ["heatmap", 24],
    queryFn: () => incidentsApi.heatmap(24).then((r) => r.data),
    refetchInterval: 30_000,
  });

  // Refresh stats when new WS event arrives
  useEffect(() => {
    if (events.length > 0) refetchStats();
  }, [events.length]);

  const handleFirePIR = async () => {
    try {
      await firePIR(selectedZone || undefined);
      toast.success(`PIR fired in ${selectedZone || "random zone"}`);
    } catch {
      toast.error("Failed to fire PIR");
    }
  };

  const latestEvent = events[0];
  const zoneNames: string[] = zones?.map((z: any) => z.name) ?? [];
  const maxHeat = Math.max(1, ...Object.values(heatmap ?? {}).map((v: any) => v.total ?? 0));

  function heatClass(count: number) {
    const ratio = count / maxHeat;
    if (ratio === 0) return { bg: "var(--bg3)", border: "var(--border)" };
    if (ratio < 0.25) return { bg: "rgba(88,166,255,.1)", border: "var(--accent)" };
    if (ratio < 0.5)  return { bg: "rgba(210,153,34,.15)", border: "var(--animal)" };
    if (ratio < 0.75) return { bg: "rgba(248,81,73,.15)", border: "var(--person)" };
    return { bg: "rgba(248,81,73,.35)", border: "var(--person)" };
  }

  return (
    <div className="space-y-5">
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard value={stats?.total ?? "—"} label="Total (24h)" />
        <StatCard value={stats?.by_type?.animal ?? 0} label="Animal" color="var(--animal)" />
        <StatCard value={stats?.by_type?.person ?? 0} label="Person" color="var(--person)" />
        <StatCard value={stats?.by_type?.motion ?? 0} label="Motion" color="var(--motion)" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        {/* Live Feed */}
        <div className="xl:col-span-1 space-y-5">
          <Card title="Live Feed">
            <div className="relative bg-black aspect-video overflow-hidden rounded-b-xl">
              {/* Canvas receives annotated JPEG frames from the WebSocket pipeline */}
              <canvas
                ref={canvasRef}
                className="w-full h-full object-contain"
                style={{ display: "block" }}
              />
              {/* Overlay when no frames have arrived yet */}
              {!connected && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2"
                     style={{ background: "rgba(0,0,0,.7)" }}>
                  <div className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin"
                       style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
                  <p className="text-xs" style={{ color: "var(--muted)" }}>Connecting…</p>
                </div>
              )}
              {latestEvent && (
                <div className="absolute top-2 left-2">
                  <span
                    className="text-xs font-semibold px-2 py-1 rounded-md"
                    style={{ background: "rgba(0,0,0,.7)", color: "var(--accent)" }}
                  >
                    {typeIcon(latestEvent.detection_type)} {latestEvent.label} · {latestEvent.zone_name ?? latestEvent.zone}
                  </span>
                </div>
              )}
            </div>
          </Card>

          {/* Latest Incident */}
          <Card title="Latest Incident">
            <div className="p-4">
              {latestEvent ? (
                <div className="flex items-start gap-3">
                  <span className="text-2xl">{typeIcon(latestEvent.detection_type)}</span>
                  <div>
                    <p className="font-semibold text-sm" style={{ color: "var(--text)" }}>
                      {latestEvent.label}
                    </p>
                    <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
                      {latestEvent.zone} · {formatDistanceToNow(new Date(latestEvent.timestamp + "Z"), { addSuffix: true })}
                    </p>
                    <div className="mt-1.5">
                      <TypePill type={latestEvent.detection_type} />
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-sm" style={{ color: "var(--muted)" }}>No incidents yet.</p>
              )}
            </div>
          </Card>

          {/* PIR Test */}
          <Card title="Test Controls">
            <div className="p-4 space-y-3">
              <select
                value={selectedZone}
                onChange={(e) => setSelectedZone(e.target.value)}
                className="w-full rounded-lg px-3 py-2 text-sm"
                style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }}
              >
                <option value="">Random zone</option>
                {zoneNames.map((z) => <option key={z} value={z}>{z}</option>)}
              </select>
              <button
                onClick={handleFirePIR}
                className="w-full py-2 rounded-lg text-sm font-semibold transition-opacity hover:opacity-80"
                style={{ background: "rgba(210,153,34,.2)", color: "var(--animal)", border: "1px solid var(--animal)" }}
              >
                🔔 Fire Mock PIR
              </button>
              <p className="text-xs" style={{ color: "var(--muted)" }}>
                Simulates a PIR trigger without hardware.
              </p>
            </div>
          </Card>
        </div>

        {/* Right column */}
        <div className="xl:col-span-2 space-y-5">
          {/* Zone Heatmap */}
          <Card title="Zone Heatmap (24h)">
            <div className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
              {zoneNames.length === 0 && (
                <p className="col-span-4 text-sm" style={{ color: "var(--muted)" }}>No zones configured.</p>
              )}
              {zoneNames.map((zone) => {
                const info = heatmap?.[zone] ?? {};
                const count = info.total ?? 0;
                const style = heatClass(count);
                return (
                  <div
                    key={zone}
                    className="rounded-xl p-4 text-center"
                    style={{ background: style.bg, border: `1px solid ${style.border}` }}
                  >
                    <p className="text-xs mb-1 truncate" style={{ color: "var(--muted)" }}>{zone}</p>
                    <p className="text-2xl font-bold" style={{ color: "var(--text)" }}>{count}</p>
                    <div className="text-xs mt-1 space-x-1">
                      {info.animal ? <span style={{ color: "var(--animal)" }}>🐾{info.animal}</span> : null}
                      {info.person ? <span style={{ color: "var(--person)" }}>🚶{info.person}</span> : null}
                      {info.motion ? <span style={{ color: "var(--motion)" }}>⚠️{info.motion}</span> : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Live Event Feed */}
          <Card title="Live Event Feed" action={
            <span className="text-xs" style={{ color: connected ? "var(--motion)" : "var(--muted)" }}>
              {connected ? "● Live" : "● Offline"}
            </span>
          }>
            <div className="divide-y" style={{ borderColor: "var(--border)" }}>
              {events.length === 0 && (
                <p className="px-4 py-5 text-sm" style={{ color: "var(--muted)" }}>
                  Waiting for events…
                </p>
              )}
              {events.slice(0, 8).map((ev) => (
                <div key={ev.id} className="flex items-center gap-3 px-4 py-3">
                  <span className="text-lg">{typeIcon(ev.detection_type)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <p className="text-sm font-medium truncate" style={{ color: "var(--text)" }}>
                        {ev.label}
                      </p>
                      {ev.is_repeat_visitor && (
                        <span
                          className="text-xs px-1.5 py-0.5 rounded-full font-semibold"
                          style={{ background: "rgba(248,81,73,.15)", color: "#f85149", border: "1px solid #f8514960" }}
                        >
                          repeat
                        </span>
                      )}
                    </div>
                    <p className="text-xs" style={{ color: "var(--muted)" }}>
                      {ev.zone_name ?? ev.zone} · {formatDistanceToNow(new Date(ev.timestamp + "Z"), { addSuffix: true })}
                    </p>
                  </div>
                  <TypePill type={ev.detection_type} />
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
