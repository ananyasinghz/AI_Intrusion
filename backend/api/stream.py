"""
Real-time endpoints.

WebSocket /ws/live carries TWO message types over a single connection:

  1. Incident events (JSON):
       { "type": "incident", "id": ..., "zone_name": ..., ... }
     Sent by the pipeline whenever a new incident is logged.

  2. Live video frames (JSON):
       { "type": "frame", "data": "<base64 JPEG>" }
     Sent by the pipeline at ~10 fps. The frontend renders these onto a
     <canvas> element. This completely replaces the old MJPEG /stream/video
     endpoint, which had browser-compatibility and event-loop-blocking issues.

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

import asyncio
import base64
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])

# Global set of active WebSocket connections
_ws_clients: set[WebSocket] = set()


# ── Broadcast helpers (called by the pipeline) ────────────────────────────────

async def broadcast_event(event: dict) -> None:
    """
    Push a new incident to all connected dashboards.
    Wraps the payload in a type envelope for client-side routing.
    """
    message = {"type": "incident", **event}
    await _broadcast_json(message)


async def broadcast_frame(jpeg_bytes: bytes) -> None:
    """
    Push an annotated JPEG frame to all connected dashboards.
    Encodes as base64 so it travels safely as JSON text.
    """
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    await _broadcast_json({"type": "frame", "data": b64})


async def _broadcast_json(payload: dict) -> None:
    dead: set[WebSocket] = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket) -> None:
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info("WebSocket client connected. Total: %d", len(_ws_clients))
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)
        logger.info("WebSocket client disconnected. Total: %d", len(_ws_clients))
