"""Playoff bracket projection handlers."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.formatters import (
    format_playoff_bracket_plain,
    format_playoff_bracket_rich,
)
from worldcupquente.handlers.utils import (
    _get_chat_language,
    _get_query_language,
    _get_service,
    _log_command,
)
from worldcupquente.i18n import text

logger = logging.getLogger(__name__)


async def playoff_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "matamata")
    message = update.effective_message
    if message is None:
        return
    language = _get_chat_language(update, context)
    service = _get_service(context)

    projection = await _fetch_projection(service, language)
    if projection is None:
        await message.reply_text(text("playoff_empty", language))
        return

    html = format_playoff_bracket_rich(projection, service.bot_timezone, language)
    try:
        await context.bot.do_api_request(
            "sendRichMessage",
            api_kwargs={
                "chat_id": message.chat_id,
                "rich_message": {"html": html, "skip_entity_detection": True},
            },
        )
    except Exception:
        logger.exception("Failed to send rich playoff projection; falling back to plain text")
        await message.reply_text(
            format_playoff_bracket_plain(projection, service.bot_timezone, language),
            parse_mode=ParseMode.HTML,
        )


async def handle_playoff_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.data != "playoff:menu" or query.message is None:
        return
    language = _get_query_language(query, context)
    service = _get_service(context)

    projection = await _fetch_projection(service, language)
    if projection is None:
        await query.edit_message_text(text("playoff_empty", language))
        return

    html = format_playoff_bracket_rich(projection, service.bot_timezone, language)
    try:
        await context.bot.do_api_request(
            "editMessageText",
            api_kwargs={
                "chat_id": query.message.chat_id,
                "message_id": query.message.message_id,
                "rich_message": {"html": html, "skip_entity_detection": True},
            },
        )
    except Exception:
        logger.exception("Failed to edit rich playoff projection; falling back to plain text")
        await query.edit_message_text(
            format_playoff_bracket_plain(projection, service.bot_timezone, language),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def _fetch_projection(service: Any, language: str) -> Any:
    try:
        return await service.get_sofascore_playoff_projection()
    except Exception:
        logger.exception("Failed to fetch playoff projection")
        return None
