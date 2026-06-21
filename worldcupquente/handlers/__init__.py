"""Telegram command and callback handlers package."""

from __future__ import annotations

from typing import Any

from telegram.ext import CallbackQueryHandler, CommandHandler, InlineQueryHandler

from worldcupquente.handlers.base import callback_query_handler, start_command
from worldcupquente.handlers.calendar import calendar_command
from worldcupquente.handlers.config import config_command
from worldcupquente.handlers.history import history_command
from worldcupquente.handlers.inline import inline_query_handler
from worldcupquente.handlers.live import live_command, today_command
from worldcupquente.handlers.standings import standings_command
from worldcupquente.handlers.teams import teams_command


def get_handlers() -> list[Any]:
    return [
        CommandHandler("start", start_command),
        CommandHandler(["hoje", "today"], today_command),
        CommandHandler(["aovivo", "live"], live_command),
        CommandHandler(["calendario", "calendar"], calendar_command),
        CommandHandler(["historico", "history"], history_command),
        CommandHandler(["tabela", "standings"], standings_command),
        CommandHandler(["selecoes", "teams"], teams_command),
        CommandHandler("config", config_command),
        InlineQueryHandler(inline_query_handler),
        CallbackQueryHandler(callback_query_handler),
    ]
