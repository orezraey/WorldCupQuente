"""Standings and group table navigation handlers."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.formatters import format_standings_group_table
from worldcupquente.handlers.utils import (
    _get_chat_language,
    _get_query_language,
    _get_service,
    _log_command,
)
from worldcupquente.i18n import text
from worldcupquente.keyboards import (
    build_standings_back_keyboard,
    build_standings_groups_keyboard,
)

logger = logging.getLogger(__name__)


async def standings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "tabela")
    message = update.effective_message
    if message is None:
        return
    await _send_standings_menu(message.reply_text, context, _get_chat_language(update, context))


async def _send_standings_menu(
    send_message: Any,
    context: ContextTypes.DEFAULT_TYPE,
    language: str,
) -> None:
    service = _get_service(context)
    try:
        groups = await service.get_standings_groups()
    except Exception:
        logger.exception("Failed to fetch standings groups")
        await send_message(text("standings_groups_error", language))
        return

    if not groups:
        await send_message(text("standings_groups_empty", language))
        return

    message_text = f"<b>{text('standings_title', language)}</b>\n{text('standings_body', language)}"
    await send_message(
        message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_standings_groups_keyboard(groups, language),
    )


async def _send_standings_group(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    if query.message is None:
        return
    language = _get_query_language(query, context)

    parts = data.split(":")
    if len(parts) < 3 or not parts[2]:
        await query.edit_message_text(
            text("invalid_group", language), reply_markup=build_standings_back_keyboard(language)
        )
        return

    group_id = parts[2]
    service = _get_service(context)
    try:
        group = await service.get_standings_group(group_id)
    except Exception:
        logger.exception("Failed to fetch standings group", extra={"group_id": group_id})
        await query.edit_message_text(
            text("standings_group_error", language),
            reply_markup=build_standings_back_keyboard(language),
        )
        return

    if group is None:
        await query.edit_message_text(
            text("standings_group_not_found", language),
            reply_markup=build_standings_back_keyboard(language),
        )
        return

    await context.bot.do_api_request(
        "editMessageText",
        api_kwargs={
            "chat_id": query.message.chat_id,
            "message_id": query.message.message_id,
            "rich_message": {
                "html": format_standings_group_table(group, language),
                "skip_entity_detection": True,
            },
            "reply_markup": build_standings_back_keyboard(language),
        },
    )


async def handle_standings_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.data == "table:menu":
        await _send_standings_menu(query.edit_message_text, context, _get_query_language(query, context))
    elif query.data.startswith("table:group:"):
        await _send_standings_group(query, context, query.data)
