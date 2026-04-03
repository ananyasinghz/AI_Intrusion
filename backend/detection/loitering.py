"""
Loitering detector.

Tracks object centroids across frames. When any tracked object remains
within a fixed radius of its initial position for longer than the zone's
configured threshold, a loitering event is raised.

Uses a simple Euclidean-distance tracker — no external tracking library needed.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

import numpy as np

from backend.detection.yolo_detector import Detection


@dataclass
class Track:
    track_id: str
    first_seen: float          # time.monotonic()
    last_seen: float
    origin_centroid: tuple[float, float]
    current_centroid: tuple[float, float]
    loitering_alerted: bool = False

    def age_seconds(self) -> float:
        return self.last_seen - self.first_seen

    def displacement(self) -> float:
        dx = self.current_centroid[0] - self.origin_centroid[0]
        dy = self.current_centroid[1] - self.origin_centroid[1]
        return (dx ** 2 + dy ** 2) ** 0.5


class LoiteringDetector:
    def __init__(
        self,
        threshold_seconds: int = 30,
        max_displacement_px: int = 80,
        max_track_age_seconds: int = 120,
    ) -> None:
        self._threshold = threshold_seconds
        self._max_displacement = max_displacement_px
        self._max_age = max_track_age_seconds
        self._tracks: dict[str, Track] = {}

    def update(
        self,
        detections: list[Detection],
    ) -> list[dict]:
        """
        Feed current frame's detections. Returns a list of loitering event
        dicts for any tracks that crossed the time threshold this frame.

        Each event dict: {track_id, label, duration_seconds, centroid}
        """
        now = time.monotonic()
        current_centroids = [_centroid(d.bbox) for d in detections]

        # Match existing tracks to current detections by nearest centroid
        matched_ids: set[str] = set()
        for track_id, track in list(self._tracks.items()):
            best_dist = float("inf")
            best_idx = -1
            for idx, c in enumerate(current_centroids):
                d = _dist(c, track.current_centroid)
                if d < best_dist:
                    best_dist = d
                    best_idx = idx

            if best_dist < 120:  # px — generous match radius
                track.current_centroid = current_centroids[best_idx]
                track.last_seen = now
                matched_ids.add(track_id)
            else:
                # Object left frame — remove stale track after max_age
                if (now - track.last_seen) > self._max_age:
                    del self._tracks[track_id]

        # Register new tracks for unmatched detections
        matched_centroid_indices = set()
        for track in self._tracks.values():
            for idx, c in enumerate(current_centroids):
                if _dist(c, track.current_centroid) < 120:
                    matched_centroid_indices.add(idx)

        for idx, (det, c) in enumerate(zip(detections, current_centroids)):
            if idx not in matched_centroid_indices:
                new_id = str(uuid.uuid4())[:8]
                self._tracks[new_id] = Track(
                    track_id=new_id,
                    first_seen=now,
                    last_seen=now,
                    origin_centroid=c,
                    current_centroid=c,
                )

        # Check for loitering
        events: list[dict] = []
        for track_id, track in self._tracks.items():
            if track.loitering_alerted:
                continue
            stationary = track.displacement() < self._max_displacement
            old_enough = track.age_seconds() >= self._threshold
            if stationary and old_enough:
                track.loitering_alerted = True
                # Find matching detection label
                label = "unknown"
                for det, c in zip(detections, current_centroids):
                    if _dist(c, track.current_centroid) < 120:
                        label = det.label
                        break
                events.append({
                    "track_id": track_id,
                    "label": label,
                    "duration_seconds": track.age_seconds(),
                    "centroid": track.current_centroid,
                })

        return events

    def clear(self) -> None:
        self._tracks.clear()


def _centroid(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
