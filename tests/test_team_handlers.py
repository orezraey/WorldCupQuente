"""Unit tests for team handler callbacks."""

from __future__ import annotations

import asyncio
from typing import Any

from worldcupquente.handlers import teams
from worldcupquente.notification_preferences import TEAM_SCOPE_FOLLOWED


def test_sofascore_team_menu_uses_sofascore_id_for_notification_toggle(monkeypatch):
    query = _FakeQuery("team:menu:sofa-bra:0")
    preferences = _FakePreferences()
    _patch_team_helpers(monkeypatch, _FakeService(), preferences)

    asyncio.run(teams._send_team_menu(query, _FakeContext(), query.data))

    keyboard = query.edited_messages[0]["kwargs"]["reply_markup"]
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert any(button.text == "Habilitar notificações" for button in buttons)
    assert any(button.callback_data == "team:notify:sofa-bra:0" for button in buttons)


def test_sofascore_team_notification_toggle_stores_sofascore_id(monkeypatch):
    query = _FakeQuery("team:notify:sofa-bra:0")
    preferences = _FakePreferences()
    _patch_team_helpers(monkeypatch, _FakeService(), preferences)

    asyncio.run(teams._toggle_team_notifications(query, _FakeContext(), query.data))

    keyboard = query.edited_reply_markups[0]["reply_markup"]
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert preferences.followed == {"sofa-bra"}
    assert any(button.text == "Desabilitar notificações" for button in buttons)
    assert any(button.callback_data == "team:notify:sofa-bra:0" for button in buttons)


def test_legacy_five_part_callback_still_extracts_sofascore_id(monkeypatch):
    query = _FakeQuery("team:notify:bra:0:sofa-bra")
    preferences = _FakePreferences()
    _patch_team_helpers(monkeypatch, _FakeService(), preferences)

    asyncio.run(teams._toggle_team_notifications(query, _FakeContext(), query.data))

    assert preferences.followed == {"sofa-bra"}


def _patch_team_helpers(monkeypatch: Any, service: _FakeService, preferences: _FakePreferences) -> None:
    monkeypatch.setattr(teams, "_get_service", lambda _context: service)
    monkeypatch.setattr(teams, "_get_notification_preferences", lambda _context: preferences)
    monkeypatch.setattr(teams, "_get_query_language", lambda _query, _context: "pt")


class _FakeContext:
    pass


class _FakeService:
    bot_timezone = None

    async def get_sofascore_team_profile(self, _team_id: str) -> dict[str, Any]:
        return {"team": {"id": "sofa-bra", "name": "Brazil", "nameCode": "BRA"}}


class _FakePreferences:
    def __init__(self) -> None:
        self.followed: set[str] = set()

    def ensure_chat(self, _chat_id: int) -> None:
        return None

    def get_language(self, _chat_id: int) -> str:
        return "pt"

    def get_team_scope(self, _chat_id: int) -> str:
        return TEAM_SCOPE_FOLLOWED

    def is_following_team(self, _chat_id: int, team_id: str) -> bool:
        return team_id in self.followed

    def toggle_followed_team(self, _chat_id: int, team_id: str) -> dict[str, Any]:
        if team_id in self.followed:
            self.followed.remove(team_id)
        else:
            self.followed.add(team_id)
        return {}


class _FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = _FakeMessage()
        self.edited_messages: list[dict[str, Any]] = []
        self.edited_reply_markups: list[dict[str, Any]] = []

    async def edit_message_text(self, *args: Any, **kwargs: Any) -> None:
        self.edited_messages.append({"args": args, "kwargs": kwargs})

    async def edit_message_reply_markup(self, **kwargs: Any) -> None:
        self.edited_reply_markups.append(kwargs)


class _FakeMessage:
    chat_id = 1
