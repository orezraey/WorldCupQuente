"""Common formatting utilities and constants."""

from __future__ import annotations

from html import escape
from typing import Any

from worldcupquente.i18n import status_text, text
from worldcupquente.team_translations import translated_team_name_html

TELEGRAM_MESSAGE_LIMIT = 3900
RECENT_COMMENTARY_LIMIT = 5
RED_CARD_EMOJI = '<tg-emoji emoji-id="5336787196479294713">🟥</tg-emoji>'
LIVE_TITLE_EMOJI = '<tg-emoji emoji-id="5850297493593529930">🏆</tg-emoji>'
LIVE_STATS_TITLE_EMOJI = '<tg-emoji emoji-id="5296265790654264117">📊</tg-emoji>'
LIVE_STAT_LEADER_EMOJI = '<tg-emoji emoji-id="5821342125458985363">🔥</tg-emoji>'
LIVE_STAT_LABEL_EMOJIS = {
    "possession": '<tg-emoji emoji-id="4958712589895861234">⚽</tg-emoji>',
    "shots": '<tg-emoji emoji-id="4958562394889520477">🥅</tg-emoji>',
    "on_target": '<tg-emoji emoji-id="5449862290834735715">🎯</tg-emoji>',
    "corners": '<tg-emoji emoji-id="4958711348650312955">🚩</tg-emoji>',
    "fouls": '<tg-emoji emoji-id="4958638587609351070">🦵</tg-emoji>',
    "passes": '<tg-emoji emoji-id="4958604885000979612">⚽</tg-emoji>',
    "crosses": '<tg-emoji emoji-id="4958910665197618290">📐</tg-emoji>',
    "tackles": '<tg-emoji emoji-id="4958645180384150616">🛡</tg-emoji>',
    "saves": '<tg-emoji emoji-id="4958484449823031980">🧤</tg-emoji>',
    "cards": (
        '<tg-emoji emoji-id="4958881820197258277">🟨</tg-emoji> '
        '<tg-emoji emoji-id="4958873294687175681">🟥</tg-emoji>'
    ),
}

LIVE_STAT_LABELS = {
    "totalShots": "shots",
    "accuratePasses": "accurate_passes",
    "defensiveInterventions": "defensive_interventions",
    "saves": "saves",
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


def _translated_status(status: str, language: str = "en") -> str:
    return status_text(status, language)


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
    language: str = "en",
) -> str:
    home_team = (home or {}).get("team", {})
    away_team = (away or {}).get("team", {})
    home_name = translated_team_name_html(home_team, language=language) if home_team else text("home", language)
    away_name = translated_team_name_html(away_team, language=language) if away_team else text("away", language)

    if state == "pre":
        return f"{home_name} x {away_name}"

    home_score = (home or {}).get("score", "-")
    away_score = (away or {}).get("score", "-")
    return f"{home_name} {escape(str(home_score))} x {escape(str(away_score))} {away_name}"
