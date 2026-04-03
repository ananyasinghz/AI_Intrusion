import { useCallback, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { approvedPersonsApi } from "../api/client";
import { Card } from "../components/UI/Card";
import {
  UserCheck,
  UserPlus,
  Trash2,
  X,
  Upload,
  Camera,
  CheckCircle,
  AlertCircle,
  Loader2,
} from "lucide-react";
import toast from "react-hot-toast";
import { formatDistanceToNow } from "date-fns";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ApprovedPerson {
  id: number;
  name: string;
  notes: string | null;
  enrolled_at: string | null;
  enrolled_by: number | null;
  embedding_model: string | null;
}

type EnrollStatus = "pending" | "enrolling" | "ok" | "error";

interface StagedFile {
  uid: string;
  file: File;
  previewUrl: string;
  name: string;
  notes: string;
  status: EnrollStatus;
  error?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fileToName(file: File): string {
  return file.name
    .replace(/\.[^.]+$/, "")        // strip extension
    .replace(/[_\-]+/g, " ")        // underscores/hyphens → spaces
    .replace(/\b\w/g, (c) => c.toUpperCase()); // title-case
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string;
      resolve(dataUrl.split(",")[1]); // strip data:...;base64, prefix
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function uid(): string {
  return Math.random().toString(36).slice(2);
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ApprovedPersons() {
  const qc = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [staged, setStaged] = useState<StagedFile[]>([]);
  const [enrolling, setEnrolling] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  // ── Data ──────────────────────────────────────────────────────────────────

  const { data: persons = [], isLoading } = useQuery<ApprovedPerson[]>({
    queryKey: ["approved-persons"],
    queryFn: () => approvedPersonsApi.list().then((r) => r.data),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => approvedPersonsApi.remove(id),
    onSuccess: () => {
      toast.success("Person removed from approved list");
      qc.invalidateQueries({ queryKey: ["approved-persons"] });
    },
    onError: () => toast.error("Failed to remove person"),
  });

  // ── File staging ──────────────────────────────────────────────────────────

  const addFiles = useCallback((files: File[]) => {
    const imageFiles = files.filter((f) => f.type.startsWith("image/"));
    if (imageFiles.length === 0) return;

    const newItems: StagedFile[] = imageFiles.map((file) => ({
      uid: uid(),
      file,
      previewUrl: URL.createObjectURL(file),
      name: fileToName(file),
      notes: "",
      status: "pending",
    }));
    setStaged((prev) => [...prev, ...newItems]);
  }, []);

  function removeStaged(uid: string) {
    setStaged((prev) => {
      const item = prev.find((f) => f.uid === uid);
      if (item) URL.revokeObjectURL(item.previewUrl);
      return prev.filter((f) => f.uid !== uid);
    });
  }

  function updateStaged(uid: string, patch: Partial<Pick<StagedFile, "name" | "notes">>) {
    setStaged((prev) =>
      prev.map((f) => (f.uid === uid ? { ...f, ...patch } : f))
    );
  }

  // ── Drag and drop ─────────────────────────────────────────────────────────

  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(true);
  }

  function onDragLeave() {
    setDragOver(false);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    addFiles(Array.from(e.dataTransfer.files));
  }

  // ── Enrollment ────────────────────────────────────────────────────────────

  async function enrollAll() {
    const pending = staged.filter((f) => f.status === "pending");
    if (pending.length === 0) return;

    setEnrolling(true);
    // Mark all pending as enrolling
    setStaged((prev) =>
      prev.map((f) => (f.status === "pending" ? { ...f, status: "enrolling" } : f))
    );

    // Build payload
    const items = await Promise.all(
      pending.map(async (f) => ({
        uid: f.uid,
        name: f.name.trim() || fileToName(f.file),
        image_b64: await readAsBase64(f.file),
        notes: f.notes || undefined,
      }))
    );

    try {
      const res = await approvedPersonsApi.batchEnroll(
        items.map(({ name, image_b64, notes }) => ({ name, image_b64, notes }))
      );
      const results: { status: string; detail?: string; name?: string }[] = res.data;

      // Map results back by index (API preserves order)
      setStaged((prev) => {
        const enrollingItems = prev.filter((f) =>
          items.some((i) => i.uid === f.uid)
        );
        let ri = 0;
        return prev.map((f) => {
          if (!items.some((i) => i.uid === f.uid)) return f;
          const result = results[ri++];
          if (result?.status === "ok") {
            return { ...f, status: "ok" };
          } else {
            return { ...f, status: "error", error: result?.detail ?? "Unknown error" };
          }
        });
      });

      const okCount = results.filter((r) => r.status === "ok").length;
      const errCount = results.filter((r) => r.status === "error").length;

      if (okCount > 0) {
        toast.success(`${okCount} person${okCount > 1 ? "s" : ""} enrolled successfully`);
        qc.invalidateQueries({ queryKey: ["approved-persons"] });
      }
      if (errCount > 0) {
        toast.error(`${errCount} image${errCount > 1 ? "s" : ""} failed — check the staging area`);
      }
    } catch {
      setStaged((prev) =>
        prev.map((f) =>
          f.status === "enrolling"
            ? { ...f, status: "error", error: "Network error" }
            : f
        )
      );
      toast.error("Batch enrollment request failed");
    } finally {
      setEnrolling(false);
    }
  }

  function closeModal() {
    if (enrolling) return;
    staged.forEach((f) => URL.revokeObjectURL(f.previewUrl));
    setStaged([]);
    setShowModal(false);
  }

  const pendingCount = staged.filter((f) => f.status === "pending").length;
  const hasStaged = staged.length > 0;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--text)" }}>
            Approved Persons
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
            Enrolled students and staff will not trigger intruder alerts.
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-opacity hover:opacity-80"
          style={{
            background: "rgba(88,166,255,.15)",
            color: "var(--accent)",
            border: "1px solid var(--accent)",
          }}
        >
          <UserPlus size={15} />
          Enroll People
        </button>
      </div>

      {/* Info banner */}
      <div
        className="flex items-start gap-3 px-4 py-3 rounded-xl text-sm"
        style={{
          background: "rgba(88,166,255,.07)",
          border: "1px solid rgba(88,166,255,.2)",
          color: "var(--muted)",
        }}
      >
        <UserCheck size={16} className="mt-0.5 shrink-0" style={{ color: "var(--accent)" }} />
        <span>
          Recognition is based on{" "}
          <strong style={{ color: "var(--text)" }}>face biometrics (ArcFace)</strong> — the
          same person is recognised regardless of outfit, lighting, or day of the week.
          Upload one clear face photo per person.
        </span>
      </div>

      {/* Enrolled persons list */}
      <Card title={`Enrolled (${persons.length})`}>
        {isLoading ? (
          <p className="px-4 py-6 text-sm" style={{ color: "var(--muted)" }}>
            Loading…
          </p>
        ) : persons.length === 0 ? (
          <div className="px-4 py-10 flex flex-col items-center gap-3">
            <UserCheck size={32} style={{ color: "var(--muted)" }} />
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              No approved persons enrolled yet.
            </p>
            <button
              onClick={() => setShowModal(true)}
              className="text-xs px-4 py-2 rounded-lg font-medium hover:opacity-80 transition-opacity"
              style={{
                background: "rgba(88,166,255,.15)",
                color: "var(--accent)",
                border: "1px solid var(--accent)",
              }}
            >
              Enroll your first person
            </button>
          </div>
        ) : (
          <div className="divide-y" style={{ borderColor: "var(--border)" }}>
            {persons.map((p) => (
              <div key={p.id} className="flex items-center gap-3 px-4 py-3">
                <div
                  className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold shrink-0"
                  style={{ background: "rgba(88,166,255,.15)", color: "var(--accent)" }}
                >
                  {p.name.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: "var(--text)" }}>
                    {p.name}
                  </p>
                  <p className="text-xs" style={{ color: "var(--muted)" }}>
                    {p.notes ? `${p.notes} · ` : ""}
                    {p.enrolled_at
                      ? `Enrolled ${formatDistanceToNow(new Date(p.enrolled_at), {
                          addSuffix: true,
                        })}`
                      : "Recently enrolled"}
                  </p>
                </div>
                <button
                  onClick={() => {
                    if (confirm(`Remove ${p.name} from approved persons?`)) {
                      deleteMutation.mutate(p.id);
                    }
                  }}
                  className="p-1.5 rounded-lg transition-opacity hover:opacity-70"
                  style={{ color: "var(--person)" }}
                  title="Remove"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* ── Enrollment modal ────────────────────────────────────────────────── */}
      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center p-4 overflow-y-auto"
          style={{ background: "rgba(0,0,0,.65)" }}
          onClick={(e) => e.target === e.currentTarget && closeModal()}
        >
          <div
            className="w-full max-w-2xl my-8 rounded-2xl shadow-2xl p-6 space-y-5"
            style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}
          >
            {/* Modal header */}
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-semibold" style={{ color: "var(--text)" }}>
                  Enroll People
                </h2>
                <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
                  Upload images or use your camera — one face photo per person.
                </p>
              </div>
              <button
                onClick={closeModal}
                disabled={enrolling}
                style={{ color: "var(--muted)" }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Drag-and-drop zone */}
            <div
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onClick={() => !enrolling && fileInputRef.current?.click()}
              className="rounded-xl py-8 flex flex-col items-center gap-2 cursor-pointer transition-all"
              style={{
                border: `2px dashed ${dragOver ? "var(--accent)" : "var(--border)"}`,
                background: dragOver ? "rgba(88,166,255,.07)" : "transparent",
                color: "var(--muted)",
              }}
            >
              <Upload size={22} style={{ color: dragOver ? "var(--accent)" : undefined }} />
              <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
                Drop images here or click to browse
              </p>
              <p className="text-xs">Select multiple files — one face photo per person</p>
            </div>

            {/* Hidden file inputs */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => addFiles(Array.from(e.target.files ?? []))}
            />
            <input
              ref={cameraInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) addFiles([file]);
                // Reset so the same file can be captured again
                e.target.value = "";
              }}
            />

            {/* Camera capture button */}
            <button
              onClick={() => cameraInputRef.current?.click()}
              disabled={enrolling}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-opacity hover:opacity-80 disabled:opacity-40"
              style={{
                background: "rgba(88,166,255,.08)",
                color: "var(--accent)",
                border: "1px solid rgba(88,166,255,.25)",
              }}
            >
              <Camera size={15} />
              Capture from Camera
            </button>

            {/* Staged files grid */}
            {hasStaged && (
              <div className="space-y-3">
                <p className="text-xs font-medium" style={{ color: "var(--muted)" }}>
                  {staged.length} image{staged.length > 1 ? "s" : ""} staged
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-96 overflow-y-auto pr-1">
                  {staged.map((sf) => (
                    <StagedCard
                      key={sf.uid}
                      sf={sf}
                      disabled={enrolling}
                      onRemove={() => removeStaged(sf.uid)}
                      onChangeName={(v) => updateStaged(sf.uid, { name: v })}
                      onChangeNotes={(v) => updateStaged(sf.uid, { notes: v })}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-1">
              <button
                onClick={closeModal}
                disabled={enrolling}
                className="flex-1 py-2 rounded-lg text-sm font-medium hover:opacity-80 disabled:opacity-40"
                style={{
                  background: "var(--bg3)",
                  color: "var(--muted)",
                  border: "1px solid var(--border)",
                }}
              >
                {hasStaged && staged.every((f) => f.status === "ok") ? "Done" : "Cancel"}
              </button>
              <button
                onClick={enrollAll}
                disabled={!hasStaged || pendingCount === 0 || enrolling}
                className="flex-1 py-2 rounded-lg text-sm font-semibold transition-opacity hover:opacity-80 disabled:opacity-40 flex items-center justify-center gap-2"
                style={{ background: "var(--accent)", color: "#000" }}
              >
                {enrolling ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Enrolling…
                  </>
                ) : (
                  `Enroll${pendingCount > 0 ? ` ${pendingCount}` : ""} Person${pendingCount !== 1 ? "s" : ""}`
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Staged file card ──────────────────────────────────────────────────────────

function StagedCard({
  sf,
  disabled,
  onRemove,
  onChangeName,
  onChangeNotes,
}: {
  sf: StagedFile;
  disabled: boolean;
  onRemove: () => void;
  onChangeName: (v: string) => void;
  onChangeNotes: (v: string) => void;
}) {
  const isOk = sf.status === "ok";
  const isErr = sf.status === "error";
  const isEnrolling = sf.status === "enrolling";

  return (
    <div
      className="rounded-xl p-3 space-y-2 relative"
      style={{
        background: "var(--bg3)",
        border: `1px solid ${isOk ? "rgba(63,185,80,.4)" : isErr ? "rgba(248,81,73,.4)" : "var(--border)"}`,
        opacity: isOk ? 0.8 : 1,
      }}
    >
      {/* Status overlay for enrolling */}
      {isEnrolling && (
        <div
          className="absolute inset-0 rounded-xl flex items-center justify-center z-10"
          style={{ background: "rgba(0,0,0,.45)" }}
        >
          <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent)" }} />
        </div>
      )}

      {/* Thumbnail + status icon */}
      <div className="relative">
        <img
          src={sf.previewUrl}
          alt={sf.name}
          className="w-full h-32 object-cover rounded-lg"
          style={{ border: "1px solid var(--border)" }}
        />
        {/* Status badge */}
        {isOk && (
          <div className="absolute top-1.5 right-1.5">
            <CheckCircle size={18} style={{ color: "#3fb950" }} />
          </div>
        )}
        {isErr && (
          <div className="absolute top-1.5 right-1.5">
            <AlertCircle size={18} style={{ color: "#f85149" }} />
          </div>
        )}
        {/* Remove button (only when not submitted successfully) */}
        {!isOk && !isEnrolling && (
          <button
            onClick={onRemove}
            disabled={disabled}
            className="absolute top-1.5 left-1.5 w-5 h-5 rounded-full flex items-center justify-center disabled:opacity-40"
            style={{ background: "rgba(0,0,0,.7)", color: "#fff" }}
          >
            <X size={11} />
          </button>
        )}
      </div>

      {/* Name field */}
      <input
        type="text"
        value={sf.name}
        onChange={(e) => onChangeName(e.target.value)}
        disabled={disabled || isOk}
        placeholder="Person's name"
        className="w-full px-2.5 py-1.5 rounded-lg text-xs outline-none focus:ring-1 disabled:opacity-60"
        style={{
          background: "var(--bg2)",
          border: "1px solid var(--border)",
          color: "var(--text)",
        }}
      />

      {/* Notes field */}
      <input
        type="text"
        value={sf.notes}
        onChange={(e) => onChangeNotes(e.target.value)}
        disabled={disabled || isOk}
        placeholder="Notes (optional)"
        className="w-full px-2.5 py-1.5 rounded-lg text-xs outline-none focus:ring-1 disabled:opacity-60"
        style={{
          background: "var(--bg2)",
          border: "1px solid var(--border)",
          color: "var(--muted)",
        }}
      />

      {/* Error message */}
      {isErr && sf.error && (
        <p className="text-xs" style={{ color: "#f85149" }}>
          {sf.error}
        </p>
      )}
    </div>
  );
}
