"""Team squad and roster handlers."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.formatters import (
    format_sofascore_team_achievements,
    format_sofascore_team_events,
    format_sofascore_team_menu,
    format_sofascore_team_players,
    format_sofascore_team_statistics,
    split_telegram_message,
)
from worldcupquente.handlers.utils import (
    _get_chat_language,
    _get_notification_preferences,
    _get_query_language,
    _get_service,
    _log_command,
)
from worldcupquente.i18n import text
from worldcupquente.keyboards import (
    TEAMS_PAGE_SIZE,
    build_back_to_teams_keyboard,
    build_sofascore_team_back_keyboard,
    build_sofascore_team_menu_keyboard,
    build_sofascore_teams_keyboard,
)
from worldcupquente.notification_preferences import TEAM_SCOPE_FOLLOWED

logger = logging.getLogger(__name__)


async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "selecoes")
    message = update.effective_message
    if message is None:
        return
    await _send_teams_page(message.reply_text, context, page=0, language=_get_chat_language(update, context))


async def _send_teams_page(
    send_message: Any,
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
    language: str,
) -> None:
    service = _get_service(context)
    try:
        teams = await service.get_sofascore_world_cup_teams()
    except Exception:
        logger.exception("Failed to fetch teams")
        await send_message(text("teams_error", language))
        return

    total_pages = max(1, (len(teams) + TEAMS_PAGE_SIZE - 1) // TEAMS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    message_text = f"<b>{text('teams_title', language)}</b>\n{text('page', language, page=page + 1, total_pages=total_pages)}"
    await send_message(
        message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_sofascore_teams_keyboard(teams, page=page, language=language),
    )


async def _send_team_menu(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    team_id, page = _parse_team_action(data)
    language = _get_query_language(query, context)
    if not team_id:
        await query.edit_message_text(text("invalid_team", language))
        return

    service = _get_service(context)
    try:
        profile = await service.get_sofascore_team_profile(team_id)
    except Exception:
        logger.exception("Failed to fetch SofaScore team profile", extra={"team_id": team_id})
        await query.edit_message_text(text("team_profile_error", language), reply_markup=build_back_to_teams_keyboard(page, language))
        return

    profile_data = profile or {"id": team_id}
    preferences = _get_notification_preferences(context)
    chat_id = _query_chat_id(query)
    show_notifications = chat_id is not None and preferences.get_team_scope(chat_id) == TEAM_SCOPE_FOLLOWED

    await query.edit_message_text(
        format_sofascore_team_menu(profile_data, language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_sofascore_team_menu_keyboard(
            team_id,
            page,
            language,
            show_notifications_button=show_notifications,
            is_following=bool(chat_id is not None and preferences.is_following_team(chat_id, team_id)),
        ),
    )


async def _send_team_players(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    team_id, page = _parse_team_action(data)
    language = _get_query_language(query, context)
    if not team_id:
        await query.edit_message_text(text("invalid_team", language))
        return

    service = _get_service(context)
    await query.edit_message_text(text("searching_roster", language))
    try:
        profile = await service.get_sofascore_team_profile(team_id)
        players = await service.get_sofascore_team_players(team_id)
        chunks = split_telegram_message(format_sofascore_team_players(players, profile.get("team") or {"id": team_id}, language))
    except Exception:
        logger.exception("Failed to fetch SofaScore team players", extra={"team_id": team_id})
        await query.edit_message_text(
            text("roster_error", language),
            reply_markup=build_sofascore_team_back_keyboard(team_id, page, language),
        )
        return

    await query.edit_message_text(
        chunks[0],
        parse_mode=ParseMode.HTML,
        reply_markup=build_sofascore_team_back_keyboard(team_id, page, language),
    )
    if query.message is None:
        return
    for chunk in chunks[1:]:
        await query.message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def _send_team_events(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str, direction: str) -> None:
    team_id, page = _parse_team_action(data)
    language = _get_query_language(query, context)
    if not team_id:
        await query.edit_message_text(text("invalid_team", language))
        return

    service = _get_service(context)
    try:
        profile = await service.get_sofascore_team_profile(team_id)
        events = await service.get_sofascore_team_events(team_id, direction)
    except Exception:
        logger.exception("Failed to fetch SofaScore team events", extra={"team_id": team_id, "direction": direction})
        await query.edit_message_text(
            text("team_games_error", language),
            reply_markup=build_sofascore_team_back_keyboard(team_id, page, language),
        )
        return

    title_key = "team_last_games" if direction == "last" else "team_next_games"
    empty_key = "team_last_games_empty" if direction == "last" else "team_next_games_empty"
    await query.edit_message_text(
        format_sofascore_team_events(
            events,
            profile.get("team") or {"id": team_id},
            service.bot_timezone,
            text(title_key, language),
            text(empty_key, language),
            language,
            newest_first=direction == "last",
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=build_sofascore_team_back_keyboard(team_id, page, language),
    )


async def _send_team_stats(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    team_id, page = _parse_team_action(data)
    language = _get_query_language(query, context)
    if not team_id:
        await query.edit_message_text(text("invalid_team", language))
        return

    service = _get_service(context)
    try:
        profile = await service.get_sofascore_team_profile(team_id)
        summary = await service.get_sofascore_team_statistics_summary(team_id)
    except Exception:
        logger.exception("Failed to fetch SofaScore team statistics", extra={"team_id": team_id})
        await query.edit_message_text(
            text("team_stats_error", language),
            reply_markup=build_sofascore_team_back_keyboard(team_id, page, language),
        )
        return

    await query.edit_message_text(
        format_sofascore_team_statistics(summary, profile.get("team") or {"id": team_id}, language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_sofascore_team_back_keyboard(team_id, page, language),
    )


async def _send_team_titles(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    team_id, page = _parse_team_action(data)
    language = _get_query_language(query, context)
    if not team_id:
        await query.edit_message_text(text("invalid_team", language))
        return

    service = _get_service(context)
    try:
        profile = await service.get_sofascore_team_profile(team_id)
        achievements = await service.get_sofascore_team_achievements(team_id)
    except Exception:
        logger.exception("Failed to fetch SofaScore team achievements", extra={"team_id": team_id})
        await query.edit_message_text(
            text("team_titles_error", language),
            reply_markup=build_sofascore_team_back_keyboard(team_id, page, language),
        )
        return

    await query.edit_message_text(
        format_sofascore_team_achievements(achievements, profile.get("team") or {"id": team_id}, language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_sofascore_team_back_keyboard(team_id, page, language),
    )


async def _toggle_team_notifications(query: Any, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    if query.message is None:
        return
    parts = data.split(":")
    language = _get_query_language(query, context)
    if len(parts) < 3 or not parts[2]:
        await query.edit_message_text(text("invalid_team", language))
        return

    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    sofascore_team_id = parts[4] if len(parts) > 4 and parts[4] else parts[2]
    preferences = _get_notification_preferences(context)
    preferences.toggle_followed_team(query.message.chat_id, sofascore_team_id)
    if len(parts) > 4:
        await query.edit_message_reply_markup(
            reply_markup=build_sofascore_team_menu_keyboard(
                sofascore_team_id,
                page,
                language,
                show_notifications_button=True,
                is_following=preferences.is_following_team(query.message.chat_id, sofascore_team_id),
            )
        )
        return
    await query.edit_message_reply_markup(
        reply_markup=_build_team_roster_keyboard(query, context, sofascore_team_id, page, language)
    )


def _build_team_roster_keyboard(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    team_id: str,
    page: int,
    language: str,
) -> Any:
    chat_id = getattr(getattr(query, "message", None), "chat_id", None)
    if chat_id is None:
        return build_back_to_teams_keyboard(page, language)

    preferences = _get_notification_preferences(context)
    show_notifications_button = preferences.get_team_scope(chat_id) == TEAM_SCOPE_FOLLOWED
    return build_back_to_teams_keyboard(
        page,
        language,
        team_id=team_id,
        show_notifications_button=show_notifications_button,
        is_following=preferences.is_following_team(chat_id, team_id),
    )


def _query_chat_id(query: Any) -> int | None:
    chat_id = getattr(getattr(query, "message", None), "chat_id", None)
    return chat_id if isinstance(chat_id, int) else None


def _parse_page(data: str) -> int:
    try:
        return int(data.split(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        return 0


def _parse_team_action(data: str) -> tuple[str, int]:
    parts = data.split(":")
    if len(parts) >= 4:
        return parts[2], int(parts[3]) if parts[3].isdigit() else 0
    if len(parts) >= 3:
        return parts[1], int(parts[2]) if parts[2].isdigit() else 0
    return "", 0


async def handle_teams_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.data.startswith("team:notify:"):
        await _toggle_team_notifications(query, context, query.data)
    elif query.data.startswith("teams:"):
        await _send_teams_page(
            query.edit_message_text,
            context,
            page=_parse_page(query.data),
            language=_get_query_language(query, context),
        )
    elif query.data.startswith("team:menu:"):
        await _send_team_menu(query, context, query.data)
    elif query.data.startswith("team:players:"):
        await _send_team_players(query, context, query.data)
    elif query.data.startswith("team:last:"):
        await _send_team_events(query, context, query.data, "last")
    elif query.data.startswith("team:next:"):
        await _send_team_events(query, context, query.data, "next")
    elif query.data.startswith("team:stats:"):
        await _send_team_stats(query, context, query.data)
    elif query.data.startswith("team:titles:"):
        await _send_team_titles(query, context, query.data)
    elif query.data.startswith("team:"):
        await _send_team_menu(query, context, query.data)
