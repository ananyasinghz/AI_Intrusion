"""
Admin-only natural language assistant: Groq turns questions into structured filters,
then SQLAlchemy runs a safe read query (no raw SQL from the model).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.auth.dependencies import require_admin
from backend.config import ZONES, refresh_groq_env
from backend.database.db import get_db
from backend.database.models import Incident, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

ALLOWED_DETECTION_TYPES = frozenset(
    {
        "animal",
        "person",
        "motion",
        "loitering",
        "zone_crossing",
        "abnormal_activity",
        "unknown",
    }
)
MAX_ROWS = 200


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    total: int
    incidents: list[dict[str, Any]]
    filters_used: dict[str, Any]


def _system_prompt(now_utc: datetime) -> str:
    zones_json = json.dumps(ZONES)
    return f"""You are a query planner for a hostel security incident database.
Current UTC time: {now_utc.isoformat()}
Known zone names (exact strings may appear in data): {zones_json}

The incidents table has columns:
- id, timestamp (UTC, ISO format), zone_name (string), detection_type, label, confidence,
  source, status ("open" or "resolved"), is_repeat_visitor (boolean)

detection_type must be one of: animal, person, motion, loitering, zone_crossing, abnormal_activity, unknown

Output ONLY valid JSON (no markdown) with this shape:
{{
  "assistant_message": "Brief friendly text describing what you will look up",
  "detection_type": null or one of the allowed strings,
  "zone_name_substring": null or string (case-insensitive substring match on zone_name, e.g. "gate" matches "Side Gate"),
  "datetime_from": null or ISO8601 UTC start (inclusive),
  "datetime_to": null or ISO8601 UTC end (exclusive or inclusive — use end of day if user says "through Friday"),
  "hour_from_utc": null or integer 0-23 (incident local hour in UTC — use for "after 10pm" as 22),
  "hour_to_utc": null or integer 0-23 (optional upper bound on hour, same UTC interpretation),
  "status": null or "open" or "resolved",
  "label_contains": null or string (substring match on label),
  "is_repeat_visitor": null or true or false,
  "limit": integer 1-{MAX_ROWS} (default 50)

Rules:
- "this week" = from Monday 00:00 UTC of current week through now unless user specifies otherwise.
- "today" = UTC day boundaries.
- If the user is vague, set wide filters and a reasonable limit.
- Never invent columns. Use null for unspecified filters.
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("No JSON object in model output")
    return json.loads(m.group())


def _parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str or not isinstance(dt_str, str):
        return None
    s = dt_str.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _call_groq(user_message: str, now_utc: datetime) -> dict[str, Any]:
    groq_key, groq_model = refresh_groq_env()
    if not groq_key:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not configured. Add it to .env in the project root and save the file.",
        )
    payload = {
        "model": groq_model,
        "messages": [
            {"role": "system", "content": _system_prompt(now_utc)},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.ConnectError as exc:
        logger.error("Cannot reach GROQ API (DNS/network): %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "Cannot reach the GROQ API — the server has no internet access. "
                "Check your network connection or firewall (Python may be blocked)."
            ),
        ) from exc
    except httpx.TimeoutException as exc:
        logger.error("GROQ API request timed out: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="GROQ API request timed out. Try again in a moment.",
        ) from exc
    except httpx.HTTPError as exc:
        logger.error("GROQ API HTTP error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Network error contacting GROQ API: {exc}",
        ) from exc

    if r.status_code == 401:
        logger.warning("GROQ API returned 401 — key may be invalid or expired")
        raise HTTPException(
            status_code=503,
            detail="GROQ API rejected the key (401). Check that GROQ_API_KEY is valid in .env.",
        )
    if r.status_code != 200:
        logger.warning("Groq API error %s: %s", r.status_code, r.text[:500])
        raise HTTPException(
            status_code=502,
            detail=f"Groq API error: {r.status_code}",
        )
    data = r.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=502, detail="Invalid Groq response") from e
    return _extract_json_object(content)


def _build_query(db: Session, spec: dict[str, Any]):
    q = db.query(Incident)

    dt = spec.get("detection_type")
    if dt and isinstance(dt, str) and dt in ALLOWED_DETECTION_TYPES:
        q = q.filter(Incident.detection_type == dt)

    zsub = spec.get("zone_name_substring")
    if zsub and isinstance(zsub, str) and zsub.strip():
        q = q.filter(Incident.zone_name.ilike(f"%{zsub.strip()}%"))

    df = _parse_iso(spec.get("datetime_from"))
    if df is not None:
        q = q.filter(Incident.timestamp >= df)
    dt_to = _parse_iso(spec.get("datetime_to"))
    if dt_to is not None:
        q = q.filter(Incident.timestamp <= dt_to)

    hf = spec.get("hour_from_utc")
    if hf is not None and isinstance(hf, (int, float)):
        h = max(0, min(23, int(hf)))
        q = q.filter(func.strftime("%H", Incident.timestamp) >= f"{h:02d}")

    ht = spec.get("hour_to_utc")
    if ht is not None and isinstance(ht, (int, float)):
        h2 = max(0, min(23, int(ht)))
        q = q.filter(func.strftime("%H", Incident.timestamp) <= f"{h2:02d}")

    st = spec.get("status")
    if st in ("open", "resolved"):
        q = q.filter(Incident.status == st)

    lc = spec.get("label_contains")
    if lc and isinstance(lc, str) and lc.strip():
        q = q.filter(Incident.label.isnot(None)).filter(
            Incident.label.ilike(f"%{lc.strip()}%")
        )

    irv = spec.get("is_repeat_visitor")
    if irv is True:
        q = q.filter(Incident.is_repeat_visitor.is_(True))
    elif irv is False:
        q = q.filter(
            or_(Incident.is_repeat_visitor.is_(False), Incident.is_repeat_visitor.is_(None))
        )

    lim = spec.get("limit", 50)
    try:
        lim = int(lim)
    except (TypeError, ValueError):
        lim = 50
    lim = max(1, min(MAX_ROWS, lim))

    return q.order_by(Incident.timestamp.desc()).limit(lim), lim


@router.post("/chat", response_model=ChatResponse)
def assistant_chat(
    body: ChatRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ChatResponse:
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        spec = _call_groq(body.message, now_utc)
    except HTTPException:
        raise
    except (ValueError, json.JSONDecodeError) as e:
        logger.exception("Failed to parse Groq JSON")
        raise HTTPException(status_code=502, detail=f"Bad model output: {e}") from e

    assistant_message = spec.get("assistant_message")
    if not isinstance(assistant_message, str):
        assistant_message = "Here are the matching incidents."

    q, lim = _build_query(db, spec)
    rows = q.all()
    items = [r.to_dict() for r in rows]

    filters_used = {k: spec.get(k) for k in (
        "detection_type",
        "zone_name_substring",
        "datetime_from",
        "datetime_to",
        "hour_from_utc",
        "hour_to_utc",
        "status",
        "label_contains",
        "is_repeat_visitor",
        "limit",
    )}

    reply = f"{assistant_message}\n\nFound **{len(items)}** incident(s) (showing up to {lim})."
    reply_plain = reply.replace("**", "")

    return ChatResponse(
        reply=reply_plain,
        total=len(items),
        incidents=items,
        filters_used=filters_used,
    )
