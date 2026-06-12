"""Standings and group table navigation handlers."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.formatters import format_standings_group_table
from worldcupquente.handlers.utils import _get_service, _log_command
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
    await _send_standings_menu(message.reply_text, context)


async def _send_standings_menu(send_message: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = _get_service(context)
    try:
        groups = await service.get_standings_groups()
    except Exception:
        logger.exception("Failed to fetch standings groups")
        await send_message("Não consegui buscar os grupos da tabela agora.")
        return

    if not groups:
        await send_message("Nenhum grupo encontrado na tabela da Copa agora.")
        return

    text = "<b>Tabela da Copa 2026</b>\nEscolha um grupo para ver a classificação."
    await send_message(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_standings_groups_keyboard(groups),
    )


async def _send_standings_group(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    if query.message is None:
        return

    parts = data.split(":")
    if len(parts) < 3 or not parts[2]:
        await query.edit_message_text("Grupo inválido.", reply_markup=build_standings_back_keyboard())
        return

    group_id = parts[2]
    service = _get_service(context)
    try:
        group = await service.get_standings_group(group_id)
    except Exception:
        logger.exception("Failed to fetch standings group", extra={"group_id": group_id})
        await query.edit_message_text(
            "Não consegui buscar a tabela deste grupo agora.",
            reply_markup=build_standings_back_keyboard(),
        )
        return

    if group is None:
        await query.edit_message_text("Grupo não encontrado.", reply_markup=build_standings_back_keyboard())
        return

    await context.bot.do_api_request(
        "editMessageText",
        api_kwargs={
            "chat_id": query.message.chat_id,
            "message_id": query.message.message_id,
            "rich_message": {
                "html": format_standings_group_table(group),
                "skip_entity_detection": True,
            },
            "reply_markup": build_standings_back_keyboard(),
        },
    )


async def handle_standings_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.data == "table:menu":
        await _send_standings_menu(query.edit_message_text, context)
    elif query.data.startswith("table:group:"):
        await _send_standings_group(query, context, query.data)
