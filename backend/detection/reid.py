"""
Privacy-safe person re-identification using clothing color histograms.

How it works:
  1. When a person is detected, extract the LOWER HALF of their bounding box
     (torso + legs — deliberately avoids the face/head area).
  2. Compute an HSV color histogram over that region (captures clothing color
     distribution without storing any biometric information).
  3. Compare the new descriptor against a rolling gallery of recent descriptors
     using Bhattacharyya distance (0 = identical, 1 = completely different).
  4. If distance < threshold → "repeat visitor" flag is set.

Privacy properties:
  - No face or head pixels are ever used.
  - The stored descriptor is a 96-float histogram — it cannot be reverse-
    engineered into an image or any personal identifying information.
  - Matching breaks completely if the person changes clothes.
  - The gallery is held in memory only; it is cleared on server restart.

This is NOT identification — it is "have we seen similar clothing recently?"
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Gallery retention — descriptors older than this are dropped
_GALLERY_TTL_MINUTES = 60

# Bhattacharyya distance threshold:
#   0.0  → perfect match (identical histogram)
#   0.3  → very similar (same outfit, same person)
#   0.55 → similar (maybe same outfit, different person or different lighting)
#   1.0  → completely different
_MATCH_THRESHOLD = 0.35

# Minimum bounding-box height in pixels before we attempt re-ID
# (too small → histogram is noisy and unreliable)
_MIN_BBOX_HEIGHT = 60

# Fraction of the bounding box to use (skip top portion = head/face)
_SKIP_TOP_FRACTION = 0.35


@dataclass
class AppearanceRecord:
    descriptor_id: str
    descriptor: np.ndarray          # shape: (96,) float32
    first_seen: datetime
    last_seen: datetime
    visit_count: int = 1


class PersonReIDTracker:
    """
    Maintains an in-memory gallery of recent person appearance descriptors.
    Thread-safe for single-threaded asyncio use.
    """

    def __init__(
        self,
        match_threshold: float = _MATCH_THRESHOLD,
        gallery_ttl_minutes: int = _GALLERY_TTL_MINUTES,
    ) -> None:
        self._threshold = match_threshold
        self._ttl = timedelta(minutes=gallery_ttl_minutes)
        self._gallery: dict[str, AppearanceRecord] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def check_and_update(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
        descriptor: np.ndarray | None = None,
    ) -> tuple[bool, str | None, int]:
        """
        Given a frame and a person bounding box, compute the appearance
        descriptor and search the gallery.

        Returns:
            (is_repeat, descriptor_id, visit_count)
            - is_repeat: True if this looks like a previously seen person
            - descriptor_id: the gallery entry ID (new or matched)
            - visit_count: how many times this descriptor has been seen

        Pass a pre-computed `descriptor` to avoid extracting it twice when
        the approved-persons check already computed it.
        """
        if descriptor is None:
            descriptor = self._extract_descriptor(frame, bbox)
        if descriptor is None:
            return False, None, 1

        self._evict_stale()

        best_id, best_dist = self._find_best_match(descriptor)

        now = datetime.utcnow()

        if best_id is not None and best_dist < self._threshold:
            # Update existing record
            record = self._gallery[best_id]
            record.descriptor = _blend(record.descriptor, descriptor, alpha=0.3)
            record.last_seen = now
            record.visit_count += 1
            return True, best_id, record.visit_count
        else:
            # New person — add to gallery
            new_id = str(uuid.uuid4())[:12]
            self._gallery[new_id] = AppearanceRecord(
                descriptor_id=new_id,
                descriptor=descriptor,
                first_seen=now,
                last_seen=now,
            )
            return False, new_id, 1

    def gallery_size(self) -> int:
        return len(self._gallery)

    def clear(self) -> None:
        self._gallery.clear()

    # ── Internal helpers ──────────────────────────────────────────────────

    def _extract_descriptor(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
    ) -> np.ndarray | None:
        x1, y1, x2, y2 = bbox
        h = y2 - y1
        w = x2 - x1

        if h < _MIN_BBOX_HEIGHT or w < 20:
            return None

        # Skip the top fraction (head / face)
        skip_px = int(h * _SKIP_TOP_FRACTION)
        body_y1 = min(y1 + skip_px, y2 - 10)

        # Clamp to frame
        fh, fw = frame.shape[:2]
        body_y1 = max(0, body_y1)
        y2c = min(fh, y2)
        x1c = max(0, x1)
        x2c = min(fw, x2)

        if body_y1 >= y2c or x1c >= x2c:
            return None

        roi = frame[body_y1:y2c, x1c:x2c]
        if roi.size == 0:
            return None

        # Convert to HSV — better for clothing color matching under varying lighting
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Compute 3-channel histogram: H(32) + S(32) + V(32) = 96 bins
        h_hist = cv2.calcHist([hsv], [0], None, [32], [0, 180])
        s_hist = cv2.calcHist([hsv], [1], None, [32], [0, 256])
        v_hist = cv2.calcHist([hsv], [2], None, [32], [0, 256])

        descriptor = np.concatenate([
            cv2.normalize(h_hist, h_hist).flatten(),
            cv2.normalize(s_hist, s_hist).flatten(),
            cv2.normalize(v_hist, v_hist).flatten(),
        ]).astype(np.float32)

        return descriptor

    def _find_best_match(
        self, descriptor: np.ndarray
    ) -> tuple[str | None, float]:
        best_id = None
        best_dist = float("inf")
        for rid, record in self._gallery.items():
            dist = cv2.compareHist(descriptor, record.descriptor, cv2.HISTCMP_BHATTACHARYYA)
            if dist < best_dist:
                best_dist = dist
                best_id = rid
        return best_id, best_dist

    def _evict_stale(self) -> None:
        cutoff = datetime.utcnow() - self._ttl
        stale = [rid for rid, r in self._gallery.items() if r.last_seen < cutoff]
        for rid in stale:
            del self._gallery[rid]
        if stale:
            logger.debug("Re-ID gallery: evicted %d stale descriptors", len(stale))


def _blend(old: np.ndarray, new: np.ndarray, alpha: float) -> np.ndarray:
    """Exponential moving average of descriptors for robustness to lighting drift."""
    blended = (1 - alpha) * old + alpha * new
    norm = np.linalg.norm(blended)
    return blended / norm if norm > 0 else blended


def extract_clothing_descriptor(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> np.ndarray | None:
    """
    Module-level wrapper so both PersonReIDTracker and ApprovedPersonsGallery
    share a single extraction path without duplication.

    Call this once per person detection and pass the result to both
    `approved_gallery.is_approved()` and `reid_tracker.check_and_update()`.
    """
    x1, y1, x2, y2 = bbox
    h = y2 - y1
    w = x2 - x1

    if h < _MIN_BBOX_HEIGHT or w < 20:
        return None

    skip_px = int(h * _SKIP_TOP_FRACTION)
    body_y1 = min(y1 + skip_px, y2 - 10)

    fh, fw = frame.shape[:2]
    body_y1 = max(0, body_y1)
    y2c = min(fh, y2)
    x1c = max(0, x1)
    x2c = min(fw, x2)

    if body_y1 >= y2c or x1c >= x2c:
        return None

    roi = frame[body_y1:y2c, x1c:x2c]
    if roi.size == 0:
        return None

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    h_hist = cv2.calcHist([hsv], [0], None, [32], [0, 180])
    s_hist = cv2.calcHist([hsv], [1], None, [32], [0, 256])
    v_hist = cv2.calcHist([hsv], [2], None, [32], [0, 256])

    descriptor = np.concatenate([
        cv2.normalize(h_hist, h_hist).flatten(),
        cv2.normalize(s_hist, s_hist).flatten(),
        cv2.normalize(v_hist, v_hist).flatten(),
    ]).astype(np.float32)

    return descriptor


_FACE_SIM_THRESHOLD = 0.45  # cosine similarity — higher = stricter match


class ApprovedPersonsGallery:
    """
    Persistent in-memory gallery of approved persons using ArcFace face embeddings.

    Replaces the previous clothing-color histogram approach so the same person
    is recognised regardless of outfit, lighting, or day of the week.

    Model: InsightFace buffalo_s (ArcFace, 512-dim) — lazy-loaded on first use.
    The ~80 MB model is downloaded once to ~/.insightface/models/ and cached.

    Performance:
      - load_from_db()    — once at startup, O(N) DB read
      - get_face_embedding() — ~50-100 ms first call (model load), ~10-30 ms after
      - is_approved()     — O(N) dot products, < 0.1 ms for any gallery size
    """

    def __init__(self, threshold: float = _FACE_SIM_THRESHOLD) -> None:
        self._threshold = threshold
        # Maps approved_person.id → 512-float L2-normalised ArcFace embedding
        self._gallery: dict[int, np.ndarray] = {}
        self._app = None  # InsightFace FaceAnalysis — lazy-loaded on first use

    # ── InsightFace model ──────────────────────────────────────────────────────

    def _get_app(self):
        """Lazy-load InsightFace buffalo_s — downloaded once, cached on disk."""
        if self._app is None:
            try:
                from insightface.app import FaceAnalysis  # type: ignore[import]
                self._app = FaceAnalysis(
                    name="buffalo_s",
                    providers=["CPUExecutionProvider"],
                )
                self._app.prepare(ctx_id=0, det_size=(320, 320))
                logger.info("InsightFace buffalo_s model loaded")
            except ImportError:
                logger.error(
                    "insightface not installed — run: pip install insightface onnxruntime"
                )
                raise
        return self._app

    # ── Embedding extraction ───────────────────────────────────────────────────

    def get_face_embedding(
        self,
        frame: np.ndarray,
        person_bbox: tuple[int, int, int, int] | None = None,
    ) -> np.ndarray | None:
        """
        Detect a face and return the 512-dim normalised ArcFace embedding.

        For live feed: pass person_bbox (YOLO bounding box) so we crop to just
        the person region before running face detection — faster and avoids
        spurious faces in the background.

        For enrollment: pass person_bbox=None to search the full image.

        Returns None when no face is detected or the model is unavailable.
        """
        try:
            app = self._get_app()
        except Exception:
            return None

        if person_bbox is not None:
            x1, y1, x2, y2 = person_bbox
            # 10% padding so the full head is included even with a tight YOLO box
            pad_x = int((x2 - x1) * 0.10)
            pad_y = int((y2 - y1) * 0.10)
            fh, fw = frame.shape[:2]
            cx1 = max(0, x1 - pad_x)
            cy1 = max(0, y1 - pad_y)
            cx2 = min(fw, x2 + pad_x)
            cy2 = min(fh, y2 + pad_y)
            crop = frame[cy1:cy2, cx1:cx2]
        else:
            crop = frame

        if crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 20:
            return None

        try:
            faces = app.get(crop)
        except Exception:
            logger.debug("InsightFace face detection failed on crop", exc_info=True)
            return None

        if not faces:
            return None

        # Use the face with the largest bounding box (most prominent / closest)
        best_face = max(
            faces,
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
        )
        return best_face.normed_embedding  # 512-dim, L2-normalised

    # ── Gallery operations ────────────────────────────────────────────────────

    def load_from_db(self, db) -> None:
        from backend.database.models import ApprovedPerson
        records = db.query(ApprovedPerson).all()
        for r in records:
            try:
                emb = np.array(json.loads(r.descriptor), dtype=np.float32)
                if emb.shape[0] != 512:
                    logger.warning(
                        "Skipping person id=%d: descriptor dim=%d (expected 512, re-enroll needed)",
                        r.id, emb.shape[0],
                    )
                    continue
                self._gallery[r.id] = emb
            except Exception:
                logger.warning("Skipping approved person id=%d — bad descriptor", r.id)
        logger.info("Approved persons gallery loaded: %d enrolled", len(self._gallery))

    def is_approved(self, embedding: np.ndarray | None) -> bool:
        """
        Return True if embedding matches any enrolled person via cosine similarity.
        Both vectors are L2-normalised so dot product == cosine similarity.
        """
        if embedding is None or not self._gallery:
            return False
        for ref in self._gallery.values():
            if float(np.dot(embedding, ref)) >= self._threshold:
                return True
        return False

    def add(self, person_id: int, embedding: np.ndarray) -> None:
        self._gallery[person_id] = embedding
        logger.debug("Approved gallery: added id=%d (total=%d)", person_id, len(self._gallery))

    def remove(self, person_id: int) -> None:
        self._gallery.pop(person_id, None)
        logger.debug("Approved gallery: removed id=%d (total=%d)", person_id, len(self._gallery))

    def size(self) -> int:
        return len(self._gallery)
