"""Calendar and fixture navigation handlers."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.espn_events import parse_espn_datetime
from worldcupquente.formatters import format_games
from worldcupquente.handlers.utils import _get_service, _log_command
from worldcupquente.keyboards import (
    CALENDAR_GAMES_PAGE_SIZE,
    TEAMS_PAGE_SIZE,
    build_calendar_all_games_keyboard,
    build_calendar_back_to_dates_keyboard,
    build_calendar_back_to_teams_keyboard,
    build_calendar_dates_keyboard,
    build_calendar_menu_keyboard,
    build_calendar_teams_keyboard,
)
from worldcupquente.team_translations import translated_team_name

logger = logging.getLogger(__name__)


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "calendario")
    message = update.effective_message
    if message is None:
        return
    await _send_calendar_menu(message.reply_text)


async def _send_calendar_menu(send_message: Any) -> None:
    text = "<b>Calendário da Copa 2026</b>\nEscolha como deseja navegar pelos jogos."
    await send_message(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_calendar_menu_keyboard(),
    )


async def _send_calendar_dates(send_message: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = _get_service(context)
    try:
        events = await service.get_schedule_events()
    except Exception:
        logger.exception("Failed to fetch calendar dates")
        await send_message("Não consegui buscar as datas do calendário agora.")
        return

    dates = _event_date_params(events, service.bot_timezone)
    text = "<b>Calendário por datas</b>\nEscolha uma data para ver os jogos."
    await send_message(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_calendar_dates_keyboard(dates),
    )


async def _send_calendar_all_games(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    service = _get_service(context)
    page = _parse_calendar_page(data)
    try:
        events = sorted(await service.get_schedule_events(), key=lambda event: event.get("date", ""))
    except Exception:
        logger.exception("Failed to fetch full calendar")
        await query.edit_message_text(
            "Não consegui buscar o calendário completo agora.",
            reply_markup=build_calendar_back_to_dates_keyboard(),
        )
        return

    total_pages = max(1, (len(events) + CALENDAR_GAMES_PAGE_SIZE - 1) // CALENDAR_GAMES_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * CALENDAR_GAMES_PAGE_SIZE
    page_events = events[start : start + CALENDAR_GAMES_PAGE_SIZE]
    text = format_games(
        page_events,
        service.bot_timezone,
        f"Calendário completo - Página {page + 1}/{total_pages}",
        "Nenhum jogo encontrado no calendário.",
    )
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_calendar_all_games_keyboard(page, total_pages),
    )


async def _send_calendar_date_games(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    parts = data.split(":")
    if len(parts) < 3 or not parts[2]:
        await query.edit_message_text("Data inválida.", reply_markup=build_calendar_back_to_dates_keyboard())
        return

    date_param = parts[2]
    service = _get_service(context)
    try:
        events = await service.get_schedule_events_by_date(date_param)
    except Exception:
        logger.exception("Failed to fetch date calendar", extra={"date": date_param})
        await query.edit_message_text(
            "Não consegui buscar os jogos desta data agora.",
            reply_markup=build_calendar_back_to_dates_keyboard(),
        )
        return

    text = format_games(
        events,
        service.bot_timezone,
        f"Jogos de {_format_date_title(date_param)}",
        "Nenhum jogo encontrado nesta data.",
    )
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_calendar_back_to_dates_keyboard(),
    )


async def _send_calendar_teams_page(
    send_message: Any,
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
) -> None:
    service = _get_service(context)
    try:
        teams = await service.get_teams()
    except Exception:
        logger.exception("Failed to fetch calendar teams")
        await send_message("Não consegui buscar a lista de seleções agora.")
        return

    total_pages = max(1, (len(teams) + TEAMS_PAGE_SIZE - 1) // TEAMS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    text = f"<b>Calendário por seleções</b>\nPágina {page + 1}/{total_pages}"
    await send_message(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_calendar_teams_keyboard(teams, page=page),
    )


async def _send_calendar_team_games(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    parts = data.split(":")
    if len(parts) < 3 or not parts[2]:
        await query.edit_message_text("Seleção inválida.")
        return

    team_id = parts[2]
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    service = _get_service(context)
    try:
        teams = await service.get_teams()
        team = next((item for item in teams if str(item.get("id", "")) == team_id), None)
        events = await service.get_schedule_events_by_team(team_id)
    except Exception:
        logger.exception("Failed to fetch team calendar", extra={"team_id": team_id})
        await query.edit_message_text(
            "Não consegui buscar os jogos desta seleção agora.",
            reply_markup=build_calendar_back_to_teams_keyboard(page),
        )
        return

    team_name = translated_team_name(team or {"id": team_id})
    text = format_games(
        events,
        service.bot_timezone,
        f"Jogos de {team_name}",
        "Nenhum jogo encontrado para esta seleção.",
    )
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_calendar_back_to_teams_keyboard(page),
    )


def _parse_calendar_page(data: str) -> int:
    try:
        return int(data.rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        return 0


def _event_date_params(events: list[dict[str, Any]], tz: Any) -> list[str]:
    dates = []
    for event in events:
        event_time = parse_espn_datetime(event.get("date", ""), tz)
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
    if data == "cal:menu":
        await _send_calendar_menu(query.edit_message_text)
    elif data == "cal:dates":
        await _send_calendar_dates(query.edit_message_text, context)
    elif data.startswith("cal:all:"):
        await _send_calendar_all_games(query, context, data)
    elif data.startswith("cal:date:"):
        await _send_calendar_date_games(query, context, data)
    elif data.startswith("cal:teams:"):
        await _send_calendar_teams_page(
            query.edit_message_text,
            context,
            page=_parse_calendar_page(data),
        )
    elif data.startswith("cal:team:"):
        await _send_calendar_team_games(query, context, data)
