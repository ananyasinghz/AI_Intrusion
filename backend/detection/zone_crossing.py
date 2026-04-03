"""
Virtual tripwire / zone-crossing detector.

A tripwire is a line segment [[x1,y1],[x2,y2]] defined per zone.
When a tracked object centroid crosses that line between consecutive frames,
a zone_crossing event fires with a direction ("entry" or "exit").

Direction is determined by the sign of the cross-product of the line
direction vector and the centroid displacement vector:
  - positive cross product → "entry"
  - negative cross product → "exit"
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.detection.yolo_detector import Detection


@dataclass
class TripwireState:
    """Stores each tracked centroid's last known side of the tripwire."""
    # track_id → last side (+1 or -1)
    sides: dict[str, int] = field(default_factory=dict)


class ZoneCrossingDetector:
    def __init__(self, tripwire: list[list[int]] | None = None) -> None:
        """
        tripwire: [[x1,y1],[x2,y2]] or None (detector disabled).
        Can be updated dynamically via set_tripwire().
        """
        self._tripwire = tripwire
        self._state = TripwireState()

    def set_tripwire(self, tripwire: list[list[int]] | None) -> None:
        self._tripwire = tripwire
        self._state = TripwireState()  # Reset state when tripwire changes

    def update(
        self,
        detections: list[Detection],
    ) -> list[dict]:
        """
        Returns a list of crossing events this frame.
        Each event: {track_id, label, direction ("entry"/"exit"), centroid}
        """
        if not self._tripwire or len(self._tripwire) < 2:
            return []

        (x1, y1), (x2, y2) = self._tripwire[0], self._tripwire[1]
        # Line direction vector
        lx, ly = x2 - x1, y2 - y1

        events: list[dict] = []
        for idx, det in enumerate(detections):
            cx, cy = _centroid(det.bbox)
            track_id = f"t{idx}"  # Simple index-based ID for crossing check

            # Vector from line start to centroid
            vx, vy = cx - x1, cy - y1
            # Cross product (sign gives which side of the line the point is on)
            cross = lx * vy - ly * vx
            side = 1 if cross >= 0 else -1

            last_side = self._state.sides.get(track_id)
            self._state.sides[track_id] = side

            if last_side is not None and last_side != side:
                direction = "entry" if side == 1 else "exit"
                events.append({
                    "track_id": track_id,
                    "label": det.label,
                    "direction": direction,
                    "centroid": (cx, cy),
                    "detection_type": det.detection_type,
                })

        return events

    def clear(self) -> None:
        self._state = TripwireState()


def _centroid(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)
