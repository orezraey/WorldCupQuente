"""Unit tests for SofaScore response normalization."""

from __future__ import annotations

import asyncio
from typing import Any

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
