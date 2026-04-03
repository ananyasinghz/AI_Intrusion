"""
FastAPI application entry point.

Startup:
  1. Run Alembic migrations (schema up-to-date)
  2. Seed default zones + admin user (first run only)
  3. Start detection pipeline as background task
  4. Start mock PIR simulator (if enabled)
  5. Start APScheduler for digests and cleanup (Phase S10)
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.assistant import router as assistant_router
from backend.api.incidents import router as incidents_router
from backend.api.reports import router as reports_router
from backend.api.stream import broadcast_event, broadcast_frame, router as stream_router
from backend.api.users import router as users_router
from backend.api.zones import router as zones_router
from backend.auth.router import router as auth_router
from backend.config import HOST, MOCK_PIR_INTERVAL, PORT, SNAPSHOT_DIR, ZONES
from backend.database.db import SessionLocal, init_db, seed_admin_user, seed_default_zones
from backend.detection.input_source import get_input_source
from backend.pipeline import DetectionPipeline
from backend.scheduler import start_scheduler, stop_scheduler
from backend.simulator.mock_pir import MockPIRSimulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    init_db()
    db = SessionLocal()
    try:
        seed_default_zones(db)
        seed_admin_user(db)
    finally:
        db.close()
    logger.info("Database ready. Default admin: admin / changeme")

    # Pytest sets SKIP_PIPELINE_LIFESPAN so TestClient does not run the camera
    # pipeline against the configured DATABASE_URL (avoids schema drift vs in-memory test DB).
    if os.getenv("SKIP_PIPELINE_LIFESPAN"):
        yield
        return

    pipeline = DetectionPipeline(
        zone=ZONES[0] if ZONES else "Main Entrance",
        broadcast_callback=broadcast_event,
        frame_callback=broadcast_frame,
    )
    application.state.pipeline = pipeline

    pir = MockPIRSimulator(interval=MOCK_PIR_INTERVAL)
    pir.register_callback(pipeline.handle_pir_event)
    application.state.pir = pir
    await pir.start()

    try:
        source = get_input_source()
        application.state.pipeline_task = asyncio.create_task(pipeline.run(source))
        logger.info("Detection pipeline started.")
    except Exception as exc:
        logger.warning("Could not open input source (%s) — pipeline paused.", exc)
        application.state.pipeline_task = None

    start_scheduler()

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    stop_scheduler()
    await pir.stop()
    pipeline.stop()
    task = getattr(application.state, "pipeline_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Intrusion & Activity Monitor",
    description="AI-based hostel intrusion detection system",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# In production, replace ["*"] with your frontend's actual origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ─────────────────────────────────────────────────────────────
app.mount("/snapshots", StaticFiles(directory=str(SNAPSHOT_DIR)), name="snapshots")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(incidents_router)
app.include_router(stream_router)
app.include_router(zones_router)
app.include_router(users_router)
app.include_router(reports_router)
app.include_router(assistant_router)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.post("/api/pir/fire")
async def fire_pir(zone: str | None = None):
    from fastapi import Request  # noqa: F811
    pir: MockPIRSimulator = app.state.pir
    await pir.fire_once(zone)
    return {"status": "fired", "zone": zone or "random"}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=False)
