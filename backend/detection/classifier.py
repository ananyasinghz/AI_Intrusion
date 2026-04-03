"""
High-level classifier: combines motion detection + YOLO detections into a
single FrameResult per frame.

Detection quality improvements (S12-A):
  1. Person-over-animal priority: if both person and animal are detected in the
     same frame, person wins. In a hostel, a human presence is always higher
     priority than an animal (and the animal label is more likely a false positive
     when a person is also strongly detected).
  2. Multi-frame vote buffer: a detection_type must win the majority in a sliding
     window of the last N frames before it is accepted. Single-frame "cat" spikes
     caused by unusual poses or lighting changes are silently discarded.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from backend.config import VOTE_THRESHOLD, VOTE_WINDOW
from backend.detection.yolo_detector import Detection, YOLODetector


@dataclass
class FrameResult:
    has_motion: bool
    detections: list[Detection]
    primary_type: str        # "animal", "person", "motion", "clear"
    primary_label: str
    max_confidence: float | None
    # Annotated with bounding boxes + blurred person interiors (viewer / privacy stream)
    annotated_frame: np.ndarray = field(repr=False)
    # Same annotations without blurring person regions (admin live stream)
    annotated_frame_admin: np.ndarray = field(repr=False)
    # Privacy-only version (blur without annotation boxes)
    privacy_frame: np.ndarray = field(repr=False)
    # Whether this result passed the vote buffer (callers can check)
    vote_accepted: bool = True


class Classifier:
    def __init__(self, yolo: YOLODetector) -> None:
        self._yolo = yolo
        # Sliding window of the last VOTE_WINDOW per-frame primary types
        self._vote_buffer: deque[str] = deque(maxlen=VOTE_WINDOW)

    def classify(
        self,
        frame: np.ndarray,
        has_motion: bool,
    ) -> FrameResult:
        """
        Run YOLO (when motion detected), apply priority rules and vote filter,
        return a FrameResult.
        """
        detections: list[Detection] = []

        if has_motion and self._yolo.available:
            detections = self._yolo.detect(frame)

        if detections:
            annotated = self._yolo.annotate(frame, detections, blur_interior=True)
            annotated_admin = self._yolo.annotate(frame, detections, blur_interior=False)
        else:
            annotated = frame.copy()
            annotated_admin = frame.copy()
        privacy_frame = self._yolo.blur_persons(frame, detections)

        raw_type, raw_label, max_conf = self._summarise(has_motion, detections)

        # Push into vote buffer and check majority
        self._vote_buffer.append(raw_type)
        vote_accepted = self._check_vote(raw_type)

        # If the vote buffer hasn't confirmed this type yet, downgrade to "clear"
        # so callers don't log an incident on a transient spike
        if vote_accepted:
            primary_type, primary_label = raw_type, raw_label
        else:
            primary_type, primary_label = "clear", "clear"

        return FrameResult(
            has_motion=has_motion,
            detections=detections,
            primary_type=primary_type,
            primary_label=primary_label,
            max_confidence=max_conf,
            annotated_frame=annotated,
            annotated_frame_admin=annotated_admin,
            privacy_frame=privacy_frame,
            vote_accepted=vote_accepted,
        )

    @staticmethod
    def _summarise(
        has_motion: bool,
        detections: list[Detection],
    ) -> tuple[str, str, float | None]:
        """
        Priority: person > animal > motion > clear.

        Person takes priority over animal deliberately:
          - In a hostel, human presence is the higher-severity event.
          - If YOLO detects "person 80%" and "cat 66%" in the same frame,
            the cat is almost certainly a false positive caused by the person's
            posture or a body part.
        """
        if not detections:
            return ("motion", "motion", None) if has_motion else ("clear", "clear", None)

        persons = [d for d in detections if d.detection_type == "person"]
        animals = [d for d in detections if d.detection_type == "animal"]

        # Person takes absolute priority
        if persons:
            best = max(persons, key=lambda d: d.confidence)
            return "person", "person (blurred)", best.confidence

        if animals:
            best = max(animals, key=lambda d: d.confidence)
            return "animal", best.label, best.confidence

        return "motion", "motion", None

    def _check_vote(self, current_type: str) -> bool:
        """
        Returns True if `current_type` appears at least VOTE_THRESHOLD times
        in the current vote buffer window.

        Non-detection types (motion, clear) always pass immediately — we only
        apply the gate to potentially noisy YOLO labels (person, animal).
        """
        if current_type in ("motion", "clear"):
            return True
        count = sum(1 for t in self._vote_buffer if t == current_type)
        return count >= VOTE_THRESHOLD
