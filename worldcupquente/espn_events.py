"""ESPN event parsing, validation and status normalization utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

LIVE_STATUS_FALLBACK_WINDOW = timedelta(hours=3)


def parse_espn_datetime(value: str, tz: tzinfo) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(tz)


def _event_local_date_param(event: dict[str, Any], tz: ZoneInfo) -> str:
    event_time = parse_espn_datetime(event.get("date", ""), tz)
    return event_time.strftime("%Y%m%d") if event_time else ""


def _event_has_team(event: dict[str, Any], team_id: str) -> bool:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    for competitor in competitors:
        team = competitor.get("team", {}) or {}
        if str(team.get("id", "")) == str(team_id):
            return True
    return False


def live_events_from_scoreboard(
    scoreboard: dict[str, Any],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    return [event for event in scoreboard.get("events", []) if is_live_event(event, current_time)]


def is_live_event(event: dict[str, Any], now: datetime | None = None) -> bool:
    state = event_state(event)
    if state == "in":
        return True
    if state != "pre":
        return False

    event_time = parse_espn_datetime(event.get("date", ""), UTC)
    if event_time is None:
        return False

    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    current_time = current_time.astimezone(UTC)

    return event_time <= current_time <= event_time + LIVE_STATUS_FALLBACK_WINDOW


def event_state(event: dict[str, Any]) -> str:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    return str((status.get("type") or {}).get("state") or "")


def event_from_summary(
    summary: dict[str, Any],
    fallback_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback_event = fallback_event or {}
    header = summary.get("header") or {}
    competition = ((header.get("competitions") or [{}])[0]).copy()
    if not competition:
        return fallback_event

    fallback_competition = (fallback_event.get("competitions") or [{}])[0]
    fallback_status = fallback_competition.get("status") or fallback_event.get("status") or {}
    competition_status = competition.get("status") or {}
    if competition_status or fallback_status:
        competition["status"] = _merge_status(competition_status, fallback_status)

    venue = ((summary.get("gameInfo") or {}).get("venue") or fallback_event.get("venue") or {}).copy()
    if venue:
        competition.setdefault("venue", venue)

    event = fallback_event.copy()
    event.update(
        {
            "id": header.get("id") or fallback_event.get("id"),
            "uid": header.get("uid") or fallback_event.get("uid"),
            "date": competition.get("date") or fallback_event.get("date"),
            "competitions": [competition],
            "status": competition.get("status") or fallback_event.get("status"),
            "venue": venue or fallback_event.get("venue"),
            "boxscore": summary.get("boxscore") or {},
            "leaders": summary.get("leaders") or [],
            "commentary": summary.get("commentary") or [],
            "rosters": summary.get("rosters") or [],
            "scoringPlays": summary.get("scoringPlays") or [],
        }
    )
    return event


def _merge_status(status: dict[str, Any], fallback_status: dict[str, Any]) -> dict[str, Any]:
    merged = fallback_status.copy()
    merged.update(status)

    fallback_type = fallback_status.get("type") or {}
    status_type = status.get("type") or {}
    if fallback_type or status_type:
        merged["type"] = {**fallback_type, **status_type}
    return merged
