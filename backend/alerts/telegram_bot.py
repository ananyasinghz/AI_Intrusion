"""
Telegram alert sender with per-zone cooldown.

Each zone has an independent cooldown timer so a busy zone
doesn't suppress alerts from a quiet zone.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from backend.config import ALERT_COOLDOWN_SECONDS, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

_TYPE_EMOJI = {
    "animal": "🐾",
    "person": "🚶",
    "motion": "⚠️",
    "unknown": "❓",
}


class TelegramAlerter:
    def __init__(
        self,
        token: str = TELEGRAM_BOT_TOKEN,
        chat_id: str = TELEGRAM_CHAT_ID,
        cooldown: int = ALERT_COOLDOWN_SECONDS,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._cooldown = cooldown
        self._last_alert: dict[str, float] = {}
        self._bot = None
        self._enabled = bool(token and chat_id)

        if self._enabled:
            try:
                from telegram import Bot  # type: ignore

                self._bot = Bot(token=token)
                logger.info("Telegram bot initialised.")
            except ImportError:
                logger.warning("python-telegram-bot not installed — alerts disabled.")
                self._enabled = False
        else:
            logger.warning(
                "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — alerts disabled."
            )

    def _is_on_cooldown(self, zone: str) -> bool:
        last = self._last_alert.get(zone, 0.0)
        return (time.time() - last) < self._cooldown

    def _mark_sent(self, zone: str) -> None:
        self._last_alert[zone] = time.time()

    async def send_alert(
        self,
        zone: str,
        detection_type: str,
        label: str,
        confidence: float | None = None,
        snapshot_path: str | None = None,
    ) -> bool:
        """
        Send a Telegram alert with optional snapshot photo.
        Returns True if the alert was sent, False if suppressed or failed.
        """
        if not self._enabled:
            logger.debug("Alert suppressed (bot not configured): %s / %s", zone, detection_type)
            return False

        if self._is_on_cooldown(zone):
            remaining = self._cooldown - (time.time() - self._last_alert.get(zone, 0))
            logger.debug("Alert on cooldown for zone '%s' (%.0fs remaining)", zone, remaining)
            return False

        emoji = _TYPE_EMOJI.get(detection_type, "❓")
        conf_str = f" ({confidence:.0%} confidence)" if confidence else ""
        message = (
            f"{emoji} *Intrusion Alert*\n"
            f"Zone: `{zone}`\n"
            f"Type: `{detection_type.capitalize()}`\n"
            f"Label: `{label}`{conf_str}\n"
            f"Time: `{self._timestamp()}`"
        )

        try:
            if snapshot_path and Path(snapshot_path).exists():
                with open(snapshot_path, "rb") as photo:
                    await self._bot.send_photo(
                        chat_id=self._chat_id,
                        photo=photo,
                        caption=message,
                        parse_mode="Markdown",
                    )
            else:
                await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=message,
                    parse_mode="Markdown",
                )

            self._mark_sent(zone)
            logger.info("Telegram alert sent: zone=%s type=%s", zone, detection_type)
            return True

        except Exception:
            logger.exception("Failed to send Telegram alert")
            return False

    @staticmethod
    def _timestamp() -> str:
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
