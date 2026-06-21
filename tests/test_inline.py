"""Unit tests for inline mode handlers and helpers."""

from __future__ import annotations

import asyncio
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.formatters import format_standings_group_plain
from worldcupquente.handlers import inline
from worldcupquente.keyboards import (
    build_inline_back_keyboard,
    build_inline_groups_list_keyboard,
    build_inline_player_back_keyboard,
    build_inline_squad_keyboard,
    build_inline_team_menu_keyboard,
)
from worldcupquente.team_translations import filter_teams_by_name

# ---------------------------------------------------------------------------
# filter_teams_by_name
# ---------------------------------------------------------------------------


def _team(team_id: str, name: str) -> dict[str, Any]:
    return {
        "id": team_id,
        "name": name,
        "shortName": name,
        "displayName": name,
        "shortDisplayName": name,
        "source": "sofascore",
    }


def test_filter_teams_exact_match_english_name():
    teams = [_team("205", "Brazil"), _team("202", "Argentina")]

    result = filter_teams_by_name(teams, "Brazil")

    assert [team["id"] for team in result] == ["205"]


def test_filter_teams_matches_portuguese_name():
    teams = [_team("205", "Brazil")]

    result = filter_teams_by_name(teams, "Brasil")

    assert [team["id"] for team in result] == ["205"]


def test_filter_teams_accent_insensitive():
    # "franca" (no cedilla) must match "França" (Portuguese for France).
    teams = [_team("478", "France")]

    result = filter_teams_by_name(teams, "franca")

    assert [team["id"] for team in result] == ["478"]


def test_filter_teams_case_insensitive_prefix_and_ranking():
    # "ARG" is a prefix; Brazil is an exact-enough prefix too but Argentina
    # ranks first because the cased query matches its name start exactly.
    teams = [_team("205", "Brazil"), _team("202", "Argentina")]

    result = filter_teams_by_name(teams, "arg")

    assert result[0]["id"] == "202"


def test_filter_teams_substring_match():
    # "korea" is a substring of "South Korea".
    teams = [_team("451", "South Korea")]

    result = filter_teams_by_name(teams, "korea")

    assert [team["id"] for team in result] == ["451"]


def test_filter_teams_alias_resolves_usa():
    teams = [_team("660", "United States")]

    result = filter_teams_by_name(teams, "USA")

    assert [team["id"] for team in result] == ["660"]


def test_filter_teams_no_match_returns_empty():
    teams = [_team("205", "Brazil")]

    assert filter_teams_by_name(teams, "zzz") == []


def test_filter_teams_empty_query_returns_all_teams_in_order():
    teams = [_team("205", "Brazil"), _team("202", "Argentina")]

    result = filter_teams_by_name(teams, "", limit=10)

    assert [team["id"] for team in result] == ["205", "202"]


# ---------------------------------------------------------------------------
# format_standings_group_plain
# ---------------------------------------------------------------------------


def test_format_standings_group_plain_has_no_rich_tags():
    group = {
        "id": "1",
        "name": "Group A",
        "standings": {
            "entries": [
                {
                    "team": {"id": "203", "name": "Mexico", "country": {"alpha2": "MX"}},
                    "stats": [
                        {"name": "rank", "displayValue": "1"},
                        {"name": "points", "displayValue": "3"},
                    ],
                }
            ]
        },
    }

    rendered = format_standings_group_plain(group, "pt")

    assert "<table" not in rendered
    assert "<h3>" not in rendered
    assert "<footer>" not in rendered
    assert "<pre>" in rendered
    assert "Tabela - Grupo A" in rendered
    assert "México" in rendered


def test_format_standings_group_plain_empty_group():
    group = {"id": "1", "name": "Group A", "standings": {"entries": []}}

    rendered = format_standings_group_plain(group, "en")

    assert "<pre>" not in rendered
    assert "No standings found" in rendered


