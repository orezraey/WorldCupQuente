"""Shared event helpers for live monitoring."""

from __future__ import annotations

from typing import Any


def _event_team_ids(event: dict[str, Any]) -> set[str]:
    competition = (event.get("competitions") or [{}])[0]
    return {
        str(((competitor.get("team") or {}).get("id")) or "")
        for competitor in competition.get("competitors", [])
        if ((competitor.get("team") or {}).get("id"))
    }


def _is_halftime_event(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    status_type = status.get("type") or {}
    if status_type.get("state") != "in":
        return False
    return any(part == "HT" or "HALFTIME" in part.upper() for part in _status_text_parts(status))


def _is_kickoff_event(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    status_type = status.get("type") or {}
    if status_type.get("state") != "in":
        return False
    return not _is_halftime_event(event)


def _is_full_time_event(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    status_type = status.get("type") or {}
    if status_type.get("state") != "post" and status_type.get("completed") is not True:
        return False
    return not _is_extra_time_or_penalties_status(status)


def _is_in_progress_event(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    status_type = status.get("type") or {}
    return status_type.get("state") == "in"


def _is_extra_time_or_penalties_status(status: dict[str, Any]) -> bool:
    for part in _status_text_parts(status):
        normalized = part.upper().replace("-", " ")
        if "FINAL" in normalized or normalized.startswith("FT") or normalized == "AET":
            continue
        if "EXTRA TIME" in normalized or normalized in {"ET", "1ET", "2ET"}:
            return True
        if "PENALT" in normalized or "PENS" in normalized or "SHOOTOUT" in normalized:
            return True
    return False


def _is_pre_game_event(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    status_type = status.get("type") or {}
    return status_type.get("state") == "pre"


def _event_status(event: dict[str, Any]) -> dict[str, Any]:
    competition = (event.get("competitions") or [{}])[0]
    return competition.get("status") or event.get("status") or {}


def _status_text_parts(status: dict[str, Any]) -> set[str]:
    status_type = status.get("type") or {}
    return {
        str(part)
        for part in [
            status.get("displayClock"),
            status_type.get("name"),
            status_type.get("description"),
            status_type.get("detail"),
            status_type.get("shortDetail"),
        ]
        if part
    }
