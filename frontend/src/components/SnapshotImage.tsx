import { useEffect, useState } from "react";
import { api } from "../api/client";

type Role = "admin" | "viewer";

interface SnapshotImageProps {
  snapshotPath: string | null;
  snapshotPathFull?: string | null;
  role: Role;
  className?: string;
  alt?: string;
}

/**
 * Renders a blurred snapshot from /snapshots for viewers, or the unblurred
 * private file via /api/snapshots/full/... for admins when available.
 */
export function SnapshotImage({
  snapshotPath,
  snapshotPathFull,
  role,
  className = "",
  alt = "snapshot",
}: SnapshotImageProps) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let blobUrl: string | null = null;

    const useFull = role === "admin" && snapshotPathFull;
    const fname = (useFull ? snapshotPathFull : snapshotPath) ?? null;
    if (!fname) {
      setSrc(null);
      return () => {};
    }

    if (useFull) {
      (async () => {
        try {
          const res = await api.get(`/api/snapshots/full/${encodeURIComponent(fname)}`, {
            responseType: "blob",
          });
          if (cancelled) return;
          blobUrl = URL.createObjectURL(res.data);
          setSrc(blobUrl);
        } catch {
          if (!cancelled) {
            const base = snapshotPath?.split(/[/\\]/).pop();
            setSrc(base ? `/snapshots/${base}` : null);
          }
        }
      })();
    } else {
      const base = fname.split(/[/\\]/).pop();
      setSrc(`/snapshots/${base}`);
    }

    return () => {
      cancelled = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [snapshotPath, snapshotPathFull, role]);

  if (!src) return null;
  return <img src={src} alt={alt} className={className} />;
}
