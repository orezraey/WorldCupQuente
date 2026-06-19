"""Live and daily match handlers."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TimedOut
from telegram.ext import ContextTypes

from worldcupquente.formatters import (
    format_live_games,
    format_live_games_rich,
    format_today_games,
    split_telegram_message,
)
from worldcupquente.handlers.utils import (
    _get_chat_language,
    _get_query_language,
    _get_service,
    _log_command,
)
from worldcupquente.i18n import text
from worldcupquente.keyboards import build_live_stats_keyboard

logger = logging.getLogger(__name__)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "hoje")
    message = update.effective_message
    if message is None:
        return
    language = _get_chat_language(update, context)
    service = _get_service(context)
    try:
        scoreboard = await service.get_sofascore_today_games()
        message_text = format_today_games(scoreboard, service.bot_timezone, language)
    except Exception:
        logger.exception("Failed to fetch today's games")
        message_text = text("today_error", language)
    for chunk in split_telegram_message(message_text):
        await message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def live_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "aovivo")
    message = update.effective_message
    if message is None:
        return
    language = _get_chat_language(update, context)
    service = _get_service(context)
    try:
        events = await service.get_sofascore_live_events(use_cache=False)
        message_text = format_live_games(events, service.bot_timezone, language=language)
    except Exception:
        logger.exception("Failed to fetch live games")
        message_text = text("live_error", language)
        events = []
    chunks = split_telegram_message(message_text)
    for index, chunk in enumerate(chunks):
        await message.reply_text(
            chunk,
            parse_mode=ParseMode.HTML,
            reply_markup=build_live_stats_keyboard(language=language) if events and index == 0 else None,
        )


async def _send_live_games(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    show_stats: bool,
    show_ratings: bool = False,
) -> None:
    service = _get_service(context)
    language = _get_query_language(query, context)
    try:
        events = await service.get_sofascore_live_events(use_cache=True, include_statistics=show_stats)
    except Exception:
        logger.exception("Failed to fetch live games")
        await query.edit_message_text(text("live_error_short", language))
        return

    if show_stats and events and query.message is not None:
        if show_ratings:
            events = await service.enrich_events_sofascore_player_ratings(events)
        await _edit_live_rich_message(query, context, events, show_ratings, language, service.bot_timezone)
        return

    message_text = format_live_games(events, service.bot_timezone, language=language)
    chunks = split_telegram_message(message_text)
    await query.edit_message_text(
        chunks[0],
        parse_mode=ParseMode.HTML,
        reply_markup=build_live_stats_keyboard(show_stats=show_stats, language=language) if events else None,
    )
    if query.message is None:
        return
    for chunk in chunks[1:]:
        await query.message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def handle_live_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.data.startswith("live:stats:"):
        await _send_live_games(query, context, show_stats=query.data.endswith(":show"))
    elif query.data.startswith("live:ratings:"):
        await _send_live_games(
            query,
            context,
            show_stats=True,
            show_ratings=query.data.endswith(":show"),
        )


async def _edit_live_rich_message(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    events: list[dict[str, Any]],
    show_ratings: bool,
    language: str,
    timezone: Any,
) -> None:
    if query.message is None:
        return

    payload = {
        "text": "\u200b",
        "chat_id": query.message.chat_id,
        "message_id": query.message.message_id,
        "reply_markup": build_live_stats_keyboard(
            show_stats=True,
            show_ratings=show_ratings,
            language=language,
        ),
        "api_kwargs": {
            "rich_message": {
                "html": format_live_games_rich(
                    events,
                    timezone,
                    language,
                    show_ratings=show_ratings,
                ),
                "skip_entity_detection": True,
            },
        },
        "read_timeout": 30,
        "write_timeout": 30,
    }
    try:
        await context.bot.edit_message_text(**payload)
    except TimedOut:
        logger.warning("Timed out sending rich live stats; retrying once")
        await context.bot.edit_message_text(**payload)