# ---------------------------------------------------------------------------
# inline_query_handler
# ---------------------------------------------------------------------------


def test_inline_query_returns_one_article_per_team(monkeypatch):
    service = _FakeService(teams=[_team("205", "Brazil"), _team("202", "Argentina")])
    update = _FakeInlineUpdate("bra")
    monkeypatch.setattr(inline, "_get_service", lambda _context: service)

    asyncio.run(inline.inline_query_handler(update, _FakeContext()))

    answered = update.inline_query.answered
    assert answered is not None
    ids = [result.id for result in answered["results"]]
    assert "205" in ids
    assert "202" not in ids  # "bra" only matches Brazil.
    assert answered["kwargs"]["cache_time"] == inline.INLINE_CACHE_SECONDS


def test_inline_query_empty_query_returns_all_teams_sorted(monkeypatch):
    service = _FakeService(teams=[_team("205", "Brazil"), _team("202", "Argentina")])
    update = _FakeInlineUpdate("")
    monkeypatch.setattr(inline, "_get_service", lambda _context: service)

    asyncio.run(inline.inline_query_handler(update, _FakeContext()))

    ids = [result.id for result in update.inline_query.answered["results"]]
    # Alphabetical: Argentina before Brazil.
    assert ids == ["202", "205"]


def test_inline_query_no_results_returns_fallback_article(monkeypatch):
    service = _FakeService(teams=[_team("205", "Brazil")])
    update = _FakeInlineUpdate("zzz")
    monkeypatch.setattr(inline, "_get_service", lambda _context: service)

    asyncio.run(inline.inline_query_handler(update, _FakeContext()))

    results = update.inline_query.answered["results"]
    assert len(results) == 1
    assert results[0].id == "inline-no-results"


def test_inline_query_team_article_has_four_button_keyboard(monkeypatch):
    service = _FakeService(teams=[_team("205", "Brazil")])
    update = _FakeInlineUpdate("Brazil")
    monkeypatch.setattr(inline, "_get_service", lambda _context: service)

    asyncio.run(inline.inline_query_handler(update, _FakeContext()))

    article = update.inline_query.answered["results"][0]
    buttons = [button for row in article.reply_markup.inline_keyboard for button in row]
    callbacks = {button.callback_data for button in buttons}
    assert callbacks == {
        "inl:last:205",
        "inl:next:205",
        "inl:players:205:0",
        "inl:group:205",
    }


# ---------------------------------------------------------------------------
# handle_inline_callback
# ---------------------------------------------------------------------------


def _patch_inline_helpers(monkeypatch: Any, service: _FakeService) -> None:
    monkeypatch.setattr(inline, "_get_service", lambda _context: service)
    monkeypatch.setattr(inline, "_get_inline_callback_language", lambda _query: "pt")


def test_inline_callback_menu_renders_profile(monkeypatch):
    service = _FakeService()
    query = _FakeCallbackQuery("inl:menu:205")
    _patch_inline_helpers(monkeypatch, service)

    asyncio.run(inline.handle_inline_callback(query, _FakeContext()))

    assert service.profile_calls == ["205"]
    text = query.edited_messages[0]["args"][0]
    assert "Brasil" in text
    keyboard = query.edited_messages[0]["kwargs"]["reply_markup"]
    callbacks = {b.callback_data for row in keyboard.inline_keyboard for b in row}
    assert "inl:last:205" in callbacks


def test_inline_callback_last_events_uses_service(monkeypatch):
    service = _FakeService()
    query = _FakeCallbackQuery("inl:last:205")
    _patch_inline_helpers(monkeypatch, service)

    asyncio.run(inline.handle_inline_callback(query, _FakeContext()))

    assert service.event_calls == [("205", "last")]
    assert service.profile_calls == ["205"]
    text = query.edited_messages[0]["args"][0]
    assert "Últimos jogos" in text


