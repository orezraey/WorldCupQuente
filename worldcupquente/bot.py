"""Telegram bot entrypoint."""

from __future__ import annotations

import argparse
import logging
from typing import Any

from telegram import Update
from telegram.ext import Application

from worldcupquente.config import get_settings
from worldcupquente.handlers import get_handlers
from worldcupquente.live_monitor import (
    LIVE_SCORE_SNAPSHOTS_KEY,
    NOTIFICATION_PREFERENCES_KEY,
    SEEN_FULL_TIME_IDS_KEY,
    SEEN_GOAL_IDS_KEY,
    SEEN_HALFTIME_IDS_KEY,
    SEEN_PENALTY_IDS_KEY,
    SEEN_RED_CARD_IDS_KEY,
    start_live_monitor,
    stop_live_monitor,
)
from worldcupquente.notification_preferences import NotificationPreferences
from worldcupquente.services import WorldCupService

logger = logging.getLogger(__name__)


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    builder = Application.builder().token(settings.telegram_bot_token)
    builder = builder.post_init(start_live_monitor).post_shutdown(stop_live_monitor)

    application = builder.build()
    application.bot_data["world_cup_service"] = WorldCupService(settings)
    application.bot_data[NOTIFICATION_PREFERENCES_KEY] = NotificationPreferences(
        settings.notification_config_path
    )
    application.bot_data[SEEN_GOAL_IDS_KEY] = set()
    application.bot_data[SEEN_PENALTY_IDS_KEY] = set()
    application.bot_data[SEEN_RED_CARD_IDS_KEY] = set()
    application.bot_data[SEEN_HALFTIME_IDS_KEY] = set()
    application.bot_data[SEEN_FULL_TIME_IDS_KEY] = set()
    application.bot_data[LIVE_SCORE_SNAPSHOTS_KEY] = {}
    application.bot_data["live_is_bootstrapped"] = False
    for handler in get_handlers():
        application.add_handler(handler)
    application.add_error_handler(error_handler)
    return application


async def error_handler(update: object, context: Any) -> None:
    chat = update.effective_chat if isinstance(update, Update) else None
    logger.exception(
        "Unhandled Telegram update error",
        exc_info=context.error,
        extra={"chat_id": getattr(chat, "id", None), "chat_type": getattr(chat, "type", None)},
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
