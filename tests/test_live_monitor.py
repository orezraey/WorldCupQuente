"""Unit tests for live notification collection and delivery helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.live_monitor import (
    PENDING_FULL_TIME_STANDINGS_KEY,
    LiveMonitorState,
    _collect_live_notifications,
    _collect_pre_game_notifications,
    _collect_status_notifications,
    _play_match_key,
    _send_incident_notifications,
    _send_pending_full_time_standings,
    _send_status_notifications,
)
from worldcupquente.notification_preferences import (
    FULL_TIME_NOTIFICATION,
    GOAL_NOTIFICATION,
    PENALTY_NOTIFICATION,
    PRE_GAME_NOTIFICATION,
)


def test_collect_live_notifications_bootstrap_records_without_sending():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 0)},
        is_bootstrapped=False,
    )
    event = _event_with_score(score=(1, 0), details=[_goal_detail()])

    notifications, penalty_goal_keys = _collect_live_notifications([event], state)

    assert notifications == []
    assert penalty_goal_keys == set()
    assert len(state.seen_goal_ids) == 1
    assert state.score_snapshots["match-1"] == (1, 0)


def test_collect_live_notifications_deduplicates_seen_score_change():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 0)},
        is_bootstrapped=True,
    )
    event = _event_with_score(score=(1, 0), details=[_goal_detail()])

    first_notifications, _ = _collect_live_notifications([event], state)
    second_notifications, _ = _collect_live_notifications([event], state)

    assert len(first_notifications) == 1
    assert second_notifications == []


def test_collect_live_notifications_tracks_penalty_goal_key():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 0)},
        is_bootstrapped=True,
    )
    detail = _goal_detail(play_type={"id": "70", "text": "Penalty Kick"})
    event = _event_with_score(score=(1, 0), details=[detail])

    notifications, penalty_goal_keys = _collect_live_notifications([event], state)

    assert len(notifications) == 2
    assert _play_match_key(event, detail) in penalty_goal_keys


def test_collect_status_notifications_bootstrap_records_without_sending():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={},
        is_bootstrapped=False,
    )
    event = _status_event("in", short_detail="HT")

    notifications = asyncio.run(_collect_status_notifications([event], state, _FakeService()))

    assert notifications == []
    assert state.seen_halftime_ids == {"match-1"}


def test_collect_status_notifications_hydrates_full_time_event():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={},
        is_bootstrapped=True,
    )
    event = _status_event("post", completed=True)


    notifications = asyncio.run(_collect_status_notifications([event], state, _FakeService()))

    assert len(notifications) == 1
    assert notifications[0][0] == FULL_TIME_NOTIFICATION
    assert notifications[0][1]["boxscore"] == {"teams": []}
    assert state.seen_full_time_ids == {"match-1"}


def test_collect_status_notifications_ignores_extra_time_or_penalties():
    for short_detail in ("Extra Time", "Penalties"):
        state = LiveMonitorState(
            seen_goal_ids=set(),
            seen_penalty_ids=set(),
            seen_red_card_ids=set(),
            seen_pre_game_ids=set(),
            seen_halftime_ids=set(),
            seen_full_time_ids=set(),
            score_snapshots={},
            is_bootstrapped=True,
        )
        event = _status_event("post", short_detail=short_detail, completed=True)

        notifications = asyncio.run(_collect_status_notifications([event], state, _FakeService()))

        assert notifications == []
        assert state.seen_full_time_ids == set()


def test_collect_pre_game_notifications_within_five_minutes_once():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={},
        is_bootstrapped=True,
    )
    now = datetime(2026, 6, 12, 15, 25, tzinfo=UTC)
    event = _status_event("pre", date=(now + timedelta(minutes=4)).isoformat())

    first_notifications = _collect_pre_game_notifications([event], state, now)
    second_notifications = _collect_pre_game_notifications([event], state, now)

    assert first_notifications == [event]
    assert second_notifications == []
    assert state.seen_pre_game_ids == {"match-1"}


def test_collect_pre_game_notifications_ignores_later_games():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={},
        is_bootstrapped=True,
    )
    now = datetime(2026, 6, 12, 15, 25, tzinfo=UTC)
    event = _status_event("pre", date=(now + timedelta(minutes=6)).isoformat())

    assert _collect_pre_game_notifications([event], state, now) == []
    assert state.seen_pre_game_ids == set()


def test_send_incident_notifications_suppresses_penalty_when_goal_enabled():
    detail = _goal_detail(play_type={"id": "70", "text": "Penalty Kick"})
    event = _event_with_score(score=(1, 0), details=[detail])
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: False})
    service = _FakeService()

    asyncio.run(
        _send_incident_notifications(
            app,
            [(PENALTY_NOTIFICATION, event, detail)],
            {_play_match_key(event, detail)},
            preferences,
            service,
        )
    )

    assert [message["chat_id"] for message in app.bot.messages] == [2]


def test_full_time_summary_sends_before_standings_are_updated():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True})
    event = _full_time_event_with_records()
    service = _FakeService(groups=[_standings_group(usa_record=(0, 0, 0, 0), par_record=(0, 0, 0, 0))])

    asyncio.run(_send_status_notifications(app, [(FULL_TIME_NOTIFICATION, event)], preferences, service))
    asyncio.run(_send_pending_full_time_standings(app, preferences, service))

    assert len(app.bot.rich_messages) == 2
    assert all("<table" not in message["rich_message"]["html"] for message in app.bot.rich_messages)
    assert app.bot.rich_messages[0]["chat_id"] == 1
    assert app.bot.rich_messages[1]["chat_id"] == 2
    assert set(app.bot_data[PENDING_FULL_TIME_STANDINGS_KEY]) == {"match-1"}


def test_pending_full_time_standings_send_after_records_match():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True})
    event = _full_time_event_with_records()
    service = _FakeService(groups=[_standings_group(usa_record=(0, 0, 0, 0), par_record=(0, 0, 0, 0))])

    asyncio.run(_send_status_notifications(app, [(FULL_TIME_NOTIFICATION, event)], preferences, service))
    service.groups = [_standings_group(usa_record=(1, 1, 0, 0), par_record=(1, 0, 0, 1))]
    asyncio.run(_send_pending_full_time_standings(app, preferences, service))

    table_messages = [message for message in app.bot.rich_messages if "<table" in message["rich_message"]["html"]]
    assert [message["chat_id"] for message in table_messages] == [1, 2]
    assert app.bot_data[PENDING_FULL_TIME_STANDINGS_KEY] == {}


def _event_with_score(
    score: tuple[int, int],
    details: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": "match-1",
        "competitions": [
            {
                "status": {"displayClock": "12'"},
                "competitors": [
                    {"score": str(score[0]), "team": {"id": "home"}},
                    {"score": str(score[1]), "team": {"id": "away"}},
                ],
                "details": details,
            }
        ],
        "scoringPlays": [],
    }


def _goal_detail(play_type: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "id": "goal-1",
        "scoringPlay": True,
        "team": {"id": "home"},
        "clock": {"value": 12, "displayValue": "12'"},
        "type": play_type or {"id": "70", "text": "Goal"},
        "scoreValue": 1,
        "athletesInvolved": [{"id": "player-1", "displayName": "Player One"}],
        "text": (play_type or {}).get("text", "Goal"),
    }


def _status_event(
    state: str,
    short_detail: str | None = None,
    completed: bool = False,
    date: str = "2026-06-12T15:30:00Z",
) -> dict[str, Any]:
    return {
        "id": "match-1",
        "date": date,
        "competitions": [
            {
                "date": date,
                "status": {
                    "displayClock": short_detail,
                    "type": {
                        "state": state,
                        "completed": completed,
                        "shortDetail": short_detail,
                    },
                },
                "competitors": [
                    {"team": {"id": "home"}},
                    {"team": {"id": "away"}},
                ],
            }
        ],
    }


def _full_time_event_with_records() -> dict[str, Any]:
    return {
        "id": "match-1",
        "date": "2026-06-13T01:00:00Z",
        "competitions": [
            {
                "status": {
                    "displayClock": "90'+9'",
                    "type": {"state": "post", "completed": True, "shortDetail": "FT"},
                },
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "660", "displayName": "United States", "abbreviation": "USA"},
                        "score": "4",
                        "records": [{"type": "total", "summary": "1-0-0"}],
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "210", "displayName": "Paraguay", "abbreviation": "PAR"},
                        "score": "1",
                        "records": [{"type": "total", "summary": "0-0-1"}],
                    },
                ],
                "venue": {"fullName": "SoFi Stadium"},
            }
        ],
        "scoringPlays": [],
    }


def _standings_group(
    usa_record: tuple[int, int, int, int],
    par_record: tuple[int, int, int, int],
) -> dict[str, Any]:
    return {
        "id": "4",
        "name": "Group D",
        "standings": {
            "entries": [
                _standings_entry("660", "United States", usa_record),
                _standings_entry("210", "Paraguay", par_record),
            ]
        },
    }


def _standings_entry(team_id: str, team_name: str, record: tuple[int, int, int, int]) -> dict[str, Any]:
    games_played, wins, draws, losses = record
    return {
        "team": {"id": team_id, "displayName": team_name},
        "stats": [
            {"name": "rank", "displayValue": "1"},
            {"name": "gamesPlayed", "value": games_played},
            {"name": "wins", "value": wins},
            {"name": "ties", "value": draws},
            {"name": "losses", "value": losses},
            {"name": "points", "value": wins * 3 + draws},
            {"name": "pointsFor", "value": 0},
            {"name": "pointsAgainst", "value": 0},
            {"name": "pointDifferential", "value": 0},
        ],
    }


@dataclass
class _FakeSettings:
    live_notification_chat_ids: tuple[int, ...] = (1, 2)


class _FakeService:
    settings = _FakeSettings()
    bot_timezone = ZoneInfo("UTC")

    def __init__(self, groups: list[dict[str, Any]] | None = None) -> None:
        self.groups = groups or []

    async def get_event_summary(self, event_id: str) -> dict[str, Any]:
        return {
            "header": {
                "id": event_id,
                "competitions": [
                    {
                        "date": "2026-06-12T15:30:00Z",
                        "status": {"type": {"state": "post", "completed": True}},
                    }
                ],
            },
            "boxscore": {"teams": []},
        }

    async def get_standings_groups(self, use_cache: bool = True) -> list[dict[str, Any]]:
        del use_cache
        return self.groups


class _FakePreferences:
    def __init__(self, goal_enabled: dict[int, bool]):
        self.goal_enabled = goal_enabled

    def enabled_chat_ids(
        self,
        _notification_type: str,
        static_chat_ids: tuple[int, ...],
        team_ids: set[str] | None = None,
    ) -> list[int]:
        assert _notification_type != PRE_GAME_NOTIFICATION or team_ids is not None
        return list(static_chat_ids)

    def get(self, chat_id: int) -> dict[str, bool]:
        return {GOAL_NOTIFICATION: self.goal_enabled[chat_id]}

    def get_language(self, _chat_id: int) -> str:
        return "en"


class _FakeApplication:
    def __init__(self) -> None:
        self.bot = _FakeBot()
        self.bot_data: dict[str, Any] = {}


class _FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.rich_messages: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)

    async def do_api_request(self, _method: str, api_kwargs: dict[str, Any]) -> None:
        self.rich_messages.append(api_kwargs)
