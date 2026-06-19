"""Calendar and fixture navigation handlers."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.event_utils import parse_event_datetime
from worldcupquente.formatters import format_games
from worldcupquente.handlers.utils import (
    _get_chat_language,
    _get_query_language,
    _get_service,
    _log_command,
)
from worldcupquente.i18n import text
from worldcupquente.keyboards import (
    CALENDAR_GAMES_PAGE_SIZE,
    TEAMS_PAGE_SIZE,
    build_calendar_all_games_keyboard,
    build_calendar_back_to_dates_keyboard,
    build_calendar_back_to_teams_keyboard,
    build_calendar_dates_keyboard,
    build_calendar_menu_keyboard,
    build_sofascore_calendar_teams_keyboard,
)
from worldcupquente.team_translations import translated_sofascore_team_name

logger = logging.getLogger(__name__)


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "calendario")
    message = update.effective_message
    if message is None:
        return
    await _send_calendar_menu(message.reply_text, _get_chat_language(update, context))


async def _send_calendar_menu(send_message: Any, language: str) -> None:
    message_text = f"<b>{text('calendar_title', language)}</b>\n{text('calendar_body', language)}"
    await send_message(
        message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_calendar_menu_keyboard(language),
    )


async def _send_calendar_dates(send_message: Any, context: ContextTypes.DEFAULT_TYPE, language: str) -> None:
    service = _get_service(context)
    try:
        events = await service.get_sofascore_schedule_events()
    except Exception:
        logger.exception("Failed to fetch calendar dates")
        await send_message(text("calendar_dates_error", language))
        return

    dates = _event_date_params(events, service.bot_timezone)
    message_text = f"<b>{text('calendar_dates_title', language)}</b>\n{text('calendar_dates_body', language)}"
    await send_message(
        message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_calendar_dates_keyboard(dates, language),
    )


async def _send_calendar_all_games(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    service = _get_service(context)
    language = _get_query_language(query, context)
    page = _parse_calendar_page(data)
    try:
        events = sorted(await service.get_sofascore_schedule_events(), key=lambda event: event.get("date", ""))
    except Exception:
        logger.exception("Failed to fetch full calendar")
        await query.edit_message_text(
            text("calendar_full_error", language),
            reply_markup=build_calendar_back_to_dates_keyboard(language),
        )
        return

    total_pages = max(1, (len(events) + CALENDAR_GAMES_PAGE_SIZE - 1) // CALENDAR_GAMES_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * CALENDAR_GAMES_PAGE_SIZE
    page_events = events[start : start + CALENDAR_GAMES_PAGE_SIZE]
    message_text = format_games(
        page_events,
        service.bot_timezone,
        text("calendar_full_title", language, page=page + 1, total_pages=total_pages),
        text("calendar_full_empty", language),
        language,
    )
    await query.edit_message_text(
        message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_calendar_all_games_keyboard(page, total_pages, language),
    )


async def _send_calendar_date_games(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    parts = data.split(":")
    language = _get_query_language(query, context)
    if len(parts) < 3 or not parts[2]:
        await query.edit_message_text(
            text("calendar_invalid_date", language),
            reply_markup=build_calendar_back_to_dates_keyboard(language),
        )
        return

    date_param = parts[2]
    service = _get_service(context)
    try:
        events = await service.get_sofascore_schedule_events_by_date(date_param)
    except Exception:
        logger.exception("Failed to fetch date calendar", extra={"date": date_param})
        await query.edit_message_text(
            text("calendar_date_error", language),
            reply_markup=build_calendar_back_to_dates_keyboard(language),
        )
        return

    message_text = format_games(
        events,
        service.bot_timezone,
        text("calendar_date_title", language, date=_format_date_title(date_param)),
        text("calendar_date_empty", language),
        language,
    )
    await query.edit_message_text(
        message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_calendar_back_to_dates_keyboard(language),
    )


async def _send_calendar_teams_page(
    send_message: Any,
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
    language: str,
) -> None:
    service = _get_service(context)
    try:
        teams = await service.get_sofascore_world_cup_teams()
    except Exception:
        logger.exception("Failed to fetch calendar teams")
        await send_message(text("calendar_teams_error", language))
        return

    total_pages = max(1, (len(teams) + TEAMS_PAGE_SIZE - 1) // TEAMS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    message_text = f"<b>{text('calendar_teams_title', language)}</b>\n{text('page', language, page=page + 1, total_pages=total_pages)}"
    await send_message(
        message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_sofascore_calendar_teams_keyboard(teams, page=page, language=language),
    )


async def _send_calendar_team_games(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    parts = data.split(":")
    language = _get_query_language(query, context)
    if len(parts) < 3 or not parts[2]:
        await query.edit_message_text(text("invalid_team", language))
        return

    team_id = parts[2]
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    service = _get_service(context)
    try:
        teams = await service.get_sofascore_world_cup_teams()
        team = next((item for item in teams if str(item.get("id", "")) == team_id), None)
        events = await service.get_sofascore_schedule_events_by_team(team_id)
    except Exception:
        logger.exception("Failed to fetch team calendar", extra={"team_id": team_id})
        await query.edit_message_text(
            text("calendar_team_error", language),
            reply_markup=build_calendar_back_to_teams_keyboard(page, language),
        )
        return

    team_name = translated_sofascore_team_name(team or {"id": team_id}, language=language)
    message_text = format_games(
        events,
        service.bot_timezone,
        text("calendar_team_title", language, team=team_name),
        text("calendar_team_empty", language),
        language,
    )
    await query.edit_message_text(
        message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_calendar_back_to_teams_keyboard(page, language),
    )


def _parse_calendar_page(data: str) -> int:
    try:
        return int(data.rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        return 0


def _event_date_params(events: list[dict[str, Any]], tz: Any) -> list[str]:
    dates = []
    for event in events:
        event_time = parse_event_datetime(event.get("date", ""), tz)
        if event_time:
            dates.append(event_time.strftime("%Y%m%d"))
    return sorted(set(dates))


def _format_date_title(date_param: str) -> str:
    try:
        date = datetime.strptime(date_param, "%Y%m%d")
    except ValueError:
        return date_param
    return date.strftime("%d/%m/%Y")


async def handle_calendar_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = query.data
    language = _get_query_language(query, context)
    if data == "cal:menu":
        await _send_calendar_menu(query.edit_message_text, language)
    elif data == "cal:dates":
        await _send_calendar_dates(query.edit_message_text, context, language)
    elif data.startswith("cal:all:"):
        await _send_calendar_all_games(query, context, data)
    elif data.startswith("cal:date:"):
        await _send_calendar_date_games(query, context, data)
    elif data.startswith("cal:teams:"):
        await _send_calendar_teams_page(
            query.edit_message_text,
            context,
            page=_parse_calendar_page(data),
            language=language,
        )
    elif data.startswith("cal:team:"):
        await _send_calendar_team_games(query, context, data)
