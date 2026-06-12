"""Telegram command and callback handlers package."""

from __future__ import annotations

from typing import Any

from telegram.ext import CallbackQueryHandler, CommandHandler

from worldcupquente.handlers.base import callback_query_handler, start_command
from worldcupquente.handlers.calendar import calendar_command
from worldcupquente.handlers.config import config_command
from worldcupquente.handlers.live import live_command, today_command
from worldcupquente.handlers.standings import standings_command
from worldcupquente.handlers.teams import teams_command


def get_handlers() -> list[Any]:
    return [
        CommandHandler("start", start_command),
        CommandHandler("hoje", today_command),
        CommandHandler("aovivo", live_command),
        CommandHandler("calendario", calendar_command),
        CommandHandler("tabela", standings_command),
        CommandHandler("selecoes", teams_command),
        CommandHandler("config", config_command),
        CallbackQueryHandler(callback_query_handler),
    ]
