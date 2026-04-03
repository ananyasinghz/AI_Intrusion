"""
YOLOv8 small (yolov8s) inference wrapper.

- Main model: COCO (person + common animals).
- Optional second model: custom monkey detector under ./best/best.pt (or MONKEY_MODEL_PATH).
  Both run each frame; monkey boxes merge with COCO output (person overlap suppressed).
- Smaller MONKEY_INFER_IMGSZ keeps dual-model latency reasonable.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from backend.config import (
    ANIMAL_CLASS_IDS,
    ANIMAL_CONFIDENCE_THRESHOLD,
    CONFIDENCE_THRESHOLD,
    MONKEY_CONFIDENCE_THRESHOLD,
    MONKEY_INFER_IMGSZ,
    MONKEY_MODEL_DIR,
    PERSON_CLASS_ID,
    YOLO_INFER_IMGSZ,
    YOLO_MODEL_PATH,
    resolve_monkey_weights_path,
)

logger = logging.getLogger(__name__)


def _bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter + 1e-6)


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
        self._model = None
        self._monkey_model = None
        self._available = False
        self._monkey_available = False
        self._infer_half = False

        try:
            import torch

            self._infer_half = bool(torch.cuda.is_available())
        except Exception:
            self._infer_half = False

        try:
            from ultralytics import YOLO  # type: ignore

            self._model = YOLO(model_path)
            self._available = True
            logger.info("YOLOv8 main model loaded from %s (imgsz=%s)", model_path, YOLO_INFER_IMGSZ)
        except Exception as exc:
            logger.warning("YOLO main unavailable (%s) — falling back to motion-only mode.", exc)
            self._model = None
            self._available = False

        mp = resolve_monkey_weights_path()
        if mp is not None:
            try:
                from ultralytics import YOLO  # type: ignore

                self._monkey_model = YOLO(str(mp))
                self._monkey_available = True
                logger.info(
                    "Monkey specialist model loaded from %s (imgsz=%s, half=%s)",
                    mp,
                    MONKEY_INFER_IMGSZ,
                    self._infer_half,
                )
            except Exception as exc:
                logger.warning("Monkey model not loaded (%s) — COCO animals only.", exc)
                self._monkey_model = None
                self._monkey_available = False
        else:
            logger.info(
                "No monkey .pt found under %s — export best.pt from training or set MONKEY_MODEL_PATH.",
                MONKEY_MODEL_DIR,
            )

    @property
    def available(self) -> bool:
        return self._available

    def _detect_coco(self, frame: np.ndarray, conf: float) -> list[Detection]:
        assert self._model is not None
        results = self._model(
            frame,
            conf=min(conf, CONFIDENCE_THRESHOLD),
            imgsz=YOLO_INFER_IMGSZ,
            verbose=False,
            half=self._infer_half,
        )[0]
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

    def _detect_monkey_specialist(self, frame: np.ndarray) -> list[Detection]:
        assert self._monkey_model is not None
        results = self._monkey_model(
            frame,
            conf=min(MONKEY_CONFIDENCE_THRESHOLD, 0.25),
            imgsz=MONKEY_INFER_IMGSZ,
            verbose=False,
            half=self._infer_half,
        )[0]
        out: list[Detection] = []
        for box in results.boxes:
            confidence = float(box.conf[0])
            if confidence < MONKEY_CONFIDENCE_THRESHOLD:
                continue
            cls_id = int(box.cls[0])
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
            label = str(self._monkey_model.names[cls_id])
            out.append(
                Detection(
                    label=label,
                    detection_type="animal",
                    confidence=confidence,
                    bbox=(x1, y1, x2, y2),
                )
            )
        return out

    @staticmethod
    def _merge_monkey_with_coco(coco: list[Detection], monkey: list[Detection]) -> list[Detection]:
        """Drop monkey boxes that overlap persons or duplicate COCO animals."""
        persons = [d for d in coco if d.detection_type == "person"]
        coco_animals = [d for d in coco if d.detection_type == "animal"]
        merged = list(coco)
        for m in monkey:
            if any(_bbox_iou(m.bbox, p.bbox) > 0.5 for p in persons):
                continue
            if any(_bbox_iou(m.bbox, a.bbox) > 0.45 for a in coco_animals):
                continue
            merged.append(m)
        return merged

    def detect(
        self,
        frame: np.ndarray,
        conf: float = CONFIDENCE_THRESHOLD,
    ) -> list[Detection]:
        """
        Run COCO model; optionally run monkey specialist and merge (no duplicate animals).
        """
        if not self._available or self._model is None:
            return []

        coco = self._detect_coco(frame, conf)
        if not self._monkey_available or self._monkey_model is None:
            return coco

        monkey = self._detect_monkey_specialist(frame)
        if not monkey:
            return coco

        return self._merge_monkey_with_coco(coco, monkey)

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

    def annotate(
        self,
        frame: np.ndarray,
        detections: list[Detection],
        blur_interior: bool = True,
    ) -> np.ndarray:
        """
        Draw labelled bounding boxes.
        When blur_interior is True (default), person regions are blurred before boxes are drawn.
        """
        output = self.blur_persons(frame, detections) if blur_interior else frame.copy()
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
