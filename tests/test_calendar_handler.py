"""Unit tests for calendar handlers."""

from __future__ import annotations

import asyncio
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.handlers import calendar


def test_calendar_dates_use_sofascore_schedule(monkeypatch):
    service = _FakeCalendarService()
    sent_messages: list[dict[str, Any]] = []

    async def send_message(*args: Any, **kwargs: Any) -> None:
        sent_messages.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(calendar, "_get_service", lambda _context: service)

    asyncio.run(calendar._send_calendar_dates(send_message, _FakeContext(), "pt"))

    assert service.sofascore_schedule_calls == 1
    assert sent_messages


def test_calendar_all_games_use_sofascore_schedule(monkeypatch):
    service = _FakeCalendarService()
    query = _FakeQuery("cal:all:0")
    _patch_calendar_helpers(monkeypatch, service)

    asyncio.run(calendar._send_calendar_all_games(query, _FakeContext(), query.data))

    assert service.sofascore_schedule_calls == 1
    assert query.edited_messages


def test_calendar_date_games_use_sofascore_date_filter(monkeypatch):
    service = _FakeCalendarService()
    query = _FakeQuery("cal:date:20260617")
    _patch_calendar_helpers(monkeypatch, service)

    asyncio.run(calendar._send_calendar_date_games(query, _FakeContext(), query.data))

    assert service.sofascore_date_calls == ["20260617"]
    assert query.edited_messages


def test_calendar_teams_page_uses_sofascore_teams_and_translation(monkeypatch):
    service = _FakeCalendarService()
    sent_messages: list[dict[str, Any]] = []

    async def send_message(*args: Any, **kwargs: Any) -> None:
        sent_messages.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(calendar, "_get_service", lambda _context: service)

    asyncio.run(calendar._send_calendar_teams_page(send_message, _FakeContext(), 0, "pt"))

    keyboard = sent_messages[0]["kwargs"]["reply_markup"]
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert service.sofascore_team_list_calls == 1
    assert any("Brasil" in button.text for button in buttons)
    assert any(button.callback_data == "cal:team:4748:0" for button in buttons)


def test_calendar_team_games_use_sofascore_team_filter(monkeypatch):
    service = _FakeCalendarService()
    query = _FakeQuery("cal:team:4748:0")
    _patch_calendar_helpers(monkeypatch, service)

    asyncio.run(calendar._send_calendar_team_games(query, _FakeContext(), query.data))

    assert service.sofascore_team_list_calls == 1
    assert service.sofascore_team_filter_calls == ["4748"]
    assert "Brasil" in query.edited_messages[0]["args"][0]


def _patch_calendar_helpers(monkeypatch: Any, service: _FakeCalendarService) -> None:
    monkeypatch.setattr(calendar, "_get_service", lambda _context: service)
    monkeypatch.setattr(calendar, "_get_query_language", lambda _query, _context: "pt")


class _FakeContext:
    pass


class _FakeCalendarService:
    bot_timezone = ZoneInfo("UTC")

    def __init__(self) -> None:
        self.sofascore_schedule_calls = 0
        self.sofascore_date_calls: list[str] = []
        self.sofascore_team_list_calls = 0
        self.sofascore_team_filter_calls: list[str] = []

    async def get_sofascore_schedule_events(self) -> list[dict[str, Any]]:
        self.sofascore_schedule_calls += 1
        return [_calendar_event("sofa-event-1")]

    async def get_sofascore_schedule_events_by_date(self, date_param: str) -> list[dict[str, Any]]:
        self.sofascore_date_calls.append(date_param)
        return [_calendar_event("sofa-event-1")]

    async def get_sofascore_schedule_events_by_team(self, team_id: str) -> list[dict[str, Any]]:
        self.sofascore_team_filter_calls.append(team_id)
        return [_calendar_event("sofa-event-1")]

    async def get_sofascore_world_cup_teams(self) -> list[dict[str, Any]]:
        self.sofascore_team_list_calls += 1
        return [{"id": 4748, "name": "Brazil", "nameCode": "BRA"}]

class _FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.edited_messages: list[dict[str, Any]] = []

    async def edit_message_text(self, *args: Any, **kwargs: Any) -> None:
        self.edited_messages.append({"args": args, "kwargs": kwargs})


def _calendar_event(event_id: str) -> dict[str, Any]:
    return {
        "id": event_id,
        "date": "2026-06-17T17:00:00Z",
        "competitions": [
            {
                "venue": {"fullName": "NRG Stadium"},
                "status": {"type": {"state": "pre", "completed": False, "shortDetail": "Scheduled"}},
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "4748", "displayName": "Brazil", "abbreviation": "BRA"},
                        "score": "-",
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "4704", "displayName": "Portugal", "abbreviation": "POR"},
                        "score": "-",
                    },
                ],
            }
        ],
    }
