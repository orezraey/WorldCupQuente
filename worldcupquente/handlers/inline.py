"""Telegram inline mode handler for team search and quick actions.

Inline flow:
  @bot <team name>  ->  one :class:`InlineQueryResultArticle` per matching team.
  Selecting an article sends a message via the bot with a 4-button keyboard
  (Past matches / Next matches / Players / Group). Tapping a button edits the
  inline message with the requested content.

The data layer (``WorldCupService``) and presentation layer (``formatters``)
are reused directly; only the inline wiring and the plain-HTML standings variant
are new.
"""

from __future__ import annotations

import logging
from typing import Any

from telegram import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.formatters import (
    format_player_detail_caption,
    format_sofascore_team_events,
    format_sofascore_team_menu,
    format_standings_group_plain,
    format_standings_group_table,
)
from worldcupquente.handlers.utils import (
    _get_inline_callback_language,
    _get_inline_query_language,
    _get_service,
)
from worldcupquente.i18n import text
from worldcupquente.keyboards import (
    build_inline_back_keyboard,
    build_inline_groups_list_keyboard,
    build_inline_player_back_keyboard,
    build_inline_squad_keyboard,
    build_inline_team_menu_keyboard,
)
from worldcupquente.team_translations import (
    filter_teams_by_name,
    translated_sofascore_team_name,
    translated_sofascore_team_name_html,
)

logger = logging.getLogger(__name__)

INLINE_CACHE_SECONDS = 30
INLINE_RESULTS_LIMIT = 25


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answer an inline query with matching World Cup teams."""
    inline_query = update.inline_query
    if inline_query is None:
        return
    language = _get_inline_query_language(update)
    query_text = (inline_query.query or "").strip()

    service = _get_service(context)
    try:
        teams = await service.get_sofascore_world_cup_teams()
    except Exception:
        logger.exception("Failed to fetch World Cup teams for inline query")
        teams = []

    if query_text:
        matched = filter_teams_by_name(teams, query_text, limit=INLINE_RESULTS_LIMIT)
    else:
        matched = _sorted_teams_for_browse(teams, language)[:INLINE_RESULTS_LIMIT]

    results = [
        _build_team_article(team, language) for team in matched if team.get("id") is not None
    ]
    if not results:
        results = [_build_no_results_article(language)]

    try:
        await inline_query.answer(
            results,
            cache_time=INLINE_CACHE_SECONDS,
            is_personal=True,
        )
    except Exception:
        logger.exception("Failed to answer inline query")


async def handle_inline_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route ``inl:`` callback queries from inline (via-bot) messages."""
    data = getattr(query, "data", None)
    if not data:
        return
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "menu":
        await _inline_menu(query, context, parts)
    elif action == "last":
        await _inline_team_events(query, context, parts, "last")
    elif action == "next":
        await _inline_team_events(query, context, parts, "next")
    elif action == "players":
        await _inline_players(query, context, parts)
    elif action == "player":
        await _inline_player_detail(query, context, parts)
    elif action == "group":
        await _inline_group(query, context, parts)
    elif action == "groupopen":
        await _inline_group_open(query, context, parts)
    else:
        language = _get_inline_callback_language(query)
        await query.edit_message_text(text("invalid_team", language))


def _build_team_article(team: dict[str, Any], language: str) -> InlineQueryResultArticle:
    team_id = str(team.get("id"))
    title = translated_sofascore_team_name(team, language=language)
    content = format_sofascore_team_menu({"team": team}, language)
    return InlineQueryResultArticle(
        id=team_id,
        title=title,
        description=_team_article_description(team, language),
        input_message_content=InputTextMessageContent(
            message_text=content,
            parse_mode=ParseMode.HTML,
        ),
        reply_markup=build_inline_team_menu_keyboard(team_id, language),
    )


def _build_no_results_article(language: str) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id="inline-no-results",
        title=text("inline_no_results", language),
        input_message_content=InputTextMessageContent(
            message_text=text("inline_no_results", language),
        ),
    )


