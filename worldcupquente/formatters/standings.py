"""Standings and group tables formatters."""

from __future__ import annotations

from html import escape
from typing import Any

from worldcupquente.team_translations import translated_team_name_html


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
