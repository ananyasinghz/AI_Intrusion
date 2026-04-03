import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { reportsApi } from "../api/client";
import { Card } from "../components/UI/Card";
import { FileText, Download, Loader2 } from "lucide-react";
import { format } from "date-fns";
import toast from "react-hot-toast";

export default function Reports() {
  const [genType, setGenType] = useState<"daily"|"weekly"|"custom">("daily");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [fileFormat, setFileFormat] = useState<"pdf"|"csv">("pdf");

  const { data: reports, refetch } = useQuery({
    queryKey: ["reports"],
    queryFn: () => reportsApi.list().then((r) => r.data),
  });

  const genMut = useMutation({
    mutationFn: () =>
      reportsApi.generate({
        report_type: genType,
        file_format: fileFormat,
        period_start: dateFrom || undefined,
        period_end: dateTo || undefined,
      }),
    onSuccess: () => {
      toast.success("Report generation started");
      setTimeout(refetch, 2000);
    },
    onError: (e: any) => toast.error(e.response?.data?.detail ?? "Error generating report"),
  });

  const downloadMut = useMutation({
    mutationFn: (id: number) => reportsApi.download(id),
    onSuccess: (res, id) => {
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `report_${id}.${fileFormat}`;
      a.click();
    },
  });

  return (
    <div className="space-y-5">
      {/* Generate form */}
      <Card title="Generate Report">
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>Report Type</label>
              <select value={genType} onChange={(e) => setGenType(e.target.value as any)}
                className="w-full rounded-lg px-3 py-2 text-sm"
                style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }}>
                <option value="daily">Daily (yesterday)</option>
                <option value="weekly">Weekly (last 7 days)</option>
                <option value="custom">Custom range</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>Format</label>
              <select value={fileFormat} onChange={(e) => setFileFormat(e.target.value as any)}
                className="w-full rounded-lg px-3 py-2 text-sm"
                style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }}>
                <option value="pdf">PDF</option>
                <option value="csv">CSV</option>
              </select>
            </div>
          </div>

          {genType === "custom" && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>From</label>
                <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 text-sm"
                  style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }} />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>To</label>
                <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 text-sm"
                  style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }} />
              </div>
            </div>
          )}

          <button onClick={() => genMut.mutate()} disabled={genMut.isPending}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold disabled:opacity-60"
            style={{ background: "var(--accent)", color: "#000" }}>
            {genMut.isPending ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
            Generate
          </button>
        </div>
      </Card>

      {/* Report history */}
      <Card title="Report History">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "var(--bg3)" }}>
                {["ID","Generated","Period","Type","Format",""].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-xs font-medium" style={{ color: "var(--muted)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(!reports || reports.length === 0) && (
                <tr><td colSpan={6} className="px-4 py-8 text-center" style={{ color: "var(--muted)" }}>
                  No reports generated yet.
                </td></tr>
              )}
              {reports?.map((r: any) => (
                <tr key={r.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="px-4 py-3" style={{ color: "var(--muted)" }}>{r.id}</td>
                  <td className="px-4 py-3" style={{ color: "var(--text)" }}>
                    {format(new Date(r.generated_at + "Z"), "MM/dd HH:mm")}
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: "var(--muted)" }}>
                    {format(new Date(r.period_start), "MM/dd")} – {format(new Date(r.period_end), "MM/dd")}
                  </td>
                  <td className="px-4 py-3">
                    <span className="capitalize text-xs px-2 py-0.5 rounded"
                          style={{ background: "var(--bg3)", color: "var(--text)" }}>{r.report_type}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="uppercase text-xs font-mono px-2 py-0.5 rounded"
                          style={{ background: "var(--bg3)", color: "var(--muted)" }}>{r.file_format}</span>
                  </td>
                  <td className="px-4 py-3">
                    {r.file_path && (
                      <button onClick={() => downloadMut.mutate(r.id)}
                        className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg"
                        style={{ background: "rgba(88,166,255,.1)", color: "var(--accent)", border: "1px solid var(--accent)" }}>
                        <Download size={11} /> Download
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
