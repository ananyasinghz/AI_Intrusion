"""
Unit tests for the new detection modules:
  - LoiteringDetector
  - ZoneCrossingDetector
  - OpticalFlowAnomalyDetector
"""

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.detection.loitering import LoiteringDetector
from backend.detection.optical_flow import OpticalFlowAnomalyDetector
from backend.detection.zone_crossing import ZoneCrossingDetector
from backend.detection.yolo_detector import Detection


def make_detection(x1=100, y1=100, x2=200, y2=300, label="person", dtype="person", conf=0.8):
    d = Detection.__new__(Detection)
    d.bbox = (x1, y1, x2, y2)
    d.label = label
    d.detection_type = dtype
    d.confidence = conf
    return d


# ── LoiteringDetector ─────────────────────────────────────────────────────
class TestLoiteringDetector:
    def test_no_events_below_threshold(self):
        ld = LoiteringDetector(threshold_seconds=30)
        dets = [make_detection()]
        events = ld.update(dets)
        assert events == []

    def test_fires_after_threshold(self):
        with patch("backend.detection.loitering.time") as mock_time:
            t0 = 1000.0
            mock_time.monotonic.return_value = t0

            ld = LoiteringDetector(threshold_seconds=30)
            dets = [make_detection(100, 100, 200, 300)]
            ld.update(dets)

            # Jump forward 35 seconds — should now exceed threshold
            mock_time.monotonic.return_value = t0 + 35.0
            events = ld.update(dets)

        assert len(events) == 1
        assert events[0]["label"] == "person"
        assert events[0]["duration_seconds"] >= 35

    def test_no_event_for_moving_object(self):
        ld = LoiteringDetector(threshold_seconds=0, max_displacement_px=10)
        ld.update([make_detection(100, 100, 200, 300)])
        # Move far away — displacement > threshold
        for t in ld._tracks.values():
            t.first_seen -= 5
            t.current_centroid = (500, 500)  # Moved far
        events = ld.update([make_detection(490, 490, 510, 510)])
        assert events == []


# ── ZoneCrossingDetector ──────────────────────────────────────────────────
class TestZoneCrossingDetector:
    def test_no_events_without_tripwire(self):
        zc = ZoneCrossingDetector(tripwire=None)
        dets = [make_detection(150, 200, 250, 300)]
        assert zc.update(dets) == []

    def test_detects_crossing(self):
        # Horizontal tripwire at y=250 from x=0 to x=640
        zc = ZoneCrossingDetector(tripwire=[[0, 250], [640, 250]])

        # First frame: centroid above the line (y < 250)
        above = make_detection(100, 100, 300, 200)  # centroid y ≈ 150
        zc.update([above])

        # Second frame: centroid below the line (y > 250)
        below = make_detection(100, 300, 300, 450)  # centroid y ≈ 375
        events = zc.update([below])

        # Should detect a crossing
        assert len(events) == 1
        assert events[0]["direction"] in ("entry", "exit")

    def test_no_event_when_staying_same_side(self):
        zc = ZoneCrossingDetector(tripwire=[[0, 250], [640, 250]])
        above1 = make_detection(100, 100, 300, 200)
        above2 = make_detection(120, 110, 320, 210)
        zc.update([above1])
        events = zc.update([above2])
        assert events == []


# ── OpticalFlowAnomalyDetector ────────────────────────────────────────────
class TestOpticalFlowAnomalyDetector:
    def test_returns_empty_on_first_frame(self):
        of = OpticalFlowAnomalyDetector()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = of.update(frame, [(50, 50, 200, 200)])
        assert result == []

    def test_no_anomaly_for_static_scene(self):
        of = OpticalFlowAnomalyDetector()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Two identical frames → no flow
        of.update(frame, [(0, 0, 640, 480)])
        result = of.update(frame.copy(), [(0, 0, 640, 480)])
        assert result == []

    def test_reset_clears_state(self):
        of = OpticalFlowAnomalyDetector()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        of.update(frame, [(0, 0, 640, 480)])
        of.reset()
        assert of._prev_gray is None
