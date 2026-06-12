"""Live and daily match handlers."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.formatters import (
    format_live_games,
    format_live_games_rich,
    format_today_games,
    split_telegram_message,
)
from worldcupquente.handlers.utils import _get_service, _log_command
from worldcupquente.keyboards import build_live_stats_keyboard

logger = logging.getLogger(__name__)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "hoje")
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


async def live_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "aovivo")
    message = update.effective_message
    if message is None:
        return
    service = _get_service(context)
    try:
        events = await service.get_live_events(use_cache=False)
        text = format_live_games(events, service.bot_timezone)
    except Exception:
        logger.exception("Failed to fetch live games")
        text = "Não consegui buscar as partidas ao vivo agora. Tente novamente em instantes."
        events = []
    chunks = split_telegram_message(text)
    for index, chunk in enumerate(chunks):
        await message.reply_text(
            chunk,
            parse_mode=ParseMode.HTML,
            reply_markup=build_live_stats_keyboard() if events and index == 0 else None,
        )


async def _send_live_games(query: Any, context: ContextTypes.DEFAULT_TYPE, show_stats: bool) -> None:
    service = _get_service(context)
    try:
        events = await service.get_live_events(use_cache=False)
    except Exception:
        logger.exception("Failed to fetch live games")
        await query.edit_message_text("Não consegui buscar as partidas ao vivo agora.")
        return

    if show_stats and events and query.message is not None:
        await context.bot.do_api_request(
            "editMessageText",
            api_kwargs={
                "chat_id": query.message.chat_id,
                "message_id": query.message.message_id,
                "rich_message": {
                    "html": format_live_games_rich(events, service.bot_timezone),
                    "skip_entity_detection": True,
                },
                "reply_markup": build_live_stats_keyboard(show_stats=True),
            },
        )
        return

    text = format_live_games(events, service.bot_timezone)
    chunks = split_telegram_message(text)
    await query.edit_message_text(
        chunks[0],
        parse_mode=ParseMode.HTML,
        reply_markup=build_live_stats_keyboard(show_stats=show_stats) if events else None,
    )
    if query.message is None:
        return
    for chunk in chunks[1:]:
        await query.message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def handle_live_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.data.startswith("live:stats:"):
        await _send_live_games(query, context, show_stats=query.data.endswith(":show"))
