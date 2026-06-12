"""Telegram message formatters."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.services import (
    parse_espn_datetime,
    red_cards_from_event,
    scoring_plays_from_event,
)
from worldcupquente.team_translations import translated_team_name_html

TELEGRAM_MESSAGE_LIMIT = 3900
RECENT_COMMENTARY_LIMIT = 5
RED_CARD_EMOJI = '<tg-emoji emoji-id="5336787196479294713">🟥</tg-emoji>'
LIVE_TITLE_EMOJI = '<tg-emoji emoji-id="5850297493593529930">🏆</tg-emoji>'
LIVE_STATS_TITLE_EMOJI = '<tg-emoji emoji-id="5296265790654264117">📊</tg-emoji>'
LIVE_STAT_LEADER_EMOJI = '<tg-emoji emoji-id="5821342125458985363">🔥</tg-emoji>'
LIVE_STAT_LABEL_EMOJIS = {
    "Posse": '<tg-emoji emoji-id="4958712589895861234">⚽</tg-emoji>',
    "Finalizações": '<tg-emoji emoji-id="4958562394889520477">🥅</tg-emoji>',
    "No alvo": '<tg-emoji emoji-id="5449862290834735715">🎯</tg-emoji>',
    "Escanteios": '<tg-emoji emoji-id="4958711348650312955">🚩</tg-emoji>',
    "Faltas": '<tg-emoji emoji-id="4958638587609351070">🦵</tg-emoji>',
    "Passes": '<tg-emoji emoji-id="4958604885000979612">⚽</tg-emoji>',
    "Cruzamentos": '<tg-emoji emoji-id="4958910665197618290">📐</tg-emoji>',
    "Desarmes": '<tg-emoji emoji-id="4958645180384150616">🛡</tg-emoji>',
    "Defesas": '<tg-emoji emoji-id="4958484449823031980">🧤</tg-emoji>',
    "Cartões": (
        '<tg-emoji emoji-id="4958881820197258277">🟨</tg-emoji> '
        '<tg-emoji emoji-id="4958873294687175681">🟥</tg-emoji>'
    ),
}

LIVE_STAT_LABELS = {
    "totalShots": "Finalizações",
    "accuratePasses": "Passes certos",
    "defensiveInterventions": "Intervenções defensivas",
    "saves": "Defesas",
}


def split_telegram_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for line in text.splitlines():
        line_length = len(line) + 1
        if current and current_length + line_length > limit:
            chunks.append("\n".join(current))
            current = []
            current_length = 0
        current.append(line)
        current_length += line_length
    if current:
        chunks.append("\n".join(current))
    return chunks


def format_today_games(scoreboard: dict[str, Any], tz: ZoneInfo) -> str:
    events = scoreboard.get("events", [])
    return format_games(
        events,
        tz,
        "Jogos de hoje - Copa do Mundo 2026",
        "Nenhum jogo da Copa do Mundo encontrado para hoje.",
    )


def format_live_games(events: list[dict[str, Any]], tz: ZoneInfo, show_stats: bool = False) -> str:
    if not events:
        return "Nenhuma partida da Copa do Mundo está ao vivo no momento."

    lines = [f"<b>{LIVE_TITLE_EMOJI} Partidas ao vivo - Copa do Mundo 2026</b>", ""]
    for event in sorted(events, key=lambda item: item.get("date", "")):
        lines.extend(_format_live_event(event, tz, show_stats=show_stats))
        lines.append("")
    return "\n".join(lines).strip()


def format_live_games_rich(events: list[dict[str, Any]], tz: ZoneInfo) -> str:
    if not events:
        return "<p>Nenhuma partida da Copa do Mundo está ao vivo no momento.</p>"

    blocks = [f"<h3>{LIVE_TITLE_EMOJI} Partidas ao vivo - Copa do Mundo 2026</h3>"]
    for event in sorted(events, key=lambda item: item.get("date", "")):
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors", [])
        home = _find_competitor(competitors, "home")
        away = _find_competitor(competitors, "away")

        blocks.append(_rich_paragraph(_format_live_event(event, tz, show_stats=False)))
        stats_table = _format_live_team_stats_table(event, home, away)
        if stats_table:
            blocks.append(stats_table)

    return "".join(blocks)


def _rich_paragraph(lines: list[str]) -> str:
    return f"<p>{'<br/>'.join(line for line in lines if line)}</p>"


def format_goal_notification(event: dict[str, Any], detail: dict[str, Any]) -> str:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    team = _find_team_by_id(competitors, str((detail.get("team") or {}).get("id", "")))
    athletes = detail.get("athletesInvolved") or [
        participant.get("athlete") or {}
        for participant in detail.get("participants", [])
        if participant.get("athlete")
    ]
    athlete = (athletes or [{}])[0]
    scorer = athlete.get("displayName") or athlete.get("fullName") or "Autor indisponível"
    minute = (detail.get("clock") or {}).get("displayValue") or "minuto indisponível"
    goal_type = str((detail.get("type") or {}).get("text") or "Goal")
    goal_note = " contra" if detail.get("ownGoal") else ""

    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    status = competition.get("status") or event.get("status") or {}
    state = (status.get("type") or {}).get("state", "in")

    lines = [
        "<b>Gol na Copa do Mundo!</b>",
        f"Minuto: <b>{escape(str(minute))}</b>",
        f"Autor: <b>{escape(str(scorer))}</b>",
        f"Seleção: <b>{translated_team_name_html(team)}</b>",
        f"Tipo: {escape(_translated_goal_type(goal_type))}{escape(goal_note)}",
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


def format_games(
    events: list[dict[str, Any]],
    tz: ZoneInfo,
    title: str,
    empty_message: str = "Nenhum jogo encontrado.",
) -> str:
    if not events:
        return empty_message

    lines = [f"<b>{escape(title)}</b>", ""]
    for event in sorted(events, key=lambda item: item.get("date", "")):
        lines.extend(_format_event(event, tz))
        lines.append("")
    return "\n".join(lines).strip()


def format_standings_group_table(group: dict[str, Any]) -> str:
    entries = (group.get("standings") or {}).get("entries", [])
    title = _standings_group_title(group)
    if not entries:
        return f"<h3>{escape(title)}</h3><p>Nenhuma classificação encontrada para este grupo.</p>"

    lines = [
        f"<h3>{escape(title)}</h3>",
        "<table bordered striped>",
        "<tr>"
        "<th>#</th>"
        "<th>Seleção</th>"
        "<th>Pts</th>"
        "<th>J</th>"
        "<th>V</th>"
        "<th>E</th>"
        "<th>D</th>"
        "<th>GP</th>"
        "<th>GC</th>"
        "<th>SG</th>"
        "</tr>",
    ]

    for index, entry in enumerate(sorted(entries, key=_standings_entry_sort_key), start=1):
        stats = _standings_stats(entry)
        rank = _standings_stat(stats, "rank") or str(index)
        team_name = translated_team_name_html(entry.get("team") or {})
        lines.append(
            "<tr>"
            f'<td align="right">{escape(rank)}</td>'
            f"<td>{team_name}</td>"
            f'<td align="right"><b>{escape(_standings_stat(stats, "points"))}</b></td>'
            f'<td align="right">{escape(_standings_stat(stats, "gamesPlayed"))}</td>'
            f'<td align="right">{escape(_standings_stat(stats, "wins"))}</td>'
            f'<td align="right">{escape(_standings_stat(stats, "ties"))}</td>'
            f'<td align="right">{escape(_standings_stat(stats, "losses"))}</td>'
            f'<td align="right">{escape(_standings_stat(stats, "pointsFor"))}</td>'
            f'<td align="right">{escape(_standings_stat(stats, "pointsAgainst"))}</td>'
            f'<td align="right">{escape(_standings_stat(stats, "pointDifferential"))}</td>'
            "</tr>"
        )

    lines.extend(
        [
            "</table>",
            "<footer>Pts: pontos · J: jogos · V: vitórias · E: empates · D: derrotas · "
            "GP: gols pró · GC: gols contra · SG: saldo</footer>",
        ]
    )
    return "".join(lines)


def _standings_group_title(group: dict[str, Any]) -> str:
    name = str(group.get("name") or "")
    if name.startswith("Group "):
        return f"Tabela - Grupo {name.removeprefix('Group ')}"
    return f"Tabela - {name or 'Grupo'}"


def _standings_stats(entry: dict[str, Any]) -> dict[str, str]:
    stats: dict[str, str] = {}
    for stat in entry.get("stats", []):
        name = stat.get("name")
        if not name:
            continue
        value = stat.get("displayValue")
        if value is None or value == "":
            value = stat.get("value")
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        stats[str(name)] = str(value) if value is not None else "-"
    return stats


def _standings_stat(stats: dict[str, str], name: str) -> str:
    return stats.get(name) or "-"


def _standings_entry_sort_key(entry: dict[str, Any]) -> tuple[int, str]:
    stats = _standings_stats(entry)
    rank = _standings_stat(stats, "rank")
    if rank.isdigit():
        return (int(rank), "")
    team = entry.get("team") or {}
    return (999, str(team.get("displayName") or team.get("name") or ""))


def _format_event(event: dict[str, Any], tz: ZoneInfo) -> list[str]:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type", {})
    state = status_type.get("state", "pre")
    status_text = _translated_status(
        status_type.get("shortDetail") or status_type.get("detail") or "Status indisponível"
    )

    event_time = parse_espn_datetime(event.get("date", ""), tz)
    now = datetime.now(tz)
    if event_time:
        if event_time.date() == now.date():
            time_text = event_time.strftime("%H:%M")
        else:
            time_text = event_time.strftime("%d/%m %H:%M")
    else:
        time_text = "Horário indefinido"

    competitors = competition.get("competitors", [])
    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    matchup = _format_matchup(home, away, state)

    venue = competition.get("venue", {}) or event.get("venue", {})
    venue_name = venue.get("fullName") or venue.get("displayName")

    lines = [
        f"<b>🕘 {escape(time_text)}</b>",
        f"⚽️ {matchup}",
    ]
    if venue_name:
        lines.append(f"🏟 Estádio: {escape(str(venue_name))}")

    if state == "pre" and event_time and event_time > now:
        time_until_str = _format_time_until(event_time, now)
        if time_until_str:
            lines.append(f"⏳ Começa em: {time_until_str}")

    if status_text != "Agendado":
        lines.append(f"Status: {escape(str(status_text))}")
    return lines


def _format_time_until(event_time: datetime, now: datetime) -> str:
    diff = event_time - now
    total_seconds = int(diff.total_seconds())
    if total_seconds <= 0:
        return ""

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    parts = []
    if days > 0:
        parts.append(f"{days} {'dia' if days == 1 else 'dias'}")
    if hours > 0:
        parts.append(f"{hours} {'hora' if hours == 1 else 'horas'}")
    if minutes > 0 or (days == 0 and hours == 0):
        parts.append(f"{minutes} {'minuto' if minutes == 1 else 'minutos'}")

    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} e {parts[1]}"
    return f"{parts[0]}, {parts[1]} e {parts[2]}"


def _format_live_event(event: dict[str, Any], tz: ZoneInfo, show_stats: bool = False) -> list[str]:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type", {})
    display_clock = status.get("displayClock")
    if status_type.get("state") == "pre":
        status_text = "Ao vivo"
    else:
        status_source = status_type.get("shortDetail") or status_type.get("detail") or "Ao vivo"
        if display_clock and status_source == display_clock:
            status_source = status_type.get("description") or status_source
        status_text = _translated_status(
            status_source
        )

    event_time = parse_espn_datetime(event.get("date", ""), tz)
    time_text = event_time.strftime("%d/%m %H:%M") if event_time else "Horário indefinido"

    competitors = competition.get("competitors", [])
    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    matchup = _format_matchup(home, away, "in")

    venue = competition.get("venue", {}) or event.get("venue", {})
    venue_name = venue.get("fullName") or venue.get("displayName")

    lines = [f"<b>{escape(time_text)}</b>", matchup]
    lines.append(f"🕘 Tempo: {escape(str(display_clock or 'indisponível'))}")
    lines.append(f"📢 Status: {escape(str(status_text))}")
    lines.append(f"🏟 Estádio: {escape(str(venue_name or 'indisponível'))}")

    goal_lines = _format_live_goals(event)
    if goal_lines:
        lines.append("")
        lines.extend(goal_lines)

    red_card_lines = _format_live_red_cards(event)
    if red_card_lines:
        if not goal_lines:
            lines.append("")
        lines.extend(red_card_lines)

    if not show_stats:
        return lines

    stat_lines = _format_live_team_stats(event, home, away)
    if stat_lines:
        lines.append("")
        lines.extend(stat_lines)

    leader_lines = _format_live_leaders(event)
    if leader_lines:
        lines.append("")
        lines.extend(leader_lines)

    commentary_lines = _format_recent_commentary(event)
    if commentary_lines:
        lines.append("")
        lines.extend(commentary_lines)

    return lines


def _format_live_red_cards(event: dict[str, Any]) -> list[str]:
    red_cards = red_cards_from_event(event)
    if not red_cards:
        return []

    lines: list[str] = []
    for red_card in red_cards:
        player = red_card.get("athlete") or {}
        player_name = player.get("displayName") or player.get("fullName") or "Jogador indisponível"
        minute = (red_card.get("clock") or {}).get("displayValue")
        suffix = f" {escape(str(minute))}" if minute else ""
        lines.append(f"{RED_CARD_EMOJI} {escape(str(player_name))}{suffix}")
    return lines


def _format_live_goals(event: dict[str, Any]) -> list[str]:
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
        scorer_name = scorer.get("displayName") or scorer.get("fullName") or "Autor indisponível"
        minute = (goal.get("clock") or {}).get("displayValue") or "minuto indisponível"
        lines.append(f"⚽️ {escape(str(scorer_name))} {escape(str(minute))}")
    return lines


def _format_live_team_stats(
    event: dict[str, Any],
    home: dict[str, Any] | None,
    away: dict[str, Any] | None,
) -> list[str]:
    home_stats, away_stats = _live_team_stats(event, home, away)
    stat_rows = _live_team_stat_rows(home_stats, away_stats)
    if not stat_rows:
        return []
    return ["<b>Estatísticas</b>", *[_format_stat_row(*row) for row in stat_rows]]


def _format_live_team_stats_table(
    event: dict[str, Any],
    home: dict[str, Any] | None,
    away: dict[str, Any] | None,
) -> str | None:
    home_stats, away_stats = _live_team_stats(event, home, away)
    stat_rows = _live_team_stat_rows(home_stats, away_stats)
    if not stat_rows:
        return None

    home_team = (home or {}).get("team") or {}
    away_team = (away or {}).get("team") or {}
    home_name = translated_team_name_html(home_team) if home_team else "Casa"
    away_name = translated_team_name_html(away_team) if away_team else "Visitante"
    lines = [
        "<table bordered striped>",
        "<tr>"
        f"<th>{home_name or 'Casa'}</th>"
        f"<th>{LIVE_STATS_TITLE_EMOJI} Estatística</th>"
        f"<th>{away_name or 'Visitante'}</th>"
        "</tr>",
    ]
    for label, home_value, away_value in stat_rows:
        leader = _live_stat_leader(label, home_value, away_value)
        lines.append(
            "<tr>"
            f'<td align="left">{_format_live_stat_table_value(home_value, leader == "home")}</td>'
            f'<td align="center">{_format_live_stat_table_label(label)}</td>'
            f'<td align="right">{_format_live_stat_table_value(away_value, leader == "away")}</td>'
            "</tr>"
        )
    lines.append("</table>")
    return "".join(lines)


def _format_live_stat_table_value(value: str | None, is_leader: bool) -> str:
    text = escape(value or "-")
    return f"{text} {LIVE_STAT_LEADER_EMOJI}" if is_leader else text


def _format_live_stat_table_label(label: str) -> str:
    emoji = LIVE_STAT_LABEL_EMOJIS.get(label)
    if not emoji:
        return escape(label)
    return f"{emoji} {escape(label)}"


def _live_stat_leader(label: str, home_value: str | None, away_value: str | None) -> str | None:
    if label == "Cartões":
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
            "Posse",
            _format_percent_value(_stat_value(home_stats, "possessionPct")),
            _format_percent_value(_stat_value(away_stats, "possessionPct")),
        ),
        ("Finalizações", _stat_value(home_stats, "totalShots"), _stat_value(away_stats, "totalShots")),
        ("No alvo", _stat_value(home_stats, "shotsOnTarget"), _stat_value(away_stats, "shotsOnTarget")),
        ("Escanteios", _stat_value(home_stats, "wonCorners"), _stat_value(away_stats, "wonCorners")),
        ("Faltas", _stat_value(home_stats, "foulsCommitted"), _stat_value(away_stats, "foulsCommitted")),
        (
            "Passes",
            _made_total_value(home_stats, "accuratePasses", "totalPasses"),
            _made_total_value(away_stats, "accuratePasses", "totalPasses"),
        ),
        (
            "Cruzamentos",
            _made_total_value(home_stats, "accurateCrosses", "totalCrosses"),
            _made_total_value(away_stats, "accurateCrosses", "totalCrosses"),
        ),
        (
            "Desarmes",
            _made_total_value(home_stats, "effectiveTackles", "totalTackles"),
            _made_total_value(away_stats, "effectiveTackles", "totalTackles"),
        ),
        ("Defesas", _stat_value(home_stats, "saves"), _stat_value(away_stats, "saves")),
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
        return ("Cartões", None, None)
    home_value = f"{home_yellow or '0'}A {home_red or '0'}V"
    away_value = f"{away_yellow or '0'}A {away_red or '0'}V"
    return ("Cartões", home_value, away_value)


def _format_stat_row(label: str, home_value: str | None, away_value: str | None) -> str | None:
    if home_value is None and away_value is None:
        return None
    return f"{escape(label)}: {escape(home_value or '-')} x {escape(away_value or '-')}"


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


def _format_live_leaders(event: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for stat_name, label in LIVE_STAT_LABELS.items():
        leader = _best_leader(event, stat_name)
        if leader is None:
            continue
        team, athlete, value = leader
        team_name = translated_team_name_html(team, include_emoji=False)
        athlete_name = escape(str(athlete.get("displayName") or athlete.get("fullName") or "Jogador"))
        lines.append(f"{escape(label)}: {athlete_name} ({team_name}) - {escape(value)}")
    if not lines:
        return []
    return ["<b>Destaques</b>", *lines]


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
                display_value = str(leader.get("displayValue") or _leader_stat_value(leader, stat_name))
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


def _format_recent_commentary(event: dict[str, Any]) -> list[str]:
    commentary = [item for item in event.get("commentary", []) if item.get("text")]
    if not commentary:
        return []

    recent = sorted(commentary, key=lambda item: int(item.get("sequence") or 0), reverse=True)
    lines = ["<b>Últimos lances</b>"]
    for item in recent[:RECENT_COMMENTARY_LIMIT]:
        minute = (item.get("time") or {}).get("displayValue")
        prefix = f"{minute}: " if minute else ""
        lines.append(f"- {escape(prefix + str(item.get('text', '')))}")
    return lines


def _find_competitor(competitors: list[dict[str, Any]], home_away: str) -> dict[str, Any] | None:
    for competitor in competitors:
        if competitor.get("homeAway") == home_away:
            return competitor
    return None


def _find_team_by_id(competitors: list[dict[str, Any]], team_id: str) -> dict[str, Any]:
    for competitor in competitors:
        team = competitor.get("team", {}) or {}
        if str(team.get("id", "")) == team_id:
            return team
    return {"id": team_id}


def _format_matchup(
    home: dict[str, Any] | None,
    away: dict[str, Any] | None,
    state: str,
) -> str:
    home_team = (home or {}).get("team", {})
    away_team = (away or {}).get("team", {})
    home_name = translated_team_name_html(home_team) if home_team else "Mandante"
    away_name = translated_team_name_html(away_team) if away_team else "Visitante"

    if state == "pre":
        return f"{home_name} x {away_name}"

    home_score = (home or {}).get("score", "-")
    away_score = (away or {}).get("score", "-")
    return f"{home_name} {escape(str(home_score))} x {escape(str(away_score))} {away_name}"


def format_team_roster(roster_data: dict[str, Any]) -> str:
    team = roster_data.get("team", {})
    team_name = translated_team_name_html(team)
    coach = roster_data.get("coach")
    athletes = roster_data.get("athletes", [])

    lines = [f"<b>{team_name}</b>", "<b>Elenco geral</b>"]
    coach_name = _coach_display_name(coach)
    if coach_name:
        lines.append(f"Técnico: {escape(str(coach_name))}")
    lines.append("")

    if not athletes:
        lines.append("Nenhum jogador encontrado para esta seleção.")
        return "\n".join(lines)

    grouped = _group_athletes_by_position(athletes)
    for group_name, players in grouped.items():
        if not players:
            continue
        lines.append(f"<b>{group_name}</b>")
        for player in sorted(players, key=_player_sort_key):
            lines.append(_format_player(player))
        lines.append("")
    return "\n".join(lines).strip()


def _coach_display_name(coach: Any) -> str:
    if isinstance(coach, dict):
        return _person_display_name(coach)
    if isinstance(coach, list):
        names = [_person_display_name(item) for item in coach if isinstance(item, dict)]
        return ", ".join(name for name in names if name)
    return ""


def _person_display_name(person: dict[str, Any]) -> str:
    display_name = person.get("displayName") or person.get("name")
    if display_name:
        return str(display_name)
    first_name = person.get("firstName", "")
    last_name = person.get("lastName", "")
    return " ".join(str(part) for part in [first_name, last_name] if part).strip()


def _group_athletes_by_position(athletes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {
        "Goleiros": [],
        "Defensores": [],
        "Meio-campistas": [],
        "Atacantes": [],
        "Outros": [],
    }
    for athlete in athletes:
        position = athlete.get("position", {}) or {}
        abbreviation = str(position.get("abbreviation", "")).upper()
        name = str(position.get("name") or position.get("displayName") or "").upper()
        if abbreviation in {"G", "GK"} or "GOAL" in name:
            groups["Goleiros"].append(athlete)
        elif abbreviation in {"D", "DEF", "CB", "LB", "RB", "LWB", "RWB"} or "BACK" in name:
            groups["Defensores"].append(athlete)
        elif abbreviation in {"M", "MF", "CM", "DM", "AM", "LM", "RM"} or "MID" in name:
            groups["Meio-campistas"].append(athlete)
        elif abbreviation in {"F", "FW", "ST", "CF", "LF", "RF", "LW", "RW"} or "FORWARD" in name:
            groups["Atacantes"].append(athlete)
        else:
            groups["Outros"].append(athlete)
    return groups


def _player_sort_key(player: dict[str, Any]) -> tuple[int, str]:
    jersey = str(player.get("jersey") or "")
    return (int(jersey) if jersey.isdigit() else 999, str(player.get("displayName") or ""))


def _format_player(player: dict[str, Any]) -> str:
    jersey = player.get("jersey")
    name = player.get("displayName") or player.get("fullName") or "Jogador"
    position = player.get("position", {}) or {}
    position_abbr = position.get("abbreviation")
    prefix = f"#{jersey} " if jersey else ""
    suffix = f" ({position_abbr})" if position_abbr else ""
    return f"- {escape(prefix + str(name))}{escape(str(suffix))}"


def _translated_status(status_text: str) -> str:
    translations = {
        "Scheduled": "Agendado",
        "Final": "Encerrado",
        "First Half": "Primeiro tempo",
        "FT": "Encerrado",
        "FT-Pens": "Encerrado nos pênaltis",
        "Halftime": "Intervalo",
        "HT": "Intervalo",
        "In Progress": "Em andamento",
        "Second Half": "Segundo tempo",
        "Postponed": "Adiado",
        "Canceled": "Cancelado",
        "Cancelled": "Cancelado",
    }
    return translations.get(status_text, status_text)


def _translated_goal_type(goal_type: str) -> str:
    translations = {
        "Goal": "Gol",
        "Penalty - Scored": "Pênalti convertido",
    }
    return translations.get(goal_type, goal_type)
