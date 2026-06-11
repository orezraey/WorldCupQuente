"""Telegram command and callback handlers."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from worldcupquente.formatters import (
    format_team_roster,
    format_today_games,
    split_telegram_message,
)
from worldcupquente.keyboards import (
    TEAMS_PAGE_SIZE,
    build_back_to_teams_keyboard,
    build_teams_keyboard,
)
from worldcupquente.services import WorldCupService

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    text = (
        "<b>Copa do Mundo 2026</b>\n\n"
        "Comandos disponíveis:\n"
        "/hoje - jogos de hoje\n"
        "/selecoes - lista de seleções e elencos"
    )
    await message.reply_text(text, parse_mode=ParseMode.HTML)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    service = _get_service(context)
    try:
        scoreboard = await service.get_today_games()
        text = format_today_games(scoreboard, service.bot_timezone)
    except Exception:
        logger.exception("Failed to fetch today's games")
        text = "Não consegui buscar os jogos de hoje agora. Tente novamente em instantes."
    for chunk in split_telegram_message(text):
        await message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await _send_teams_page(message.reply_text, context, page=0)


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    if query.data.startswith("teams:"):
        await _send_teams_page(query.edit_message_text, context, page=_parse_page(query.data))
        return
    if query.data.startswith("team:"):
        await _send_team_roster(query, context, query.data)


def get_handlers() -> list[Any]:
    return [
        CommandHandler("start", start_command),
        CommandHandler("hoje", today_command),
        CommandHandler("selecoes", teams_command),
        CallbackQueryHandler(callback_query_handler),
    ]


def _get_service(context: ContextTypes.DEFAULT_TYPE) -> WorldCupService:
    service = context.application.bot_data["world_cup_service"]
    if not isinstance(service, WorldCupService):
        raise RuntimeError("world_cup_service is not configured")
    return service


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
