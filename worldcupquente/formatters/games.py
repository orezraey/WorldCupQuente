"""Games, fixtures and match statistics formatters."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.espn_events import parse_espn_datetime
from worldcupquente.event_incidents import (
    red_cards_from_event,
    scoring_plays_from_event,
)
from worldcupquente.formatters.utils import (
    LIVE_STAT_LABEL_EMOJIS,
    LIVE_STAT_LABELS,
    LIVE_STAT_LEADER_EMOJI,
    LIVE_STATS_TITLE_EMOJI,
    LIVE_TITLE_EMOJI,
    RECENT_COMMENTARY_LIMIT,
    RED_CARD_EMOJI,
    _find_competitor,
    _format_matchup,
    _translated_status,
)
from worldcupquente.i18n import format_duration, text
from worldcupquente.team_translations import translated_team_name_html


def format_today_games(scoreboard: dict[str, Any], tz: ZoneInfo, language: str = "en") -> str:
    events = scoreboard.get("events", [])
    return format_games(
        events,
        tz,
        text("today_title", language),
        text("today_empty", language),
        language,
    )


def format_live_games(
    events: list[dict[str, Any]],
    tz: ZoneInfo,
    show_stats: bool = False,
    language: str = "en",
) -> str:
    if not events:
        return text("live_empty", language)

    lines = [f"<b>{LIVE_TITLE_EMOJI} {text('live_title', language)}</b>", ""]
    for event in sorted(events, key=lambda item: item.get("date", "")):
        lines.extend(_format_live_event(event, tz, show_stats=show_stats, language=language))
        lines.append("")
    return "\n".join(lines).strip()


def format_live_games_rich(events: list[dict[str, Any]], tz: ZoneInfo, language: str = "en") -> str:
    if not events:
        return f"<p>{text('live_empty', language)}</p>"

    blocks = [f"<h3>{LIVE_TITLE_EMOJI} {text('live_title', language)}</h3>"]
    for event in sorted(events, key=lambda item: item.get("date", "")):
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors", [])
        home = _find_competitor(competitors, "home")
        away = _find_competitor(competitors, "away")

        # In order to avoid circular dependency, we inline the rich paragraph logic here
        lines = _format_live_event(event, tz, show_stats=False, language=language)
        paragraph = f"<p>{'<br/>'.join(line for line in lines if line)}</p>"
        blocks.append(paragraph)

        stats_table = _format_live_team_stats_table(event, home, away, language)
        if stats_table:
            blocks.append(stats_table)

    return "".join(blocks)


def format_games(
    events: list[dict[str, Any]],
    tz: ZoneInfo,
    title: str,
    empty_message: str | None = None,
    language: str = "en",
) -> str:
    if not events:
        return empty_message or text("games_empty", language)

    lines = [f"<b>{escape(title)}</b>", ""]
    for event in sorted(events, key=lambda item: item.get("date", "")):
        lines.extend(_format_event(event, tz, language))
        lines.append("")
    return "\n".join(lines).strip()


def _format_event(event: dict[str, Any], tz: ZoneInfo, language: str = "en") -> list[str]:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type", {})
    state = status_type.get("state", "pre")
    status_text = _translated_status(
        status_type.get("shortDetail") or status_type.get("detail") or text("status_unavailable", language),
        language,
    )

    event_time = parse_espn_datetime(event.get("date", ""), tz)
    now = datetime.now(tz)
    if event_time:
        if event_time.date() == now.date():
            time_text = event_time.strftime("%H:%M")
        else:
            time_text = event_time.strftime("%d/%m %H:%M")
    else:
        time_text = text("time_unknown", language)

    competitors = competition.get("competitors", [])
    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    matchup = _format_matchup(home, away, state, language)

    venue = competition.get("venue", {}) or event.get("venue", {})
    venue_name = venue.get("fullName") or venue.get("displayName")

    lines = [
        f"<b>🕒 {escape(time_text)}</b>",
        f"⚽️ {matchup}",
    ]
    if venue_name:
        lines.append(f"🏟 {text('stadium', language)}: {escape(str(venue_name))}")

    if state == "pre" and event_time and event_time > now:
        time_until_str = _format_time_until(event_time, now, language)
        if time_until_str:
            lines.append(f"⏳ {text('starts_in', language)}: {time_until_str}")

    if status_text != _translated_status("Scheduled", language):
        lines.append(f"{text('status', language)}: {escape(str(status_text))}")
    return lines


def _format_time_until(event_time: datetime, now: datetime, language: str = "en") -> str:
    diff = event_time - now
    total_seconds = int(diff.total_seconds())
    if total_seconds <= 0:
        return ""

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    parts = []
    if days > 0:
        parts.append((days, "day"))
    if hours > 0:
        parts.append((hours, "hour"))
    if minutes > 0 or (days == 0 and hours == 0):
        parts.append((minutes, "minute"))

    return format_duration(parts, language)


def _format_live_event(
    event: dict[str, Any],
    tz: ZoneInfo,
    show_stats: bool = False,
    language: str = "en",
) -> list[str]:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type", {})
    display_clock = status.get("displayClock")
    if status_type.get("state") == "pre":
        status_text = _translated_status("In Progress", language)
    else:
        status_source = status_type.get("shortDetail") or status_type.get("detail") or "In Progress"
        if display_clock and status_source == display_clock:
            status_source = status_type.get("description") or status_source
        status_text = _translated_status(status_source, language)

    event_time = parse_espn_datetime(event.get("date", ""), tz)
    time_text = event_time.strftime("%d/%m %H:%M") if event_time else text("time_unknown", language)

    competitors = competition.get("competitors", [])
    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    matchup = _format_matchup(home, away, "in", language)

    venue = competition.get("venue", {}) or event.get("venue", {})
    venue_name = venue.get("fullName") or venue.get("displayName")

    lines = [f"<b>{escape(time_text)}</b>", matchup]
    lines.append(f"🕘 {text('live_time', language)}: {escape(str(display_clock or text('unavailable', language)))}")
    lines.append(f"📢 {text('status', language)}: {escape(str(status_text))}")
    lines.append(f"🏟 {text('stadium', language)}: {escape(str(venue_name or text('unavailable', language)))}")

    goal_lines = _format_live_goals(event, language)
    if goal_lines:
        lines.append("")
        lines.extend(goal_lines)

    red_card_lines = _format_live_red_cards(event, language)
    if red_card_lines:
        if not goal_lines:
            lines.append("")
        lines.extend(red_card_lines)

    if not show_stats:
        return lines

    stat_lines = _format_live_team_stats(event, home, away, language)
    if stat_lines:
        lines.append("")
        lines.extend(stat_lines)

    leader_lines = _format_live_leaders(event, language)
    if leader_lines:
        lines.append("")
        lines.extend(leader_lines)

    commentary_lines = _format_recent_commentary(event, language)
    if commentary_lines:
        lines.append("")
        lines.extend(commentary_lines)

    return lines


def _format_live_red_cards(event: dict[str, Any], language: str = "en") -> list[str]:
    red_cards = red_cards_from_event(event)
    if not red_cards:
        return []

    lines: list[str] = []
    for red_card in red_cards:
        player = red_card.get("athlete") or {}
        player_name = player.get("displayName") or player.get("fullName") or text("player_unavailable", language)
        minute = (red_card.get("clock") or {}).get("displayValue")
        suffix = f" {escape(str(minute))}" if minute else ""
        lines.append(f"{RED_CARD_EMOJI} {escape(str(player_name))}{suffix}")
    return lines


def _format_live_goals(event: dict[str, Any], language: str = "en") -> list[str]:
    goals = scoring_plays_from_event(event)
    if not goals:
        return []

    lines: list[str] = []
    for goal in goals:
        athletes = goal.get("athletesInvolved") or [
            participant.get("athlete") or {}
            for participant in goal.get("participants", [])
            if participant.get("athlete")
        ]
        scorer = (athletes or [{}])[0]
        scorer_name = scorer.get("displayName") or scorer.get("fullName") or text("scorer_unavailable", language)
        minute = (goal.get("clock") or {}).get("displayValue") or text("minute_unavailable", language)
        lines.append(f"⚽️ {escape(str(scorer_name))} {escape(str(minute))}")
    return lines


def _format_live_team_stats(
    event: dict[str, Any],
    home: dict[str, Any] | None,
    away: dict[str, Any] | None,
    language: str = "en",
) -> list[str]:
    home_stats, away_stats = _live_team_stats(event, home, away)
    stat_rows = _live_team_stat_rows(home_stats, away_stats)
    if not stat_rows:
        return []
    return ["<b>" + text("stats", language) + "</b>", *[_format_stat_row(*row, language) for row in stat_rows]]


def _format_live_team_stats_table(
    event: dict[str, Any],
    home: dict[str, Any] | None,
    away: dict[str, Any] | None,
    language: str = "en",
) -> str | None:
    home_stats, away_stats = _live_team_stats(event, home, away)
    stat_rows = _live_team_stat_rows(home_stats, away_stats)
    if not stat_rows:
        return None

    home_team = (home or {}).get("team") or {}
    away_team = (away or {}).get("team") or {}
    home_name = translated_team_name_html(home_team, language=language) if home_team else text("home", language)
    away_name = translated_team_name_html(away_team, language=language) if away_team else text("away", language)
    lines = [
        "<table bordered striped>",
        "<tr>"
        f"<th>{home_name or text('home', language)}</th>"
        f"<th>{LIVE_STATS_TITLE_EMOJI} {text('stats', language)}</th>"
        f"<th>{away_name or text('away', language)}</th>"
        "</tr>",
    ]
    for label, home_value, away_value in stat_rows:
        leader = _live_stat_leader(label, home_value, away_value)
        home_display_value = _localized_card_value(home_value, language) if label == "cards" else home_value
        away_display_value = _localized_card_value(away_value, language) if label == "cards" else away_value
        lines.append(
            "<tr>"
            f'<td align="left">{_format_live_stat_table_value(home_display_value, leader == "home")}</td>'
            f'<td align="center">{_format_live_stat_table_label(label, language)}</td>'
            f'<td align="right">{_format_live_stat_table_value(away_display_value, leader == "away")}</td>'
            "</tr>"
        )
    lines.append("</table>")
    return "".join(lines)


def _format_live_stat_table_value(value: str | None, is_leader: bool) -> str:
    text = escape(value or "-")
    return f"{text} {LIVE_STAT_LEADER_EMOJI}" if is_leader else text


def _format_live_stat_table_label(label: str, language: str = "en") -> str:
    emoji = LIVE_STAT_LABEL_EMOJIS.get(label)
    localized_label = text(label, language)
    if not emoji:
        return escape(localized_label)
    return f"{emoji} {escape(localized_label)}"


def _live_stat_leader(label: str, home_value: str | None, away_value: str | None) -> str | None:
    if label == "cards":
        return None

    home_number = _first_stat_number(home_value)
    away_number = _first_stat_number(away_value)
    if home_number is None or away_number is None or home_number == away_number:
        return None
    return "home" if home_number > away_number else "away"


def _first_stat_number(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", value)
    if match is None:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _live_team_stat_rows(
    home_stats: dict[str, dict[str, Any]],
    away_stats: dict[str, dict[str, Any]],
) -> list[tuple[str, str | None, str | None]]:
    if not home_stats and not away_stats:
        return []

    rows = [
        (
            "possession",
            _format_percent_value(_stat_value(home_stats, "possessionPct")),
            _format_percent_value(_stat_value(away_stats, "possessionPct")),
        ),
        (
            "shots",
            _stat_value(home_stats, "totalShots"),
            _stat_value(away_stats, "totalShots"),
        ),
        (
            "on_target",
            _stat_value(home_stats, "shotsOnTarget"),
            _stat_value(away_stats, "shotsOnTarget"),
        ),
        (
            "corners",
            _stat_value(home_stats, "wonCorners"),
            _stat_value(away_stats, "wonCorners"),
        ),
        (
            "fouls",
            _stat_value(home_stats, "foulsCommitted"),
            _stat_value(away_stats, "foulsCommitted"),
        ),
        (
            "passes",
            _made_total_value(home_stats, "accuratePasses", "totalPasses"),
            _made_total_value(away_stats, "accuratePasses", "totalPasses"),
        ),
        (
            "crosses",
            _made_total_value(home_stats, "accurateCrosses", "totalCrosses"),
            _made_total_value(away_stats, "accurateCrosses", "totalCrosses"),
        ),
        (
            "tackles",
            _made_total_value(home_stats, "effectiveTackles", "totalTackles"),
            _made_total_value(away_stats, "effectiveTackles", "totalTackles"),
        ),
        ("saves", _stat_value(home_stats, "saves"), _stat_value(away_stats, "saves")),
        _cards_stat_values(home_stats, away_stats),
    ]
    return [row for row in rows if row[1] is not None or row[2] is not None]


def _live_team_stats(
    event: dict[str, Any],
    home: dict[str, Any] | None,
    away: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    boxscore_teams = (event.get("boxscore") or {}).get("teams", [])
    boxscore_stats = {
        str((team_item.get("team") or {}).get("id", "")): _stats_by_name(
            team_item.get("statistics", [])
        )
        for team_item in boxscore_teams
    }

    home_id = str(((home or {}).get("team") or {}).get("id", ""))
    away_id = str(((away or {}).get("team") or {}).get("id", ""))
    home_stats = boxscore_stats.get(home_id) or _stats_by_name((home or {}).get("statistics", []))
    away_stats = boxscore_stats.get(away_id) or _stats_by_name((away or {}).get("statistics", []))
    return home_stats, away_stats


def _stats_by_name(statistics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(stat.get("name")): stat for stat in statistics if stat.get("name")}


def _format_percent_stat(
    label: str,
    home_stats: dict[str, dict[str, Any]],
    away_stats: dict[str, dict[str, Any]],
    name: str,
) -> str | None:
    home_value = _format_percent_value(_stat_value(home_stats, name))
    away_value = _format_percent_value(_stat_value(away_stats, name))
    return _format_stat_row(label, home_value, away_value)


def _format_single_stat(
    label: str,
    home_stats: dict[str, dict[str, Any]],
    away_stats: dict[str, dict[str, Any]],
    name: str,
) -> str | None:
    return _format_stat_row(label, _stat_value(home_stats, name), _stat_value(away_stats, name))


def _format_made_total_stat(
    label: str,
    home_stats: dict[str, dict[str, Any]],
    away_stats: dict[str, dict[str, Any]],
    made_name: str,
    total_name: str,
) -> str | None:
    home_value = _made_total_value(home_stats, made_name, total_name)
    away_value = _made_total_value(away_stats, made_name, total_name)
    return _format_stat_row(label, home_value, away_value)


def _format_cards_stat(
    home_stats: dict[str, dict[str, Any]],
    away_stats: dict[str, dict[str, Any]],
) -> str | None:
    label, home_value, away_value = _cards_stat_values(home_stats, away_stats)
    return _format_stat_row(label, home_value, away_value)


def _cards_stat_values(
    home_stats: dict[str, dict[str, Any]],
    away_stats: dict[str, dict[str, Any]],
) -> tuple[str, str | None, str | None]:
    home_yellow = _stat_value(home_stats, "yellowCards")
    home_red = _stat_value(home_stats, "redCards")
    away_yellow = _stat_value(away_stats, "yellowCards")
    away_red = _stat_value(away_stats, "redCards")
    if home_yellow is None and home_red is None and away_yellow is None and away_red is None:
        return ("cards", None, None)
    home_value = f"{home_yellow or '0'}Y {home_red or '0'}R"
    away_value = f"{away_yellow or '0'}Y {away_red or '0'}R"
    return ("cards", home_value, away_value)


def _format_stat_row(
    label: str,
    home_value: str | None,
    away_value: str | None,
    language: str = "en",
) -> str | None:
    if home_value is None and away_value is None:
        return None
    home_value = _localized_card_value(home_value, language) if label == "cards" else home_value
    away_value = _localized_card_value(away_value, language) if label == "cards" else away_value
    return f"{escape(text(label, language))}: {escape(home_value or '-')} x {escape(away_value or '-')}"


def _localized_card_value(value: str | None, language: str) -> str | None:
    if value is None:
        return None
    return value.replace("Y", text("yellow_short", language)).replace("R", text("red_short", language))


def _stat_value(stats: dict[str, dict[str, Any]], name: str) -> str | None:
    stat = stats.get(name) or {}
    value = stat.get("displayValue")
    if value is None:
        value = stat.get("value")
    return str(value) if value is not None else None


def _format_percent_value(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):.0f}%"
    except ValueError:
        return value if value.endswith("%") else f"{value}%"


def _made_total_value(
    stats: dict[str, dict[str, Any]],
    made_name: str,
    total_name: str,
) -> str | None:
    made = _stat_value(stats, made_name)
    total = _stat_value(stats, total_name)
    if made is None and total is None:
        return None
    if made is None or total is None:
        return made or total
    return f"{made}/{total}"


def _format_live_leaders(event: dict[str, Any], language: str = "en") -> list[str]:
    lines: list[str] = []
    for stat_name, label in LIVE_STAT_LABELS.items():
        leader = _best_leader(event, stat_name)
        if leader is None:
            continue
        team, athlete, value = leader
        team_name = translated_team_name_html(team, include_emoji=False, language=language)
        athlete_name = escape(
            str(athlete.get("displayName") or athlete.get("fullName") or text("player", language))
        )
        lines.append(f"{escape(text(label, language))}: {athlete_name} ({team_name}) - {escape(value)}")
    if not lines:
        return []
    return [f"<b>{text('highlights', language)}</b>", *lines]


def _best_leader(
    event: dict[str, Any],
    stat_name: str,
) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    candidates: list[tuple[float, dict[str, Any], dict[str, Any], str]] = []
    for team_group in event.get("leaders", []):
        team = team_group.get("team") or {}
        for stat_group in team_group.get("leaders", []):
            if stat_group.get("name") != stat_name:
                continue
            for leader in stat_group.get("leaders", []):
                athlete = leader.get("athlete") or {}
                display_value = str(
                    leader.get("displayValue") or _leader_stat_value(leader, stat_name)
                )
                value = _numeric_value(display_value)
                candidates.append((value, team, athlete, display_value))
    if not candidates:
        return None
    _, team, athlete, display_value = max(candidates, key=lambda item: item[0])
    return team, athlete, display_value


def _leader_stat_value(leader: dict[str, Any], stat_name: str) -> str:
    for stat in leader.get("statistics", []):
        if stat.get("name") == stat_name:
            return str(stat.get("displayValue") or stat.get("value") or "0")
    return "0"


def _numeric_value(value: str) -> float:
    try:
        return float(value.replace("%", ""))
    except ValueError:
        return 0.0


def _format_recent_commentary(event: dict[str, Any], language: str = "en") -> list[str]:
    commentary = [item for item in event.get("commentary", []) if item.get("text")]
    if not commentary:
        return []

    recent = sorted(commentary, key=lambda item: int(item.get("sequence") or 0), reverse=True)
    lines = [f"<b>{text('recent_plays', language)}</b>"]
    for item in recent[:RECENT_COMMENTARY_LIMIT]:
        minute = (item.get("time") or {}).get("displayValue")
        prefix = f"{minute}: " if minute else ""
        lines.append(f"- {escape(prefix + str(item.get('text', '')))}")
    return lines
