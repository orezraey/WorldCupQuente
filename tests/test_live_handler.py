"""Unit tests for live command callback behavior."""

from __future__ import annotations

import asyncio
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.handlers import live


def test_today_command_uses_sofascore_today_games(monkeypatch):
    service = _FakeService()
    context = _FakeContext(service)
    update = _FakeUpdate()
    monkeypatch.setattr(live, "_get_service", lambda _context: service)
    monkeypatch.setattr(live, "_get_chat_language", lambda _update, _context: "pt")
    monkeypatch.setattr(live, "_log_command", lambda _update, _context, _command: None)

    asyncio.run(live.today_command(update, context))

    assert service.today_calls == 1
    assert update.effective_message.replies


def test_live_command_uses_sofascore_live_events(monkeypatch):
    service = _FakeService()
    context = _FakeContext(service)
    update = _FakeUpdate()
    monkeypatch.setattr(live, "_get_service", lambda _context: service)
    monkeypatch.setattr(live, "_get_chat_language", lambda _update, _context: "pt")
    monkeypatch.setattr(live, "_log_command", lambda _update, _context, _command: None)

    asyncio.run(live.live_command(update, context))

    assert service.live_calls == 1
    assert update.effective_message.replies


def test_live_stats_callback_does_not_enrich_sofascore_ratings(monkeypatch):
    query = _FakeQuery("live:stats:show")
    service = _FakeService()
    context = _FakeContext(service)
    _patch_live_helpers(monkeypatch, service)

    asyncio.run(live._send_live_games(query, context, show_stats=True))

    assert service.ratings_enriched is False
    assert service.last_include_statistics is True
    rich_message = context.bot.edited_messages[0]["api_kwargs"]["rich_message"]
    assert "Notas SofaScore" not in rich_message["html"]


def test_live_plain_callback_does_not_enrich_sofascore_ratings(monkeypatch):
    query = _FakeQuery("live:stats:hide")
    service = _FakeService()
    context = _FakeContext(service)
    _patch_live_helpers(monkeypatch, service)

    asyncio.run(live._send_live_games(query, context, show_stats=False))

    assert service.ratings_enriched is False
    assert query.edited_messages


def test_live_ratings_callback_enriches_sofascore_ratings(monkeypatch):
    query = _FakeQuery("live:ratings:show")
    service = _FakeService()
    context = _FakeContext(service)
    _patch_live_helpers(monkeypatch, service)

    asyncio.run(live.handle_live_callback(query, context))

    assert service.ratings_enriched is True
    rich_message = context.bot.edited_messages[0]["api_kwargs"]["rich_message"]
    assert "Notas SofaScore" in rich_message["html"]
    assert 'emoji-id="5431497092281421497"' in rich_message["html"]


class _FakeService:
    bot_timezone = ZoneInfo("UTC")

    def __init__(self) -> None:
        self.ratings_enriched = False
        self.today_calls = 0
        self.live_calls = 0
        self.last_include_statistics: bool | None = None

    async def get_sofascore_today_games(self) -> dict[str, Any]:
        self.today_calls += 1
        return {"events": [_live_event()]}

    async def get_sofascore_live_events(
        self,
        use_cache: bool = True,
        include_statistics: bool = False,
    ) -> list[dict[str, Any]]:
        del use_cache
        self.live_calls += 1
        self.last_include_statistics = include_statistics
        return [_live_event()]

    async def enrich_events_sofascore_player_ratings(
        self,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        self.ratings_enriched = True
        events[0]["sofascorePlayerRatings"] = {
            "home": [{"name": "Home Player", "rating": 7.8}],
            "away": [{"name": "Away Player", "rating": 7.2}],
        }
        return events


def _patch_live_helpers(monkeypatch: Any, service: _FakeService) -> None:
    monkeypatch.setattr(live, "_get_service", lambda _context: service)
    monkeypatch.setattr(live, "_get_query_language", lambda _query, _context: "pt")


class _FakeContext:
    def __init__(self, service: _FakeService) -> None:
        self.application = _FakeApplication(service)
        self.bot = _FakeBot()


class _FakeApplication:
    def __init__(self, service: _FakeService) -> None:
        self.bot_data = {
            "world_cup_service": service,
            "notification_preferences": _FakePreferences(),
        }


class _FakePreferences:
    def ensure_chat(self, _chat_id: int) -> None:
        return None

    def get_language(self, _chat_id: int) -> str:
        return "pt"


class _FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = _FakeMessage()
        self.edited_messages: list[dict[str, Any]] = []

    async def answer(self) -> None:
        return None

    async def edit_message_text(self, *args: Any, **kwargs: Any) -> None:
        self.edited_messages.append({"args": args, "kwargs": kwargs})


class _FakeMessage:
    chat_id = 1
    message_id = 10

    def __init__(self) -> None:
        self.replies: list[dict[str, Any]] = []

    async def reply_text(self, *args: Any, **kwargs: Any) -> None:
        self.replies.append({"args": args, "kwargs": kwargs})


class _FakeUpdate:
    def __init__(self) -> None:
        self.effective_message = _FakeMessage()


class _FakeBot:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.edited_messages: list[dict[str, Any]] = []

    async def edit_message_text(self, **kwargs: Any) -> None:
        self.edited_messages.append(kwargs)

    async def do_api_request(self, _method: str, api_kwargs: dict[str, Any]) -> None:
        self.requests.append(api_kwargs)


def _live_event() -> dict[str, Any]:
    return {
        "id": "match-1",
        "date": "2026-06-12T19:00:00Z",
        "competitions": [
            {
                "status": {
                    "type": {"state": "in", "shortDetail": "First Half"},
                    "displayClock": "22'",
                },
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "home", "displayName": "Netherlands", "abbreviation": "NED"},
                        "score": "1",
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "away", "displayName": "Japan", "abbreviation": "JPN"},
                        "score": "0",
                    },
                ],
                "venue": {"fullName": "BMO Field"},
            }
        ],
    }
