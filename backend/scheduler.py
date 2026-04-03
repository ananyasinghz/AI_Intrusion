"""
APScheduler background jobs:

  - Daily digest: 8 AM every day — summary sent to Telegram (and email if configured)
  - Weekly PDF:   Monday 8 AM  — full PDF report emailed to admin
  - DB cleanup:   3 AM daily   — delete old snapshots + incidents past retention window
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.config import DATA_RETENTION_DAYS, SNAPSHOT_DIR

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


def start_scheduler() -> None:
    scheduler.add_job(_daily_digest, "cron", hour=8, minute=0, id="daily_digest")
    scheduler.add_job(_weekly_report, "cron", day_of_week="mon", hour=8, minute=5, id="weekly_report")
    if DATA_RETENTION_DAYS > 0:
        scheduler.add_job(_cleanup, "cron", hour=3, minute=0, id="cleanup")
    scheduler.start()
    logger.info("Scheduler started. Jobs: %s", [j.id for j in scheduler.get_jobs()])


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


async def _daily_digest() -> None:
    """Send a daily summary via Telegram."""
    from backend.alerts.telegram_bot import TelegramAlerter
    from backend.database.db import SessionLocal
    from backend.database.models import Incident

    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(hours=24)
        incidents = db.query(Incident).filter(Incident.timestamp >= since).all()
        total = len(incidents)
        from collections import Counter
        by_type = Counter(i.detection_type for i in incidents)

        lines = [
            "📊 *Daily Digest*",
            f"Period: last 24 hours",
            f"Total incidents: *{total}*",
        ]
        for dtype, count in by_type.most_common():
            lines.append(f"  • {dtype}: {count}")

        alerter = TelegramAlerter()
        if alerter._enabled:
            await alerter._bot.send_message(
                chat_id=alerter._chat_id,
                text="\n".join(lines),
                parse_mode="Markdown",
            )
            logger.info("Daily digest sent.")
    except Exception:
        logger.exception("Failed to send daily digest")
    finally:
        db.close()


async def _weekly_report() -> None:
    """Generate a PDF report for the past week and email it."""
    from backend.alerts.email_notifier import send_email_with_attachment
    from backend.config import ADMIN_EMAIL
    from backend.database.db import SessionLocal
    from backend.database.models import Incident
    from backend.reports.pdf_generator import generate_pdf

    if not ADMIN_EMAIL:
        logger.info("Weekly report skipped: ADMIN_EMAIL not set.")
        return

    db = SessionLocal()
    try:
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=7)
        incidents = (
            db.query(Incident)
            .filter(Incident.timestamp >= period_start)
            .order_by(Incident.timestamp.desc())
            .all()
        )
        from collections import Counter
        stats = {
            "total": len(incidents),
            "by_type": dict(Counter(i.detection_type for i in incidents)),
            "by_zone": dict(Counter(i.zone_name for i in incidents)),
        }
        pdf_path = generate_pdf(incidents, stats, period_start, period_end)
        await send_email_with_attachment(
            to=ADMIN_EMAIL,
            subject="Weekly Intrusion Report",
            body="Please find the weekly intrusion monitoring report attached.",
            attachment_path=pdf_path,
        )
        logger.info("Weekly PDF sent to %s", ADMIN_EMAIL)
    except Exception:
        logger.exception("Failed to send weekly report")
    finally:
        db.close()


async def _cleanup() -> None:
    """Delete incidents and snapshots older than DATA_RETENTION_DAYS."""
    from backend.database.db import SessionLocal
    from backend.database.models import Incident

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=DATA_RETENTION_DAYS)
        old = db.query(Incident).filter(Incident.timestamp < cutoff).all()

        deleted_snaps = 0
        for inc in old:
            if inc.snapshot_path:
                p = Path(inc.snapshot_path)
                if p.exists():
                    p.unlink()
                    deleted_snaps += 1

        count = len(old)
        for inc in old:
            db.delete(inc)
        db.commit()
        logger.info("Cleanup: removed %d incidents, %d snapshots (older than %d days)",
                    count, deleted_snaps, DATA_RETENTION_DAYS)
    except Exception:
        logger.exception("Cleanup failed")
    finally:
        db.close()
