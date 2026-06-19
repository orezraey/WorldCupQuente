"""Event parsing and status helpers."""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any
from zoneinfo import ZoneInfo


def parse_event_datetime(value: str, tz: tzinfo) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(tz)


def _event_local_date_param(event: dict[str, Any], tz: ZoneInfo) -> str:
    event_time = parse_event_datetime(event.get("date", ""), tz)
    return event_time.strftime("%Y%m%d") if event_time else ""


def _event_has_team(event: dict[str, Any], team_id: str) -> bool:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    for competitor in competitors:
        team = competitor.get("team", {}) or {}
        if str(team.get("id", "")) == str(team_id):
            return True
    return False


def event_state(event: dict[str, Any]) -> str:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    return str((status.get("type") or {}).get("state") or "")
