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


def format_win_probability(event: dict[str, Any], language: str = "en") -> list[str]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    home = _find_competitor(competitors, "home")
    away = _find_competitor(competitors, "away")
    if not home or not away:
        return []

    probabilities = _win_probabilities_from_event(event)
    if probabilities is None:
        return []

    home_team = home.get("team") or {}
    away_team = away.get("team") or {}
    home_name = translated_team_name_html(home_team, language=language) if home_team else text("home", language)
    away_name = translated_team_name_html(away_team, language=language) if away_team else text("away", language)

    return [
        f"<b>📊 {text('win_probability', language)}</b>",
        "<blockquote>"
        f"{home_name} {probabilities['home']}%\n"
        f"🤝 {text('draw', language)} {probabilities['draw']}%\n"
        f"{away_name} {probabilities['away']}%"
        "</blockquote>",
    ]


def _win_probabilities_from_event(event: dict[str, Any]) -> dict[str, int] | None:
    source = event.get("winProbability") or {}
    if not isinstance(source, dict):
        return None

    probabilities = {
        "home": _probability_value(source, "home", "homeWin"),
        "draw": _probability_value(source, "draw"),
        "away": _probability_value(source, "away", "awayWin"),
    }
    if any(value is None for value in probabilities.values()):
        return None

    values = {side: float(value) for side, value in probabilities.items() if value is not None}
    if max(values.values()) <= 1:
        values = {side: value * 100 for side, value in values.items()}
    return _normalize_probabilities(values)


def _probability_value(source: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _normalize_probabilities(probabilities: dict[str, float]) -> dict[str, int]:
    total = sum(probabilities.values())
    if total <= 0:
        return dict.fromkeys(probabilities, 0)

    normalized = {side: (probability / total) * 100 for side, probability in probabilities.items()}
    rounded = {side: int(value) for side, value in normalized.items()}
    remaining = 100 - sum(rounded.values())

    remainders = sorted(
        normalized,
        key=lambda side: normalized[side] - rounded[side],
        reverse=True,
    )
    for side in remainders[:remaining]:
        rounded[side] += 1
    return rounded
