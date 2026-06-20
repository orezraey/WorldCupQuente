"""Live match lineups and single player detail formatters."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from typing import Any

from worldcupquente.i18n import text

_RATING_STAR = "⭐"

_PLAYER_STAT_LABELS: dict[str, dict[str, str]] = {
    "minutesPlayed": {"en": "Minutes played", "pt": "Minutos jogados"},
    "rating": {"en": "Rating", "pt": "Nota"},
    "goals": {"en": "Goals", "pt": "Gols"},
    "expectedGoals": {"en": "Expected goals (xG)", "pt": "Gols esperados (xG)"},
    "assists": {"en": "Assists", "pt": "Assistências"},
    "expectedAssists": {"en": "Expected assists (xA)", "pt": "Assistências esperadas (xA)"},
    "totalShots": {"en": "Shots", "pt": "Finalizações"},
    "shotsOnTarget": {"en": "Shots on target", "pt": "Finalizações no alvo"},
    "shotsOffTarget": {"en": "Shots off target", "pt": "Finalizações para fora"},
    "blockedScoringAttempt": {"en": "Blocked shots", "pt": "Finalizações bloqueadas"},
    "hitWoodwork": {"en": "Hit woodwork", "pt": "Na trave"},
    "bigChanceMissed": {"en": "Big chances missed", "pt": "Oportunidades claras perdidas"},
    "bigChanceCreated": {"en": "Big chances created", "pt": "Oportunidades claras criadas"},
    "totalPass": {"en": "Passes", "pt": "Passes"},
    "accuratePass": {"en": "Accurate passes", "pt": "Passes certos"},
    "totalLongBalls": {"en": "Long balls", "pt": "Bolas longas"},
    "accurateLongBalls": {"en": "Accurate long balls", "pt": "Bolas longas certas"},
    "totalCross": {"en": "Crosses", "pt": "Cruzamentos"},
    "accurateCross": {"en": "Accurate crosses", "pt": "Cruzamentos certos"},
    "totalOwnHalfPasses": {"en": "Own-half passes", "pt": "Passes no próprio campo"},
    "accurateOwnHalfPasses": {"en": "Accurate own-half passes", "pt": "Passes certos no próprio campo"},
    "totalOppositionHalfPasses": {"en": "Opposition-half passes", "pt": "Passes no campo adversário"},
    "accurateOppositionHalfPasses": {"en": "Accurate opposition-half passes", "pt": "Passes certos no campo adversário"},
    "totalFinalThirdPasses": {"en": "Final-third passes", "pt": "Passes no terço final"},
    "accurateFinalThirdPasses": {"en": "Accurate final-third passes", "pt": "Passes certos no terço final"},
    "keyPasses": {"en": "Key passes", "pt": "Passes decisivos"},
    "smartPasses": {"en": "Smart passes", "pt": "Passes inteligentes"},
    "accurateSmartPasses": {"en": "Accurate smart passes", "pt": "Passes inteligentes certos"},
    "totalCornerKicks": {"en": "Corner kicks", "pt": "Escanteios"},
    "touches": {"en": "Touches", "pt": "Toques na bola"},
    "duelWon": {"en": "Duels won", "pt": "Duelos vencidos"},
    "duelLost": {"en": "Duels lost", "pt": "Duelos perdidos"},
    "dispossessed": {"en": "Dispossessed", "pt": "Desarmado"},
    "possessionLostCtrl": {"en": "Possession lost", "pt": "Perdas de posse"},
    "ballRecovery": {"en": "Ball recoveries", "pt": "Recuperações de bola"},
    "interception": {"en": "Interceptions", "pt": "Interceptações"},
    "totalTackle": {"en": "Tackles", "pt": "Carrinhos"},
    "totalClearance": {"en": "Clearances", "pt": "Cortes"},
    "blockedPass": {"en": "Blocked passes", "pt": "Passes bloqueados"},
    "foulGiven": {"en": "Fouls won", "pt": "Faltas sofridas"},
    "wasFouled": {"en": "Fouls won", "pt": "Faltas sofridas"},
    "foulCommitted": {"en": "Fouls committed", "pt": "Faltas cometidas"},
    "yellowCards": {"en": "Yellow cards", "pt": "Cartões amarelos"},
    "redCards": {"en": "Red cards", "pt": "Cartões vermelhos"},
    "offsides": {"en": "Offsides", "pt": "Impedimentos"},
    "penaltyWon": {"en": "Penalties won", "pt": "Pênaltis sofridos"},
    "penaltyConceded": {"en": "Penalties conceded", "pt": "Pênaltis causados"},
    "penaltyScored": {"en": "Penalties scored", "pt": "Pênaltis convertidos"},
    "penaltyMissed": {"en": "Penalties missed", "pt": "Pênaltis perdidos"},
    "errorLeadToGoal": {"en": "Errors leading to goal", "pt": "Erros que levaram a gol"},
    "errorLeadToShot": {"en": "Errors leading to shot", "pt": "Erros que levaram a finalização"},
    "saves": {"en": "Saves", "pt": "Defesas"},
    "savedShotsFromInsideTheBox": {"en": "Saves from inside the box", "pt": "Defesas na área"},
    "goalsPrevented": {"en": "Goals prevented", "pt": "Gols evitados"},
    "totalKeeperSweeper": {"en": "Sweeper actions", "pt": "Ações fora da área"},
    "accurateKeeperSweeper": {"en": "Accurate sweeper actions", "pt": "Ações fora da área certas"},
    "keeperSaveValue": {"en": "Keeper save value", "pt": "Valor de defesa do goleiro"},
    "passValueNormalized": {"en": "Passing value", "pt": "Valor nos passes"},
    "defensiveValueNormalized": {"en": "Defensive value", "pt": "Valor defensivo"},
    "goalkeeperValueNormalized": {"en": "Goalkeeper value", "pt": "Valor como goleiro"},
    "expectedGoalsOnTarget": {"en": "Expected goals on target", "pt": "Finalizações no alvo esperadas"},
}


def format_match_lineups(
    lineups: dict[str, Any],
    home_name: str,
    away_name: str,
    *,
    show_subs: bool = False,
    language: str = "en",
) -> str:
    home = lineups.get("home") or {}
    away = lineups.get("away") or {}
    home_players = home.get("players") or []
    away_players = away.get("players") or []
    if not home_players and not away_players:
        return text("lineup_empty", language)

    lines = [f"<b>{_RATING_STAR} {text('lineup_title', language)}</b>", ""]

    for side_name, side_data, side_players in (
        (home_name, home, home_players),
        (away_name, away, away_players),
    ):
        formation = side_data.get("formation")
        header = escape(str(side_name or text("team", language)))
        if formation:
            header = f"{header} ({escape(str(formation))})"
        lines.append(f"<b>{header}</b>")
        lines.append(f"<b>{text('lineup_starters', language)}</b>")
        starters = [p for p in side_players if not p.get("substitute")]
        for player in starters:
            lines.append(_format_lineup_player(player, language))
        if show_subs:
            subs = [p for p in side_players if p.get("substitute")]
            if subs:
                lines.append(f"<b>{text('lineup_subs', language)}</b>")
                for player in subs:
                    lines.append(_format_lineup_player(player, language))
        lines.append("")
    return "\n".join(lines).strip()


def format_player_detail_caption(
    detail: dict[str, Any],
    *,
    rating: float | None = None,
    language: str = "en",
) -> str:
    if not isinstance(detail, dict) or not detail:
        return text("player_not_found", language)

    name = detail.get("shortName") or detail.get("name") or text("player", language)
    lines = [f"<b>{escape(str(name))}</b>", ""]

    rating_line = (
        f"{_RATING_STAR} <b>{text('player_rating_label', language)}</b>: {_format_rating(rating)}"
        if rating is not None
        else None
    )
    if rating_line:
        lines.append(rating_line)
        lines.append("")

    lines.append(f"<b>{text('player_personal_title', language)}</b>")
    rows = [
        (text("position_label", language), _position_label(detail.get("position"), language)),
        (text("club_label", language), _team_name(detail.get("team"))),
        (text("nationality_label", language), _country_name(detail.get("country"))),
        (text("height_label", language), _format_height(detail.get("height"))),
        (text("weight_label", language), _format_weight(detail.get("weight"))),
        (text("preferred_foot_label", language), _foot_label(detail.get("preferredFoot"), language)),
        (text("birth_date_label", language), _format_birth_date(detail.get("dateOfBirthTimestamp"))),
        (text("shirt_number_label", language), detail.get("shirtNumber") or detail.get("jerseyNumber")),
    ]
    for label, value in rows:
        if value not in (None, "", "-"):
            lines.append(f"{escape(str(label))}: {escape(str(value))}")
    return "\n".join(lines)


def format_player_match_statistics(
    player_item: dict[str, Any],
    *,
    language: str = "en",
) -> str:
    lines = [f"<b>{_RATING_STAR} {text('player_match_stats_title', language)}</b>", ""]
    if not isinstance(player_item, dict):
        lines.append(text("player_no_stats", language))
        return "\n".join(lines)

    statistics = player_item.get("statistics")
    if not isinstance(statistics, dict) or not statistics:
        lines.append(text("player_no_stats", language))
        return "\n".join(lines)

    for key, value in statistics.items():
        if key in {"ratingVersions", "statisticsType"}:
            continue
        if value is None or value == "":
            continue
        label = _stat_label(key, language)
        lines.append(f"{escape(label)}: {escape(_format_stat_value(value))}")
    return "\n".join(lines)


def lineup_player_rating(player_item: dict[str, Any]) -> float | None:
    if not isinstance(player_item, dict):
        return None
    statistics = player_item.get("statistics") if isinstance(player_item.get("statistics"), dict) else {}
    value = statistics.get("rating") if isinstance(statistics, dict) else None
    if value is None:
        value = player_item.get("rating")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_lineup_player(player_item: dict[str, Any], language: str) -> str:
    player = player_item.get("player") or {}
    name = player.get("shortName") or player.get("name") or text("player", language)
    shirt = player_item.get("shirtNumber") or player.get("shirtNumber") or player_item.get("jerseyNumber")
    rating = lineup_player_rating(player_item)
    shirt_text = f"#{escape(str(shirt))} " if shirt not in (None, "") else ""
    rating_text = f" <b>{_format_rating(rating)}</b>" if rating is not None else ""
    return f"- {shirt_text}{escape(str(name))}{rating_text}"


def _format_rating(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "-"


def _format_stat_value(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 100 or number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _stat_label(key: str, language: str) -> str:
    entry = _PLAYER_STAT_LABELS.get(key)
    if entry:
        return entry.get(language) or entry.get("en") or _humanize_key(key)
    return _humanize_key(key)


def _humanize_key(key: str) -> str:
    result: list[str] = []
    for index, char in enumerate(key):
        if char.isupper() and index > 0:
            result.append(" ")
        result.append(char)
    return "".join(result).capitalize()


def _position_label(position: Any, language: str) -> str:
    key = {
        "G": "position_goalkeeper",
        "D": "position_defender",
        "M": "position_midfielder",
        "F": "position_forward",
    }.get(str(position or "").upper())
    return text(key, language) if key else (str(position) if position else "")


def _team_name(team: Any) -> str:
    if not isinstance(team, dict):
        return ""
    return str(team.get("shortName") or team.get("name") or "")


def _country_name(country: Any) -> str:
    if not isinstance(country, dict):
        return ""
    return str(country.get("name") or "")


def _format_height(height: Any) -> str:
    try:
        return f"{int(height)} cm"
    except (TypeError, ValueError):
        return ""


def _format_weight(weight: Any) -> str:
    try:
        return f"{int(weight)} kg"
    except (TypeError, ValueError):
        return ""


def _foot_label(foot: Any, language: str) -> str:
    normalized = str(foot or "").strip().lower()
    if normalized in {"right", "direito", "r"}:
        return text("foot_right", language)
    if normalized in {"left", "esquerdo", "l"}:
        return text("foot_left", language)
    return text("foot_unknown", language)


def _format_birth_date(timestamp: Any) -> str:
    try:
        seconds = int(timestamp)
    except (TypeError, ValueError):
        return ""
    birth = datetime.fromtimestamp(seconds, tz=UTC)
    age = _age_years(birth)
    formatted_date = birth.strftime("%d/%m/%Y")
    if age is None:
        return formatted_date
    return f"{formatted_date} ({age})"


def _age_years(birth: datetime) -> int | None:
    now = datetime.now(tz=UTC)
    age = now.year - birth.year
    if (now.month, now.day) < (birth.month, birth.day):
        age -= 1
    if age < 0 or age > 120:
        return None
    return age
