import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zonesApi } from "../api/client";
import { Card } from "../components/UI/Card";
import { useAuthStore } from "../store/authStore";
import { Plus, Trash2, Edit2, CheckCircle, XCircle } from "lucide-react";
import toast from "react-hot-toast";

interface ZoneForm {
  name: string;
  description: string;
  loitering_threshold_seconds: number;
  tripwire_x1: string;
  tripwire_y1: string;
  tripwire_x2: string;
  tripwire_y2: string;
}

export default function Zones() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "admin";
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const qc = useQueryClient();

  const { data: zones, isLoading } = useQuery({
    queryKey: ["zones"],
    queryFn: () => zonesApi.list().then((r) => r.data),
  });

  const { register, handleSubmit, reset } = useForm<ZoneForm>({
    defaultValues: { loitering_threshold_seconds: 30 },
  });

  const createMut = useMutation({
    mutationFn: (d: any) => editId ? zonesApi.update(editId, d) : zonesApi.create(d),
    onSuccess: () => {
      toast.success(editId ? "Zone updated" : "Zone created");
      qc.invalidateQueries({ queryKey: ["zones"] });
      setShowForm(false);
      setEditId(null);
      reset();
    },
    onError: (e: any) => toast.error(e.response?.data?.detail ?? "Error"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => zonesApi.delete(id),
    onSuccess: () => {
      toast.success("Zone deleted");
      qc.invalidateQueries({ queryKey: ["zones"] });
    },
  });

  const onSubmit = (data: ZoneForm) => {
    const tripwire = data.tripwire_x1
      ? [[parseInt(data.tripwire_x1), parseInt(data.tripwire_y1)],
         [parseInt(data.tripwire_x2), parseInt(data.tripwire_y2)]]
      : null;
    createMut.mutate({
      name: data.name,
      description: data.description,
      loitering_threshold_seconds: data.loitering_threshold_seconds,
      tripwire,
    });
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold" style={{ color: "var(--text)" }}>Zones</h1>
        {isAdmin && (
          <button onClick={() => { setShowForm(true); setEditId(null); reset(); }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium"
            style={{ background: "var(--accent)", color: "#000" }}>
            <Plus size={16} /> Add Zone
          </button>
        )}
      </div>

      {/* Create/Edit form */}
      {showForm && isAdmin && (
        <Card title={editId ? "Edit Zone" : "New Zone"}>
          <form onSubmit={handleSubmit(onSubmit)} className="p-4 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>Zone Name *</label>
                <input {...register("name", { required: true })}
                  className="w-full rounded-lg px-3 py-2 text-sm"
                  style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }}
                  placeholder="Main Entrance" />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>Description</label>
                <input {...register("description")}
                  className="w-full rounded-lg px-3 py-2 text-sm"
                  style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }} />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>Loitering Threshold (s)</label>
                <input {...register("loitering_threshold_seconds", { valueAsNumber: true })} type="number"
                  className="w-full rounded-lg px-3 py-2 text-sm"
                  style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }} />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium mb-2" style={{ color: "var(--muted)" }}>
                Tripwire Coordinates (optional — pixel coordinates on camera frame)
              </label>
              <div className="grid grid-cols-4 gap-2">
                {[["tripwire_x1","X1"],["tripwire_y1","Y1"],["tripwire_x2","X2"],["tripwire_y2","Y2"]].map(([name, label]) => (
                  <div key={name}>
                    <label className="block text-xs mb-1" style={{ color: "var(--muted)" }}>{label}</label>
                    <input {...register(name as keyof ZoneForm)} type="number" placeholder="0"
                      className="w-full rounded-lg px-3 py-2 text-sm"
                      style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }} />
                  </div>
                ))}
              </div>
              <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
                Leave blank to disable zone crossing alerts for this zone.
              </p>
            </div>

            <div className="flex gap-3">
              <button type="submit"
                className="px-5 py-2 rounded-lg text-sm font-semibold"
                style={{ background: "var(--accent)", color: "#000" }}>
                {editId ? "Save Changes" : "Create Zone"}
              </button>
              <button type="button" onClick={() => { setShowForm(false); setEditId(null); reset(); }}
                className="px-5 py-2 rounded-lg text-sm font-medium"
                style={{ background: "var(--bg3)", color: "var(--text)", border: "1px solid var(--border)" }}>
                Cancel
              </button>
            </div>
          </form>
        </Card>
      )}

      {/* Zone list */}
      {isLoading && <p className="text-sm" style={{ color: "var(--muted)" }}>Loading zones…</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {zones?.map((zone: any) => (
          <Card key={zone.id}>
            <div className="p-4">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-semibold" style={{ color: "var(--text)" }}>{zone.name}</h3>
                  {zone.description && (
                    <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>{zone.description}</p>
                  )}
                </div>
                <span className="flex items-center gap-1 text-xs"
                      style={{ color: zone.is_active ? "var(--motion)" : "var(--muted)" }}>
                  {zone.is_active ? <CheckCircle size={12} /> : <XCircle size={12} />}
                  {zone.is_active ? "Active" : "Inactive"}
                </span>
              </div>

              <div className="space-y-1.5 text-xs" style={{ color: "var(--muted)" }}>
                <div>Loitering threshold: <span style={{ color: "var(--text)" }}>{zone.loitering_threshold_seconds}s</span></div>
                <div>Camera: <span style={{ color: "var(--text)" }}>Index {zone.camera_index}</span></div>
                <div>Tripwire: <span style={{ color: zone.tripwire ? "var(--accent)" : "var(--muted)" }}>
                  {zone.tripwire ? `[${zone.tripwire[0]}] → [${zone.tripwire[1]}]` : "Not set"}
                </span></div>
              </div>

              {isAdmin && (
                <div className="flex gap-2 mt-4">
                  <button onClick={() => toast("Edit coming in next release")}
                    className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg"
                    style={{ background: "var(--bg3)", color: "var(--muted)", border: "1px solid var(--border)" }}>
                    <Edit2 size={11} /> Edit
                  </button>
                  <button onClick={() => deleteMut.mutate(zone.id)}
                    className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg"
                    style={{ background: "rgba(248,81,73,.1)", color: "var(--person)", border: "1px solid var(--person)" }}>
                    <Trash2 size={11} /> Delete
                  </button>
                </div>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
