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
from backend.config import SNAPSHOT_DIR, SNAPSHOT_DIR_FULL, ZONES
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

        # Latest detections from YOLO — updated by _detection_loop, read by _broadcast_loop.
        # Stored separately so _broadcast_loop can annotate a FRESH raw frame rather than
        # reusing the stale pixel content baked into result.annotated_frame.
        self._latest_detections: list = []

        # Monotonic timestamp of the last frame broadcast
        self._last_frame_broadcast: float = 0.0
        # Target: 10 fps for the live stream
        self._frame_interval: float = 1.0 / 10.0

        # Consecutive high-flow frame counter for optical flow sensitivity guard
        self._flow_strike_count: int = 0

        self._tripwire_loaded = False

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(self, source: InputSource | None = None) -> None:
        """
        Three concurrent loops keep the live feed smooth regardless of YOLO speed:

        _capture_loop   — reads raw frames from the source via run_in_executor so it
                          never blocks the event loop; stores the latest frame in
                          self._latest_raw_frame.

        _broadcast_loop — encodes and pushes the most-recent annotated frame (falling
                          back to the raw frame before the first YOLO result) to all
                          WebSocket clients at a steady 10 fps.  Runs in the event loop
                          so it can always send, even while YOLO is working.

        _detection_loop — grabs self._latest_raw_frame, runs motion + YOLO via
                          run_in_executor (off the event loop), then handles all
                          detection events (DB, alerts, loitering …).  Runs as fast as
                          YOLO allows without starving the other loops.
        """
        owns_source = source is None
        src = source or get_input_source()
        self._running = True
        loop = asyncio.get_running_loop()
        logger.info("Pipeline started for zone '%s'", self._zone)

        # Shared state — all writes happen on the event-loop thread (after await), so
        # no explicit locking is needed in CPython's cooperative scheduler.
        self._latest_raw_frame: np.ndarray | None = None
        self._latest_annotated_viewer: np.ndarray | None = None
        self._latest_annotated_admin: np.ndarray | None = None

        async def _capture_loop() -> None:
            while self._running:
                ret, frame = await loop.run_in_executor(None, src.read)
                if not ret or frame is None:
                    logger.info("Input source exhausted or disconnected.")
                    self._running = False
                    break
                self._latest_raw_frame = frame
                await asyncio.sleep(0)

        async def _broadcast_loop() -> None:
            """
            Broadcast at a steady 10 fps using the LATEST raw frame from _capture_loop,
            annotated with the most-recent YOLO detection results.

            Key design decisions:
            - We annotate `_latest_raw_frame` (always ≤ 33 ms old at 30fps) rather than
              `_latest_annotated_viewer` (which contains pixel content from the frame YOLO
              processed, potentially 400 ms ago).  This eliminates the "frozen then jump"
              effect.
            - Both annotation (OpenCV blur/box drawing) and JPEG encoding are done inside
              run_in_executor so they never block the asyncio event loop.
            - We snapshot `raw` and `dets` as local variables before entering the executor
              so concurrent writes to self._latest_raw_frame / self._latest_detections by
              _capture_loop / _detection_loop don't interfere mid-encode.
            """
            yolo = self._yolo  # local ref — YOLODetector.annotate() is read-only, thread-safe

            while self._running:
                try:
                    raw = self._latest_raw_frame
                    if raw is not None and self._frame_cb is not None:
                        dets = list(self._latest_detections)  # shallow copy, Detection objects are immutable

                        def _annotate_and_encode(
                            _raw=raw, _dets=dets
                        ) -> tuple[bytes, bytes] | None:
                            frame_v = yolo.annotate(_raw, _dets, blur_interior=True)
                            frame_a = yolo.annotate(_raw, _dets, blur_interior=False)
                            ok_v, buf_v = cv2.imencode(
                                ".jpg", frame_v, [cv2.IMWRITE_JPEG_QUALITY, 55]
                            )
                            ok_a, buf_a = cv2.imencode(
                                ".jpg", frame_a, [cv2.IMWRITE_JPEG_QUALITY, 55]
                            )
                            if ok_v and ok_a:
                                return buf_v.tobytes(), buf_a.tobytes()
                            return None

                        result_bufs = await loop.run_in_executor(None, _annotate_and_encode)
                        if result_bufs is not None:
                            await self._frame_cb(result_bufs[0], result_bufs[1])

                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.debug("Frame broadcast skipped", exc_info=True)
                await asyncio.sleep(self._frame_interval)

        async def _detection_loop() -> None:
            if not self._tripwire_loaded:
                self._load_tripwire()
                self._tripwire_loaded = True

            while self._running:
                frame = self._latest_raw_frame
                if frame is None:
                    await asyncio.sleep(0.02)
                    continue

                try:
                    has_motion, bboxes = await loop.run_in_executor(
                        None, self._motion_detector.detect, frame
                    )
                    result = await loop.run_in_executor(
                        None, self._classifier.classify, frame, has_motion
                    )

                    self._latest_annotated_viewer = result.annotated_frame
                    self._latest_annotated_admin = result.annotated_frame_admin
                    # Snapshot the current detection list so _broadcast_loop can re-apply
                    # the boxes to whatever raw frame it has at the time of encoding.
                    self._latest_detections = result.detections

                    if result.primary_type not in ("clear",):
                        await self._handle_primary_event(frame, result)

                    if result.detections:
                        for ev in self._loitering.update(result.detections):
                            if self._is_cooldown_ok(self._zone, "loitering"):
                                snap, snap_full = self._save_snapshot(
                                    frame, result.privacy_frame, "loitering", result.detections,
                                )
                                await self._log_and_alert(
                                    zone=self._zone,
                                    detection_type="loitering",
                                    label=f"{ev['label']} (loitering {ev['duration_seconds']:.0f}s)",
                                    confidence=None,
                                    snapshot_path=snap,
                                    snapshot_path_full=snap_full,
                                    source="camera",
                                    track_id=ev["track_id"],
                                    duration_seconds=ev["duration_seconds"],
                                )

                    if result.detections:
                        for ev in self._zone_crossing.update(result.detections):
                            if self._is_cooldown_ok(self._zone, "zone_crossing"):
                                snap, snap_full = self._save_snapshot(
                                    frame, result.privacy_frame, "zone_crossing", result.detections,
                                )
                                await self._log_and_alert(
                                    zone=self._zone,
                                    detection_type="zone_crossing",
                                    label=f"{ev['label']} ({ev['direction']})",
                                    confidence=None,
                                    snapshot_path=snap,
                                    snapshot_path_full=snap_full,
                                    source="camera",
                                    track_id=ev["track_id"],
                                )

                    if has_motion and bboxes:
                        anomalies = self._optical_flow.update(frame, bboxes)
                        if anomalies:
                            self._flow_strike_count += 1
                        else:
                            self._flow_strike_count = 0

                        if self._flow_strike_count >= OPTICAL_FLOW_MIN_FRAMES:
                            if self._is_cooldown_ok(self._zone, "abnormal_activity"):
                                label = " + ".join(anomalies)
                                snap, snap_full = self._save_snapshot(
                                    frame, result.privacy_frame, "abnormal_activity", result.detections,
                                )
                                await self._log_and_alert(
                                    zone=self._zone,
                                    detection_type="abnormal_activity",
                                    label=label,
                                    confidence=None,
                                    snapshot_path=snap,
                                    snapshot_path_full=snap_full,
                                    source="camera",
                                )
                                self._flow_strike_count = 0
                    else:
                        self._flow_strike_count = 0

                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Detection loop error — skipping frame")

                await asyncio.sleep(0)

        try:
            await asyncio.gather(
                _capture_loop(),
                _broadcast_loop(),
                _detection_loop(),
            )
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

    async def _maybe_broadcast_frame(
        self,
        frame_viewer: np.ndarray,
        frame_admin: np.ndarray,
    ) -> None:
        """Encode and broadcast annotated frames at a capped rate (~10 fps)."""
        if self._frame_cb is None:
            return
        now = time.monotonic()
        if now - self._last_frame_broadcast < self._frame_interval:
            return
        self._last_frame_broadcast = now
        try:
            ok_v, buf_v = cv2.imencode(".jpg", frame_viewer, [cv2.IMWRITE_JPEG_QUALITY, 60])
            ok_a, buf_a = cv2.imencode(".jpg", frame_admin, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if ok_v and ok_a:
                await self._frame_cb(buf_v.tobytes(), buf_a.tobytes())
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
        if is_approved:
            snapshot_path, snapshot_path_full = None, None
        else:
            snapshot_path, snapshot_path_full = self._save_snapshot(
                frame, result.privacy_frame, dtype, result.detections
            )

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
            snapshot_path_full=snapshot_path_full,
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
        snapshot_path_full: str | None = None,
    ) -> None:
        incident = self._save_to_db(
            zone, detection_type, label, confidence,
            snapshot_path, snapshot_path_full, source, track_id, duration_seconds,
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
        snapshot_path_full: str | None,
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
                snapshot_path_full=snapshot_path_full,
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
        except Exception:
            logger.exception("Failed to save incident to DB — pipeline will continue")
            db.rollback()
            return incident
        finally:
            db.close()

    def _save_snapshot(
        self,
        raw_frame: np.ndarray,
        privacy_frame: np.ndarray,
        tag: str,
        detections: list,
    ) -> tuple[str | None, str | None]:
        """
        Save privacy (blurred) snapshot for all viewers; when a person is present,
        also save an unblurred copy for admin-only access.
        """
        has_person = any(d.detection_type == "person" for d in detections)
        try:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
            base = f"{tag}_{self._zone.replace(' ', '_')}_{ts}"
            blur_name = f"{base}.jpg"
            path_blur = SNAPSHOT_DIR / blur_name
            cv2.imwrite(str(path_blur), privacy_frame)
            full_name: str | None = None
            if has_person:
                full_name = f"{base}_full.jpg"
                cv2.imwrite(str(SNAPSHOT_DIR_FULL / full_name), raw_frame)
            return blur_name, full_name
        except Exception:
            logger.exception("Failed to save snapshot")
            return None, None

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
