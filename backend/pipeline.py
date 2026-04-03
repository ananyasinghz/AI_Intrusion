"""
Central detection pipeline.

Per-frame processing order:
  1. Read frame from InputSource
  2. Motion detection (OpenCV MOG2)
  3. YOLOv8 classification (if motion)
  4. Privacy blur on persons
  5. Per-type DB cooldown check (prevents DB/snapshot flooding)
  6. Person re-ID (clothing color histogram — repeat visitor check)
  7. Loitering detection (time-based centroid tracking)
  8. Zone crossing detection (virtual tripwire)
  9. Optical flow anomaly detection (running / erratic — with sensitivity guard)
  10. Log incidents + save snapshot (snapshot only on first detection in cooldown window)
  11. Fire Telegram alerts
  12. Broadcast over WebSocket

Key behaviours:
  - DB_COOLDOWN_SECONDS: minimum gap between two logged incidents of the same
    detection_type in the same zone. Prevents flooding with hundreds of identical rows.
  - Snapshots are saved once per cooldown window (the very first detection).
  - Re-ID: for person detections, a clothing-color descriptor is computed and
    matched against a rolling 60-min gallery. Repeat visitors are flagged.
  - Optical flow: fires only after OPTICAL_FLOW_MIN_FRAMES consecutive frames
    of high magnitude, with its own separate cooldown.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

import cv2
import numpy as np

from backend.alerts.telegram_bot import TelegramAlerter
from backend.config import SNAPSHOT_DIR, ZONES
from backend.database.db import SessionLocal
from backend.database.models import Incident
from backend.detection.classifier import Classifier
from backend.detection.input_source import InputSource, get_input_source
from backend.detection.loitering import LoiteringDetector
from backend.detection.motion import MotionDetector
from backend.detection.optical_flow import OpticalFlowAnomalyDetector
from backend.detection.reid import ApprovedPersonsGallery, PersonReIDTracker, extract_clothing_descriptor
from backend.detection.yolo_detector import YOLODetector
from backend.detection.zone_crossing import ZoneCrossingDetector

logger = logging.getLogger(__name__)

# ── Cooldown configuration ────────────────────────────────────────────────────
# Minimum seconds between two DB log entries for the same type in the same zone.
DB_COOLDOWN: dict[str, int] = {
    "person":           30,
    "animal":           30,
    "motion":           20,
    "loitering":        60,
    "zone_crossing":    10,
    "abnormal_activity": 30,
    "unknown":          30,
}

# Optical flow: how many consecutive high-magnitude frames before firing
OPTICAL_FLOW_MIN_FRAMES = 5


class DetectionPipeline:
    def __init__(
        self,
        zone: str | None = None,
        broadcast_callback=None,
        frame_callback=None,
        approved_gallery: ApprovedPersonsGallery | None = None,
    ) -> None:
        self._zone = zone or (ZONES[0] if ZONES else "Zone 1")
        self._motion_detector = MotionDetector()
        self._yolo = YOLODetector()
        self._classifier = Classifier(self._yolo)
        self._loitering = LoiteringDetector()
        self._zone_crossing = ZoneCrossingDetector()
        self._optical_flow = OpticalFlowAnomalyDetector()
        self._reid = PersonReIDTracker()
        self._approved_gallery = approved_gallery or ApprovedPersonsGallery()
        self._alerter = TelegramAlerter()
        self._broadcast = broadcast_callback
        # Called with raw JPEG bytes of the annotated frame at ~10fps
        self._frame_cb = frame_callback
        self._running = False

        # Per-(zone, type) last-logged timestamp for DB cooldown
        # key: (zone_name, detection_type) → monotonic timestamp
        self._last_logged: dict[tuple[str, str], float] = {}

        # Monotonic timestamp of the last frame broadcast
        self._last_frame_broadcast: float = 0.0
        # Target: 10 fps for the live stream
        self._frame_interval: float = 1.0 / 10.0

        # Consecutive high-flow frame counter for optical flow sensitivity guard
        self._flow_strike_count: int = 0

        self._tripwire_loaded = False

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(self, source: InputSource | None = None) -> None:
        owns_source = source is None
        src = source or get_input_source()
        self._running = True
        logger.info("Pipeline started for zone '%s'", self._zone)

        try:
            while self._running:
                ret, frame = src.read()
                if not ret or frame is None:
                    logger.info("Input source exhausted or disconnected.")
                    break

                if not self._tripwire_loaded:
                    self._load_tripwire()
                    self._tripwire_loaded = True

                has_motion, bboxes = self._motion_detector.detect(frame)
                result = self._classifier.classify(frame, has_motion)

                # Broadcast annotated frame at ~10 fps over WebSocket
                await self._maybe_broadcast_frame(result.annotated_frame)

                # Primary detection (animal / person / motion)
                if result.primary_type not in ("clear",):
                    await self._handle_primary_event(frame, result)

                # Loitering
                if result.detections:
                    for ev in self._loitering.update(result.detections):
                        if self._is_cooldown_ok(self._zone, "loitering"):
                            snap = self._save_snapshot(result.privacy_frame, "loitering")
                            await self._log_and_alert(
                                zone=self._zone,
                                detection_type="loitering",
                                label=f"{ev['label']} (loitering {ev['duration_seconds']:.0f}s)",
                                confidence=None,
                                snapshot_path=snap,
                                source="camera",
                                track_id=ev["track_id"],
                                duration_seconds=ev["duration_seconds"],
                            )

                # Zone crossing
                if result.detections:
                    for ev in self._zone_crossing.update(result.detections):
                        if self._is_cooldown_ok(self._zone, "zone_crossing"):
                            snap = self._save_snapshot(result.privacy_frame, "zone_crossing")
                            await self._log_and_alert(
                                zone=self._zone,
                                detection_type="zone_crossing",
                                label=f"{ev['label']} ({ev['direction']})",
                                confidence=None,
                                snapshot_path=snap,
                                source="camera",
                                track_id=ev["track_id"],
                            )

                # Optical flow — with consecutive-frame guard
                if has_motion and bboxes:
                    anomalies = self._optical_flow.update(frame, bboxes)
                    if anomalies:
                        self._flow_strike_count += 1
                    else:
                        self._flow_strike_count = 0

                    if self._flow_strike_count >= OPTICAL_FLOW_MIN_FRAMES:
                        if self._is_cooldown_ok(self._zone, "abnormal_activity"):
                            label = " + ".join(anomalies)
                            snap = self._save_snapshot(result.privacy_frame, "abnormal_activity")
                            await self._log_and_alert(
                                zone=self._zone,
                                detection_type="abnormal_activity",
                                label=label,
                                confidence=None,
                                snapshot_path=snap,
                                source="camera",
                            )
                            self._flow_strike_count = 0
                else:
                    self._flow_strike_count = 0

                await asyncio.sleep(0)

        except asyncio.CancelledError:
            pass
        finally:
            if owns_source:
                src.release()
            self._running = False
            logger.info("Pipeline stopped for zone '%s'", self._zone)

    def stop(self) -> None:
        self._running = False

    # ── Frame broadcast ───────────────────────────────────────────────────────

    async def _maybe_broadcast_frame(self, frame: np.ndarray) -> None:
        """Encode and broadcast the annotated frame at a capped rate (~10 fps)."""
        if self._frame_cb is None:
            return
        now = time.monotonic()
        if now - self._last_frame_broadcast < self._frame_interval:
            return
        self._last_frame_broadcast = now
        try:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if ok:
                await self._frame_cb(buf.tobytes())
        except Exception:
            logger.debug("Frame broadcast skipped (encode error)")

    # ── Cooldown helper ───────────────────────────────────────────────────────

    def _is_cooldown_ok(self, zone: str, detection_type: str) -> bool:
        """
        Returns True if enough time has elapsed since the last logged incident
        of this type in this zone. Updates the timestamp on True.
        """
        key = (zone, detection_type)
        cooldown = DB_COOLDOWN.get(detection_type, 30)
        now = time.monotonic()
        last = self._last_logged.get(key, 0.0)
        if now - last >= cooldown:
            self._last_logged[key] = now
            return True
        return False

    # ── Event handlers ────────────────────────────────────────────────────────

    async def _handle_primary_event(self, frame: np.ndarray, result) -> None:
        dtype = result.primary_type
        if not self._is_cooldown_ok(self._zone, dtype):
            return

        appearance_id: str | None = None
        is_repeat: bool = False
        is_approved: bool = False

        if dtype == "person" and result.detections:
            person_dets = [d for d in result.detections if d.detection_type == "person"]
            if person_dets:
                best = max(person_dets, key=lambda d: d.confidence)
                # Face recognition check — identify approved persons regardless of outfit
                embedding = self._approved_gallery.get_face_embedding(frame, best.bbox)
                if embedding is not None:
                    is_approved = self._approved_gallery.is_approved(embedding)
                if not is_approved:
                    # Clothing-based repeat-visitor tracking (unchanged — runs only for non-approved)
                    descriptor = extract_clothing_descriptor(frame, best.bbox)
                    is_repeat, appearance_id, visit_count = self._reid.check_and_update(
                        frame, best.bbox, descriptor=descriptor
                    )
                    if is_repeat:
                        logger.info(
                            "Repeat visitor detected in %s (appearance_id=%s, visit=%d)",
                            self._zone, appearance_id, visit_count,
                        )
                else:
                    logger.debug("Approved person (face match) in %s — alert suppressed", self._zone)

        # No snapshot saved for approved persons (saves disk, less intrusive)
        snapshot_path = None if is_approved else self._save_snapshot(result.privacy_frame, dtype)

        if is_approved:
            label = "approved visitor"
        elif is_repeat:
            label = f"{result.primary_label} [repeat visitor]"
        else:
            label = result.primary_label

        await self._log_and_alert(
            zone=self._zone,
            detection_type=dtype,
            label=label,
            confidence=result.max_confidence,
            snapshot_path=snapshot_path,
            source="camera",
            appearance_id=appearance_id,
            is_repeat_visitor=is_repeat,
            is_approved=is_approved,
            skip_alert=is_approved,
        )

    async def handle_pir_event(self, zone: str) -> None:
        # Apply the same per-zone cooldown as camera events to prevent flooding
        # when the mock PIR fires frequently.
        if not self._is_cooldown_ok(zone, "motion"):
            logger.debug("PIR event in %s suppressed by cooldown", zone)
            return
        await self._log_and_alert(
            zone=zone,
            detection_type="motion",
            label="pir_trigger",
            confidence=None,
            snapshot_path=None,
            source="mock_pir",
        )

    async def _log_and_alert(
        self,
        zone: str,
        detection_type: str,
        label: str,
        confidence: float | None,
        snapshot_path: str | None,
        source: str,
        track_id: str | None = None,
        duration_seconds: float | None = None,
        appearance_id: str | None = None,
        is_repeat_visitor: bool = False,
        is_approved: bool = False,
        skip_alert: bool = False,
    ) -> None:
        incident = self._save_to_db(
            zone, detection_type, label, confidence,
            snapshot_path, source, track_id, duration_seconds,
            appearance_id, is_repeat_visitor, is_approved,
        )

        if self._broadcast:
            try:
                await self._broadcast(incident.to_dict())
            except Exception:
                logger.exception("WebSocket broadcast failed")

        if not skip_alert:
            asyncio.create_task(
                self._alerter.send_alert(
                    zone=zone,
                    detection_type=detection_type,
                    label=label,
                    confidence=confidence,
                    snapshot_path=snapshot_path,
                )
            )

    def _save_to_db(
        self,
        zone: str,
        detection_type: str,
        label: str,
        confidence: float | None,
        snapshot_path: str | None,
        source: str,
        track_id: str | None = None,
        duration_seconds: float | None = None,
        appearance_id: str | None = None,
        is_repeat_visitor: bool = False,
        is_approved: bool = False,
    ) -> Incident:
        from backend.database.models import Zone as ZoneModel
        db = SessionLocal()
        try:
            zone_row = db.query(ZoneModel).filter(ZoneModel.name == zone).first()
            incident = Incident(
                timestamp=datetime.utcnow(),
                zone_id=zone_row.id if zone_row else None,
                zone_name=zone,
                detection_type=detection_type,
                label=label,
                confidence=confidence,
                snapshot_path=snapshot_path,
                source=source,
                track_id=track_id,
                duration_seconds=duration_seconds,
                appearance_id=appearance_id,
                is_repeat_visitor=is_repeat_visitor,
                is_approved=is_approved,
            )
            db.add(incident)
            db.commit()
            db.refresh(incident)
            logger.info(
                "Incident logged: id=%d zone=%s type=%s label=%s%s",
                incident.id, zone, detection_type, label,
                " [REPEAT]" if is_repeat_visitor else "",
            )
            return incident
        finally:
            db.close()

    def _save_snapshot(self, frame: np.ndarray, detection_type: str) -> str | None:
        try:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{detection_type}_{self._zone.replace(' ', '_')}_{ts}.jpg"
            path = SNAPSHOT_DIR / filename
            cv2.imwrite(str(path), frame)
            # Store only the filename so the /snapshots/ static route works
            # regardless of where the project directory lives on disk.
            return filename
        except Exception:
            logger.exception("Failed to save snapshot")
            return None

    def _load_tripwire(self) -> None:
        try:
            from backend.database.models import Zone as ZoneModel
            db = SessionLocal()
            zone_row = db.query(ZoneModel).filter(ZoneModel.name == self._zone).first()
            if zone_row and zone_row.tripwire:
                self._zone_crossing.set_tripwire(zone_row.tripwire)
                logger.info("Tripwire loaded for zone '%s': %s", self._zone, zone_row.tripwire)
            db.close()
        except Exception:
            logger.exception("Failed to load tripwire from DB")
