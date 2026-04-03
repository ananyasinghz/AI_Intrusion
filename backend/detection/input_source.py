"""
Hardware-abstraction layer for video input.

Swap between webcam, video file, and ESP32-CAM MJPEG stream
by changing INPUT_SOURCE in .env — no code changes required.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import cv2
import numpy as np

from backend.config import ESP32CAM_URL, INPUT_SOURCE, VIDEO_FILE_PATH, WEBCAM_INDEX

logger = logging.getLogger(__name__)


class InputSource(ABC):
    """Abstract base for all video input sources."""

    @abstractmethod
    def read(self) -> tuple[bool, np.ndarray | None]:
        """Return (success, frame). Returns (False, None) when exhausted."""

    @abstractmethod
    def release(self) -> None:
        """Release underlying resources."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.release()


class WebcamSource(InputSource):
    def __init__(self, index: int = WEBCAM_INDEX) -> None:
        self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open webcam at index {index}")
        logger.info("Webcam source opened (index=%d)", index)

    def read(self) -> tuple[bool, np.ndarray | None]:
        ret, frame = self._cap.read()
        if not ret:
            return False, None
        return True, frame

    def release(self) -> None:
        self._cap.release()


class VideoFileSource(InputSource):
    def __init__(self, path: str = VIDEO_FILE_PATH) -> None:
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open video file: {path}")
        self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 25
        logger.info("Video file source opened: %s (%.1f fps)", path, self._fps)

    @property
    def fps(self) -> float:
        return self._fps

    def read(self) -> tuple[bool, np.ndarray | None]:
        ret, frame = self._cap.read()
        if not ret:
            return False, None
        return True, frame

    def release(self) -> None:
        self._cap.release()


class ESP32CamSource(InputSource):
    """
    Reads from an ESP32-CAM MJPEG stream over HTTP.
    The ESP32-CAM firmware must serve a MJPEG stream (standard in AI-Thinker firmware).
    This source is used in Phase H2 — kept as a stub during software phases.
    """

    def __init__(self, url: str = ESP32CAM_URL) -> None:
        self._cap = cv2.VideoCapture(url)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot connect to ESP32-CAM stream at {url}")
        logger.info("ESP32-CAM source connected: %s", url)

    def read(self) -> tuple[bool, np.ndarray | None]:
        ret, frame = self._cap.read()
        if not ret:
            return False, None
        return True, frame

    def release(self) -> None:
        self._cap.release()


def get_input_source(source_type: str | None = None) -> InputSource:
    """Factory function — reads INPUT_SOURCE from config if not provided."""
    src = source_type or INPUT_SOURCE
    if src == "webcam":
        return WebcamSource()
    if src == "video":
        return VideoFileSource()
    if src == "esp32cam":
        return ESP32CamSource()
    raise ValueError(f"Unknown INPUT_SOURCE: '{src}'. Choose webcam, video, or esp32cam.")
