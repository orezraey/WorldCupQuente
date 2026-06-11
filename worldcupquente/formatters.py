"""Telegram message formatters."""

from __future__ import annotations

from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.services import parse_espn_datetime
from worldcupquente.team_translations import translated_team_name_html

TELEGRAM_MESSAGE_LIMIT = 3900


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


def format_live_games(events: list[dict[str, Any]], tz: ZoneInfo) -> str:
    if not events:
        return "Nenhuma partida da Copa do Mundo está ao vivo no momento."

    lines = ["<b>Partidas ao vivo - Copa do Mundo 2026</b>", ""]
    for event in sorted(events, key=lambda item: item.get("date", "")):
        lines.extend(_format_live_event(event, tz))
        lines.append("")
    return "\n".join(lines).strip()


def format_goal_notification(event: dict[str, Any], detail: dict[str, Any]) -> str:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    team = _find_team_by_id(competitors, str((detail.get("team") or {}).get("id", "")))
    athlete = (detail.get("athletesInvolved") or [{}])[0]
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


def _format_event(event: dict[str, Any], tz: ZoneInfo) -> list[str]:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type", {})
    state = status_type.get("state", "pre")
    status_text = _translated_status(
        status_type.get("shortDetail") or status_type.get("detail") or "Status indisponível"
    )

    event_time = parse_espn_datetime(event.get("date", ""), tz)
    time_text = event_time.strftime("%d/%m %H:%M") if event_time else "Horário indefinido"

    competitors = competition.get("competitors", [])
    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    matchup = _format_matchup(home, away, state)

    venue = competition.get("venue", {}) or event.get("venue", {})
    venue_name = venue.get("fullName") or venue.get("displayName")

    lines = [f"<b>{escape(time_text)}</b> - {matchup}"]
    if venue_name:
        lines.append(f"Estádio: {escape(str(venue_name))}")
    if status_text != "Agendado":
        lines.append(f"Status: {escape(str(status_text))}")
    return lines


def _format_live_event(event: dict[str, Any], tz: ZoneInfo) -> list[str]:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type", {})
    status_text = _translated_status(
        status_type.get("shortDetail") or status_type.get("detail") or "Ao vivo"
    )
    display_clock = status.get("displayClock")

    event_time = parse_espn_datetime(event.get("date", ""), tz)
    time_text = event_time.strftime("%d/%m %H:%M") if event_time else "Horário indefinido"

    competitors = competition.get("competitors", [])
    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    matchup = _format_matchup(home, away, "in")

    venue = competition.get("venue", {}) or event.get("venue", {})
    venue_name = venue.get("fullName") or venue.get("displayName")

    lines = [f"<b>{escape(time_text)}</b> - {matchup}"]
    if display_clock:
        lines.append(f"Minuto: {escape(str(display_clock))}")
    lines.append(f"Status: {escape(str(status_text))}")
    if venue_name:
        lines.append(f"Estádio: {escape(str(venue_name))}")
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
        "FT": "Encerrado",
        "FT-Pens": "Encerrado nos pênaltis",
        "Halftime": "Intervalo",
        "HT": "Intervalo",
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
