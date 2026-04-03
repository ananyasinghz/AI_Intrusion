"""
End-to-end pipeline test using a synthetic video (no camera or model needed).

Injects frames directly into the pipeline, asserts incidents are logged
and the broadcast callback is invoked.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import models as _models  # noqa: F401 — register ORM tables
from backend.database.db import Base
from backend.detection.input_source import InputSource
from backend.pipeline import DetectionPipeline


class SyntheticSource(InputSource):
    """
    Emits a sequence of frames:
      - 20 identical blank frames (to train background model)
      - 5 frames with a bright blob (triggers motion)
    """

    def __init__(self):
        self._count = 0
        self._blank = np.zeros((480, 640, 3), dtype=np.uint8)
        self._blob = self._blank.copy()
        self._blob[100:250, 100:400] = 200

    def read(self):
        self._count += 1
        if self._count <= 20:
            return True, self._blank.copy()
        if self._count <= 25:
            return True, self._blob.copy()
        return False, None  # Signal end of source

    def release(self):
        pass


async def test_pipeline_logs_incidents(tmp_path):
    """Pipeline should log at least one incident when motion frames arrive."""
    db_path = tmp_path / "test_e2e.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    session_local_test = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    broadcast_mock = AsyncMock()

    with (
        patch("backend.pipeline.SessionLocal", session_local_test),
        patch("backend.pipeline.TelegramAlerter") as mock_alerter_cls,
        patch("backend.pipeline.YOLODetector") as mock_yolo_cls,
    ):
        mock_alerter = MagicMock()
        mock_alerter.send_alert = AsyncMock(return_value=True)
        mock_alerter_cls.return_value = mock_alerter

        mock_yolo = MagicMock()
        mock_yolo.available = False
        mock_yolo.detect.return_value = []
        mock_yolo.blur_persons.side_effect = lambda f, _: f.copy()
        mock_yolo.annotate.side_effect = lambda f, _, blur_interior=True: f.copy()
        mock_yolo_cls.return_value = mock_yolo

        pipeline = DetectionPipeline(zone="Test Zone", broadcast_callback=broadcast_mock)
        source = SyntheticSource()

        await pipeline.run(source=source)

    # The broadcast callback should have been called at least once
    assert broadcast_mock.call_count >= 1

    # Each call should have received an incident dict
    for call in broadcast_mock.call_args_list:
        event = call.args[0]
        assert "zone" in event
        assert "detection_type" in event
        assert event["zone"] == "Test Zone"


async def test_pir_event_logs_incident(tmp_path):
    """PIR events should log motion incidents independently of camera."""
    db_path = tmp_path / "test_pir.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    session_local_test = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    broadcast_mock = AsyncMock()

    with (
        patch("backend.pipeline.SessionLocal", session_local_test),
        patch("backend.pipeline.TelegramAlerter") as mock_alerter_cls,
        patch("backend.pipeline.YOLODetector"),
    ):
        mock_alerter = MagicMock()
        mock_alerter.send_alert = AsyncMock(return_value=True)
        mock_alerter_cls.return_value = mock_alerter

        pipeline = DetectionPipeline(zone="Test Zone", broadcast_callback=broadcast_mock)
        await pipeline.handle_pir_event("Side Gate")

    assert broadcast_mock.call_count == 1
    event = broadcast_mock.call_args.args[0]
    assert event["zone"] == "Side Gate"
    assert event["source"] == "mock_pir"
