"""
CSV report exporter.
Writes all incidents in a period to a CSV file.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from backend.config import REPORTS_DIR

logger = logging.getLogger(__name__)


def generate_csv(incidents: list, output_filename: str | None = None) -> str:
    """Export incidents to CSV. Returns the file path."""
    filename = output_filename or f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = REPORTS_DIR / filename

    fieldnames = [
        "id", "timestamp", "zone", "detection_type", "label",
        "confidence", "source", "status", "track_id", "duration_seconds",
        "snapshot_path",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for inc in incidents:
            writer.writerow({
                "id": inc.id,
                "timestamp": inc.timestamp.isoformat() if inc.timestamp else "",
                "zone": inc.zone_name,
                "detection_type": inc.detection_type,
                "label": inc.label,
                "confidence": round(inc.confidence, 3) if inc.confidence else "",
                "source": inc.source,
                "status": inc.status,
                "track_id": inc.track_id or "",
                "duration_seconds": inc.duration_seconds or "",
                "snapshot_path": inc.snapshot_path or "",
            })

    logger.info("CSV report generated: %s (%d rows)", filepath, len(incidents))
    return str(filepath)
