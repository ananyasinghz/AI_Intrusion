"""
PDF report generator using ReportLab.

Produces a multi-page PDF report containing:
  - Cover page (period, generated time, system name)
  - Summary stats table
  - Top zones by activity
  - Full incident log (paginated table)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from backend.config import REPORTS_DIR

logger = logging.getLogger(__name__)

# Dark-ish theme adapted for print (light backgrounds for legibility)
ACCENT = colors.HexColor("#1a73e8")
HEADER_BG = colors.HexColor("#f0f4ff")
ROW_ALT = colors.HexColor("#f9f9f9")
MUTED = colors.HexColor("#666666")
DANGER = colors.HexColor("#d32f2f")
WARNING = colors.HexColor("#f57c00")
SUCCESS = colors.HexColor("#388e3c")


def _type_color(dtype: str) -> colors.Color:
    return {
        "animal": WARNING,
        "person": DANGER,
        "loitering": WARNING,
        "zone_crossing": ACCENT,
        "abnormal_activity": DANGER,
    }.get(dtype, MUTED)


def generate_pdf(
    incidents: list,
    stats: dict,
    period_start: datetime,
    period_end: datetime,
    output_filename: str | None = None,
) -> str:
    """
    Generate a PDF report and return the file path.

    incidents: list of Incident ORM objects
    stats: dict with by_type, by_zone, total keys
    """
    filename = output_filename or f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = REPORTS_DIR / filename
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2 * cm,
    )

    story = []

    # ── Cover ─────────────────────────────────────────────────────────────
    title_style = ParagraphStyle("Title", parent=styles["Title"], textColor=ACCENT, fontSize=22, spaceAfter=6)
    story.append(Paragraph("Intrusion & Activity Report", title_style))
    story.append(Paragraph(
        f"Period: {period_start.strftime('%Y-%m-%d')} — {period_end.strftime('%Y-%m-%d')}",
        styles["Normal"],
    ))
    story.append(Paragraph(
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        ParagraphStyle("muted", parent=styles["Normal"], textColor=MUTED, fontSize=9),
    ))
    story.append(Spacer(1, 0.6 * cm))

    # ── Summary stats ──────────────────────────────────────────────────────
    story.append(Paragraph("Summary", styles["Heading2"]))
    summary_data = [["Metric", "Value"]]
    summary_data.append(["Total incidents", str(stats.get("total", 0))])
    for dtype, count in stats.get("by_type", {}).items():
        summary_data.append([f"  {dtype.replace('_', ' ').title()}", str(count)])

    summary_table = Table(summary_data, colWidths=[10 * cm, 5 * cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Top zones ──────────────────────────────────────────────────────────
    story.append(Paragraph("Activity by Zone", styles["Heading2"]))
    zone_data = [["Zone", "Incident Count"]]
    for zone, count in sorted(stats.get("by_zone", {}).items(), key=lambda x: -x[1])[:10]:
        zone_data.append([zone, str(count)])

    zone_table = Table(zone_data, colWidths=[10 * cm, 5 * cm])
    zone_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(zone_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Incident log ───────────────────────────────────────────────────────
    story.append(Paragraph("Incident Log", styles["Heading2"]))
    inc_data = [["ID", "Time", "Zone", "Type", "Label", "Conf."]]
    for inc in incidents[:200]:  # Cap at 200 rows for PDF
        inc_data.append([
            str(inc.id),
            inc.timestamp.strftime("%m/%d %H:%M") if inc.timestamp else "",
            (inc.zone_name or "")[:20],
            inc.detection_type,
            (inc.label or "")[:25],
            f"{inc.confidence:.0%}" if inc.confidence else "—",
        ])

    inc_table = Table(
        inc_data,
        colWidths=[1.2 * cm, 2.5 * cm, 3.5 * cm, 3 * cm, 4.5 * cm, 1.5 * cm],
    )
    inc_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(inc_table)

    doc.build(story)
    logger.info("PDF report generated: %s", filepath)
    return str(filepath)
