"""
Report generation and download endpoints.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import require_admin, require_viewer
from backend.database.db import get_db
from backend.database.models import Incident, Report, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["reports"])


class GenerateRequest(BaseModel):
    report_type: str = "daily"   # daily, weekly, custom
    file_format: str = "pdf"     # pdf, csv
    period_start: str | None = None
    period_end: str | None = None


def _resolve_period(report_type: str, period_start: str | None, period_end: str | None):
    now = datetime.utcnow()
    if report_type == "daily":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
    elif report_type == "weekly":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=7)
    else:
        if not period_start or not period_end:
            raise HTTPException(400, "Custom reports require period_start and period_end")
        start = datetime.fromisoformat(period_start)
        end = datetime.fromisoformat(period_end)
    return start, end


@router.get("")
def list_reports(
    _: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return [r.to_dict() for r in db.query(Report).order_by(Report.generated_at.desc()).all()]


@router.post("/generate")
def generate_report(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    start, end = _resolve_period(body.report_type, body.period_start, body.period_end)

    report = Report(
        period_start=start,
        period_end=end,
        report_type=body.report_type,
        file_format=body.file_format,
        generated_by=user.id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    background_tasks.add_task(_run_generation, report.id, body.file_format)
    return report.to_dict()


def _run_generation(report_id: int, file_format: str) -> None:
    from backend.database.db import SessionLocal
    from backend.database.models import Incident, Report
    from collections import Counter

    db = SessionLocal()
    try:
        report = db.query(Report).filter(Report.id == report_id).first()
        if not report:
            return

        incidents = (
            db.query(Incident)
            .filter(
                Incident.timestamp >= report.period_start,
                Incident.timestamp <= report.period_end,
            )
            .order_by(Incident.timestamp.desc())
            .all()
        )

        stats = {
            "total": len(incidents),
            "by_type": dict(Counter(i.detection_type for i in incidents)),
            "by_zone": dict(Counter(i.zone_name for i in incidents)),
        }

        if file_format == "csv":
            from backend.reports.csv_exporter import generate_csv
            path = generate_csv(incidents)
        else:
            from backend.reports.pdf_generator import generate_pdf
            path = generate_pdf(incidents, stats, report.period_start, report.period_end)

        report.file_path = path
        db.commit()
        logger.info("Report %d generated: %s", report_id, path)
    except Exception:
        logger.exception("Report generation failed for id=%d", report_id)
    finally:
        db.close()


@router.get("/{report_id}/download")
def download_report(
    report_id: int,
    _: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    if not report.file_path or not Path(report.file_path).exists():
        raise HTTPException(404, "Report file not yet generated or was deleted")

    media_type = "application/pdf" if report.file_format == "pdf" else "text/csv"
    return FileResponse(report.file_path, media_type=media_type, filename=Path(report.file_path).name)
