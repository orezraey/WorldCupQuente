"""Unit tests for SofaScore standings service methods."""

from __future__ import annotations

import asyncio
from typing import Any

from worldcupquente.config import Settings
from worldcupquente.services import WorldCupService


def test_sofascore_standings_groups_are_normalized_for_formatter():
    service = _service()
    fake_client = _FakeSofaScoreStandingsClient([_sofascore_group()])
    service.sofascore_client = fake_client  # type: ignore[assignment]

    groups = asyncio.run(service.get_sofascore_standings_groups())

    assert fake_client.calls == [(16, 58210)]
    assert len(groups) == 1
    group = groups[0]
    assert group["id"] == "1"
    assert group["name"] == "Group A"

    entry = group["standings"]["entries"][0]
    stats = {item["name"]: item["displayValue"] for item in entry["stats"]}

    assert entry["team"]["id"] == "4781"
    assert entry["team"]["name"] == "Mexico"
    assert stats == {
        "rank": "1",
        "points": "3",
        "gamesPlayed": "1",
        "wins": "1",
        "ties": "0",
        "losses": "0",
        "pointsFor": "2",
        "pointsAgainst": "0",
        "pointDifferential": "+2",
    }


def test_sofascore_standings_group_uses_normalized_group_id():
    service = _service()
    service.sofascore_client = _FakeSofaScoreStandingsClient([_sofascore_group()])  # type: ignore[assignment]

    group = asyncio.run(service.get_sofascore_standings_group("1"))

    assert group is not None
    assert group["name"] == "Group A"


def _service() -> WorldCupService:
    return WorldCupService(Settings(telegram_bot_token="test", bot_time_zone="UTC"))


class _FakeSofaScoreStandingsClient:
    def __init__(self, standings: list[dict[str, Any]]) -> None:
        self.standings = standings
        self.calls: list[tuple[int | str, int | str]] = []

    async def get_tournament_standings(
        self,
        unique_tournament_id: int | str,
        season_id: int | str,
    ) -> list[dict[str, Any]]:
        self.calls.append((unique_tournament_id, season_id))
        return self.standings


def _sofascore_group() -> dict[str, Any]:
    return {
        "name": "Group A",
        "groupSign": "A",
        "rows": [
            {
                "team": {
                    "id": 4781,
                    "name": "Mexico",
                    "shortName": "Mexico",
                    "nameCode": "MEX",
                    "country": {"alpha2": "MX"},
                },
                "position": 1,
                "matches": 1,
                "wins": 1,
                "draws": 0,
                "losses": 0,
                "scoresFor": 2,
                "scoresAgainst": 0,
                "points": 3,
                "scoreDiffFormatted": "+2",
            }
        ],
    }