def test_inline_callback_next_events_uses_service(monkeypatch):
    service = _FakeService()
    query = _FakeCallbackQuery("inl:next:205")
    _patch_inline_helpers(monkeypatch, service)

    asyncio.run(inline.handle_inline_callback(query, _FakeContext()))

    assert service.event_calls == [("205", "next")]
    text = query.edited_messages[0]["args"][0]
    assert "Próximos jogos" in text


def test_inline_callback_players_renders_squad_grid(monkeypatch):
    service = _FakeService(
        players=[
            {"player": {"id": 1, "name": "Neymar", "shortName": "Neymar", "position": "F", "shirtNumber": 10}},
            {"player": {"id": 2, "name": "Alisson", "shortName": "Alisson", "position": "G", "shirtNumber": 1}},
        ]
    )
    query = _FakeCallbackQuery("inl:players:205:0")
    _patch_inline_helpers(monkeypatch, service)

    asyncio.run(inline.handle_inline_callback(query, _FakeContext()))

    header = query.edited_messages[0]["args"][0]
    assert "Elenco geral" in header
    keyboard = query.edited_messages[0]["kwargs"]["reply_markup"]
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    # Both players become tappable buttons (sorted: goalkeeper first).
    assert "inl:player:205:2" in callbacks
    assert "inl:player:205:1" in callbacks
    assert callbacks[-1] == "inl:menu:205"


def test_inline_callback_player_detail_renders_caption(monkeypatch):
    service = _FakeService()
    query = _FakeCallbackQuery("inl:player:205:1")
    _patch_inline_helpers(monkeypatch, service)

    asyncio.run(inline.handle_inline_callback(query, _FakeContext()))

    assert service.player_detail_calls == ["1"]
    caption = query.edited_messages[0]["args"][0]
    assert "Neymar" in caption
    assert "Altura" in caption  # height label (pt)
    keyboard = query.edited_messages[0]["kwargs"]["reply_markup"]
    button = keyboard.inline_keyboard[0][0]
    assert button.callback_data == "inl:players:205:0"
    assert button.text == "Voltar ao elenco"


def test_inline_callback_group_found_renders_rich_table(monkeypatch):
    service = _FakeService()
    context = _FakeContext()
    query = _FakeCallbackQuery("inl:group:205")
    _patch_inline_helpers(monkeypatch, service)

    asyncio.run(inline.handle_inline_callback(query, context))

    assert service.standings_group_list_calls == 1
    # Rich path was used (via do_api_request), not a plain text edit.
    assert context.bot.rich_requests
    html = context.bot.rich_requests[0]["api_kwargs"]["rich_message"]["html"]
    assert "<table" in html
    assert query.edited_messages == []


def test_inline_callback_group_falls_back_to_plain_when_rich_fails(monkeypatch):
    service = _FakeService()
    context = _FakeContext(_FakeBot(raise_rich=True))
    query = _FakeCallbackQuery("inl:group:205")
    _patch_inline_helpers(monkeypatch, service)

    asyncio.run(inline.handle_inline_callback(query, context))

    assert context.bot.rich_requests == []  # attempted but raised
    rendered = query.edited_messages[0]["args"][0]
    assert "<pre>" in rendered  # plain fallback
    assert "Brasil" in rendered


def test_inline_callback_group_not_found_lists_all_groups(monkeypatch):
    service = _FakeService()
    query = _FakeCallbackQuery("inl:group:9999")  # team not in any group
    _patch_inline_helpers(monkeypatch, service)

    asyncio.run(inline.handle_inline_callback(query, _FakeContext()))

    keyboard = query.edited_messages[0]["kwargs"]["reply_markup"]
    callbacks = {b.callback_data for row in keyboard.inline_keyboard for b in row}
    assert "inl:groupopen:9999:1" in callbacks
    assert "inl:menu:9999" in callbacks


