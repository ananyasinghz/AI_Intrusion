"""
Hardware-abstraction layer for video input.

Swap between webcam, video file, and ESP32-CAM MJPEG stream
by changing INPUT_SOURCE in .env — no code changes required.
"""

from __future__ import annotations

import logging
import time
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
        # Minimise the internal frame queue so we always read the newest frame.
        # Default is 4-8 frames; at 30fps that means up to 266ms of stale data
        # before our pipeline even touches it.
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
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

    CameraWebServer firmware (the most common Arduino example) serves:
      - Control page  →  http://<ip>/          (port 80)
      - MJPEG stream  →  http://<ip>:81/stream (port 81)

    The stream must be started on the ESP32 web UI before this source can connect.
    This class retries for up to RETRY_SECS seconds so the pipeline stays alive
    while you open the browser and press "Start Stream".  It also auto-reconnects
    if the stream drops mid-session.
    """

    RETRY_SECS = 60   # wait up to 60 s on startup for the ESP32 stream to appear
    RETRY_INTERVAL = 2  # seconds between connection attempts

    def __init__(self, url: str = ESP32CAM_URL) -> None:
        self._url = url
        self._cap: cv2.VideoCapture | None = None
        self._connect(startup=True)

    def _connect(self, startup: bool = False) -> None:
        """
        Try to open the MJPEG stream, retrying until RETRY_SECS is exhausted.
        On startup=True, waits patiently (user still needs to press Start Stream).
        On reconnect (startup=False), tries once and raises if it fails.
        """
        deadline = time.monotonic() + (self.RETRY_SECS if startup else self.RETRY_INTERVAL)
        attempt = 0
        while True:
            cap = cv2.VideoCapture(self._url)
            if cap.isOpened():
                # Discard any buffered frames so we always read the newest one
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self._cap = cap
                logger.info("ESP32-CAM stream connected: %s", self._url)
                return
            cap.release()
            attempt += 1
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"Cannot connect to ESP32-CAM stream at {self._url} after "
                    f"{self.RETRY_SECS}s.  Make sure the ESP32 is on the same "
                    f"network, then open http://{self._url.split('/')[2].split(':')[0]}/ "
                    f"in a browser and press 'Start Stream'."
                )
            logger.warning(
                "ESP32-CAM: attempt %d — stream not available yet at %s  "
                "(%.0fs remaining, retrying in %ds)",
                attempt, self._url, remaining, self.RETRY_INTERVAL,
            )
            time.sleep(self.RETRY_INTERVAL)

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._cap is None:
            return False, None
        ret, frame = self._cap.read()
        if not ret or frame is None:
            # Stream dropped — try once to reconnect so the pipeline survives a
            # brief ESP32 reboot or Wi-Fi hiccup.
            logger.warning("ESP32-CAM: stream lost — attempting reconnect …")
            self._cap.release()
            self._cap = None
            try:
                self._connect(startup=False)
                ret, frame = self._cap.read()  # type: ignore[union-attr]
            except RuntimeError:
                logger.error("ESP32-CAM: reconnect failed — stopping capture")
                return False, None
        if not ret or frame is None:
            return False, None
        return True, frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


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
