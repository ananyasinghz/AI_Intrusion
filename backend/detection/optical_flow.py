"""
Optical flow anomaly detector.

Uses Lucas-Kanade sparse optical flow on Shi-Tomasi corner features detected
within motion bounding boxes. Analyses the resulting flow vectors to detect:

  - "running": high average flow magnitude (fast movement)
  - "erratic_movement": high angular variance (chaotic/unpredictable motion)

Both conditions simultaneously raise "abnormal_activity".
"""

from __future__ import annotations

import math

import cv2
import numpy as np


# Lucas-Kanade parameters
_LK_PARAMS = dict(
    winSize=(15, 15),
    maxLevel=2,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
)

_FEATURE_PARAMS = dict(
    maxCorners=30,
    qualityLevel=0.3,
    minDistance=7,
    blockSize=7,
)


class OpticalFlowAnomalyDetector:
    def __init__(
        self,
        magnitude_threshold: float = 28.0,
        angular_variance_threshold: float = 1.6,
    ) -> None:
        """
        magnitude_threshold: mean flow vector length (px/frame) above which
            "running" / fast movement is flagged.
            Normal walking  ≈  5–12 px/frame at typical distances.
            Fast walking    ≈ 12–20 px/frame.
            Jogging/running ≥ 25–30 px/frame.
            28.0 is a conservative threshold that avoids triggering on brisk walking.
        angular_variance_threshold: circular variance of flow angles above which
            "erratic_movement" is flagged (range 0–1).
            0.0 = all vectors pointing the same direction (normal walking).
            1.6 requires highly chaotic motion; raised from 1.2 to reduce false positives
            from people simply turning around.
        Note: the pipeline additionally requires OPTICAL_FLOW_MIN_FRAMES (5) consecutive
        frames of anomaly before logging — this prevents single-frame spikes.
        """
        self._mag_threshold = magnitude_threshold
        self._ang_threshold = angular_variance_threshold
        self._prev_gray: np.ndarray | None = None
        self._prev_points: np.ndarray | None = None

    def update(
        self,
        frame: np.ndarray,
        motion_bboxes: list[tuple[int, int, int, int]],
    ) -> list[str]:
        """
        Analyse the current frame for anomalous motion patterns.

        Returns a list of anomaly labels:
            []                        → no anomaly
            ["running"]               → high speed
            ["erratic_movement"]      → chaotic directions
            ["running","erratic_movement"] → both
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if self._prev_gray is None or not motion_bboxes:
            self._prev_gray = gray
            self._prev_points = None
            return []

        # Sample feature points inside motion regions
        mask = np.zeros_like(gray)
        for x, y, w, h in motion_bboxes:
            mask[y: y + h, x: x + w] = 255

        points = cv2.goodFeaturesToTrack(gray, mask=mask, **_FEATURE_PARAMS)
        if points is None or len(points) < 4:
            self._prev_gray = gray
            self._prev_points = None
            return []

        if self._prev_points is None:
            self._prev_gray = gray
            self._prev_points = points
            return []

        # Track points from previous to current frame
        next_pts, status, _ = cv2.calcOpticalFlowPyrLK(
            self._prev_gray, gray, self._prev_points, None, **_LK_PARAMS
        )
        if next_pts is None:
            self._prev_gray = gray
            self._prev_points = points
            return []

        good_prev = self._prev_points[status == 1]
        good_next = next_pts[status == 1]

        if len(good_prev) < 4:
            self._prev_gray = gray
            self._prev_points = points
            return []

        flow = good_next - good_prev
        magnitudes = np.linalg.norm(flow, axis=1)
        angles = np.arctan2(flow[:, 1], flow[:, 0])

        self._prev_gray = gray
        self._prev_points = points

        anomalies: list[str] = []

        mean_mag = float(np.mean(magnitudes))
        if mean_mag > self._mag_threshold:
            anomalies.append("running")

        ang_variance = _circular_variance(angles)
        if ang_variance > self._ang_threshold:
            anomalies.append("erratic_movement")

        return anomalies

    def reset(self) -> None:
        self._prev_gray = None
        self._prev_points = None


def _circular_variance(angles: np.ndarray) -> float:
    """
    Circular variance in [0, 1]:
      0 = all vectors pointing the same direction (uniform movement)
      1 = vectors pointing in all directions (chaotic)
    """
    sin_mean = float(np.mean(np.sin(angles)))
    cos_mean = float(np.mean(np.cos(angles)))
    r = math.sqrt(sin_mean ** 2 + cos_mean ** 2)
    return 1.0 - r
