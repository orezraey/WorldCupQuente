"""Event notifications and alert formatters."""

from __future__ import annotations

from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.espn_events import parse_espn_datetime
from worldcupquente.event_incidents import is_own_goal_play, scoring_plays_from_event
from worldcupquente.formatters.games import format_player_ratings_table
from worldcupquente.formatters.standings import format_standings_group_table
from worldcupquente.formatters.utils import (
    RED_CARD_EMOJI,
    _find_competitor,
    _find_team_by_id,
    _format_matchup,
    format_win_probability,
)
from worldcupquente.i18n import text
from worldcupquente.team_translations import translated_team_name_html

KICKOFF_EMOJI = '<tg-emoji emoji-id="5264919878082509254">⚽️</tg-emoji>'


def format_match_status_notification(event: dict[str, Any], tz: ZoneInfo, language: str = "en") -> str:
    status = (event.get("competitions") or [{}])[0].get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    header_key = (
        "second_half_end_header"
        if status_type.get("state") == "post" or status_type.get("completed") is True
        else "first_half_end_header"
    )
    is_full_time = header_key == "second_half_end_header"
    return "\n".join(
        _format_period_end_lines(
            event,
            tz,
            header_key,
            language,
            include_win_probability=not is_full_time,
            include_goal_scorers=is_full_time,
        )
    )


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
    win_probability_lines = format_win_probability(event, language)
    if win_probability_lines:
        lines.append("")
        lines.extend(win_probability_lines)
    return "\n".join(lines)


def format_kickoff_notification(event: dict[str, Any], tz: ZoneInfo, language: str = "en") -> str:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    event_time = parse_espn_datetime(event.get("date", ""), tz)
    venue = competition.get("venue", {}) or event.get("venue", {})
    venue_name = venue.get("fullName") or venue.get("displayName")

    lines = [
        f"{KICKOFF_EMOJI} <b>{text('kickoff_header', language)}</b>",
        "",
        f"⚽️ {_format_matchup(home, away, 'pre', language)}",
    ]
    if event_time:
        lines.append(f"🕒 {escape(event_time.strftime('%d/%m %H:%M'))}")
    if venue_name:
        lines.append(f"🏟 {text('stadium', language)}: {escape(str(venue_name))}")
    win_probability_lines = format_win_probability(event, language)
    if win_probability_lines:
        lines.append("")
        lines.extend(win_probability_lines)
    return "\n".join(lines)


def format_full_time_notification_rich(
    event: dict[str, Any],
    tz: ZoneInfo,
    group: dict[str, Any] | None,
    language: str = "en",
) -> str:
    blocks = [
        _rich_paragraph(
            _format_period_end_lines(
                event,
                tz,
                "second_half_end_header",
                language,
                include_win_probability=False,
                include_goal_scorers=True,
            )
        )
    ]
    ratings_table = format_player_ratings_table(event, language=language)
    if ratings_table:
        blocks.append(ratings_table)
    if group is not None:
        blocks.append(format_standings_group_table(group, language))
    return "".join(blocks)


def _format_period_end_lines(
    event: dict[str, Any],
    tz: ZoneInfo,
    header_key: str,
    language: str,
    include_win_probability: bool = True,
    include_goal_scorers: bool = False,
) -> list[str]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    event_time = parse_espn_datetime(event.get("date", ""), tz)
    venue = competition.get("venue", {}) or event.get("venue", {})
    venue_name = venue.get("fullName") or venue.get("displayName")

    lines = [
        f"<b>⏰ {text(header_key, language)}</b>",
        "",
        f"⚽️ {_format_matchup(home, away, _period_end_matchup_state(header_key), language)}",
    ]
    if event_time:
        lines.append(f"🕒 {escape(event_time.strftime('%d/%m %H:%M'))}")
    if venue_name:
        lines.append(f"🏟 {text('stadium', language)}: {escape(str(venue_name))}")
    goal_lines = _format_goal_scorers(event, language) if include_goal_scorers else []
    if goal_lines:
        lines.append("")
        lines.extend(goal_lines)
    win_probability_lines = format_win_probability(event, language) if include_win_probability else []
    if win_probability_lines:
        lines.append("")
        lines.extend(win_probability_lines)
    return lines


