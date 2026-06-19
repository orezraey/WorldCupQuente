"""Games, fixtures and match statistics formatters."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.event_incidents import (
    is_own_goal_play,
    red_cards_from_event,
    scoring_plays_from_event,
)
from worldcupquente.event_utils import parse_event_datetime
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
    format_win_probability,
)
from worldcupquente.i18n import format_duration, text
from worldcupquente.team_translations import translated_team_name_html

SOFASCORE_RATINGS_TITLE_EMOJI = '<tg-emoji emoji-id="5431497092281421497">⭐</tg-emoji>'
SOFASCORE_RATING_EMOJI_IDS = {
    "10": "5280826091894755088",
    "9.9": "5280749757441003265",
    "9.8": "5280693158361977151",
    "9.7": "5280625362303209424",
    "9.6": "5280950925119214104",
    "9.5": "5281014074023370266",
    "9.4": "5280973001251116677",
    "9.3": "5280546111566664917",
    "9.2": "5280622652178844121",
    "9.1": "5280779401305281374",
    "9.0": "5280757789029847623",
    "8.9": "5280671726475170158",
    "8.8": "5280827818471608636",
    "8.7": "5280601194522235834",
    "8.6": "5283126016816991158",
    "8.5": "5280553760903419760",
    "8.4": "5280616050814113762",
    "8.3": "5280785835166292486",
    "8.2": "5281025086319515627",
    "8.1": "5280942326594688686",
    "8.0": "5280949769773012061",
    "7.9": "5280528862978003478",
    "7.8": "5283257193708147680",
    "7.7": "5280583666760701153",
    "7.6": "5283005813567278868",
    "7.5": "5283010220203724344",
    "7.4": "5280781050572723088",
    "7.3": "5282977355113980089",
    "7.2": "5280483160231007394",
    "7.1": "5280693115412303532",
    "7.0": "5280599781477996703",
    "6.9": "5280542258980999980",
    "6.8": "5280663424303388569",
    "6.7": "5280813799698377437",
    "6.6": "5280794721453626393",
    "6.5": "5280709685396135826",
    "6.4": "5280698539955999929",
    "6.3": "5280842932461524700",
    "6.2": "5280668651278589611",
    "6.1": "5283047659433643113",
    "6.0": "5282724798152068931",
    "5.9": "5353012449052219996",
    "5.8": "5354941207195702386",
    "5.7": "5352825420406350207",
    "5.6": "5352582690329619372",
    "5.5": "5352787882392181661",
    "5.4": "5353047633424308568",
    "5.3": "5355013916697056243",
    "5.2": "5355074265282533942",
    "5.1": "5352652900160002943",
    "5.0": "5352897657461300767",
    "4.9": "5352825635154714322",
    "4.8": "5353047216812481766",
    "4.7": "5352836033270539498",
    "4.6": "5352801763726484430",
    "4.5": "5352798473781533222",
    "4.4": "5352933825380898625",
    "4.3": "5352639783329882341",
    "4.2": "5352907570245818583",
    "4.1": "5355248692494358601",
    "4.0": "5353014325952929517",
    "3.9": "5352910306139987530",
    "3.8": "5352771114839855445",
    "3.7": "5352697176977860571",
    "3.6": "5352902377630358028",
    "3.5": "5355228686536695744",
    "3.4": "5354899962624760596",
    "3.3": "5354785510336255431",
    "3.2": "5355204450036242031",
    "3.1": "5352551401492867711",
    "3.0": "5354929713863219313",
}


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


def format_live_games_rich(
    events: list[dict[str, Any]],
    tz: ZoneInfo,
    language: str = "en",
    show_ratings: bool = False,
) -> str:
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
        paragraph = f"<p>{'<br/>'.join(line for line in lines if line is not None)}</p>"
        blocks.append(paragraph)

        stats_table = _format_live_team_stats_table(event, home, away, language)
        if stats_table:
            blocks.append(stats_table)

        ratings_table = format_player_ratings_table(event, home, away, language) if show_ratings else None
        if ratings_table:
            blocks.append(ratings_table)

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


def format_history_games(
    events: list[dict[str, Any]],
    page: int,
    total_pages: int,
    language: str = "en",
) -> str:
    if not events:
        return text("history_empty", language)
    return "\n".join(
        [
            f"<b>{text('history_title', language)}</b>",
            text("history_body", language),
            text("page", language, page=page + 1, total_pages=total_pages),
        ]
    )


def format_history_game_details(event: dict[str, Any], tz: ZoneInfo, language: str = "en") -> str:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    event_time = parse_event_datetime(event.get("date", ""), tz)
    venue = competition.get("venue", {}) or event.get("venue", {})
    venue_name = venue.get("fullName") or venue.get("displayName")

    lines = [
        f"<b>{text('match_details', language)}</b>",
        "",
        f"⚽️ {_format_matchup(home, away, 'post', language)}",
    ]
    if event_time:
        lines.append(f"🕒 {escape(event_time.strftime('%d/%m %H:%M'))}")
    if venue_name:
        lines.append(f"🏟 {text('stadium', language)}: {escape(str(venue_name))}")

    goal_lines = _format_live_goals(event, language)
    if goal_lines:
        lines.append("")
        lines.extend(goal_lines)

    red_card_lines = _format_live_red_cards(event, language)
    if red_card_lines:
        lines.append("")
        lines.extend(red_card_lines)
    return "\n".join(lines)


def format_history_statistics(event: dict[str, Any], language: str = "en") -> str:
    rows = event.get("sofascoreStatistics") or []
    if not rows:
        return text("sofascore_stats_unavailable", language)

    lines = [f"<b>📊 {text('sofascore_stats', language)}</b>"]
    for row in rows:
        key = str(row.get("key") or "")
        label = _sofascore_stat_label(key, row.get("name"), language)
        lines.append(
            f"{escape(label)}: {escape(str(row.get('home') or '-'))} x {escape(str(row.get('away') or '-'))}"
        )
    return "\n".join(lines)


def format_history_player_ratings(event: dict[str, Any], language: str = "en") -> str:
    lines = _format_player_ratings_lines(event, language)
    if not lines:
        return text("player_ratings_unavailable", language)
    return "\n".join(lines)


def format_player_ratings_table(
    event: dict[str, Any],
    home: dict[str, Any] | None = None,
    away: dict[str, Any] | None = None,
    language: str = "en",
) -> str | None:
    ratings = event.get("sofascorePlayerRatings") or {}
    if not isinstance(ratings, dict) or not (ratings.get("home") or ratings.get("away")):
        return None

    if home is None or away is None:
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors", [])
        home = home or _find_competitor(competitors, "home")
        away = away or _find_competitor(competitors, "away")

    home_team = (home or {}).get("team") or {}
    away_team = (away or {}).get("team") or {}
    home_name = translated_team_name_html(home_team, language=language) if home_team else text("home", language)
    away_name = translated_team_name_html(away_team, language=language) if away_team else text("away", language)
    home_players = ratings.get("home") or []
    away_players = ratings.get("away") or []
    max_rows = max(len(home_players), len(away_players))

    lines = [
        "<table bordered striped>",
        "<tr>"
        f"<th>{home_name}</th>"
        f"<th>{SOFASCORE_RATINGS_TITLE_EMOJI} {text('player_ratings_short', language)}</th>"
        f"<th>{away_name}</th>"
        "</tr>",
    ]
    for index in range(max_rows):
        home_player = home_players[index] if index < len(home_players) else None
        away_player = away_players[index] if index < len(away_players) else None
        lines.append(
            "<tr>"
            f'<td align="left">{_format_rating_table_player(home_player, language)}</td>'
            f'<td align="center">{escape(text("player_ratings_short", language))}</td>'
            f'<td align="right">{_format_rating_table_player(away_player, language)}</td>'
            "</tr>"
        )
    lines.append("</table>")
    return "".join(lines)


def _format_event(event: dict[str, Any], tz: ZoneInfo, language: str = "en") -> list[str]:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    state = status_type.get("state", "pre")
    status_text = _event_status_display_text(status, state, language)

    event_time = parse_event_datetime(event.get("date", ""), tz)
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

    if status_text:
        lines.append(f"{text('status', language)}: {escape(str(status_text))}")
    return lines


def _event_status_display_text(status: dict[str, Any], state: str, language: str = "en") -> str | None:
    status_type = status.get("type") or {}
    display_clock = str(status.get("displayClock") or "").strip()
    status_source = str(
        status_type.get("shortDetail")
        or status_type.get("detail")
        or status_type.get("description")
        or display_clock
        or text("status_unavailable", language)
    ).strip()

    if state == "pre" and _is_hidden_pre_game_status(status_source):
        return None
    if state == "in" and _is_match_minute(display_clock):
        return display_clock
    return _translated_status(status_source, language)


def _is_hidden_pre_game_status(status: str) -> bool:
    normalized = re.sub(r"[^a-z]", "", status.lower())
    return normalized in {"scheduled", "notstarted"}


def _is_match_minute(value: str) -> bool:
    return re.fullmatch(r"\d{1,3}'(?:\+\d{1,2}')?", value.strip()) is not None


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

    event_time = parse_event_datetime(event.get("date", ""), tz)
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

    win_probability_lines = format_win_probability(event, language)
    if win_probability_lines:
        lines.append("")
        lines.extend(win_probability_lines)

    goal_lines = _format_live_goals(event, language)
    if goal_lines:
        lines.append("")
        lines.extend(goal_lines)

    red_card_lines = _format_live_red_cards(event, language)
    if red_card_lines:
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


def _format_player_ratings_lines(event: dict[str, Any], language: str = "en") -> list[str]:
    ratings = event.get("sofascorePlayerRatings") or {}
    if not isinstance(ratings, dict):
        return []

    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    lines = [f"<b>⭐ {text('player_ratings', language)}</b>"]
    for side in ("home", "away"):
        players = ratings.get(side) or []
        if not players:
            continue
        competitor = _find_competitor(competitors, side)
        team = (competitor or {}).get("team") or {}
        lines.append("")
        lines.append(f"<b>{translated_team_name_html(team, language=language)}</b>")
        for player in players:
            shirt = player.get("shirtNumber")
            shirt_text = f"#{escape(str(shirt))} " if shirt not in (None, "") else ""
            substitute = f" ({text('substitute_short', language)})" if player.get("substitute") else ""
            lines.append(
                f"{shirt_text}{escape(str(player.get('name') or text('player_unavailable', language)))}"
                f"{substitute}: <b>{_format_rating(player.get('rating'))}</b>"
            )
    return lines if len(lines) > 1 else []


def _format_rating(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "-"


def _format_rating_table_player(player: dict[str, Any] | None, language: str = "en") -> str:
    if not player:
        return "-"
    shirt = player.get("shirtNumber")
    shirt_text = f"#{escape(str(shirt))} " if shirt not in (None, "") else ""
    name = escape(str(player.get("name") or "-"))
    substitute = f" ({text('substitute_short', language)})" if player.get("substitute") else ""
    return f"{_rating_emoji(player.get('rating'))} {shirt_text}{name}{substitute}"


def _rating_emoji(value: Any) -> str:
    rating = _rating_key(value)
    if not rating:
        return "-"
    emoji_id = SOFASCORE_RATING_EMOJI_IDS.get(rating)
    if emoji_id is None:
        return escape(rating)
    return f'<tg-emoji emoji-id="{emoji_id}">⭐</tg-emoji>'


def _rating_key(value: Any) -> str:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return ""
    if rating == 10:
        return "10"
    return f"{rating:.1f}"


def _sofascore_stat_label(key: str, fallback: Any, language: str = "en") -> str:
    label_keys = {
        "ballPossession": "possession",
        "expectedGoals": "expected_goals",
        "bigChanceCreated": "big_chances",
        "totalShotsOnGoal": "shots",
        "shotsOnGoal": "on_target",
        "goalkeeperSaves": "saves",
        "cornerKicks": "corners",
        "fouls": "fouls",
        "yellowCards": "yellow_cards",
        "redCards": "red_cards",
    }
    label_key = label_keys.get(key)
    return text(label_key, language) if label_key else str(fallback or key)


def _format_live_goals(event: dict[str, Any], language: str = "en") -> list[str]:
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
