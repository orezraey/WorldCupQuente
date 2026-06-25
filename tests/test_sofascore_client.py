"""Unit tests for SofaScore response normalization."""

from __future__ import annotations

import asyncio
from typing import Any

from worldcupquente import sofascore_client as sofascore_client_module
from worldcupquente.sofascore_client import SofaScoreClient, normalize_odds_win_probability


def test_normalize_odds_win_probability_uses_live_1x2_market():
    data = {
        "markets": [
            {
                "marketGroup": "1X2",
                "isLive": False,
                "choices": [
                    {"name": "1", "fractionalValue": "3/50"},
                    {"name": "X", "fractionalValue": "14/1"},
                    {"name": "2", "fractionalValue": "22/1"},
                ],
            },
            {
                "marketGroup": "1X2",
                "isLive": True,
                "choices": [
                    {"name": "1", "fractionalValue": "1/4"},
                    {"name": "X", "fractionalValue": "4/1"},
                    {"name": "2", "fractionalValue": "18/1"},
                ],
            },
        ]
    }

    assert normalize_odds_win_probability(data) == {"home": 76, "draw": 19, "away": 5}


def test_get_win_probability_prefers_direct_sofascore_probability():
    client = _FakeSofaScoreClient(
        {
            "/event/1/win-probability": {"winProbability": {"homeWin": 0.5, "draw": 0.3, "awayWin": 0.2}},
            "/event/1/odds/1/all": _odds_response(),
        }
    )

    assert asyncio.run(client.get_win_probability(1)) == {"home": 50, "draw": 30, "away": 20}
    assert client.paths == ["/event/1/win-probability"]


def test_get_win_probability_falls_back_to_sofascore_odds():
    client = _FakeSofaScoreClient(
        {
            "/event/1/win-probability": RuntimeError("404"),
            "/event/1/odds/1/all": _odds_response(),
        }
    )

    assert asyncio.run(client.get_win_probability(1)) == {"home": 76, "draw": 19, "away": 5}
    assert client.paths == ["/event/1/win-probability", "/event/1/odds/1/all"]


def test_get_match_incidents_returns_incidents_list():
    client = _FakeSofaScoreClient(
        {
            "/event/1/incidents": {"incidents": [{"id": 10, "type": "goal"}]},
        }
    )

    assert asyncio.run(client.get_match_incidents(1)) == [{"id": 10, "type": "goal"}]
    assert client.paths == ["/event/1/incidents"]


def test_get_match_incidents_returns_empty_list_on_failure():
    client = _FakeSofaScoreClient({"/event/1/incidents": RuntimeError("404")})

    assert asyncio.run(client.get_match_incidents(1)) == []
    assert client.paths == ["/event/1/incidents"]


def test_get_match_lineups_returns_payload():
    client = _FakeSofaScoreClient({"/event/1/lineups": {"home": {"players": []}}})

    assert asyncio.run(client.get_match_lineups(1)) == {"home": {"players": []}}
    assert client.paths == ["/event/1/lineups"]


def test_get_match_statistics_returns_statistics_list():
    client = _FakeSofaScoreClient({"/event/1/statistics": {"statistics": [{"period": "ALL"}]}})

    assert asyncio.run(client.get_match_statistics(1)) == [{"period": "ALL"}]
    assert client.paths == ["/event/1/statistics"]


def test_get_tournament_events_returns_events_and_pagination_flag():
    client = _FakeSofaScoreClient(
        {"/unique-tournament/16/season/58210/events/last/0": {"events": [{"id": 1}], "hasNextPage": True}}
    )

    assert asyncio.run(client.get_tournament_events(16, 58210, "last")) == {
        "events": [{"id": 1}],
        "hasNextPage": True,
    }
    assert client.paths == ["/unique-tournament/16/season/58210/events/last/0"]


def test_get_tournament_standings_returns_standings_list():
    client = _FakeSofaScoreClient(
        {"/unique-tournament/16/season/58210/standings/total": {"standings": [{"id": 1}]}}
    )

    assert asyncio.run(client.get_tournament_standings(16, 58210)) == [{"id": 1}]
    assert client.paths == ["/unique-tournament/16/season/58210/standings/total"]


