"""
Tests for the Classifier — uses a mock YOLODetector so no GPU/model needed.

Priority rules (S12-A):
  - person > animal > motion > clear
  - Vote buffer: YOLO labels (person/animal) must appear in VOTE_THRESHOLD
    of the last VOTE_WINDOW frames before the result is accepted.
    motion and clear pass immediately without a vote gate.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from backend.detection.classifier import Classifier
from backend.detection.yolo_detector import Detection, YOLODetector
from backend.config import VOTE_THRESHOLD


def blank_frame():
    return np.zeros((480, 640, 3), dtype=np.uint8)


def make_mock_yolo(detections: list[Detection], available: bool = True) -> YOLODetector:
    mock = MagicMock(spec=YOLODetector)
    mock.available = available
    mock.detect.return_value = detections
    mock.blur_persons.side_effect = lambda frame, _dets: frame.copy()
    mock.annotate.side_effect = lambda frame, _dets: frame.copy()
    return mock


def classify_n(clf: Classifier, frame, has_motion: bool, n: int):
    """Call classify n times and return the last result."""
    result = None
    for _ in range(n):
        result = clf.classify(frame, has_motion=has_motion)
    return result


class TestClassifier:
    def test_clear_when_no_motion(self):
        yolo = make_mock_yolo([])
        clf = Classifier(yolo)
        result = clf.classify(blank_frame(), has_motion=False)
        assert result.primary_type == "clear"
        assert not result.has_motion

    def test_motion_only_when_no_yolo_detections(self):
        yolo = make_mock_yolo([])
        clf = Classifier(yolo)
        result = clf.classify(blank_frame(), has_motion=True)
        # motion passes vote gate immediately (no YOLO label)
        assert result.primary_type == "motion"

    def test_person_takes_priority_over_animal(self):
        """Person > animal: when both are detected, person wins."""
        detections = [
            Detection("cat", "animal", 0.91, (10, 10, 100, 100)),
            Detection("person", "person", 0.80, (200, 10, 400, 300)),
        ]
        yolo = make_mock_yolo(detections)
        clf = Classifier(yolo)
        # Warm up vote buffer so the result is accepted
        result = classify_n(clf, blank_frame(), has_motion=True, n=VOTE_THRESHOLD)
        assert result.primary_type == "person"

    def test_animal_detected_when_no_person(self):
        """Animal is reported when no person is present (after vote gate passes)."""
        detections = [Detection("cat", "animal", 0.91, (10, 10, 100, 100))]
        yolo = make_mock_yolo(detections)
        clf = Classifier(yolo)
        result = classify_n(clf, blank_frame(), has_motion=True, n=VOTE_THRESHOLD)
        assert result.primary_type == "animal"
        assert result.primary_label == "cat"

    def test_person_detected_when_no_animal(self):
        detections = [Detection("person", "person", 0.88, (50, 50, 200, 400))]
        yolo = make_mock_yolo(detections)
        clf = Classifier(yolo)
        result = classify_n(clf, blank_frame(), has_motion=True, n=VOTE_THRESHOLD)
        assert result.primary_type == "person"

    def test_yolo_not_called_when_no_motion(self):
        yolo = make_mock_yolo([])
        clf = Classifier(yolo)
        clf.classify(blank_frame(), has_motion=False)
        yolo.detect.assert_not_called()

    def test_vote_buffer_suppresses_single_frame_spike(self):
        """A one-off YOLO detection is downgraded to 'clear' until votes accumulate."""
        detections = [Detection("cat", "animal", 0.91, (10, 10, 100, 100))]
        yolo = make_mock_yolo(detections)
        clf = Classifier(yolo)
        # Only one classify call — vote buffer has only 1 entry, needs VOTE_THRESHOLD
        result = clf.classify(blank_frame(), has_motion=True)
        assert result.primary_type == "clear", (
            f"Expected 'clear' on first frame (vote not yet met), got '{result.primary_type}'"
        )

    def test_vote_buffer_accepts_after_threshold(self):
        """After enough consistent detections the result is accepted."""
        detections = [Detection("person", "person", 0.88, (50, 50, 200, 400))]
        yolo = make_mock_yolo(detections)
        clf = Classifier(yolo)
        result = classify_n(clf, blank_frame(), has_motion=True, n=VOTE_THRESHOLD)
        assert result.primary_type == "person"
        assert result.vote_accepted is True

    def test_max_confidence_returned(self):
        detections = [
            Detection("cat", "animal", 0.70, (0, 0, 50, 50)),
            Detection("dog", "animal", 0.92, (60, 0, 120, 60)),
        ]
        yolo = make_mock_yolo(detections)
        clf = Classifier(yolo)
        result = classify_n(clf, blank_frame(), has_motion=True, n=VOTE_THRESHOLD)
        assert result.max_confidence == pytest.approx(0.92)
