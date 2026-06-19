"""Roster and coaching staff formatters."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.i18n import text
from worldcupquente.team_translations import (
    translated_sofascore_team_name_html,
)


def format_sofascore_team_menu(profile_data: dict[str, Any], language: str = "en") -> str:
    team = profile_data.get("team") or profile_data
    if not isinstance(team, dict):
        team = {}

    lines = [f"<b>{_sofascore_team_name_html(team, language)}</b>", text("team_menu_body", language)]
    details = [
        (text("team_code", language), team.get("nameCode")),
        (text("team_ranking", language), team.get("ranking")),
        (text("team_followers", language), _format_number(team.get("userCount"))),
        (text("team_current_tournament", language), ((team.get("tournament") or {}).get("name"))),
        (text("team_main_tournament", language), ((team.get("primaryUniqueTournament") or {}).get("name"))),
    ]
    for label, value in details:
        if value not in (None, ""):
            lines.append(f"{escape(str(label))}: {escape(str(value))}")
    return "\n".join(lines)


def format_sofascore_team_players(
    players_data: list[dict[str, Any]],
    team: dict[str, Any],
    language: str = "en",
) -> str:
    lines = [f"<b>{_sofascore_team_name_html(team, language)}</b>", f"<b>{text('roster_title', language)}</b>", ""]
    if not players_data:
        lines.append(text("roster_empty", language))
        return "\n".join(lines)

    grouped = _group_sofascore_players_by_position(players_data, language)
    for group_name, players in grouped.items():
        if not players:
            continue
        lines.append(f"<b>{escape(group_name)}</b>")
        for entry in sorted(players, key=_sofascore_player_sort_key):
            lines.append(_format_sofascore_player(entry, language))
        lines.append("")
    return "\n".join(lines).strip()


def format_sofascore_team_events(
    events: list[dict[str, Any]],
    team: dict[str, Any],
    tz: ZoneInfo,
    title: str,
    empty_message: str,
    language: str = "en",
    newest_first: bool = False,
) -> str:
    lines = [f"<b>{_sofascore_team_name_html(team, language)}</b>", f"<b>{escape(title)}</b>", ""]
    if not events:
        lines.append(empty_message)
        return "\n".join(lines)

    for event in sorted(events, key=lambda item: int(item.get("startTimestamp") or 0), reverse=newest_first)[:10]:
        lines.extend(_format_sofascore_event(event, tz, language))
        lines.append("")
    return "\n".join(lines).strip()


def format_sofascore_team_achievements(
    achievements_data: dict[str, Any],
    team: dict[str, Any],
    language: str = "en",
) -> str:
    lines = [f"<b>{_sofascore_team_name_html(team, language)}</b>", f"<b>{text('team_titles', language)}</b>"]
    total = achievements_data.get("totalTrophies")
    if total is not None:
        lines.append(f"{text('team_total_titles', language)}: {escape(str(total))}")
    lines.append("")

    achievements = achievements_data.get("achievements") or []
    if not achievements:
        lines.append(text("team_titles_empty", language))
        return "\n".join(lines)

    for achievement in achievements[:12]:
        tournament = achievement.get("uniqueTournament") or {}
        name = tournament.get("name") or text("unavailable", language)
        trophies = achievement.get("trophiesWon") or 0
        lines.append(f"- {escape(str(name))}: {escape(str(trophies))}")
    return "\n".join(lines)


def format_sofascore_team_statistics(
    summary: dict[str, Any],
    team: dict[str, Any],
    language: str = "en",
) -> str:
    lines = [f"<b>{_sofascore_team_name_html(team, language)}</b>", f"<b>{text('stats', language)}</b>"]
    statistics = summary.get("statistics") or {}
    if not statistics:
        lines.append("")
        lines.append(text("team_stats_empty", language))
        return "\n".join(lines)

    tournament = summary.get("tournament") or {}
    season = summary.get("season") or {}
    context = " - ".join(str(value) for value in [tournament.get("name"), season.get("name")] if value)
    if context:
        lines.append(escape(context))
    lines.append("")

    metrics = [
        ("matches", "team_matches"),
        ("avgRating", "team_avg_rating"),
        ("goalsScored", "team_goals_scored"),
        ("goalsConceded", "team_goals_conceded"),
        ("averageBallPossession", "possession"),
        ("shots", "shots"),
        ("shotsOnTarget", "on_target"),
        ("accuratePassesPercentage", "team_accurate_passes_pct"),
        ("bigChances", "big_chances"),
        ("corners", "corners"),
        ("yellowCards", "yellow_cards"),
        ("redCards", "red_cards"),
    ]
    for key, label_key in metrics:
        value = statistics.get(key)
        if value is None:
            continue
        lines.append(f"{text(label_key, language)}: {escape(_format_stat_value(key, value))}")
    return "\n".join(lines)


def _sofascore_team_name_html(team: dict[str, Any], language: str = "en") -> str:
    return translated_sofascore_team_name_html(team, language=language)


def _format_number(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return ""


def _group_sofascore_players_by_position(
    players_data: list[dict[str, Any]],
    language: str = "en",
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {
        text("goalkeepers", language): [],
        text("defenders", language): [],
        text("midfielders", language): [],
        text("forwards", language): [],
        text("others", language): [],
    }
    for entry in players_data:
        player = entry.get("player") or {}
        position = str(player.get("position") or "").upper()
        if position == "G":
            groups[text("goalkeepers", language)].append(entry)
        elif position == "D":
            groups[text("defenders", language)].append(entry)
        elif position == "M":
            groups[text("midfielders", language)].append(entry)
        elif position == "F":
            groups[text("forwards", language)].append(entry)
        else:
            groups[text("others", language)].append(entry)
    return groups


def _sofascore_player_sort_key(entry: dict[str, Any]) -> tuple[int, str]:
    player = entry.get("player") or {}
    number = player.get("shirtNumber") or player.get("jerseyNumber")
    number_text = str(number or "")
    return (int(number_text) if number_text.isdigit() else 999, str(player.get("name") or ""))


def _format_sofascore_player(entry: dict[str, Any], language: str = "en") -> str:
    player = entry.get("player") or {}
    name = player.get("name") or player.get("shortName") or text("player", language)
    number = player.get("shirtNumber") or player.get("jerseyNumber")
    club = (player.get("team") or {}).get("shortName") or (player.get("team") or {}).get("name")
    prefix = f"#{number} " if number else ""
    suffix = f" - {club}" if club else ""
    return f"- {escape(prefix + str(name))}{escape(str(suffix))}"


def _format_sofascore_event(event: dict[str, Any], tz: ZoneInfo, language: str = "en") -> list[str]:
    start_timestamp = event.get("startTimestamp")
    date_text = text("time_unknown", language)
    if isinstance(start_timestamp, int | float):
        date_text = datetime.fromtimestamp(start_timestamp, tz).strftime("%d/%m/%Y %H:%M")

    home = event.get("homeTeam") or {}
    away = event.get("awayTeam") or {}
    status = event.get("status") or {}
    state = str(status.get("type") or "")
    home_name = _sofascore_team_name_html(home, language)
    away_name = _sofascore_team_name_html(away, language)
    if state in {"finished", "inprogress"}:
        home_score = (event.get("homeScore") or {}).get("current", "-")
        away_score = (event.get("awayScore") or {}).get("current", "-")
        matchup = f"{home_name} {escape(str(home_score))} x {escape(str(away_score))} {away_name}"
    else:
        matchup = f"{home_name} x {away_name}"

    tournament_name = (event.get("tournament") or {}).get("name")
    lines = [f"<b>{escape(date_text)}</b>", matchup]
    if tournament_name:
        lines.append(escape(str(tournament_name)))
    status_text = status.get("description")
    if status_text:
        lines.append(f"{text('status', language)}: {escape(str(status_text))}")
    return lines


def _format_stat_value(key: str, value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if key in {"averageBallPossession", "accuratePassesPercentage"}:
        return f"{number:.1f}%"
    if key == "avgRating":
        return f"{number:.2f}"
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}"