def test_get_event_returns_inner_event_payload():
    client = _FakeSofaScoreClient({"/event/1": {"event": {"id": 1}}})

    assert asyncio.run(client.get_event(1)) == {"id": 1}
    assert client.paths == ["/event/1"]


def test_get_player_detail_returns_inner_player_payload():
    client = _FakeSofaScoreClient({"/player/9": {"player": {"id": 9, "name": "Player Nine"}}})

    assert asyncio.run(client.get_player_detail(9)) == {"id": 9, "name": "Player Nine"}
    assert client.paths == ["/player/9"]


def test_get_player_detail_returns_empty_on_failure():
    client = _FakeSofaScoreClient({"/player/9": RuntimeError("404")})

    assert asyncio.run(client.get_player_detail(9)) == {}
    assert client.paths == ["/player/9"]


def test_get_player_image_returns_bytes(monkeypatch):
    client = SofaScoreClient(timeout=1, user_agent="test")
    monkeypatch.setattr(
        sofascore_client_module.requests,
        "AsyncSession",
        _make_image_session_factory(b"image-bytes"),
    )
    result = asyncio.run(client.get_player_image(9))
    assert result == b"image-bytes"


def test_get_player_image_returns_none_on_non_image_content_type(monkeypatch):
    client = SofaScoreClient(timeout=1, user_agent="test")
    monkeypatch.setattr(
        sofascore_client_module.requests,
        "AsyncSession",
        _make_image_session_factory(b"{}", content_type="application/json", status=403),
    )
    assert asyncio.run(client.get_player_image(9)) is None


def test_get_player_image_returns_none_on_request_error(monkeypatch):
    client = SofaScoreClient(timeout=1, user_agent="test")
    monkeypatch.setattr(
        sofascore_client_module.requests,
        "AsyncSession",
        _make_image_session_factory(b"", raise_error=True),
    )
    assert asyncio.run(client.get_player_image(9)) is None


def _make_image_session_factory(
    content: bytes,
    *,
    content_type: str = "image/webp",
    status: int = 200,
    raise_error: bool = False,
):
    def factory(**_kwargs: object) -> _FakeImageSession:
        return _FakeImageSession(content, content_type=content_type, status=status, raise_error=raise_error)

    return factory


class _FakeImageSession:
    def __init__(
        self,
        content: bytes = b"",
        *,
        content_type: str = "image/webp",
        status: int = 200,
        raise_error: bool = False,
    ) -> None:
        self._content = content
        self._content_type = content_type
        self._status = status
        self._raise_error = raise_error

    async def __aenter__(self) -> _FakeImageSession:
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    async def get(self, _url: str, headers: dict[str, str] | None = None) -> _FakeImageResponse:
        del headers
        if self._raise_error:
            raise sofascore_client_module.requests.errors.RequestsError("boom")
        return _FakeImageResponse(self._status, self._content, self._content_type)


class _FakeImageResponse:
    def __init__(self, status: int, content: bytes, content_type: str) -> None:
        self.status_code = status
        self.content = content
        self.headers = {"content-type": content_type}


class _FakeSofaScoreClient(SofaScoreClient):
    def __init__(self, responses: dict[str, dict[str, Any] | Exception]) -> None:
        super().__init__(timeout=1, user_agent="test")
        self.responses = responses
        self.paths: list[str] = []

    async def get_json(self, path: str, *, quiet_statuses: tuple[int, ...] = ()) -> dict[str, Any]:
        del quiet_statuses
        self.paths.append(path)
        response = self.responses[path]
        if isinstance(response, Exception):
            raise response
        return response


def _odds_response() -> dict[str, Any]:
    return {
        "markets": [
            {
                "marketGroup": "1X2",
                "isLive": True,
                "choices": [
                    {"name": "1", "fractionalValue": "1/4"},
                    {"name": "X", "fractionalValue": "4/1"},
                    {"name": "2", "fractionalValue": "18/1"},
                ],
            }
        ]
    }