def _team_article_description(team: dict[str, Any], language: str) -> str:
    other_language = "en" if language == "pt" else "pt"
    other_name = translated_sofascore_team_name(team, include_emoji=False, language=other_language)
    current_name = translated_sofascore_team_name(team, include_emoji=False, language=language)
    if other_name and other_name != current_name:
        return other_name
    return text("bot_title", language)


def _sorted_teams_for_browse(teams: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    return sorted(
        teams,
        key=lambda team: translated_sofascore_team_name(team, include_emoji=False, language=language),
    )


def _team_id_from_parts(parts: list[str], index: int = 2) -> str:
    return parts[index] if len(parts) > index else ""


async def _inline_menu(query: Any, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    team_id = _team_id_from_parts(parts)
    language = _get_inline_callback_language(query)
    if not team_id:
        await query.edit_message_text(text("invalid_team", language))
        return

    service = _get_service(context)
    try:
        profile = await service.get_sofascore_team_profile(team_id)
    except Exception:
        logger.exception("Failed to fetch team profile for inline menu", extra={"team_id": team_id})
        profile = None

    content = format_sofascore_team_menu(profile or {"id": team_id}, language)
    await query.edit_message_text(
        content,
        parse_mode=ParseMode.HTML,
        reply_markup=build_inline_team_menu_keyboard(team_id, language),
    )


async def _inline_team_events(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    parts: list[str],
    direction: str,
) -> None:
    team_id = _team_id_from_parts(parts)
    language = _get_inline_callback_language(query)
    if not team_id:
        await query.edit_message_text(text("invalid_team", language))
        return

    service = _get_service(context)
    try:
        profile = await service.get_sofascore_team_profile(team_id)
        events = await service.get_sofascore_team_events(team_id, direction)
    except Exception:
        logger.exception(
            "Failed to fetch team events for inline",
            extra={"team_id": team_id, "direction": direction},
        )
        await query.edit_message_text(
            text("team_games_error", language),
            parse_mode=ParseMode.HTML,
            reply_markup=build_inline_back_keyboard(team_id, language),
        )
        return

    title_key = "team_last_games" if direction == "last" else "team_next_games"
    empty_key = "team_last_games_empty" if direction == "last" else "team_next_games_empty"
    content = format_sofascore_team_events(
        events,
        (profile or {}).get("team") or {"id": team_id},
        service.bot_timezone,
        text(title_key, language),
        text(empty_key, language),
        language,
        newest_first=direction == "last",
    )
    await query.edit_message_text(
        content,
        parse_mode=ParseMode.HTML,
        reply_markup=build_inline_back_keyboard(team_id, language),
    )


async def _inline_players(query: Any, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    team_id = _team_id_from_parts(parts)
    language = _get_inline_callback_language(query)
    if not team_id:
        await query.edit_message_text(text("invalid_team", language))
        return

    service = _get_service(context)
    try:
        profile = await service.get_sofascore_team_profile(team_id)
        players = await service.get_sofascore_team_players(team_id)
    except Exception:
        logger.exception("Failed to fetch team players for inline", extra={"team_id": team_id})
        await query.edit_message_text(
            text("roster_error", language),
            parse_mode=ParseMode.HTML,
            reply_markup=build_inline_back_keyboard(team_id, language),
        )
        return

    team = (profile or {}).get("team") or {"id": team_id}
    name_html = translated_sofascore_team_name_html(team, language=language)
    if not players:
        await query.edit_message_text(
            f"<b>{name_html}</b>\n{text('roster_empty', language)}",
            parse_mode=ParseMode.HTML,
            reply_markup=build_inline_back_keyboard(team_id, language),
        )
        return

    header = f"<b>{name_html}</b>\n<b>{text('roster_title', language)}</b>"
    await query.edit_message_text(
        header,
        parse_mode=ParseMode.HTML,
        reply_markup=build_inline_squad_keyboard(team_id, players, language),
    )


async def _inline_player_detail(query: Any, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    team_id = _team_id_from_parts(parts)
    player_id = parts[3] if len(parts) > 3 else ""
    language = _get_inline_callback_language(query)
    if not team_id or not player_id:
        await query.edit_message_text(text("invalid_team", language))
        return

    service = _get_service(context)
    try:
        detail = await service.get_sofascore_player_detail(player_id)
    except Exception:
        logger.exception("Failed to fetch player detail for inline", extra={"player_id": player_id})
        await query.edit_message_text(
            text("player_not_found", language),
            parse_mode=ParseMode.HTML,
            reply_markup=build_inline_player_back_keyboard(team_id, language),
        )
        return

    caption = format_player_detail_caption(detail or {}, rating=None, language=language)
    await query.edit_message_text(
        caption,
        parse_mode=ParseMode.HTML,
        reply_markup=build_inline_player_back_keyboard(team_id, language),
    )


async def _inline_group(query: Any, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    team_id = _team_id_from_parts(parts)
    language = _get_inline_callback_language(query)
    if not team_id:
        await query.edit_message_text(text("invalid_team", language))
        return

    service = _get_service(context)
    try:
        groups = await service.get_sofascore_standings_groups()
    except Exception:
        logger.exception("Failed to fetch standings groups for inline")
        await query.edit_message_text(
            text("team_games_error", language),
            parse_mode=ParseMode.HTML,
            reply_markup=build_inline_back_keyboard(team_id, language),
        )
        return

    match = _find_team_group(groups, team_id)
    if match is not None:
        await _edit_inline_standings(
            query, context, match, language, build_inline_back_keyboard(team_id, language)
        )
        return

    await query.edit_message_text(
        text("inline_pick_group", language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_inline_groups_list_keyboard(team_id, groups, language),
    )


async def _inline_group_open(query: Any, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    team_id = _team_id_from_parts(parts)
    group_id = parts[3] if len(parts) > 3 else ""
    language = _get_inline_callback_language(query)
    if not team_id or not group_id:
        await query.edit_message_text(text("invalid_team", language))
        return

    service = _get_service(context)
    try:
        group = await service.get_sofascore_standings_group(group_id)
    except Exception:
        logger.exception("Failed to fetch standings group for inline", extra={"group_id": group_id})
        group = None

    if not group:
        await query.edit_message_text(
            text("standings_empty_group", language),
            parse_mode=ParseMode.HTML,
            reply_markup=build_inline_back_keyboard(team_id, language),
        )
        return

    await _edit_inline_standings(
        query, context, group, language, build_inline_back_keyboard(team_id, language)
    )


async def _edit_inline_standings(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    group: dict[str, Any],
    language: str,
    reply_markup: Any,
) -> None:
    """Render a standings group as a rich table on an inline message.

    Uses the same rich-message path as ``/standings`` via ``inline_message_id``.
    Falls back to the plain-HTML variant if the rich call is unavailable.
    """
    inline_message_id = getattr(query, "inline_message_id", None)
    if inline_message_id:
        try:
            await context.bot.do_api_request(
                "editMessageText",
                api_kwargs={
                    "inline_message_id": inline_message_id,
                    "rich_message": {
                        "html": format_standings_group_table(group, language),
                        "skip_entity_detection": True,
                    },
                    "reply_markup": reply_markup,
                },
            )
            return
        except Exception:
            logger.exception("Rich inline standings failed; falling back to plain text")

    await query.edit_message_text(
        format_standings_group_plain(group, language),
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
    )


def _find_team_group(groups: list[dict[str, Any]], team_id: str) -> dict[str, Any] | None:
    for group in groups:
        entries = (group.get("standings") or {}).get("entries") or []
        for entry in entries:
            entry_team_id = str((entry.get("team") or {}).get("id") or "")
            if entry_team_id and entry_team_id == team_id:
                return group
    return None
