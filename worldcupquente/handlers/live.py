"""Live and daily match handlers."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TimedOut
from telegram.ext import ContextTypes

from worldcupquente.formatters import (
    format_live_games,
    format_live_games_rich,
    format_match_lineups,
    format_player_detail_caption,
    format_player_match_statistics,
    format_today_games,
    lineup_player_rating,
    split_telegram_message,
)
from worldcupquente.formatters.utils import _find_competitor
from worldcupquente.handlers.utils import (
    _get_chat_language,
    _get_query_language,
    _get_service,
    _log_command,
)
from worldcupquente.i18n import text
from worldcupquente.keyboards import (
    build_live_lineup_keyboard,
    build_live_lineup_picker_keyboard,
    build_live_stats_keyboard,
    build_player_detail_back_keyboard,
)
from worldcupquente.team_translations import translated_sofascore_team_name

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
    data = query.data
    if data == "live:lineup":
        await _send_lineup_entry(query, context)
    elif data.startswith("live:lineup:pick:"):
        event_id = data.rsplit(":", 1)[-1]
        await _send_match_lineups(query, context, event_id, show_subs=False)
    elif data.startswith("live:lineup:view:"):
        parts = data.split(":")
        event_id = parts[3] if len(parts) > 3 else ""
        show_subs = len(parts) > 4 and parts[4] == "1"
        await _send_match_lineups(query, context, event_id, show_subs=show_subs)
    elif data.startswith("live:pl:back:"):
        parts = data.split(":")
        photo_message_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        await _close_player_detail(query, context, photo_message_id)
    elif data.startswith("live:pl:"):
        parts = data.split(":")
        event_id = parts[2] if len(parts) > 2 else ""
        player_id = parts[3] if len(parts) > 3 else ""
        side = parts[4] if len(parts) > 4 else "home"
        await _send_player_detail(query, context, event_id, player_id, side)
    elif data.startswith("live:stats:"):
        await _send_live_games(query, context, show_stats=data.endswith(":show"))
    elif data.startswith("live:ratings:"):
        await _send_live_games(
            query,
            context,
            show_stats=True,
            show_ratings=data.endswith(":show"),
        )


async def _send_lineup_entry(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = _get_service(context)
    language = _get_query_language(query, context)
    try:
        events = await service.get_sofascore_live_events(use_cache=True)
    except Exception:
        logger.exception("Failed to fetch live games")
        await query.edit_message_text(text("live_error_short", language))
        return

    if not events:
        await query.edit_message_text(text("lineup_empty", language))
        return

    if len(events) == 1:
        event_id = str(events[0].get("id") or "")
        await _send_match_lineups(query, context, event_id, show_subs=False)
        return

    matches: list[tuple[str, str]] = []
    for event in events:
        home_team, away_team = _live_event_teams(event)
        matches.append(
            (
                str(event.get("id") or ""),
                f"{_team_plain_name(home_team, language)} x {_team_plain_name(away_team, language)}",
            )
        )
    await query.edit_message_text(
        text("lineup_pick_game", language),
        reply_markup=build_live_lineup_picker_keyboard(matches, language),
    )


async def _send_match_lineups(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    event_id: str,
    *,
    show_subs: bool,
) -> None:
    language = _get_query_language(query, context)
    if not event_id:
        await query.edit_message_text(text("live_error_short", language))
        return

    service = _get_service(context)
    try:
        lineups = await service.get_sofascore_match_lineups(event_id)
        events = await service.get_sofascore_live_events(use_cache=True)
    except Exception:
        logger.exception("Failed to fetch match lineups", extra={"event_id": event_id})
        await query.edit_message_text(text("live_error_short", language))
        return

    home_name, away_name = _event_team_names(events, event_id, language)
    home_players = (lineups.get("home") or {}).get("players") if isinstance(lineups, dict) else None
    away_players = (lineups.get("away") or {}).get("players") if isinstance(lineups, dict) else None
    if not home_players and not away_players:
        await query.edit_message_text(
            text("lineup_empty", language),
            reply_markup=build_live_lineup_picker_keyboard([], language),
        )
        return

    body = format_match_lineups(lineups, home_name, away_name, show_subs=show_subs, language=language)
    prefix = ""
    if lineups.get("confirmed") is False:
        prefix = f"<i>{text('lineup_not_confirmed', language)}</i>\n\n"
    await query.edit_message_text(
        prefix + body,
        parse_mode=ParseMode.HTML,
        reply_markup=build_live_lineup_keyboard(event_id, lineups, show_subs, language),
    )


async def _send_player_detail(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    event_id: str,
    player_id: str,
    side: str,
) -> None:
    if query.message is None:
        return
    language = _get_query_language(query, context)
    if not player_id:
        await query.edit_message_text(text("player_not_found", language))
        return

    service = _get_service(context)
    try:
        lineups, detail, image = await asyncio.gather(
            service.get_sofascore_match_lineups(event_id),
            service.get_sofascore_player_detail(player_id),
            service.get_sofascore_player_image(player_id),
        )
    except Exception:
        logger.exception("Failed to fetch player detail", extra={"player_id": player_id})
        await query.edit_message_text(text("player_not_found", language))
        return

    player_item = _find_lineup_player(lineups, side, player_id)
    rating = lineup_player_rating(player_item) if player_item else None

    if not detail and not player_item:
        await query.edit_message_text(text("player_not_found", language))
        return

    caption = format_player_detail_caption(detail or {}, rating=rating, language=language)
    stats_text = format_player_match_statistics(player_item or {}, language=language)

    photo_message_id = await _send_player_photo(query, image, caption, language)
    back_keyboard = build_player_detail_back_keyboard(photo_message_id or 0, language)
    await query.message.reply_text(
        stats_text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard,
    )


async def _send_player_photo(
    query: Any,
    image: bytes | None,
    caption: str,
    language: str,
) -> int | None:
    if query.message is None:
        return None
    if image:
        try:
            buffer = io.BytesIO(image)
            buffer.name = "player.webp"
            photo_message = await query.message.reply_photo(
                photo=buffer,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
            return _extract_message_id(photo_message)
        except Exception:
            logger.exception("Failed to send player photo")
    await query.message.reply_text(caption, parse_mode=ParseMode.HTML)
    return None


async def _close_player_detail(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    photo_message_id: int,
) -> None:
    if query.message is None:
        return
    chat_id = query.message.chat_id
    try:
        await query.delete_message()
    except Exception:
        logger.debug("Could not delete player stats message", exc_info=True)
    if photo_message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=photo_message_id)
        except Exception:
            logger.debug("Could not delete player photo message", exc_info=True)


def _live_event_teams(event: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors") or []
    home = _find_competitor(competitors, "home") or {}
    away = _find_competitor(competitors, "away") or {}
    return home.get("team") or {}, away.get("team") or {}


def _event_team_names(
    events: list[dict[str, Any]],
    event_id: str,
    language: str,
) -> tuple[str, str]:
    for event in events:
        if str(event.get("id") or "") == str(event_id):
            home_team, away_team = _live_event_teams(event)
            return _team_plain_name(home_team, language), _team_plain_name(away_team, language)
    return "", ""


def _team_plain_name(team: dict[str, Any], language: str) -> str:
    name = translated_sofascore_team_name(team, include_emoji=False, language=language)
    return name or str(team.get("displayName") or team.get("name") or "")


def _find_lineup_player(lineups: Any, side: str, player_id: str) -> dict[str, Any] | None:
    if not isinstance(lineups, dict):
        return None
    if side in ("home", "away"):
        order = (side, "away" if side == "home" else "home")
    else:
        order = ("home", "away")
    for side_key in order:
        players = (lineups.get(side_key) or {}).get("players") or []
        for item in players:
            player = item.get("player") or {}
            if str(player.get("id") or "") == str(player_id):
                return item
    return None


def _extract_message_id(message: Any) -> int | None:
    message_id = getattr(message, "message_id", None)
    if isinstance(message_id, int):
        return message_id
    return None


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
