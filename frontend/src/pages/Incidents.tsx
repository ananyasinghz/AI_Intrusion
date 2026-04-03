import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { incidentsApi, zonesApi } from "../api/client";
import { TypePill } from "../components/UI/TypePill";
import { Card } from "../components/UI/Card";
import { CheckCircle, X, ZoomIn } from "lucide-react";
import { format } from "date-fns";
import toast from "react-hot-toast";

export default function Incidents() {
  const [page, setPage] = useState(1);
  const [filterType, setFilterType] = useState("");
  const [filterZone, setFilterZone] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [modalImg, setModalImg] = useState<string | null>(null);
  const qc = useQueryClient();
  const PER_PAGE = 15;

  const { data: zones } = useQuery({
    queryKey: ["zones"],
    queryFn: () => zonesApi.list().then((r) => r.data),
  });

  interface IncidentsPage { total: number; page: number; per_page: number; items: any[] }
  const { data, isLoading } = useQuery<IncidentsPage>({
    queryKey: ["incidents", page, filterType, filterZone, dateFrom, dateTo],
    queryFn: () =>
      incidentsApi
        .list({ page, per_page: PER_PAGE, detection_type: filterType, zone: filterZone, date_from: dateFrom, date_to: dateTo })
        .then((r) => r.data),
    placeholderData: (prev) => prev,
  });

  const resolve = useMutation({
    mutationFn: (id: number) => incidentsApi.resolve(id),
    onSuccess: () => {
      toast.success("Incident resolved");
      qc.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  const totalPages = data ? Math.ceil(data.total / PER_PAGE) : 1;

  function snapshotUrl(path: string | null) {
    if (!path) return null;
    const fname = path.split(/[/\\]/).pop();
    return `/snapshots/${fname}`;
  }

  return (
    <div className="space-y-5">
      <Card title="Incident Log" action={
        <span className="text-xs" style={{ color: "var(--muted)" }}>{data?.total ?? 0} total</span>
      }>
        {/* Filters */}
        <div className="px-4 py-3 flex flex-wrap gap-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <select value={filterType} onChange={(e) => { setFilterType(e.target.value); setPage(1); }}
            className="rounded-lg px-3 py-1.5 text-sm"
            style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }}>
            <option value="">All Types</option>
            {["animal","person","motion","loitering","zone_crossing","abnormal_activity"].map(t =>
              <option key={t} value={t}>{t}</option>
            )}
          </select>
          <select value={filterZone} onChange={(e) => { setFilterZone(e.target.value); setPage(1); }}
            className="rounded-lg px-3 py-1.5 text-sm"
            style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }}>
            <option value="">All Zones</option>
            {(zones ?? []).map((z: any) => <option key={z.id} value={z.name}>{z.name}</option>)}
          </select>
          <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
            className="rounded-lg px-3 py-1.5 text-sm"
            style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }} />
          <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
            className="rounded-lg px-3 py-1.5 text-sm"
            style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }} />
          {(filterType || filterZone || dateFrom || dateTo) && (
            <button onClick={() => { setFilterType(""); setFilterZone(""); setDateFrom(""); setDateTo(""); setPage(1); }}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg"
              style={{ background: "var(--bg3)", color: "var(--muted)", border: "1px solid var(--border)" }}>
              <X size={12} /> Clear
            </button>
          )}
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "var(--bg3)" }}>
                {["ID","Time","Zone","Type","Label","Confidence","Snapshot",""].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-xs font-medium" style={{ color: "var(--muted)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={8} className="px-4 py-8 text-center" style={{ color: "var(--muted)" }}>Loading…</td></tr>
              )}
              {!isLoading && data?.items?.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-8 text-center" style={{ color: "var(--muted)" }}>No incidents found.</td></tr>
              )}
              {data?.items?.map((inc: any) => {
                const thumb = snapshotUrl(inc.snapshot_path);
                return (
                  <tr key={inc.id} className="border-t transition-colors hover:bg-opacity-50"
                      style={{ borderColor: "var(--border)" }}>
                    <td className="px-4 py-3" style={{ color: "var(--muted)" }}>{inc.id}</td>
                    <td className="px-4 py-3 whitespace-nowrap" style={{ color: "var(--text)" }}>
                      {format(new Date(inc.timestamp + "Z"), "MM/dd HH:mm:ss")}
                    </td>
                    <td className="px-4 py-3" style={{ color: "var(--text)" }}>{inc.zone}</td>
                    <td className="px-4 py-3"><TypePill type={inc.detection_type} /></td>
                    <td className="px-4 py-3 max-w-[140px] truncate" style={{ color: "var(--text)" }}>{inc.label}</td>
                    <td className="px-4 py-3" style={{ color: "var(--muted)" }}>
                      {inc.confidence ? `${(inc.confidence * 100).toFixed(0)}%` : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {thumb ? (
                        <button onClick={() => setModalImg(thumb)} className="relative group">
                          <img src={thumb} alt="snapshot" className="w-12 h-9 object-cover rounded" />
                          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity rounded"
                               style={{ background: "rgba(0,0,0,.6)" }}>
                            <ZoomIn size={14} className="text-white" />
                          </div>
                        </button>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {inc.status === "open" && (
                        <button onClick={() => resolve.mutate(inc.id)}
                          className="flex items-center gap-1 text-xs px-2 py-1 rounded"
                          style={{ background: "rgba(63,185,80,.1)", color: "var(--motion)", border: "1px solid var(--motion)" }}>
                          <CheckCircle size={11} /> Resolve
                        </button>
                      )}
                      {inc.status === "resolved" && (
                        <span className="text-xs" style={{ color: "var(--muted)" }}>Resolved</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex justify-center gap-2 px-4 py-3" style={{ borderTop: "1px solid var(--border)" }}>
            {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => i + 1).map((p) => (
              <button key={p} onClick={() => setPage(p)}
                className="w-8 h-8 rounded-lg text-sm font-medium"
                style={{
                  background: p === page ? "var(--accent)" : "var(--bg3)",
                  color: p === page ? "#000" : "var(--text)",
                  border: "1px solid var(--border)",
                }}>
                {p}
              </button>
            ))}
          </div>
        )}
      </Card>

      {/* Snapshot Modal */}
      {modalImg && (
        <div className="fixed inset-0 z-50 flex items-center justify-center"
             style={{ background: "rgba(0,0,0,.8)" }}
             onClick={() => setModalImg(null)}>
          <img src={modalImg} alt="snapshot" className="max-w-4xl max-h-screen rounded-xl object-contain" />
        </div>
      )}
    </div>
  );
}
