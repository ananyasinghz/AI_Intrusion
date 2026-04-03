"""
OpenCV MOG2 background subtraction for motion detection.
Works on both live webcam frames and video file frames.
"""

import cv2
import numpy as np

from backend.config import MOTION_MIN_AREA


class MotionDetector:
    def __init__(self, min_area: int = MOTION_MIN_AREA) -> None:
        self.min_area = min_area
        # MOG2 is robust to gradual lighting changes (shadows, etc.)
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=50,
            detectShadows=True,
        )
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def detect(self, frame: np.ndarray) -> tuple[bool, list[tuple[int, int, int, int]]]:
        """
        Analyse a single frame for motion.

        Returns:
            motion_detected: True if at least one contour exceeds min_area.
            bounding_boxes: List of (x, y, w, h) for each motion region.
        """
        fg_mask = self._subtractor.apply(frame)

        # Remove shadows (value 127 in MOG2 mask) — keep only full foreground (255)
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        # Morphological cleanup: close small holes, remove noise
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, self._kernel, iterations=2)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self._kernel, iterations=1)

        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        bboxes: list[tuple[int, int, int, int]] = []
        for contour in contours:
            if cv2.contourArea(contour) >= self.min_area:
                x, y, w, h = cv2.boundingRect(contour)
                bboxes.append((x, y, w, h))

        return len(bboxes) > 0, bboxes

    def draw_boxes(
        self,
        frame: np.ndarray,
        bboxes: list[tuple[int, int, int, int]],
        color: tuple[int, int, int] = (0, 255, 0),
        label: str = "Motion",
    ) -> np.ndarray:
        """Draw bounding boxes onto frame (non-destructive copy)."""
        output = frame.copy()
        for x, y, w, h in bboxes:
            cv2.rectangle(output, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                output,
                label,
                (x, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
            )
        return output
