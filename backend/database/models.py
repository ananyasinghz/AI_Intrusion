from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(254), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    # "admin" or "viewer"
    role = Column(String(20), nullable=False, default="viewer")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    generated_reports = relationship("Report", back_populates="generated_by_user")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    # Index of the camera feed (0 = primary webcam, etc.)
    camera_index = Column(Integer, default=0)
    # JSON list of [[x1,y1],[x2,y2]] defining a virtual tripwire line
    tripwire_coords = Column(Text, nullable=True)
    # Seconds before a stationary object triggers a loitering alert
    loitering_threshold_seconds = Column(Integer, default=30)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    incidents = relationship("Incident", back_populates="zone_rel")
    alert_rules = relationship("AlertRule", back_populates="zone", cascade="all, delete-orphan")

    @property
    def tripwire(self) -> list | None:
        if self.tripwire_coords:
            return json.loads(self.tripwire_coords)
        return None

    @tripwire.setter
    def tripwire(self, value: list | None) -> None:
        self.tripwire_coords = json.dumps(value) if value else None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "camera_index": self.camera_index,
            "tripwire": self.tripwire,
            "loitering_threshold_seconds": self.loitering_threshold_seconds,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    # "animal", "person", "motion", "loitering", "zone_crossing", "abnormal_activity"
    detection_type = Column(String(50), nullable=False)
    enabled = Column(Boolean, default=True)
    cooldown_seconds = Column(Integer, default=30)

    zone = relationship("Zone", back_populates="alert_rules")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "zone_id": self.zone_id,
            "detection_type": self.detection_type,
            "enabled": self.enabled,
            "cooldown_seconds": self.cooldown_seconds,
        }


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    # Foreign key to zones table; nullable for legacy/mock PIR events
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=True, index=True)
    # Kept for display when zone_id is null or zone is deleted
    zone_name = Column(String(100), nullable=False)
    # "animal", "person", "motion", "loitering", "zone_crossing", "abnormal_activity", "unknown"
    detection_type = Column(String(50), nullable=False)
    label = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)
    snapshot_path = Column(Text, nullable=True)
    # Unblurred snapshot (admin only); set when a person is visible in the frame
    snapshot_path_full = Column(Text, nullable=True)
    # "camera", "pir", "mock_pir"
    source = Column(String(50), default="camera")
    # "open", "resolved"
    status = Column(String(20), default="open")
    # Object tracking ID (used for loitering and zone crossing)
    track_id = Column(String(50), nullable=True)
    # How long (seconds) the object was tracked — populated for loitering events
    duration_seconds = Column(Float, nullable=True)
    # Re-ID: gallery descriptor ID matched or created for this detection
    appearance_id = Column(String(20), nullable=True)
    # True if appearance_id matched a previously seen person (repeat visitor)
    is_repeat_visitor = Column(Boolean, default=False, nullable=False)

    zone_rel = relationship("Zone", back_populates="incidents")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "zone_id": self.zone_id,
            "zone": self.zone_name,
            "detection_type": self.detection_type,
            "label": self.label,
            "confidence": round(self.confidence, 3) if self.confidence else None,
            "snapshot_path": self.snapshot_path,
            "snapshot_path_full": self.snapshot_path_full,
            "source": self.source,
            "status": self.status,
            "track_id": self.track_id,
            "duration_seconds": self.duration_seconds,
            "appearance_id": self.appearance_id,
            "is_repeat_visitor": self.is_repeat_visitor,
        }


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Stored as bcrypt hash — never store the raw token
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="refresh_tokens")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    # "daily", "weekly", "custom"
    report_type = Column(String(20), nullable=False)
    # "pdf" or "csv"
    file_format = Column(String(10), nullable=False, default="pdf")
    file_path = Column(Text, nullable=True)
    generated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    generated_by_user = relationship("User", back_populates="generated_reports")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "report_type": self.report_type,
            "file_format": self.file_format,
            "file_path": self.file_path,
            "generated_by": self.generated_by,
        }
