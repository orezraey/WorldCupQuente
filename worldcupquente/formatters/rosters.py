"""Roster and coaching staff formatters."""

from __future__ import annotations

from html import escape
from typing import Any

from worldcupquente.team_translations import translated_team_name_html


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
