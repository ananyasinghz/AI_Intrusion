import { useState } from "react";
import { assistantApi } from "../api/client";
import { Card } from "../components/UI/Card";
import { MessageSquare, Send } from "lucide-react";
import toast from "react-hot-toast";
import { format } from "date-fns";

interface IncidentRow {
  id: number;
  timestamp: string | null;
  zone: string;
  detection_type: string;
  label: string | null;
  status: string;
  confidence: number | null;
}

interface ChatTurn {
  role: "user" | "assistant";
  text: string;
  incidents?: IncidentRow[];
  filters_used?: Record<string, unknown>;
}

export default function Assistant() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [turns, setTurns] = useState<ChatTurn[]>([]);

  async function send() {
    const msg = input.trim();
    if (!msg || loading) return;
    setInput("");
    setTurns((t) => [...t, { role: "user", text: msg }]);
    setLoading(true);
    try {
      const { data } = await assistantApi.chat(msg);
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          text: data.reply,
          incidents: data.incidents as IncidentRow[],
          filters_used: data.filters_used,
        },
      ]);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.error(err.response?.data?.detail ?? "Request failed");
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          text: "Something went wrong. Check that GROQ_API_KEY is set on the server and try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5 max-w-4xl">
      <div className="flex items-center gap-2">
        <MessageSquare size={22} style={{ color: "var(--accent)" }} />
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--text)" }}>
            Data assistant
          </h1>
          <p className="text-xs" style={{ color: "var(--muted)" }}>
            Ask in plain language — e.g. “animal detections near the gate after 10pm this week”.
            Filters are applied safely on the server (no raw SQL from the model).
          </p>
        </div>
      </div>

      <Card title="Conversation">
        <div
          className="p-4 space-y-4 min-h-[200px] max-h-[45vh] overflow-y-auto"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          {turns.length === 0 && (
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              No messages yet. Type a question below.
            </p>
          )}
          {turns.map((turn, i) => (
            <div key={i} className="space-y-2">
              <div
                className={`text-sm rounded-lg px-3 py-2 max-w-[95%] ${
                  turn.role === "user" ? "ml-auto" : ""
                }`}
                style={{
                  background: turn.role === "user" ? "rgba(88,166,255,.15)" : "var(--bg)",
                  color: "var(--text)",
                  border: "1px solid var(--border)",
                }}
              >
                <span className="text-xs uppercase tracking-wide block mb-1" style={{ color: "var(--muted)" }}>
                  {turn.role === "user" ? "You" : "Assistant"}
                </span>
                <pre className="whitespace-pre-wrap font-sans">{turn.text}</pre>
              </div>
              {turn.role === "assistant" && turn.filters_used && (
                <details className="text-xs" style={{ color: "var(--muted)" }}>
                  <summary className="cursor-pointer">Filters used</summary>
                  <pre className="mt-1 p-2 rounded overflow-x-auto" style={{ background: "var(--bg2)" }}>
                    {JSON.stringify(turn.filters_used, null, 2)}
                  </pre>
                </details>
              )}
              {turn.role === "assistant" && turn.incidents && turn.incidents.length > 0 && (
                <div className="overflow-x-auto rounded-lg border text-xs" style={{ borderColor: "var(--border)" }}>
                  <table className="w-full text-left">
                    <thead>
                      <tr style={{ background: "var(--bg2)", color: "var(--muted)" }}>
                        <th className="px-2 py-1.5 font-medium">Time</th>
                        <th className="px-2 py-1.5 font-medium">Zone</th>
                        <th className="px-2 py-1.5 font-medium">Type</th>
                        <th className="px-2 py-1.5 font-medium">Label</th>
                        <th className="px-2 py-1.5 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {turn.incidents.map((row) => (
                        <tr key={row.id} style={{ borderTop: "1px solid var(--border)" }}>
                          <td className="px-2 py-1.5 whitespace-nowrap" style={{ color: "var(--text)" }}>
                            {row.timestamp
                              ? format(new Date(row.timestamp), "MMM d, HH:mm")
                              : "—"}
                          </td>
                          <td className="px-2 py-1.5">{row.zone}</td>
                          <td className="px-2 py-1.5">{row.detection_type}</td>
                          <td className="px-2 py-1.5">{row.label ?? "—"}</td>
                          <td className="px-2 py-1.5 capitalize">{row.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="p-3 flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder="Ask about incidents…"
            rows={2}
            className="flex-1 rounded-lg px-3 py-2 text-sm resize-none"
            style={{
              background: "var(--bg2)",
              color: "var(--text)",
              border: "1px solid var(--border)",
            }}
            disabled={loading}
          />
          <button
            type="button"
            onClick={() => void send()}
            disabled={loading || !input.trim()}
            className="shrink-0 px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 self-end"
            style={{
              background: loading || !input.trim() ? "var(--border)" : "var(--accent)",
              color: loading || !input.trim() ? "var(--muted)" : "#000",
            }}
          >
            <Send size={16} />
            {loading ? "…" : "Send"}
          </button>
        </div>
      </Card>
    </div>
  );
}