def test_inline_callback_group_open_renders_specific_group(monkeypatch):
    service = _FakeService()
    context = _FakeContext()
    query = _FakeCallbackQuery("inl:groupopen:205:1")
    _patch_inline_helpers(monkeypatch, service)

    asyncio.run(inline.handle_inline_callback(query, context))

    assert service.standings_group_calls == ["1"]
    assert context.bot.rich_requests
    html = context.bot.rich_requests[0]["api_kwargs"]["rich_message"]["html"]
    assert "<table" in html


def test_inline_callback_invalid_team_shows_error(monkeypatch):
    service = _FakeService()
    query = _FakeCallbackQuery("inl:menu:")
    _patch_inline_helpers(monkeypatch, service)

    asyncio.run(inline.handle_inline_callback(query, _FakeContext()))

    assert service.profile_calls == []
    assert "Seleção inválida" in query.edited_messages[0]["args"][0]


# ---------------------------------------------------------------------------
# keyboards
# ---------------------------------------------------------------------------


def test_build_inline_team_menu_keyboard_has_four_buttons():
    keyboard = build_inline_team_menu_keyboard("205", "pt")

    callbacks = {b.callback_data for row in keyboard.inline_keyboard for b in row}
    assert callbacks == {"inl:last:205", "inl:next:205", "inl:players:205:0", "inl:group:205"}


def test_build_inline_back_keyboard():
    keyboard = build_inline_back_keyboard("205", "pt")

    button = keyboard.inline_keyboard[0][0]
    assert button.callback_data == "inl:menu:205"
    assert button.text == "Voltar ao menu"


def test_build_inline_squad_keyboard_sorts_by_position_then_shirt():
    players = [
        {"player": {"id": 1, "name": "Neymar", "shortName": "Neymar", "position": "F", "shirtNumber": 10}},
        {"player": {"id": 2, "name": "Alisson", "shortName": "Alisson", "position": "G", "shirtNumber": 1}},
        {"player": {"id": 3, "name": "Marquinhos", "shortName": "Marquinhos", "position": "D", "shirtNumber": 4}},
    ]
    keyboard = build_inline_squad_keyboard("205", players, "pt")

    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    # Goalkeeper (G) first, then defender (D), then forward (F).
    assert callbacks == ["inl:player:205:2", "inl:player:205:3", "inl:player:205:1", "inl:menu:205"]
    labels = [b.text for row in keyboard.inline_keyboard for b in row]
    assert "#10 Neymar" in labels
    assert "#1 Alisson" in labels


def test_build_inline_player_back_keyboard():
    keyboard = build_inline_player_back_keyboard("205", "pt")

    button = keyboard.inline_keyboard[0][0]
    assert button.callback_data == "inl:players:205:0"
    assert button.text == "Voltar ao elenco"


def test_build_inline_groups_list_keyboard():
    groups = [{"id": "1", "name": "Group A"}, {"id": "2", "name": "Group B"}]
    keyboard = build_inline_groups_list_keyboard("205", groups, "pt")

    callbacks = {b.callback_data for row in keyboard.inline_keyboard for b in row}
    assert "inl:groupopen:205:1" in callbacks
    assert "inl:groupopen:205:2" in callbacks
    assert "inl:menu:205" in callbacks


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _player_detail() -> dict[str, Any]:
    return {
        "id": 1,
        "name": "Neymar Jr",
        "shortName": "Neymar",
        "position": "F",
        "team": {"shortName": "Santos"},
        "country": {"name": "Brazil"},
        "height": 175,
        "weight": 68,
        "preferredFoot": "Right",
        "dateOfBirthTimestamp": 631152000,
        "shirtNumber": 10,
    }


class _FakeUser:
    def __init__(self, language_code: str = "pt") -> None:
        self.language_code = language_code
        self.id = 123


class _FakeInlineQuery:
    def __init__(self, query: str, language_code: str = "pt") -> None:
        self.query = query
        self.from_user = _FakeUser(language_code)
        self.answered: dict[str, Any] | None = None

    async def answer(self, results: list[Any], **kwargs: Any) -> None:
        self.answered = {"results": results, "kwargs": kwargs}


