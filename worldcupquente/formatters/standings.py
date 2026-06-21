"""Standings and group tables formatters."""

from __future__ import annotations

from html import escape
from typing import Any

from worldcupquente.i18n import text
from worldcupquente.team_translations import translated_team_name, translated_team_name_html


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


def format_standings_group_plain(group: dict[str, Any], language: str = "en") -> str:
    """Render a standings group as plain HTML (no rich ``<table>``/``<h3>``).

    Unlike :func:`format_standings_group_table`, this output is safe for inline
    mode messages (``InputTextMessageContent``), which do not support Telegram's
    rich message tags. The table is laid out inside a monospaced ``<pre>`` block.
    """
    entries = (group.get("standings") or {}).get("entries", [])
    title = _standings_group_title(group, language)
    if not entries:
        return f"<b>{escape(title)}</b>\n{text('standings_empty_group', language)}"

    header = (
        text("team", language),
        "Pts",
        text("played_short", language),
        text("wins_short", language),
        text("draws_short", language),
        text("losses_short", language),
        text("goals_for_short", language),
        text("goals_against_short", language),
        text("goal_diff_short", language),
    )
    rows: list[tuple[str, ...]] = [header]
    for entry in sorted(entries, key=_standings_entry_sort_key):
        stats = _standings_stats(entry)
        team = entry.get("team") or {}
        # No emoji inside <pre>: emoji widths break monospace column alignment.
        name = translated_team_name(team, include_emoji=False, language=language)
        rows.append(
            (
                name,
                _standings_stat(stats, "points"),
                _standings_stat(stats, "gamesPlayed"),
                _standings_stat(stats, "wins"),
                _standings_stat(stats, "ties"),
                _standings_stat(stats, "losses"),
                _standings_stat(stats, "pointsFor"),
                _standings_stat(stats, "pointsAgainst"),
                _standings_stat(stats, "pointDifferential"),
            )
        )

    columns = list(zip(*[[str(cell) for cell in row] for row in rows], strict=True))
    widths = [max(len(cell) for cell in column) for column in columns]
    body_lines = [
        "  ".join(str(cell).ljust(width) for cell, width in zip(row, widths, strict=True))
        for row in rows
    ]
    # Underline the header row to mark the separation from data rows.
    body_lines.insert(1, "  ".join("-" * width for width in widths))
    body = "\n".join(body_lines)
    footer = text("standings_footer", language)
    return f"<b>{escape(title)}</b>\n\n<pre>{escape(body)}</pre>\n\n{escape(footer)}"


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
