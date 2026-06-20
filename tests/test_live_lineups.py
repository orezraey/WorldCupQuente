"""Unit tests for live lineups and player detail callback flows."""

from __future__ import annotations

import asyncio
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.handlers import live


def test_live_lineup_entry_single_match_shows_lineups(monkeypatch):
    service = _FakeService(events=[_live_event("match-1")], lineups=_lineups_payload())
    query = _FakeQuery("live:lineup")
    context = _FakeContext()
    _patch(monkeypatch, service)

    asyncio.run(live.handle_live_callback(query, context))

    assert query.edited
    keyboard = query.edited[0]["kwargs"]["reply_markup"].inline_keyboard
    callbacks = [btn.callback_data for row in keyboard for btn in row]
    assert any(cb.startswith("live:pl:match-1:") for cb in callbacks)
    assert any("4-3-3" in arg for edited in query.edited for arg in edited["args"])


def test_live_lineup_entry_multiple_matches_shows_picker(monkeypatch):
    service = _FakeService(
        events=[_live_event("match-1", "USA", "Australia"), _live_event("match-2", "Brazil", "Japan")],
        lineups=_lineups_payload(),
    )
    query = _FakeQuery("live:lineup")
    context = _FakeContext()
    _patch(monkeypatch, service)

    asyncio.run(live.handle_live_callback(query, context))

    assert query.edited
    keyboard = query.edited[0]["kwargs"]["reply_markup"].inline_keyboard
    callbacks = [btn.callback_data for row in keyboard for btn in row]
    assert "live:lineup:pick:match-1" in callbacks
    assert "live:lineup:pick:match-2" in callbacks


def test_live_lineup_view_toggle_includes_subs(monkeypatch):
    service = _FakeService(events=[_live_event("match-1")], lineups=_lineups_payload(with_sub=True))
    query = _FakeQuery("live:lineup:view:match-1:1")
    context = _FakeContext()
    _patch(monkeypatch, service)

    asyncio.run(live.handle_live_callback(query, context))

    body = query.edited[0]["args"][0]
    assert "Sub Player" in body


def test_live_player_detail_sends_photo_and_stats(monkeypatch):
    service = _FakeService(
        events=[_live_event("match-1")],
        lineups=_lineups_payload(),
        detail=_player_detail(),
        image=b"photo-bytes",
    )
    query = _FakeQuery("live:pl:match-1:1:home")
    context = _FakeContext()
    _patch(monkeypatch, service)

    asyncio.run(live.handle_live_callback(query, context))

    assert query.message.photo_replies
    assert len(query.message.text_replies) == 1
    back_keyboard = query.message.text_replies[0]["kwargs"]["reply_markup"].inline_keyboard
    back_callback = back_keyboard[0][0].callback_data
    assert back_callback.startswith("live:pl:back:")


def test_live_player_detail_without_image_sends_text_only(monkeypatch):
    service = _FakeService(
        events=[_live_event("match-1")],
        lineups=_lineups_payload(),
        detail=_player_detail(),
        image=None,
    )
    query = _FakeQuery("live:pl:match-1:1:home")
    context = _FakeContext()
    _patch(monkeypatch, service)

    asyncio.run(live.handle_live_callback(query, context))

    assert not query.message.photo_replies
    assert len(query.message.text_replies) == 2


def test_live_player_detail_back_deletes_photo_and_stats(monkeypatch):
    service = _FakeService(events=[_live_event("match-1")], lineups=_lineups_payload())
    query = _FakeQuery("live:pl:back:200")
    context = _FakeContext()
    _patch(monkeypatch, service)

    asyncio.run(live.handle_live_callback(query, context))

    assert query.deleted is True
    assert (1, 200) in context.bot.deleted


def _patch(monkeypatch: Any, service: _FakeService) -> None:
    monkeypatch.setattr(live, "_get_service", lambda _context: service)
    monkeypatch.setattr(live, "_get_query_language", lambda _query, _context: "pt")


def _live_event(event_id: str, home: str = "USA", away: str = "Australia") -> dict[str, Any]:
    return {
        "id": event_id,
        "competitions": [
            {
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "h", "displayName": home, "name": home, "source": "sofascore"},
                        "score": "1",
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "a", "displayName": away, "name": away, "source": "sofascore"},
                        "score": "0",
                    },
                ]
            }
        ],
    }


def _lineups_payload(with_sub: bool = False) -> dict[str, Any]:
    players = [
        {
            "player": {"id": 1, "name": "Starter", "shortName": "Starter"},
            "shirtNumber": 10,
            "substitute": False,
            "statistics": {"rating": 7.1, "goals": 1, "minutesPlayed": 45},
        }
    ]
    if with_sub:
        players.append(
            {
                "player": {"id": 2, "name": "Sub Player", "shortName": "Sub Player"},
                "shirtNumber": 12,
                "substitute": True,
                "statistics": {"rating": 6.5},
            }
        )
    return {
        "confirmed": True,
        "home": {"formation": "4-3-3", "players": players},
        "away": {"formation": "5-4-1", "players": []},
    }


def _player_detail() -> dict[str, Any]:
    return {
        "shortName": "Starter",
        "position": "F",
        "team": {"shortName": "Some Club"},
        "country": {"name": "USA"},
        "height": 180,
        "preferredFoot": "Right",
        "dateOfBirthTimestamp": 700000000,
        "shirtNumber": 10,
    }


class _FakeService:
    bot_timezone = ZoneInfo("UTC")

    def __init__(
        self,
        *,
        events: list[dict[str, Any]],
        lineups: dict[str, Any],
        detail: dict[str, Any] | None = None,
        image: bytes | None = None,
    ) -> None:
        self._events = events
        self._lineups = lineups
        self._detail = detail or {}
        self._image = image

    async def get_sofascore_live_events(
        self,
        use_cache: bool = True,
        include_statistics: bool = False,
    ) -> list[dict[str, Any]]:
        del use_cache, include_statistics
        return self._events

    async def get_sofascore_match_lineups(self, _event_id: int | str) -> dict[str, Any]:
        return self._lineups

    async def get_sofascore_player_detail(self, _player_id: int | str) -> dict[str, Any]:
        return self._detail

    async def get_sofascore_player_image(self, _player_id: int | str) -> bytes | None:
        return self._image


class _FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = _FakeMessage()
        self.edited: list[dict[str, Any]] = []
        self.deleted = False

    async def edit_message_text(self, *args: Any, **kwargs: Any) -> None:
        self.edited.append({"args": args, "kwargs": kwargs})

    async def delete_message(self) -> bool:
        self.deleted = True
        return True


class _FakeMessage:
    chat_id = 1
    message_id = 10

    def __init__(self) -> None:
        self.text_replies: list[dict[str, Any]] = []
        self.photo_replies: list[dict[str, Any]] = []

    async def reply_text(self, *args: Any, **kwargs: Any) -> _FakeSentMessage:
        self.text_replies.append({"args": args, "kwargs": kwargs})
        return _FakeSentMessage(100)

    async def reply_photo(self, *args: Any, **kwargs: Any) -> _FakeSentMessage:
        self.photo_replies.append({"args": args, "kwargs": kwargs})
        return _FakeSentMessage(200)


class _FakeSentMessage:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class _FakeContext:
    def __init__(self) -> None:
        self.bot = _FakeBot()


class _FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))
