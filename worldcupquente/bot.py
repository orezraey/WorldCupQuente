"""Telegram bot entrypoint."""

from __future__ import annotations

import argparse
import logging

from telegram.ext import Application

from worldcupquente.config import get_settings
from worldcupquente.handlers import get_handlers
from worldcupquente.services import WorldCupService


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
    for handler in get_handlers():
        application.add_handler(handler)
    return application


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
