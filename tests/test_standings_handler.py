"""Unit tests for standings handlers."""

from __future__ import annotations

import asyncio
from typing import Any

from worldcupquente.handlers import standings


def test_standings_menu_uses_sofascore_groups(monkeypatch):
    service = _FakeStandingsService()
    sent_messages: list[dict[str, Any]] = []

    async def send_message(*args: Any, **kwargs: Any) -> None:
        sent_messages.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(standings, "_get_service", lambda _context: service)

    asyncio.run(standings._send_standings_menu(send_message, _FakeContext(), "pt"))

    assert service.sofascore_group_list_calls == 1
    assert sent_messages
    keyboard = sent_messages[0]["kwargs"]["reply_markup"]
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.callback_data == "table:group:1" for button in buttons)


def test_standings_group_uses_sofascore_group(monkeypatch):
    service = _FakeStandingsService()
    context = _FakeContext()
    query = _FakeQuery("table:group:1")

    monkeypatch.setattr(standings, "_get_service", lambda _context: service)
    monkeypatch.setattr(standings, "_get_query_language", lambda _query, _context: "pt")

    asyncio.run(standings._send_standings_group(query, context, query.data))

    assert service.sofascore_group_calls == ["1"]
    assert context.bot.requests
    payload = context.bot.requests[0]["api_kwargs"]["rich_message"]["html"]
    assert "Tabela - Grupo A" in payload
    assert "México" in payload


class _FakeStandingsService:
    def __init__(self) -> None:
        self.sofascore_group_list_calls = 0
        self.sofascore_group_calls: list[str] = []

    async def get_sofascore_standings_groups(self) -> list[dict[str, Any]]:
        self.sofascore_group_list_calls += 1
        return [_standings_group()]

    async def get_sofascore_standings_group(self, group_id: str) -> dict[str, Any] | None:
        self.sofascore_group_calls.append(group_id)
        return _standings_group() if group_id == "1" else None

class _FakeContext:
    def __init__(self) -> None:
        self.bot = _FakeBot()


class _FakeBot:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    async def do_api_request(self, method: str, api_kwargs: dict[str, Any]) -> None:
        self.requests.append({"method": method, "api_kwargs": api_kwargs})


class _FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = _FakeMessage()
        self.edited_messages: list[dict[str, Any]] = []

    async def edit_message_text(self, *args: Any, **kwargs: Any) -> None:
        self.edited_messages.append({"args": args, "kwargs": kwargs})


class _FakeMessage:
    chat_id = 1
    message_id = 2


def _standings_group() -> dict[str, Any]:
    return {
        "id": "1",
        "name": "Group A",
        "standings": {
            "entries": [
                {
                    "team": {"id": "4781", "name": "Mexico", "country": {"alpha2": "MX"}},
                    "stats": [
                        {"name": "rank", "displayValue": "1"},
                        {"name": "points", "displayValue": "3"},
                        {"name": "gamesPlayed", "displayValue": "1"},
                        {"name": "wins", "displayValue": "1"},
                        {"name": "ties", "displayValue": "0"},
                        {"name": "losses", "displayValue": "0"},
                        {"name": "pointsFor", "displayValue": "2"},
                        {"name": "pointsAgainst", "displayValue": "0"},
                        {"name": "pointDifferential", "displayValue": "+2"},
                    ],
                }
            ]
        },
    }
