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

    probabilities = _win_probabilities_from_odds(event)
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


def _win_probabilities_from_odds(event: dict[str, Any]) -> dict[str, int] | None:
    state = _event_state(event)
    priority = ("current", "close", "live", "open") if state == "pre" else ("live", "current", "close", "open")
    for odds in _event_odds(event):
        probabilities = _moneyline_probabilities(odds, priority)
        if probabilities is not None:
            return _normalize_probabilities(probabilities)
    return None


def _event_state(event: dict[str, Any]) -> str:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    return str((status.get("type") or {}).get("state") or "")


def _event_odds(event: dict[str, Any]) -> list[dict[str, Any]]:
    competition = (event.get("competitions") or [{}])[0]
    sources = [competition.get("odds"), event.get("odds")]
    odds: list[dict[str, Any]] = []
    for source in sources:
        if isinstance(source, dict):
            odds.append(source)
            continue
        if isinstance(source, list):
            odds.extend(item for item in source if isinstance(item, dict))
    return odds


def _moneyline_probabilities(
    odds: dict[str, Any],
    priority: tuple[str, ...],
) -> dict[str, float] | None:
    moneyline = odds.get("moneyline") or {}
    if not isinstance(moneyline, dict):
        return None

    probabilities: dict[str, float] = {}
    for side in ("home", "draw", "away"):
        side_data = moneyline.get(side) or {}
        if not isinstance(side_data, dict):
            return None
        probability = _side_probability(side_data, priority)
        if probability is None:
            return None
        probabilities[side] = probability
    return probabilities


def _side_probability(side_data: dict[str, Any], priority: tuple[str, ...]) -> float | None:
    for key in priority:
        market = side_data.get(key) or {}
        if not isinstance(market, dict):
            continue
        probability = _implied_probability(market.get("odds"))
        if probability is not None:
            return probability
    return None


def _implied_probability(value: Any) -> float | None:
    odds = _parse_american_odds(value)
    if odds is None or odds == 0:
        return None
    if odds > 0:
        return 100 / (odds + 100)
    odds = abs(odds)
    return odds / (odds + 100)


def _parse_american_odds(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    odds_text = str(value).strip().upper()
    if odds_text in {"EVEN", "EV"}:
        return 100.0
    if odds_text.startswith("+"):
        odds_text = odds_text[1:]
    try:
        return float(odds_text)
    except ValueError:
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
