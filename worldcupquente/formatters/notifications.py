"""Event notifications and alert formatters."""

from __future__ import annotations

from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.formatters.games import _format_live_event
from worldcupquente.formatters.standings import format_standings_group_table
from worldcupquente.formatters.utils import (
    RED_CARD_EMOJI,
    _find_competitor,
    _find_team_by_id,
    _format_matchup,
)
from worldcupquente.team_translations import translated_team_name_html


def format_match_status_notification(event: dict[str, Any], tz: ZoneInfo) -> str:
    return "\n".join(_format_live_event(event, tz, show_stats=False))


def format_full_time_notification_rich(
    event: dict[str, Any],
    tz: ZoneInfo,
    group: dict[str, Any] | None,
) -> str:
    blocks = [_rich_paragraph(_format_live_event(event, tz, show_stats=False))]
    if group is not None:
        blocks.append(format_standings_group_table(group))
    return "".join(blocks)


def _rich_paragraph(lines: list[str]) -> str:
    return f"<p>{'<br/>'.join(line for line in lines if line)}</p>"


def format_goal_notification(event: dict[str, Any], detail: dict[str, Any]) -> str:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    athletes = detail.get("athletesInvolved") or [
        participant.get("athlete") or {}
        for participant in detail.get("participants", [])
        if participant.get("athlete")
    ]
    athlete = (athletes or [{}])[0]
    scorer = athlete.get("displayName") or athlete.get("fullName") or "Autor indisponível"
    minute = (detail.get("clock") or {}).get("displayValue") or "minuto indisponível"

    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    status = competition.get("status") or event.get("status") or {}
    state = (status.get("type") or {}).get("state", "in")

    header = "⚽️ <b>GOL CONTRA!</b>" if detail.get("ownGoal") else "⚽️ <b>GOL!</b>"

    lines = [
        header,
        f"👤 {escape(str(scorer))} ({escape(str(minute))})",
        "",
        _format_matchup(home, away, str(state)),
    ]
    return "\n".join(lines)


def format_penalty_notification(event: dict[str, Any], detail: dict[str, Any]) -> str:
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
    minute = (detail.get("clock") or {}).get("displayValue") or "minuto indisponível"
    description = detail.get("text") or (detail.get("type") or {}).get("text") or "Pênalti"

    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    status = competition.get("status") or event.get("status") or {}
    state = (status.get("type") or {}).get("state", "in")

    lines = [
        "<b>Pênalti na Copa do Mundo!</b>",
        f"Minuto: <b>{escape(str(minute))}</b>",
        f"Seleção: <b>{translated_team_name_html(team)}</b>",
    ]
    if player:
        lines.append(f"Jogador: <b>{escape(str(player))}</b>")
    lines.extend(
        [
            f"Lance: {escape(str(description))}",
            "",
            _format_matchup(home, away, str(state)),
        ]
    )
    return "\n".join(lines)


def format_red_card_notification(event: dict[str, Any], detail: dict[str, Any]) -> str:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    team = _find_team_by_id(competitors, str((detail.get("team") or {}).get("id", "")))
    athlete = detail.get("athlete") or {}
    player = athlete.get("displayName") or athlete.get("fullName") or "Jogador indisponível"
    minute = (detail.get("clock") or {}).get("displayValue") or "minuto indisponível"
    description = detail.get("text") or (detail.get("type") or {}).get("text") or "Cartão vermelho"

    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    status = competition.get("status") or event.get("status") or {}
    state = (status.get("type") or {}).get("state", "in")

    lines = [
        f"<b>{RED_CARD_EMOJI} Cartão vermelho na Copa do Mundo!</b>",
        f"Minuto: <b>{escape(str(minute))}</b>",
        f"Jogador: <b>{escape(str(player))}</b>",
        f"Seleção: <b>{translated_team_name_html(team)}</b>",
        f"Lance: {escape(str(description))}",
        "",
        _format_matchup(home, away, str(state)),
    ]
    return "\n".join(lines)
