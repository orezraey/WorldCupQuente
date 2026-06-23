"""Formatters for the knockout bracket projection."""

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from worldcupquente.i18n import text
from worldcupquente.playoff_bracket import (
    PlayoffProjection,
    ProjectedMatch,
    ProjectedRound,
    ProjectedSide,
)
from worldcupquente.team_translations import (
    translated_team_name,
    translated_team_name_html,
)

_ROUND_NAME_KEYS: dict[int, str] = {
    1: "playoff_round_of_32",
    2: "playoff_round_of_16",
    3: "playoff_quarterfinal",
    4: "playoff_semifinal",
    5: "playoff_final",
}


def format_playoff_bracket_rich(
    projection: PlayoffProjection,
    tz: ZoneInfo,
    language: str = "en",
) -> str:
    if not projection.rounds:
        return f"<h3>{escape(text('playoff_title', language))}</h3><p>{escape(text('playoff_empty', language))}</p>"

    sections = [f"<h3>{escape(text('playoff_title', language))}</h3>"]
    for rnd in projection.rounds:
        sections.append(_format_round_table_rich(rnd, tz, language))

    sections.append(f"<footer>{escape(text('playoff_disclaimer', language))}</footer>")
    return "".join(sections)


def format_playoff_bracket_plain(
    projection: PlayoffProjection,
    tz: ZoneInfo,
    language: str = "en",
) -> str:
    if not projection.rounds:
        return f"<b>{escape(text('playoff_title', language))}</b>\n{escape(text('playoff_empty', language))}"

    body_lines = [f"{text('playoff_title', language)}", ""]
    for rnd in projection.rounds:
        body_lines.append(_round_label(rnd, language))
        body_lines.append("-" * max(2, len(_round_label(rnd, language))))
        for match in rnd.matches:
            body_lines.append(_format_match_line_plain(match, tz, language))
        body_lines.append("")

    body = "\n".join(body_lines).rstrip()
    footer = text("playoff_disclaimer", language)
    return f"<b>{escape(text('playoff_title', language))}</b>\n\n<pre>{escape(body)}</pre>\n\n{escape(footer)}"


def _format_round_table_rich(
    rnd: ProjectedRound,
    tz: ZoneInfo,
    language: str,
) -> str:
    lines = [
        f"<h4>{escape(_round_label(rnd, language))}</h4>",
        "<table bordered striped>",
        "<tr>"
        f"<th>{text('playoff_match', language)}</th>"
        f"<th>{text('playoff_date', language)}</th>"
        "</tr>",
    ]
    for match in rnd.matches:
        lines.append(
            "<tr>"
            f"<td>{_format_match_sides_rich(match, language)}</td>"
            f'<td align="right">{escape(_format_match_date(match, tz, language))}</td>'
            "</tr>"
        )
    lines.append("</table>")
    return "".join(lines)


def _format_match_sides_rich(match: ProjectedMatch, language: str) -> str:
    home = _format_side_rich(match.home, language)
    away = _format_side_rich(match.away, language)
    if match.finished:
        return f"<s>{home}</s> x <s>{away}</s>"
    return f"{home} x {away}"


def _format_side_rich(side: ProjectedSide, language: str) -> str:
    if side.team:
        name = translated_team_name_html(side.team, language=language)
        return f"{name}{text('playoff_projected_badge', language) if side.projected else ''}"
    if side.ambiguous:
        return f'<i>{escape(side.seed or text("playoff_tbd", language))}</i>'
    return f'<i>{escape(text("playoff_tbd", language))}</i>'


def _format_match_line_plain(
    match: ProjectedMatch,
    tz: ZoneInfo,
    language: str,
) -> str:
    home = _format_side_plain(match.home, language)
    away = _format_side_plain(match.away, language)
    date_text = _format_match_date(match, tz, language)
    return f"{home} x {away}  {date_text}"


def _format_side_plain(side: ProjectedSide, language: str) -> str:
    if side.team:
        name = translated_team_name(side.team, include_emoji=False, language=language)
        suffix = text("playoff_projected_badge", language) if side.projected else ""
        return f"{name}{suffix}"
    if side.ambiguous:
        return side.seed or text("playoff_tbd", language)
    return text("playoff_tbd", language)


def _format_match_date(match: ProjectedMatch, tz: ZoneInfo, language: str) -> str:
    if not match.start_timestamp:
        return text("playoff_date_tbd", language)
    try:
        event_time = datetime.fromtimestamp(match.start_timestamp, tz)
    except (TypeError, OSError, ValueError):
        return text("playoff_date_tbd", language)
    weekdays = text("weekdays", language).split(",")
    weekday = weekdays[min(event_time.weekday(), len(weekdays) - 1)] if weekdays else ""
    return f"{weekday} {event_time.strftime('%d/%m %H:%M')}"


def _round_label(rnd: ProjectedRound, language: str) -> str:
    key = _ROUND_NAME_KEYS.get(rnd.order)
    if key:
        label = text(key, language)
        if label:
            return label
    return rnd.name or f"Round {rnd.order}"
