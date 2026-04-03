"""
YOLOv8 small (yolov8s) inference wrapper.

Changes from the nano version:
  - Uses yolov8s.pt for meaningfully better accuracy (~44.9 vs 36.3 mAP on COCO).
  - Applies class-specific confidence thresholds:
      person: CONFIDENCE_THRESHOLD (default 0.45)
      animal: ANIMAL_CONFIDENCE_THRESHOLD (default 0.65)
    Animals require higher confidence to reduce false positives (person-as-cat errors).
  - Privacy blur over person bounding boxes is unchanged.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from backend.config import (
    ANIMAL_CLASS_IDS,
    ANIMAL_CONFIDENCE_THRESHOLD,
    CONFIDENCE_THRESHOLD,
    PERSON_CLASS_ID,
    YOLO_MODEL_PATH,
)

logger = logging.getLogger(__name__)


class Detection:
    __slots__ = ("label", "detection_type", "confidence", "bbox")

    def __init__(
        self,
        label: str,
        detection_type: str,
        confidence: float,
        bbox: tuple[int, int, int, int],
    ) -> None:
        self.label = label
        self.detection_type = detection_type  # "person", "animal", "unknown"
        self.confidence = confidence
        self.bbox = bbox  # (x1, y1, x2, y2)


class YOLODetector:
    def __init__(self, model_path: str = YOLO_MODEL_PATH) -> None:
        try:
            from ultralytics import YOLO  # type: ignore

            self._model = YOLO(model_path)
            self._available = True
            logger.info("YOLOv8 model loaded from %s", model_path)
        except Exception as exc:
            logger.warning("YOLO unavailable (%s) — falling back to motion-only mode.", exc)
            self._model = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def detect(
        self,
        frame: np.ndarray,
        conf: float = CONFIDENCE_THRESHOLD,
    ) -> list[Detection]:
        """
        Run inference and return Detection objects.

        Uses a low base conf for the initial pass so ultralytics returns all
        candidates, then we apply class-specific thresholds ourselves.
        This avoids the model silently dropping animal detections before we can
        apply the stricter animal threshold.
        """
        if not self._available or self._model is None:
            return []

        # Run at the lower person threshold so we see everything, filter below
        results = self._model(frame, conf=min(conf, CONFIDENCE_THRESHOLD), verbose=False)[0]
        detections: list[Detection] = []

        for box in results.boxes:
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
            label = self._model.names[cls_id]

            if cls_id == PERSON_CLASS_ID:
                if confidence < CONFIDENCE_THRESHOLD:
                    continue
                detection_type = "person"
            elif cls_id in ANIMAL_CLASS_IDS:
                # Stricter threshold for animals — avoids person-as-cat false positives
                if confidence < ANIMAL_CONFIDENCE_THRESHOLD:
                    continue
                detection_type = "animal"
            else:
                continue

            detections.append(
                Detection(
                    label=label,
                    detection_type=detection_type,
                    confidence=confidence,
                    bbox=(x1, y1, x2, y2),
                )
            )

        return detections

    def blur_persons(self, frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
        """
        Apply Gaussian blur over all person bounding boxes.
        Ensures no facial or personal identification data is retained in snapshots.
        """
        output = frame.copy()
        h, w = output.shape[:2]

        for det in detections:
            if det.detection_type != "person":
                continue
            x1, y1, x2, y2 = det.bbox
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            roi = output[y1:y2, x1:x2]
            ksize = max(51, ((x2 - x1) // 5) | 1)
            blurred = cv2.GaussianBlur(roi, (ksize, ksize), 0)
            output[y1:y2, x1:x2] = blurred

        return output

    def annotate(self, frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
        """Draw labelled bounding boxes; persons are shown with blurred interiors."""
        output = self.blur_persons(frame, detections)
        color_map = {"person": (0, 165, 255), "animal": (0, 0, 220)}

        for det in detections:
            color = color_map.get(det.detection_type, (128, 128, 128))
            x1, y1, x2, y2 = det.bbox
            cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
            text = f"{det.label} {det.confidence:.0%}"
            cv2.putText(
                output,
                text,
                (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
            )

        return output
