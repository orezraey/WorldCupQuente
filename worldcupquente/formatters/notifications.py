"""Event notifications and alert formatters."""

from __future__ import annotations

from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.espn_events import parse_espn_datetime
from worldcupquente.formatters.games import _format_live_event
from worldcupquente.formatters.standings import format_standings_group_table
from worldcupquente.formatters.utils import (
    RED_CARD_EMOJI,
    _find_competitor,
    _find_team_by_id,
    _format_matchup,
)
from worldcupquente.i18n import text
from worldcupquente.team_translations import translated_team_name_html


def format_match_status_notification(event: dict[str, Any], tz: ZoneInfo, language: str = "en") -> str:
    return "\n".join(_format_live_event(event, tz, show_stats=False, language=language))


def format_pre_game_notification(event: dict[str, Any], tz: ZoneInfo, language: str = "en") -> str:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    event_time = parse_espn_datetime(event.get("date", ""), tz)
    venue = competition.get("venue", {}) or event.get("venue", {})
    venue_name = venue.get("fullName") or venue.get("displayName")

    lines = [
        f"<b>⏰ {text('pre_game_header', language)}</b>",
        "",
        f"⚽️ {_format_matchup(home, away, 'pre', language)}",
    ]
    if event_time:
        lines.append(f"🕒 {escape(event_time.strftime('%d/%m %H:%M'))}")
    if venue_name:
        lines.append(f"🏟 {text('stadium', language)}: {escape(str(venue_name))}")
    return "\n".join(lines)


def format_full_time_notification_rich(
    event: dict[str, Any],
    tz: ZoneInfo,
    group: dict[str, Any] | None,
    language: str = "en",
) -> str:
    blocks = [_rich_paragraph(_format_live_event(event, tz, show_stats=False, language=language))]
    if group is not None:
        blocks.append(format_standings_group_table(group, language))
    return "".join(blocks)


def _rich_paragraph(lines: list[str]) -> str:
    return f"<p>{'<br/>'.join(line for line in lines if line is not None)}</p>"


def format_goal_notification(
    event: dict[str, Any],
    detail: dict[str, Any],
    language: str = "en",
) -> str:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    athletes = detail.get("athletesInvolved") or [
        participant.get("athlete") or {}
        for participant in detail.get("participants", [])
        if participant.get("athlete")
    ]
    athlete = (athletes or [{}])[0]
    scorer = athlete.get("displayName") or athlete.get("fullName") or text("scorer_unavailable", language)
    minute = (detail.get("clock") or {}).get("displayValue") or text("minute_unavailable", language)

    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    status = competition.get("status") or event.get("status") or {}
    state = (status.get("type") or {}).get("state", "in")

    header_key = "own_goal_header" if detail.get("ownGoal") else "goal_header"
    header = f"⚽️ <b>{text(header_key, language)}</b>"

    lines = [
        header,
        f"👤 {escape(str(scorer))} ({escape(str(minute))})",
        "",
        _format_matchup(home, away, str(state), language),
    ]
    return "\n".join(lines)


def format_penalty_notification(
    event: dict[str, Any],
    detail: dict[str, Any],
    language: str = "en",
) -> str:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    team = _find_team_by_id(competitors, str((detail.get("team") or {}).get("id", "")))
    athletes = detail.get("athletesInvolved") or [
        participant.get("athlete") or {}
        for participant in detail.get("participants", [])
        if participant.get("athlete")
    ]
    athlete = (athletes or [{}])[0]
    player = athlete.get("displayName") or athlete.get("fullName")
    minute = (detail.get("clock") or {}).get("displayValue") or text("minute_unavailable", language)
    description = detail.get("text") or (detail.get("type") or {}).get("text") or text("notification_penalty", language)

    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    status = competition.get("status") or event.get("status") or {}
    state = (status.get("type") or {}).get("state", "in")

    lines = [
        f"<b>{text('penalty_header', language)}</b>",
        f"{text('minute', language)}: <b>{escape(str(minute))}</b>",
        f"{text('team_label', language)}: <b>{translated_team_name_html(team, language=language)}</b>",
    ]
    if player:
        lines.append(f"{text('player', language)}: <b>{escape(str(player))}</b>")
    lines.extend(
        [
            f"{text('play', language)}: {escape(str(description))}",
            "",
            _format_matchup(home, away, str(state), language),
        ]
    )
    return "\n".join(lines)


def format_red_card_notification(
    event: dict[str, Any],
    detail: dict[str, Any],
    language: str = "en",
) -> str:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    team = _find_team_by_id(competitors, str((detail.get("team") or {}).get("id", "")))
    athlete = detail.get("athlete") or {}
    player = athlete.get("displayName") or athlete.get("fullName") or text("player_unavailable", language)
    minute = (detail.get("clock") or {}).get("displayValue") or text("minute_unavailable", language)
    description = detail.get("text") or (detail.get("type") or {}).get("text") or text("red_card_description", language)

    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    status = competition.get("status") or event.get("status") or {}
    state = (status.get("type") or {}).get("state", "in")

    lines = [
        f"<b>{RED_CARD_EMOJI} {text('red_card_header', language)}</b>",
        f"{text('minute', language)}: <b>{escape(str(minute))}</b>",
        f"{text('player', language)}: <b>{escape(str(player))}</b>",
        f"{text('team_label', language)}: <b>{translated_team_name_html(team, language=language)}</b>",
        f"{text('play', language)}: {escape(str(description))}",
        "",
        _format_matchup(home, away, str(state), language),
    ]
    return "\n".join(lines)
