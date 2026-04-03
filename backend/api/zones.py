"""
Zone management CRUD — admin can create/update/delete, viewer can read.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import require_admin, require_viewer
from backend.database.db import get_db
from backend.database.models import AlertRule, Zone

router = APIRouter(prefix="/api/zones", tags=["zones"])


class ZoneCreate(BaseModel):
    name: str
    description: str | None = None
    camera_index: int = 0
    tripwire: list | None = None
    loitering_threshold_seconds: int = 30


class ZoneUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    camera_index: int | None = None
    tripwire: list | None = None
    loitering_threshold_seconds: int | None = None
    is_active: bool | None = None


class AlertRuleCreate(BaseModel):
    detection_type: str
    enabled: bool = True
    cooldown_seconds: int = 30


@router.get("")
def list_zones(
    _: object = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return [z.to_dict() for z in db.query(Zone).all()]


@router.get("/{zone_id}")
def get_zone(
    zone_id: int,
    _: object = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    result = zone.to_dict()
    result["alert_rules"] = [r.to_dict() for r in zone.alert_rules]
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
def create_zone(
    body: ZoneCreate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(Zone).filter(Zone.name == body.name).first():
        raise HTTPException(status_code=409, detail="Zone name already exists")
    zone = Zone(
        name=body.name,
        description=body.description,
        camera_index=body.camera_index,
        tripwire_coords=json.dumps(body.tripwire) if body.tripwire else None,
        loitering_threshold_seconds=body.loitering_threshold_seconds,
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone.to_dict()


@router.patch("/{zone_id}")
def update_zone(
    zone_id: int,
    body: ZoneUpdate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    if body.name is not None:
        zone.name = body.name
    if body.description is not None:
        zone.description = body.description
    if body.camera_index is not None:
        zone.camera_index = body.camera_index
    if body.tripwire is not None:
        zone.tripwire_coords = json.dumps(body.tripwire)
    if body.loitering_threshold_seconds is not None:
        zone.loitering_threshold_seconds = body.loitering_threshold_seconds
    if body.is_active is not None:
        zone.is_active = body.is_active
    db.commit()
    db.refresh(zone)
    return zone.to_dict()


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_zone(
    zone_id: int,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    db.delete(zone)
    db.commit()


@router.post("/{zone_id}/alert-rules", status_code=status.HTTP_201_CREATED)
def add_alert_rule(
    zone_id: int,
    body: AlertRuleCreate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not db.query(Zone).filter(Zone.id == zone_id).first():
        raise HTTPException(status_code=404, detail="Zone not found")
    rule = AlertRule(
        zone_id=zone_id,
        detection_type=body.detection_type,
        enabled=body.enabled,
        cooldown_seconds=body.cooldown_seconds,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule.to_dict()
