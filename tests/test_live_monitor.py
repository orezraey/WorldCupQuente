"""Unit tests for live notification collection and delivery helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.live_monitor import (
    LiveMonitorState,
    _collect_live_notifications,
    _collect_status_notifications,
    _play_match_key,
    _send_incident_notifications,
)
from worldcupquente.notification_preferences import (
    FULL_TIME_NOTIFICATION,
    GOAL_NOTIFICATION,
    PENALTY_NOTIFICATION,
)


def test_collect_live_notifications_bootstrap_records_without_sending():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
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
) -> dict[str, Any]:
    return {
        "id": "match-1",
        "competitions": [
            {
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


@dataclass
class _FakeSettings:
    live_notification_chat_ids: tuple[int, ...] = (1, 2)


class _FakeService:
    settings = _FakeSettings()
    bot_timezone = ZoneInfo("UTC")

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


class _FakePreferences:
    def __init__(self, goal_enabled: dict[int, bool]):
        self.goal_enabled = goal_enabled

    def enabled_chat_ids(self, _notification_type: str, static_chat_ids: tuple[int, ...]) -> list[int]:
        return list(static_chat_ids)

    def get(self, chat_id: int) -> dict[str, bool]:
        return {GOAL_NOTIFICATION: self.goal_enabled[chat_id]}

    def get_language(self, _chat_id: int) -> str:
        return "en"


class _FakeApplication:
    def __init__(self) -> None:
        self.bot = _FakeBot()


class _FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)
