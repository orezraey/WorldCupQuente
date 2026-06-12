"""Common formatting utilities and constants."""

from __future__ import annotations

from html import escape
from typing import Any

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
