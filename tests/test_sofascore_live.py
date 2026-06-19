"""Unit tests for SofaScore today and live service methods."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from worldcupquente.config import Settings
from worldcupquente.services import WorldCupService


def test_sofascore_today_games_filters_world_cup_events():
    service = _service()
    fake_client = _FakeSofaScoreLiveClient(
        scheduled_events={
            service.sofascore_date_param_for_offset(): [
                _raw_event(1, timestamp=_date_timestamp(service.sofascore_date_param_for_offset()), tournament_id=16, season_id=58210),
                _raw_event(2, timestamp=_date_timestamp(service.sofascore_date_param_for_offset()), tournament_id=99, season_id=58210),
            ]
        }
    )
    service.sofascore_client = fake_client  # type: ignore[assignment]

    scoreboard = asyncio.run(service.get_sofascore_today_games())

    assert [event["id"] for event in scoreboard["events"]] == ["1"]
    assert fake_client.scheduled_calls == [service.sofascore_date_param_for_offset()]


def test_sofascore_games_by_date_filters_returned_events_by_local_date():
    service = _service()
    fake_client = _FakeSofaScoreLiveClient(
        scheduled_events={
            "2026-06-18": [
                _raw_event(1, timestamp=1781715600),
                _raw_event(2, timestamp=1781784000),
            ]
        }
    )
    service.sofascore_client = fake_client  # type: ignore[assignment]

    events = asyncio.run(service.get_sofascore_games_by_date("2026-06-18"))

    assert [event["id"] for event in events] == ["2"]


def test_sofascore_games_by_date_hydrates_missing_venue_from_event_detail():
    service = _service()
    fake_client = _FakeSofaScoreLiveClient(
        scheduled_events={"2026-06-18": [_raw_event(10, timestamp=_date_timestamp("2026-06-18"))]},
        event_details={10: {"venue": {"name": "Mercedes-Benz Stadium", "stadium": {"name": "Mercedes-Benz Stadium"}}}},
    )
    service.sofascore_client = fake_client  # type: ignore[assignment]

    events = asyncio.run(service.get_sofascore_games_by_date("2026-06-18"))

    assert fake_client.event_detail_calls == ["10"]
    assert events[0]["venue"]["fullName"] == "Mercedes-Benz Stadium"
    assert events[0]["competitions"][0]["venue"]["fullName"] == "Mercedes-Benz Stadium"


def test_sofascore_live_events_filter_and_enrich_live_matches():
    service = _service()
    today = service.sofascore_date_param_for_offset()
    fake_client = _FakeSofaScoreLiveClient(
        scheduled_events={
            service.sofascore_date_param_for_offset(-1): [],
            today: [
                _raw_event(10, timestamp=_date_timestamp(today), status_type="inprogress", description="2nd half"),
                _raw_event(11, timestamp=_date_timestamp(today), status_type="notstarted", description="Not started"),
            ],
            service.sofascore_date_param_for_offset(1): [],
        },
        incidents={10: [_goal_incident()]},
        statistics={10: _statistics_response()},
        probabilities={10: {"home": 50, "draw": 30, "away": 20}},
    )
    service.sofascore_client = fake_client  # type: ignore[assignment]

    events = asyncio.run(service.get_sofascore_live_events(use_cache=False, include_statistics=True))

    assert [event["id"] for event in events] == ["10"]
    event = events[0]
    competitors = event["competitions"][0]["competitors"]

    assert event["winProbability"] == {"home": 50, "draw": 30, "away": 20, "source": "sofascore"}
    assert event["sofascoreIncidents"]["goals"][0]["clock"]["displayValue"] == "69'"
    assert {stat["name"]: stat["displayValue"] for stat in competitors[0]["statistics"]} == {
        "possessionPct": "55%",
        "totalShots": "10",
        "shotsOnTarget": "4",
        "wonCorners": "6",
        "totalPasses": "783",
        "accuratePasses": "724",
        "accurateCrosses": "6/23 (26%)",
        "totalTackles": "12",
    }


def test_sofascore_monitor_events_return_status_and_enriched_live_events():
    service = _service()
    today = service.sofascore_date_param_for_offset()
    fake_client = _FakeSofaScoreLiveClient(
        scheduled_events={
            service.sofascore_date_param_for_offset(-1): [],
            today: [
                _raw_event(20, timestamp=_date_timestamp(today), status_type="inprogress", description="1st half"),
                _raw_event(21, timestamp=_date_timestamp(today), status_type="notstarted", description="Not started"),
            ],
            service.sofascore_date_param_for_offset(1): [],
        },
        incidents={20: [_goal_incident()]},
    )
    service.sofascore_client = fake_client  # type: ignore[assignment]

    events = asyncio.run(service.get_sofascore_monitor_events(use_cache=False))

    assert [event["id"] for event in events["status_events"]] == ["20", "21"]
    assert [event["id"] for event in events["live_events"]] == ["20"]
    assert events["live_events"][0]["sofascoreIncidents"]["goals"]


def test_sofascore_player_ratings_use_native_event_id():
    service = _service()
    fake_client = _FakeSofaScoreLiveClient(lineups={10: _lineups_response()})
    service.sofascore_client = fake_client  # type: ignore[assignment]

    event = _normalized_live_event(10)

    enriched = asyncio.run(service.enrich_event_sofascore_player_ratings(event))

    assert fake_client.lineup_calls == ["10"]
    assert enriched["sofascorePlayerRatings"]["home"][0]["name"] == "Home Player"


def test_sofascore_team_id_mapping_matches_legacy_ids_by_name():
    service = _service()
    fake_client = _FakeSofaScoreLiveClient(
        world_cup_teams=[
            {"id": 4748, "name": "Brazil", "nameCode": "BRA"},
            {"id": 4704, "name": "Portugal", "nameCode": "POR"},
        ]
    )
    service.sofascore_client = fake_client  # type: ignore[assignment]

    mapping = asyncio.run(service.get_sofascore_team_id_mapping())

    assert mapping["205"] == "4748"
    assert mapping["482"] == "4704"


def _service() -> WorldCupService:
    return WorldCupService(Settings(telegram_bot_token="test", bot_time_zone="UTC"))


def _date_timestamp(date_param: str) -> int:
    return int(datetime.strptime(date_param, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()) + 3600


class _FakeSofaScoreLiveClient:
    def __init__(
        self,
        *,
        scheduled_events: dict[str, list[dict[str, Any]]] | None = None,
        incidents: dict[int, list[dict[str, Any]]] | None = None,
        statistics: dict[int, list[dict[str, Any]]] | None = None,
        probabilities: dict[int, dict[str, int]] | None = None,
        lineups: dict[int, dict[str, Any]] | None = None,
        world_cup_teams: list[dict[str, Any]] | None = None,
        event_details: dict[int, dict[str, Any]] | None = None,
    ) -> None:
        self.scheduled_events = scheduled_events or {}
        self.incidents = incidents or {}
        self.statistics = statistics or {}
        self.probabilities = probabilities or {}
        self.lineups = lineups or {}
        self._world_cup_teams = world_cup_teams or []
        self.event_details = event_details or {}
        self.scheduled_calls: list[str] = []
        self.lineup_calls: list[str] = []
        self.event_detail_calls: list[str] = []

    async def get_world_cup_teams(self, _tournament_id: int | str, _season_id: int | str) -> list[dict[str, Any]]:
        return self._world_cup_teams

    async def get_scheduled_events(self, date: str) -> list[dict[str, Any]]:
        self.scheduled_calls.append(date)
        return self.scheduled_events.get(date, [])

    async def get_event(self, event_id: int | str, suppress_errors: bool = True) -> dict[str, Any]:
        del suppress_errors
        self.event_detail_calls.append(str(event_id))
        return self.event_details.get(int(event_id), {})

    async def get_match_incidents(self, event_id: int | str) -> list[dict[str, Any]]:
        return self.incidents.get(int(event_id), [])

    async def get_match_statistics(self, event_id: int | str) -> list[dict[str, Any]]:
        return self.statistics.get(int(event_id), [])

    async def get_win_probability(self, event_id: int | str) -> dict[str, int] | None:
        return self.probabilities.get(int(event_id))

    async def get_match_lineups(self, event_id: int | str) -> dict[str, Any]:
        self.lineup_calls.append(str(event_id))
        return self.lineups.get(int(event_id), {})


def _raw_event(
    event_id: int,
    *,
    timestamp: int = 1781784000,
    tournament_id: int = 16,
    season_id: int = 58210,
    status_type: str = "notstarted",
    description: str = "Not started",
) -> dict[str, Any]:
    return {
        "id": event_id,
        "startTimestamp": timestamp + event_id,
        "status": {"type": status_type, "description": description},
        "time": {"initial": 4080} if status_type == "inprogress" else {},
        "tournament": {"uniqueTournament": {"id": tournament_id}},
        "season": {"id": season_id},
        "homeTeam": {"id": 4748, "name": "Brazil", "nameCode": "BRA"},
        "awayTeam": {"id": 4704, "name": "Portugal", "nameCode": "POR"},
        "homeScore": {"current": 1},
        "awayScore": {"current": 0},
    }


def _normalized_live_event(event_id: int) -> dict[str, Any]:
    return {
        "id": str(event_id),
        "source": "sofascore",
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "team": {"id": "4748", "name": "Brazil"}, "score": "1"},
                    {"homeAway": "away", "team": {"id": "4704", "name": "Portugal"}, "score": "0"},
                ]
            }
        ],
    }


def _goal_incident() -> dict[str, Any]:
    return {
        "id": 1,
        "type": "goal",
        "time": 69,
        "isHome": True,
        "homeScore": 1,
        "awayScore": 0,
        "player": {"id": 9, "name": "Home Scorer"},
    }


def _statistics_response() -> list[dict[str, Any]]:
    return [
        {
            "period": "ALL",
            "groups": [
                {
                    "statisticsItems": [
                        {"key": "ballPossession", "name": "Ball possession", "home": "55%", "away": "45%"},
                        {"key": "totalShotsOnGoal", "name": "Total shots", "home": "10", "away": "7"},
                        {"key": "shotsOnGoal", "name": "Shots on target", "home": "4", "away": "2"},
                        {"key": "cornerKicks", "name": "Corner kicks", "home": "6", "away": "3"},
                        {"key": "passes", "name": "Passes", "home": "783", "away": "249"},
                        {"key": "accuratePasses", "name": "Accurate passes", "home": "724", "away": "195"},
                        {"key": "accurateCross", "name": "Crosses", "home": "6/23 (26%)", "away": "1/10 (10%)"},
                        {"key": "totalTackle", "name": "Total tackles", "home": "12", "away": "17"},
                    ]
                }
            ],
        }
    ]


def _lineups_response() -> dict[str, Any]:
    return {
        "home": {"players": [{"player": {"id": 1, "name": "Home Player"}, "statistics": {"rating": 7.5}}]},
        "away": {"players": []},
    }
