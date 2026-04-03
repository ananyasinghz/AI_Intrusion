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
    ) -> tuple[bool, str | None, int]:
        """
        Given a frame and a person bounding box, compute the appearance
        descriptor and search the gallery.

        Returns:
            (is_repeat, descriptor_id, visit_count)
            - is_repeat: True if this looks like a previously seen person
            - descriptor_id: the gallery entry ID (new or matched)
            - visit_count: how many times this descriptor has been seen
        """
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
