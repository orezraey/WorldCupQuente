"""Telegram bot entrypoint."""

from __future__ import annotations

import argparse
import logging
from typing import Any

from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes

from worldcupquente.config import get_settings
from worldcupquente.formatters import format_goal_notification
from worldcupquente.handlers import get_handlers
from worldcupquente.services import WorldCupService, scoring_plays_from_event

logger = logging.getLogger(__name__)

SEEN_GOAL_IDS_KEY = "live_seen_goal_ids"
SEEDED_EVENT_IDS_KEY = "live_seeded_event_ids"


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["world_cup_service"] = WorldCupService(settings)
    application.bot_data[SEEN_GOAL_IDS_KEY] = set()
    application.bot_data[SEEDED_EVENT_IDS_KEY] = set()
    for handler in get_handlers():
        application.add_handler(handler)
    if settings.live_notification_chat_ids:
        if application.job_queue is None:
            raise RuntimeError("Install python-telegram-bot with the job-queue extra to enable live notifications")
        application.job_queue.run_repeating(
            live_goal_monitor_job,
            interval=settings.live_poll_interval_seconds,
            first=5,
            name="live_goal_monitor",
        )
    return application


async def live_goal_monitor_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    service = context.application.bot_data["world_cup_service"]
    if not isinstance(service, WorldCupService):
        raise RuntimeError("world_cup_service is not configured")

    try:
        live_events = await service.get_live_events(use_cache=False)
    except Exception:
        logger.exception("Failed to poll live games for goal notifications")
        return

    seen_goal_ids: set[str] = context.application.bot_data.setdefault(SEEN_GOAL_IDS_KEY, set())
    seeded_event_ids: set[str] = context.application.bot_data.setdefault(SEEDED_EVENT_IDS_KEY, set())
    notifications: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for event in live_events:
        event_id = str(event.get("id", ""))
        event_was_seeded = event_id in seeded_event_ids
        for detail in scoring_plays_from_event(event):
            goal_id = _goal_id(event, detail)
            if goal_id in seen_goal_ids:
                continue
            seen_goal_ids.add(goal_id)
            if event_was_seeded:
                notifications.append((event, detail))
        if event_id:
            seeded_event_ids.add(event_id)

    for event, detail in notifications:
        text = format_goal_notification(event, detail)
        for chat_id in service.settings.live_notification_chat_ids:
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
            except Exception:
                logger.exception("Failed to send goal notification", extra={"chat_id": chat_id})


def _goal_id(event: dict[str, Any], detail: dict[str, Any]) -> str:
    athlete_ids = ",".join(str(athlete.get("id", "")) for athlete in detail.get("athletesInvolved", []))
    clock = detail.get("clock") or {}
    detail_type = detail.get("type") or {}
    team = detail.get("team") or {}
    return ":".join(
        [
            str(event.get("id", "")),
            str(team.get("id", "")),
            str(clock.get("value", "")),
            str(clock.get("displayValue", "")),
            athlete_ids,
            str(detail_type.get("id", "")),
            str(detail.get("scoreValue", "")),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run WorldCupQuente Telegram bot")
    parser.add_argument(
        "--drop-pending-updates",
        action="store_true",
        help="Drop Telegram updates queued while the bot was offline.",
    )
    args = parser.parse_args()

    application = build_application()
    application.run_polling(drop_pending_updates=args.drop_pending_updates)