class _FakeInlineUpdate:
    def __init__(self, query: str, language_code: str = "pt") -> None:
        self.inline_query = _FakeInlineQuery(query, language_code)


class _FakeCallbackQuery:
    def __init__(self, data: str, language_code: str = "pt") -> None:
        self.data = data
        self.from_user = _FakeUser(language_code)
        self.message = None  # inline messages have no message object
        self.inline_message_id = "inline-msg-1"
        self.edited_messages: list[dict[str, Any]] = []

    async def edit_message_text(self, *args: Any, **kwargs: Any) -> None:
        self.edited_messages.append({"args": args, "kwargs": kwargs})


class _FakeContext:
    def __init__(self, bot: _FakeBot | None = None) -> None:
        self.bot = bot if bot is not None else _FakeBot()


class _FakeBot:
    def __init__(self, raise_rich: bool = False) -> None:
        self.raise_rich = raise_rich
        self.rich_requests: list[dict[str, Any]] = []

    async def do_api_request(self, method: str, api_kwargs: dict[str, Any] | None = None) -> None:
        if self.raise_rich:
            raise RuntimeError("rich message not supported")
        self.rich_requests.append({"method": method, "api_kwargs": api_kwargs or {}})


class _FakeService:
    bot_timezone = ZoneInfo("UTC")

    def __init__(
        self,
        teams: list[dict[str, Any]] | None = None,
        players: list[dict[str, Any]] | None = None,
    ) -> None:
        self._teams = teams if teams is not None else [_team("205", "Brazil")]
        self._players = players
        self.profile_calls: list[str] = []
        self.event_calls: list[tuple[str, str]] = []
        self.player_detail_calls: list[str] = []
        self.standings_group_list_calls = 0
        self.standings_group_calls: list[str] = []

    async def get_sofascore_world_cup_teams(self) -> list[dict[str, Any]]:
        return self._teams

    async def get_sofascore_team_profile(self, team_id: str) -> dict[str, Any]:
        self.profile_calls.append(team_id)
        return {"team": _team(team_id, "Brazil")}

    async def get_sofascore_team_events(self, team_id: str, direction: str) -> list[dict[str, Any]]:
        self.event_calls.append((team_id, direction))
        state = "notstarted" if direction == "next" else "finished"
        return [
            {
                "id": "evt-1",
                "startTimestamp": 1700000000,
                "status": {"type": state, "description": "Final" if state == "finished" else ""},
                "homeTeam": _team(team_id, "Brazil"),
                "awayTeam": _team("202", "Argentina"),
                "homeScore": {"current": 2},
                "awayScore": {"current": 1},
                "tournament": {"name": "World Cup 2026"},
            }
        ]

    async def get_sofascore_team_players(self, _team_id: str) -> list[dict[str, Any]]:
        if self._players is not None:
            return self._players
        return [
            {
                "player": {"id": 1, "name": "Neymar", "shortName": "Neymar", "position": "F"},
                "shirtNumber": 10,
            }
        ]

    async def get_sofascore_player_detail(self, player_id: int | str) -> dict[str, Any]:
        self.player_detail_calls.append(str(player_id))
        return _player_detail()

    async def get_sofascore_standings_groups(self) -> list[dict[str, Any]]:
        self.standings_group_list_calls += 1
        return [_standings_group_with_brazil()]

    async def get_sofascore_standings_group(self, group_id: str) -> dict[str, Any] | None:
        self.standings_group_calls.append(group_id)
        return _standings_group_with_brazil() if group_id == "1" else None


def _standings_group_with_brazil() -> dict[str, Any]:
    return {
        "id": "1",
        "name": "Group A",
        "standings": {
            "entries": [
                {
                    "team": {"id": "205", "name": "Brazil", "country": {"alpha2": "BR"}},
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
