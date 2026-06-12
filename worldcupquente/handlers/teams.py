"""Team squad and roster handlers."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.formatters import format_team_roster, split_telegram_message
from worldcupquente.handlers.utils import _get_service, _log_command
from worldcupquente.keyboards import (
    TEAMS_PAGE_SIZE,
    build_back_to_teams_keyboard,
    build_teams_keyboard,
)

logger = logging.getLogger(__name__)


async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "selecoes")
    message = update.effective_message
    if message is None:
        return
    await _send_teams_page(message.reply_text, context, page=0)


async def _send_teams_page(send_message: Any, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    service = _get_service(context)
    try:
        teams = await service.get_teams()
    except Exception:
        logger.exception("Failed to fetch teams")
        await send_message("Não consegui buscar a lista de seleções agora.")
        return

    total_pages = max(1, (len(teams) + TEAMS_PAGE_SIZE - 1) // TEAMS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    text = f"<b>Seleções da Copa 2026</b>\nPágina {page + 1}/{total_pages}"
    await send_message(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_teams_keyboard(teams, page=page),
    )


async def _send_team_roster(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    parts = data.split(":")
    if len(parts) < 2 or not parts[1]:
        await query.edit_message_text("Seleção inválida.")
        return

    team_id = parts[1]
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    service = _get_service(context)

    await query.edit_message_text("Buscando elenco...")
    try:
        roster = await service.get_team_roster(team_id)
        chunks = split_telegram_message(format_team_roster(roster))
    except Exception:
        logger.exception("Failed to fetch team roster", extra={"team_id": team_id})
        await query.edit_message_text(
            "Não consegui buscar o elenco desta seleção agora.",
            reply_markup=build_back_to_teams_keyboard(page),
        )
        return

    await query.edit_message_text(
        chunks[0],
        parse_mode=ParseMode.HTML,
        reply_markup=build_back_to_teams_keyboard(page),
    )
    if query.message is None:
        return
    for chunk in chunks[1:]:
        await query.message.reply_text(chunk, parse_mode=ParseMode.HTML)


def _parse_page(data: str) -> int:
    try:
        return int(data.split(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        return 0


async def handle_teams_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.data.startswith("teams:"):
        await _send_teams_page(query.edit_message_text, context, page=_parse_page(query.data))
    elif query.data.startswith("team:"):
        await _send_team_roster(query, context, query.data)
