import { useEffect, useRef, useState, useCallback } from "react";

export interface LiveEvent {
  id: number;
  timestamp: string;
  zone: string;
  zone_name?: string;
  detection_type: string;
  label: string;
  confidence: number | null;
  snapshot_path: string | null;
  source: string;
  appearance_id?: string | null;
  is_repeat_visitor?: boolean;
}

/**
 * Connects to /ws/live and handles two message types:
 *   { type: "incident", ...fields }  → pushed into the events array
 *   { type: "frame",    data: "<b64 JPEG>" } → drawn onto canvasRef (if provided)
 *
 * Frames arrive at ~10 fps from the backend pipeline and are rendered
 * onto a <canvas> element, replacing the old MJPEG <img> approach.
 */
export function useWebSocket(maxEvents = 50, canvasRef?: React.RefObject<HTMLCanvasElement | null>) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  // Keep canvasRef stable in the closure
  const canvasRefRef = useRef(canvasRef);
  canvasRefRef.current = canvasRef;

  const connect = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    // In dev, Vite proxies /ws → ws://localhost:8000
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/live`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      const ping = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 20_000);
      ws.addEventListener("close", () => clearInterval(ping));
    };

    ws.onmessage = ({ data }) => {
      try {
        const msg = JSON.parse(data);

        if (msg.type === "frame" && msg.data) {
          // Render the JPEG frame onto the canvas
          const canvas = canvasRefRef.current?.current;
          if (canvas) {
            const ctx = canvas.getContext("2d");
            if (ctx) {
              const img = new Image();
              img.onload = () => {
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                ctx.drawImage(img, 0, 0);
              };
              img.src = `data:image/jpeg;base64,${msg.data}`;
            }
          }
          return;
        }

        if (msg.type === "incident") {
          // Strip the type envelope before storing
          const { type: _t, ...event } = msg;
          if (event.id) {
            setEvents((prev) => [event as LiveEvent, ...prev].slice(0, maxEvents));
          }
          return;
        }

        // Legacy: messages without a type field are treated as incidents
        if (msg.id) {
          setEvents((prev) => [msg as LiveEvent, ...prev].slice(0, maxEvents));
        }
      } catch { /* ignore malformed messages */ }
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimer.current = setTimeout(connect, 3_000);
    };

    ws.onerror = () => ws.close();
  }, [maxEvents]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { events, connected };
}
