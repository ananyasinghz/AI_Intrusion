"""
Software PIR simulator.

Fires synthetic motion events at a configurable interval so you can
develop and test the full alert + dashboard pipeline without any hardware.

Set MOCK_PIR_INTERVAL=20 in .env to fire an event every 20 seconds.
Set to 0 (default) to disable — rely purely on camera-based motion detection.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable, Coroutine
from typing import Any

from backend.config import MOCK_PIR_INTERVAL, ZONES

logger = logging.getLogger(__name__)

# Callback type: async function(zone: str) -> None
PIRCallback = Callable[[str], Coroutine[Any, Any, None]]


class MockPIRSimulator:
    def __init__(
        self,
        interval: int = MOCK_PIR_INTERVAL,
        zones: list[str] | None = None,
    ) -> None:
        self._interval = interval
        self._zones = zones or ZONES
        self._callbacks: list[PIRCallback] = []
        self._task: asyncio.Task | None = None
        self._running = False

    def register_callback(self, callback: PIRCallback) -> None:
        """Register an async callback that fires on each simulated PIR event."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        if self._interval <= 0:
            logger.info("Mock PIR disabled (MOCK_PIR_INTERVAL=0).")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Mock PIR started — firing every %ds across zones: %s",
            self._interval,
            self._zones,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._interval)
            zone = random.choice(self._zones)
            logger.info("Mock PIR triggered in zone: %s", zone)
            for cb in self._callbacks:
                try:
                    await cb(zone)
                except Exception:
                    logger.exception("Error in PIR callback")

    async def fire_once(self, zone: str | None = None) -> None:
        """Manually fire a single event (useful for testing via API endpoint)."""
        target_zone = zone or random.choice(self._zones)
        logger.info("Manual PIR fire in zone: %s", target_zone)
        for cb in self._callbacks:
            await cb(target_zone)
