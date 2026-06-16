"""Finished match history handlers."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.formatters import (
    format_history_game_details,
    format_history_games,
    format_history_player_ratings,
    format_history_statistics,
)
from worldcupquente.handlers.utils import (
    _get_chat_language,
    _get_query_language,
    _get_service,
    _log_command,
)
from worldcupquente.i18n import text
from worldcupquente.keyboards import (
    HISTORY_GAMES_PAGE_SIZE,
    build_history_back_to_game_keyboard,
    build_history_game_keyboard,
    build_history_games_keyboard,
)

logger = logging.getLogger(__name__)


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "historico")
    message = update.effective_message
    if message is None:
        return
    await _send_history_page(message.reply_text, context, 0, _get_chat_language(update, context))


async def _send_history_page(
    send_message: Any,
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
    language: str,
) -> None:
    service = _get_service(context)
    try:
        events = await service.get_finished_events()
    except Exception:
        logger.exception("Failed to fetch history games")
        await send_message(text("history_error", language))
        return

    total_pages = max(1, (len(events) + HISTORY_GAMES_PAGE_SIZE - 1) // HISTORY_GAMES_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_events = events[page * HISTORY_GAMES_PAGE_SIZE : (page + 1) * HISTORY_GAMES_PAGE_SIZE]
    await send_message(
        format_history_games(page_events, page, total_pages, language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_history_games_keyboard(
            page_events,
            page,
            total_pages,
            service.bot_timezone,
            language,
        )
        if page_events
        else None,
    )


async def _edit_history_page(query: Any, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    service = _get_service(context)
    language = _get_query_language(query, context)
    try:
        events = await service.get_finished_events()
    except Exception:
        logger.exception("Failed to fetch history games")
        await query.edit_message_text(text("history_error", language))
        return

    total_pages = max(1, (len(events) + HISTORY_GAMES_PAGE_SIZE - 1) // HISTORY_GAMES_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_events = events[page * HISTORY_GAMES_PAGE_SIZE : (page + 1) * HISTORY_GAMES_PAGE_SIZE]
    await query.edit_message_text(
        format_history_games(page_events, page, total_pages, language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_history_games_keyboard(
            page_events,
            page,
            total_pages,
            service.bot_timezone,
            language,
        )
        if page_events
        else None,
    )


async def _send_history_game(query: Any, context: ContextTypes.DEFAULT_TYPE, event_id: str, page: int) -> None:
    service = _get_service(context)
    language = _get_query_language(query, context)
    event = await _history_event_details(service, event_id, language, query)
    if event is None:
        return

    await query.edit_message_text(
        format_history_game_details(event, service.bot_timezone, language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_history_game_keyboard(event_id, page, language),
    )


async def _send_history_stats(query: Any, context: ContextTypes.DEFAULT_TYPE, event_id: str, page: int) -> None:
    service = _get_service(context)
    language = _get_query_language(query, context)
    event = await _history_event_details(service, event_id, language, query)
    if event is None:
        return

    await query.edit_message_text(
        format_history_statistics(event, language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_history_back_to_game_keyboard(event_id, page, language),
    )


async def _send_history_ratings(query: Any, context: ContextTypes.DEFAULT_TYPE, event_id: str, page: int) -> None:
    service = _get_service(context)
    language = _get_query_language(query, context)
    event = await _history_event_details(service, event_id, language, query)
    if event is None:
        return

    await query.edit_message_text(
        format_history_player_ratings(event, language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_history_back_to_game_keyboard(event_id, page, language),
    )


async def _history_event_details(
    service: Any,
    event_id: str,
    language: str,
    query: Any,
) -> dict[str, Any] | None:
    try:
        event = await service.get_finished_event_details(event_id)
    except Exception:
        logger.exception("Failed to fetch history game details", extra={"event_id": event_id})
        event = None
    if event is None:
        await query.edit_message_text(text("history_detail_error", language))
        return None
    return event


async def handle_history_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = query.data or ""
    if data.startswith("hist:page:"):
        await _edit_history_page(query, context, _parse_history_page(data))
        return

    parts = data.split(":")
    if len(parts) < 4:
        await query.edit_message_text(text("history_detail_error", _get_query_language(query, context)))
        return

    action = parts[1]
    event_id = parts[2]
    page = int(parts[3]) if parts[3].isdigit() else 0
    if action == "game":
        await _send_history_game(query, context, event_id, page)
    elif action == "stats":
        await _send_history_stats(query, context, event_id, page)
    elif action == "ratings":
        await _send_history_ratings(query, context, event_id, page)


def _parse_history_page(data: str) -> int:
    try:
        return int(data.rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        return 0