def _period_end_matchup_state(header_key: str) -> str:
    return "post" if header_key == "second_half_end_header" else "in"


def _rich_paragraph(lines: list[str]) -> str:
    return f"<p>{'<br/>'.join(line for line in lines if line is not None)}</p>"


def _format_goal_scorers(event: dict[str, Any], language: str = "en") -> list[str]:
    goals = scoring_plays_from_event(event)
    if not goals:
        return []

    grouped_goals: list[dict[str, Any]] = []
    grouped_by_scorer: dict[str, dict[str, Any]] = {}
    for goal in goals:
        athletes = goal.get("athletesInvolved") or [
            participant.get("athlete") or {}
            for participant in goal.get("participants", [])
            if participant.get("athlete")
        ]
        scorer = (athletes or [{}])[0]
        scorer_name = scorer.get("displayName") or scorer.get("fullName") or text("scorer_unavailable", language)
        minute = (goal.get("clock") or {}).get("displayValue") or text("minute_unavailable", language)
        scorer_key = str(scorer.get("id") or scorer_name)
        if scorer_key not in grouped_by_scorer:
            grouped_by_scorer[scorer_key] = {
                "scorer_name": scorer_name,
                "goals": [],
            }
            grouped_goals.append(grouped_by_scorer[scorer_key])
        grouped_by_scorer[scorer_key]["goals"].append(
            {
                "minute": minute,
                "own_goal": is_own_goal_play(goal),
            }
        )

    return [_format_grouped_goal_line(group, language) for group in grouped_goals]


def _format_grouped_goal_line(group: dict[str, Any], language: str = "en") -> str:
    scorer_name = escape(str(group["scorer_name"]))
    goal_parts = []
    for index, goal in enumerate(group["goals"]):
        minute = escape(str(goal["minute"]))
        own_goal_suffix = f" ({text('own_goal_suffix', language)})" if goal["own_goal"] else ""
        if index == 0:
            goal_parts.append(f"⚽️ {scorer_name} {minute}{own_goal_suffix}")
        else:
            goal_parts.append(f"⚽️ {minute}{own_goal_suffix}")
    return ", ".join(goal_parts)


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

    header_key = "own_goal_header" if is_own_goal_play(detail) else "goal_header"
    header = f"⚽️ <b>{text(header_key, language)}</b>"

    lines = [
        header,
        f"👤 {escape(str(scorer))} ({escape(str(minute))})",
        "",
        _format_goal_matchup(home, away, str(state), detail, language),
    ]
    win_probability_lines = format_win_probability(event, language)
    if win_probability_lines:
        lines.append("")
        lines.extend(win_probability_lines)
    return "\n".join(lines)


def _format_goal_matchup(
    home: dict[str, Any] | None,
    away: dict[str, Any] | None,
    state: str,
    detail: dict[str, Any],
    language: str = "en",
) -> str:
    score_after = _score_after_values(detail)
    if score_after is None:
        return _format_matchup(home, away, state, language)

    home_team = (home or {}).get("team", {})
    away_team = (away or {}).get("team", {})
    home_name = translated_team_name_html(home_team, language=language) if home_team else text("home", language)
    away_name = translated_team_name_html(away_team, language=language) if away_team else text("away", language)
    home_score, away_score = score_after
    return f"{home_name} {escape(home_score)} x {escape(away_score)} {away_name}"


def _score_after_values(detail: dict[str, Any]) -> tuple[str, str] | None:
    score_after = detail.get("scoreAfter")
    if isinstance(score_after, str):
        separator = ":" if ":" in score_after else "-" if "-" in score_after else None
        if separator is None:
            return None
        home_score, away_score = score_after.split(separator, 1)
        return home_score.strip(), away_score.strip()
    if isinstance(score_after, (list, tuple)) and len(score_after) >= 2:
        return str(score_after[0]), str(score_after[1])
    if isinstance(score_after, dict):
        home_score = _first_present_score_value(score_after, "home", "homeScore")
        away_score = _first_present_score_value(score_after, "away", "awayScore")
        if home_score is not None and away_score is not None:
            return str(home_score), str(away_score)
    return None


def _first_present_score_value(score: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in score:
            return score[key]
    return None


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
