"""Unit tests for finished match history handlers."""

from __future__ import annotations

import asyncio
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.handlers import history


def test_history_page_uses_sofascore_finished_events(monkeypatch):
    service = _FakeHistoryService()
    sent_messages: list[dict[str, Any]] = []

    async def send_message(*args: Any, **kwargs: Any) -> None:
        sent_messages.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(history, "_get_service", lambda _context: service)

    asyncio.run(history._send_history_page(send_message, _FakeContext(), 0, "pt"))

    assert service.sofascore_list_calls == 1
    assert sent_messages


def test_history_game_uses_sofascore_finished_event_details(monkeypatch):
    service = _FakeHistoryService()
    query = _FakeQuery()

    monkeypatch.setattr(history, "_get_service", lambda _context: service)
    monkeypatch.setattr(history, "_get_query_language", lambda _query, _context: "pt")

    asyncio.run(history._send_history_game(query, _FakeContext(), "sofa-event-1", 0))

    assert service.sofascore_detail_calls == ["sofa-event-1"]
    assert query.edited_messages


class _FakeContext:
    pass


class _FakeHistoryService:
    bot_timezone = ZoneInfo("UTC")

    def __init__(self) -> None:
        self.sofascore_list_calls = 0
        self.sofascore_detail_calls: list[str] = []

    async def get_sofascore_finished_events(self) -> list[dict[str, Any]]:
        self.sofascore_list_calls += 1
        return [_history_event("sofa-event-1")]

    async def get_sofascore_finished_event_details(self, event_id: str) -> dict[str, Any]:
        self.sofascore_detail_calls.append(event_id)
        return _history_event(event_id)

class _FakeQuery:
    def __init__(self) -> None:
        self.edited_messages: list[dict[str, Any]] = []

    async def edit_message_text(self, *args: Any, **kwargs: Any) -> None:
        self.edited_messages.append({"args": args, "kwargs": kwargs})


def _history_event(event_id: str) -> dict[str, Any]:
    return {
        "id": event_id,
        "date": "2026-06-17T17:00:00Z",
        "competitions": [
            {
                "venue": {"fullName": "NRG Stadium"},
                "status": {"type": {"state": "post", "completed": True, "shortDetail": "FT"}},
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "4704", "displayName": "Portugal", "abbreviation": "POR"},
                        "score": "1",
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "4752", "displayName": "DR Congo", "abbreviation": "DCO"},
                        "score": "1",
                    },
                ],
            }
        ],
    }
