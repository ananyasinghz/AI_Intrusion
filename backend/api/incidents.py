"""
REST API endpoints for incident management and statistics.
All routes require authentication (viewer or admin).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth.dependencies import require_admin, require_viewer
from backend.database.db import get_db
from backend.database.models import Incident, User

router = APIRouter(prefix="/api", tags=["incidents"])


@router.get("/incidents")
def list_incidents(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    zone: str | None = None,
    detection_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    _: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(Incident).order_by(Incident.timestamp.desc())

    if zone:
        query = query.filter(Incident.zone_name == zone)
    if detection_type:
        query = query.filter(Incident.detection_type == detection_type)
    if date_from:
        query = query.filter(Incident.timestamp >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(Incident.timestamp <= datetime.fromisoformat(date_to))

    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [i.to_dict() for i in items],
    }


@router.get("/incidents/{incident_id}")
def get_incident(
    incident_id: int,
    _: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident.to_dict()


@router.patch("/incidents/{incident_id}/resolve")
def resolve_incident(
    incident_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident.status = "resolved"
    db.commit()
    return incident.to_dict()


@router.get("/stats")
def get_stats(
    hours: int = Query(24, ge=1, le=8760),
    _: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(hours=hours)
    base_query = db.query(Incident).filter(Incident.timestamp >= since)

    total = base_query.count()

    by_type = (
        base_query.with_entities(Incident.detection_type, func.count(Incident.id))
        .group_by(Incident.detection_type)
        .all()
    )

    by_zone = (
        base_query.with_entities(Incident.zone_name, func.count(Incident.id))
        .group_by(Incident.zone_name)
        .all()
    )

    hourly = _hourly_counts(db, since)

    # Loitering stats: average duration per zone
    loitering = (
        base_query.filter(
            Incident.detection_type == "loitering",
            Incident.duration_seconds.isnot(None),
        )
        .with_entities(Incident.zone_name, func.avg(Incident.duration_seconds))
        .group_by(Incident.zone_name)
        .all()
    )

    return {
        "period_hours": hours,
        "total": total,
        "by_type": {t: c for t, c in by_type},
        "by_zone": {z: c for z, c in by_zone},
        "hourly": hourly,
        "avg_loitering_seconds": {z: round(avg, 1) for z, avg in loitering},
    }


@router.get("/heatmap")
def get_heatmap(
    hours: int = Query(24, ge=1, le=8760),
    _: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(Incident.zone_name, Incident.detection_type, func.count(Incident.id))
        .filter(Incident.timestamp >= since)
        .group_by(Incident.zone_name, Incident.detection_type)
        .all()
    )
    result: dict[str, dict] = {}
    for zone, dtype, count in rows:
        if zone not in result:
            result[zone] = {"total": 0}
        result[zone][dtype] = count
        result[zone]["total"] = result[zone].get("total", 0) + count

    return result


@router.get("/analytics/hourly-heatmap")
def get_hourly_zone_heatmap(
    hours: int = Query(168, ge=1, le=8760),
    _: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """
    Returns a 24×N grid: hour-of-day (0–23) × zone,
    used for the analytics hour-of-day heatmap chart.
    """
    since = datetime.utcnow() - timedelta(hours=hours)
    incidents = (
        db.query(Incident.timestamp, Incident.zone_name)
        .filter(Incident.timestamp >= since)
        .all()
    )

    grid: dict[str, dict[int, int]] = {}
    for ts, zone in incidents:
        hour = ts.hour
        if zone not in grid:
            grid[zone] = {h: 0 for h in range(24)}
        grid[zone][hour] = grid[zone].get(hour, 0) + 1

    return grid


def _hourly_counts(db: Session, since: datetime) -> list[dict]:
    incidents = (
        db.query(Incident.timestamp, Incident.detection_type)
        .filter(Incident.timestamp >= since)
        .all()
    )
    buckets: dict[str, dict[str, int]] = {}
    for ts, dtype in incidents:
        hour_key = ts.strftime("%Y-%m-%dT%H:00")
        if hour_key not in buckets:
            buckets[hour_key] = {}
        buckets[hour_key][dtype] = buckets[hour_key].get(dtype, 0) + 1

    return [{"hour": k, **v} for k, v in sorted(buckets.items())]
