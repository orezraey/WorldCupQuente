"""Unit tests for SofaScore calendar schedule service methods."""

from __future__ import annotations

import asyncio
from typing import Any

from worldcupquente.config import Settings
from worldcupquente.services import WorldCupService, _normalize_sofascore_event


def test_sofascore_schedule_combines_last_and_next_events_sorted_and_deduped():
    service = _service()
    calls: list[str] = []

    async def tournament_events(direction: str) -> list[dict[str, Any]]:
        calls.append(direction)
        if direction == "last":
            return [_raw_event(2, 1781802000), _raw_event(1, 1781715600)]
        return [_raw_event(2, 1781802000), _raw_event(3, 1781888400)]

    service._sofascore_tournament_events = tournament_events  # type: ignore[method-assign]

    events = asyncio.run(service.get_sofascore_schedule_events())

    assert calls == ["last", "next"]
    assert [event["id"] for event in events] == ["1", "2", "3"]


def test_sofascore_schedule_filters_by_date_and_team():
    service = _service()
    events = [
        _normalize_sofascore_event(_raw_event(1, 1781715600, home_id=4748, away_id=4704)),
        _normalize_sofascore_event(_raw_event(2, 1781802000, home_id=4752, away_id=4704)),
    ]

    async def schedule_events() -> list[dict[str, Any]]:
        return events

    service.get_sofascore_schedule_events = schedule_events  # type: ignore[method-assign]

    date_events = asyncio.run(service.get_sofascore_schedule_events_by_date("20260617"))
    team_events = asyncio.run(service.get_sofascore_schedule_events_by_team("4748"))

    assert [event["id"] for event in date_events] == ["1"]
    assert [event["id"] for event in team_events] == ["1"]


def _service() -> WorldCupService:
    return WorldCupService(Settings(telegram_bot_token="test", bot_time_zone="UTC"))


def _raw_event(
    event_id: int,
    timestamp: int,
    *,
    home_id: int = 4748,
    away_id: int = 4704,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "startTimestamp": timestamp,
        "status": {"type": "notstarted", "description": "Not started"},
        "homeTeam": {"id": home_id, "name": "Brazil", "nameCode": "BRA"},
        "awayTeam": {"id": away_id, "name": "Portugal", "nameCode": "POR"},
        "venue": {"name": "NRG Stadium"},
    }
