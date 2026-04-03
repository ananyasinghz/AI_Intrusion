"""
Real-time endpoints.

WebSocket /ws/live carries TWO message types over a single connection:

  1. Incident events (JSON):
       { "type": "incident", "id": ..., "zone_name": ..., ... }
     Sent by the pipeline whenever a new incident is logged.

  2. Live video frames (JSON):
       { "type": "frame", "data": "<base64 JPEG>" }
     Sent by the pipeline at ~10 fps. The frontend renders these onto a
     <canvas> element. Clients must pass ?token=<JWT> when connecting;
     viewers receive person-blurred frames; admins receive unblurred annotated frames.

Why WebSocket for frames instead of MJPEG?
  - MJPEG (multipart/x-mixed-replace) is unreliable through Vite's proxy and
    increasingly unsupported in modern browsers.
  - YOLO inference is synchronous and blocks the asyncio event loop, which
    starves the MJPEG generator and causes the feed to freeze or go black.
  - WebSocket messages are queued; the browser renders each frame on the next
    animation frame, giving a smooth, browser-native experience.
  - One connection instead of two (WebSocket + HTTP stream) simplifies the
    frontend significantly.
"""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.orm import Session

from backend.auth.jwt_handler import decode_access_token
from backend.database.db import SessionLocal
from backend.database.models import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])

# Active WebSocket connections → user role ("admin" | "viewer")
_ws_clients: dict[WebSocket, str] = {}


# ── Broadcast helpers (called by the pipeline) ────────────────────────────────

async def broadcast_event(event: dict) -> None:
    """
    Push a new incident to all connected dashboards.
    Wraps the payload in a type envelope for client-side routing.
    """
    message = {"type": "incident", **event}
    await _broadcast_json(message)


async def broadcast_frame(jpeg_viewer: bytes, jpeg_admin: bytes) -> None:
    """
    Push annotated JPEG frames to connected dashboards (role-based).
    Encodes as base64 so it travels safely as JSON text.
    """
    b64_viewer = base64.b64encode(jpeg_viewer).decode("ascii")
    b64_admin = base64.b64encode(jpeg_admin).decode("ascii")
    dead: set[WebSocket] = set()
    for ws, role in list(_ws_clients.items()):
        b64 = b64_admin if role == "admin" else b64_viewer
        try:
            await ws.send_json({"type": "frame", "data": b64})
        except Exception:
            dead.add(ws)
    for ws in dead:
        _ws_clients.pop(ws, None)


async def _broadcast_json(payload: dict) -> None:
    dead: set[WebSocket] = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _ws_clients.pop(ws, None)


# ── WebSocket endpoint ────────────────────────────────────────────────────────

def _role_from_access_token(token: str) -> str | None:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError, TypeError):
        return None
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
        if user is None:
            return None
        return user.role if user.role in ("admin", "viewer") else "viewer"
    finally:
        db.close()


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    role = _role_from_access_token(token)
    if role is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    _ws_clients[websocket] = role
    logger.info("WebSocket client connected (%s). Total: %d", role, len(_ws_clients))
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.pop(websocket, None)
        logger.info("WebSocket client disconnected. Total: %d", len(_ws_clients))
