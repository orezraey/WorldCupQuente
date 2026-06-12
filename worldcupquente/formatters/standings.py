"""Standings and group tables formatters."""

from __future__ import annotations

from html import escape
from typing import Any

from worldcupquente.i18n import text
from worldcupquente.team_translations import translated_team_name_html


def format_standings_group_table(group: dict[str, Any], language: str = "en") -> str:
    entries = (group.get("standings") or {}).get("entries", [])
    title = _standings_group_title(group, language)
    if not entries:
        return f"<h3>{escape(title)}</h3><p>{text('standings_empty_group', language)}</p>"

    lines = [
        f"<h3>{escape(title)}</h3>",
        "<table bordered striped>",
        "<tr>"
        "<th>#</th>"
        f"<th>{text('team', language)}</th>"
        "<th>Pts</th>"
        f"<th>{text('played_short', language)}</th>"
        f"<th>{text('wins_short', language)}</th>"
        f"<th>{text('draws_short', language)}</th>"
        f"<th>{text('losses_short', language)}</th>"
        f"<th>{text('goals_for_short', language)}</th>"
        f"<th>{text('goals_against_short', language)}</th>"
        f"<th>{text('goal_diff_short', language)}</th>"
        "</tr>",
    ]

    for index, entry in enumerate(sorted(entries, key=_standings_entry_sort_key), start=1):
        stats = _standings_stats(entry)
        rank = _standings_stat(stats, "rank") or str(index)
        team_name = translated_team_name_html(entry.get("team") or {}, language=language)
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
            f"<footer>{text('standings_footer', language)}</footer>",
        ]
    )
    return "".join(lines)


def _standings_group_title(group: dict[str, Any], language: str = "en") -> str:
    name = str(group.get("name") or "")
    if name.startswith("Group "):
        return text("standings_title_group", language, group=name.removeprefix("Group "))
    return text("standings_title_default", language, group=name or text("standings_default_group", language))


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
