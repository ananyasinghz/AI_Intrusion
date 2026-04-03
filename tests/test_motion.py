"""
Unit tests for motion detection logic.
No hardware required — uses synthetic numpy frames.
"""

import numpy as np
import pytest

from backend.detection.motion import MotionDetector


def make_frame(h: int = 480, w: int = 640) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def make_frame_with_blob(h: int = 480, w: int = 640) -> np.ndarray:
    frame = make_frame(h, w)
    # Draw a white rectangle large enough to exceed MOTION_MIN_AREA
    frame[100:200, 100:300] = 255
    return frame


class TestMotionDetector:
    def setup_method(self):
        self.detector = MotionDetector(min_area=500)

    def test_no_motion_on_static_frames(self):
        """Static identical frames should not trigger motion (after warm-up)."""
        frame = make_frame()
        # Prime the background model
        for _ in range(30):
            self.detector.detect(frame)
        has_motion, bboxes = self.detector.detect(frame)
        assert not has_motion
        assert bboxes == []

    def test_motion_on_sudden_change(self):
        """A sudden large bright blob should trigger motion."""
        static = make_frame()
        for _ in range(30):
            self.detector.detect(static)

        blob = make_frame_with_blob()
        has_motion, bboxes = self.detector.detect(blob)
        assert has_motion
        assert len(bboxes) >= 1

    def test_bounding_boxes_are_tuples(self):
        """Bounding boxes should be 4-element tuples."""
        static = make_frame()
        for _ in range(30):
            self.detector.detect(static)
        blob = make_frame_with_blob()
        _, bboxes = self.detector.detect(blob)
        for bb in bboxes:
            assert len(bb) == 4

    def test_draw_boxes_does_not_modify_original(self):
        """draw_boxes should return a copy, not modify the input frame."""
        frame = make_frame_with_blob()
        original = frame.copy()
        self.detector.draw_boxes(frame, [(10, 10, 50, 50)])
        np.testing.assert_array_equal(frame, original)
