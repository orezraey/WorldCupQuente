"""Telegram command definitions by language."""

from __future__ import annotations

import logging
from typing import Any

from telegram import BotCommand, BotCommandScopeChat

from worldcupquente.i18n import normalize_language, text

logger = logging.getLogger(__name__)

COMMANDS_BY_LANGUAGE = {
    "en": (
        ("start", "bot_command_start"),
        ("today", "bot_command_today"),
        ("live", "bot_command_live"),
        ("calendar", "bot_command_calendar"),
        ("standings", "bot_command_standings"),
        ("teams", "bot_command_teams"),
        ("config", "bot_command_config"),
    ),
    "pt": (
        ("start", "bot_command_start"),
        ("hoje", "bot_command_today"),
        ("aovivo", "bot_command_live"),
        ("calendario", "bot_command_calendar"),
        ("tabela", "bot_command_standings"),
        ("selecoes", "bot_command_teams"),
        ("config", "bot_command_config"),
    ),
}


def build_bot_commands(language: str = "en") -> list[BotCommand]:
    normalized = normalize_language(language)
    return [
        BotCommand(command=command, description=text(description_key, normalized))
        for command, description_key in COMMANDS_BY_LANGUAGE[normalized]
    ]


async def set_chat_commands(bot: Any, chat_id: int, language: str) -> None:
    try:
        await bot.set_my_commands(
            build_bot_commands(language),
            scope=BotCommandScopeChat(chat_id=chat_id),
        )
    except Exception:
        logger.exception("Failed to set chat Telegram commands", extra={"chat_id": chat_id})
