import { useEffect, useRef, useCallback } from "react";

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
 *   { type: "frame",    data: "<b64 JPEG>" } → forwarded to the current frame handler (if any)
 *
 * Frames arrive at ~10 fps from the backend pipeline and are rendered
 * by whoever registers a frame handler (e.g. Dashboard).
 */
import { useLiveEventsStore } from "../store/liveEventsStore";

export function useWebSocket(maxEvents = 50) {
  const events = useLiveEventsStore((s) => s.events);
  const connected = useLiveEventsStore((s) => s.connected);
  const setConnected = useLiveEventsStore((s) => s.setConnected);
  const pushEvent = useLiveEventsStore((s) => s.pushEvent);

  const frameHandlerRef = useRef<((base64Jpeg: string) => void) | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const mountedRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);
  const frameHandler = useLiveEventsStore((s) => s.frameHandler);
  useEffect(() => {
    frameHandlerRef.current = frameHandler;
  }, [frameHandler]);

  const connect = useCallback(() => {
    // Avoid duplicate sockets when reconnect timer and manual connect overlap.
    const current = wsRef.current;
    if (current && (current.readyState === WebSocket.OPEN || current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    // Avoid Vite WS proxy instability in dev by connecting directly to backend.
    const wsUrl = import.meta.env.DEV
      ? "ws://127.0.0.1:8000/ws/live"
      : `${proto}://${window.location.host}/ws/live`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttemptsRef.current = 0;
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
          const handler = frameHandlerRef.current;
          if (handler) handler(msg.data);
          return;
        }

        if (msg.type === "incident") {
          // Strip the type envelope before storing
          const { type: _t, ...event } = msg;
          if (event.id) {
            pushEvent(event as LiveEvent, maxEvents);
          }
          return;
        }

        // Legacy: messages without a type field are treated as incidents
        if (msg.id) {
          pushEvent(msg as LiveEvent, maxEvents);
        }
      } catch { /* ignore malformed messages */ }
    };

    ws.onclose = () => {
      // Ignore stale sockets after a newer socket replaced this one.
      if (wsRef.current !== ws) return;
      setConnected(false);

      // Don't reconnect after unmount/cleanup.
      if (!mountedRef.current) return;

      // Exponential backoff (max 10s) to reduce reconnect storms in dev.
      reconnectAttemptsRef.current += 1;
      const backoffMs = Math.min(10_000, 1000 * (2 ** Math.min(reconnectAttemptsRef.current, 4)));
      reconnectTimer.current = setTimeout(connect, backoffMs);
    };

    ws.onerror = () => ws.close();
  }, [maxEvents]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  return { events, connected };
}
