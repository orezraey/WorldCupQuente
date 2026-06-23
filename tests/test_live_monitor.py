"""Unit tests for live notification collection and delivery helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import worldcupquente.live_monitor as live_monitor
from worldcupquente.live_monitor import (
    DISALLOWED_GOAL_NOTIFICATION,
    KICKOFF_NOTIFICATION,
    PENDING_FULL_TIME_STANDINGS_KEY,
    STANDINGS_SNAPSHOTS_KEY,
    LiveMonitorState,
    _collect_live_notifications,
    _collect_pre_game_notifications,
    _collect_status_notifications,
    _play_match_key,
    _remember_active_standings_snapshots,
    _send_incident_notifications,
    _send_pending_full_time_standings,
    _send_pending_player_ratings,
    _send_status_notifications,
    poll_live_notifications,
)
from worldcupquente.notification_preferences import (
    FULL_TIME_NOTIFICATION,
    GOAL_NOTIFICATION,
    HALFTIME_NOTIFICATION,
    PENALTY_NOTIFICATION,
    PRE_GAME_NOTIFICATION,
)


def test_poll_live_notifications_uses_sofascore_monitor_events(monkeypatch):
    app = _FakeApplication()
    service = _FakeService(monitor_events={"live_events": [], "status_events": []})
    preferences = _FakePreferences(goal_enabled={1: True, 2: True})
    app.bot_data["world_cup_service"] = service
    app.bot_data[live_monitor.NOTIFICATION_PREFERENCES_KEY] = preferences
    monkeypatch.setattr(live_monitor, "WorldCupService", _FakeService)
    monkeypatch.setattr(live_monitor, "NotificationPreferences", _FakePreferences)

    asyncio.run(poll_live_notifications(app))

    assert service.monitor_event_calls == [False]


def test_collect_live_notifications_bootstrap_records_without_sending():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 0)},
        is_bootstrapped=False,
    )
    event = _event_with_score(score=(1, 0), details=[_goal_detail()])

    notifications, penalty_goal_keys = _collect_live_notifications([event], state)

    assert notifications == []
    assert penalty_goal_keys == set()
    assert state.seen_goal_ids
    assert state.score_snapshots["match-1"] == (1, 0)


def test_collect_live_notifications_deduplicates_seen_score_change():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
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


def test_collect_live_notifications_sends_only_goal_for_converted_penalty():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 0)},
        is_bootstrapped=True,
    )
    detail = _goal_detail(play_type={"id": "70", "text": "Penalty Kick"})
    event = _event_with_score(score=(1, 0), details=[detail])

    notifications, penalty_goal_keys = _collect_live_notifications([event], state)

    assert [notification[0] for notification in notifications] == [GOAL_NOTIFICATION]
    assert _play_match_key(event, detail) in penalty_goal_keys


def test_collect_live_notifications_uses_sofascore_goal_without_score_change():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (1, 0)},
        is_bootstrapped=True,
    )
    detail = _goal_detail()
    detail["id"] = "sofascore:goal-1"
    detail["source"] = "sofascore"
    event = _event_with_score(score=(1, 0), details=[])
    event["sofascoreIncidents"] = {"goals": [detail], "redCards": []}

    notifications, penalty_goal_keys = _collect_live_notifications([event], state)

    assert [notification[0] for notification in notifications] == [GOAL_NOTIFICATION]
    assert notifications[0][2]["source"] == "sofascore"
    assert penalty_goal_keys == set()
    assert state.score_snapshots["match-1"] == (1, 0)


def test_collect_live_notifications_uses_sofascore_disallowed_goal():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (1, 0)},
        is_bootstrapped=True,
    )
    detail = _disallowed_goal_detail()
    event = _event_with_score(score=(0, 0), details=[])
    event["sofascoreIncidents"] = {"goals": [], "disallowedGoals": [detail], "redCards": []}

    first_notifications, penalty_goal_keys = _collect_live_notifications([event], state)
    second_notifications, _ = _collect_live_notifications([event], state)

    assert [notification[0] for notification in first_notifications] == [DISALLOWED_GOAL_NOTIFICATION]
    assert first_notifications[0][2]["source"] == "sofascore"
    assert second_notifications == []
    assert penalty_goal_keys == set()
    assert state.score_snapshots["match-1"] == (0, 0)


def test_collect_live_notifications_suppresses_disallowed_goal_when_currently_confirmed():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 0)},
        is_bootstrapped=True,
    )
    disallowed = _disallowed_goal_detail()
    confirmed = {
        "id": "sofascore:goal-1",
        "source": "sofascore",
        "scoringPlay": True,
        "shootout": False,
        "team": {"id": "away"},
        "clock": {"value": 8, "displayValue": "8'"},
        "type": {"id": "goal", "type": "goal", "text": "Goal"},
        "scoreValue": 1,
        "scoreAfter": {"home": 0, "away": 1},
        "athletesInvolved": [{"id": "player-2", "displayName": "Player Two"}],
        "text": "Goal",
    }
    event = _event_with_score(score=(0, 1), details=[])
    event["sofascoreIncidents"] = {"goals": [confirmed], "redCards": []}

    first_notifications, _ = _collect_live_notifications([event], state)

    event["sofascoreIncidents"]["disallowedGoals"] = [disallowed]
    second_notifications, _ = _collect_live_notifications([event], state)

    assert [notification[0] for notification in first_notifications] == [GOAL_NOTIFICATION]
    assert second_notifications == []


def test_collect_live_notifications_emits_disallowed_goal_when_no_longer_confirmed():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 1)},
        is_bootstrapped=True,
    )
    disallowed = _disallowed_goal_detail()
    event = _event_with_score(score=(0, 0), details=[])
    event["sofascoreIncidents"] = {"goals": [], "disallowedGoals": [disallowed], "redCards": []}

    notifications, _ = _collect_live_notifications([event], state)

    assert [notification[0] for notification in notifications] == [DISALLOWED_GOAL_NOTIFICATION]


def test_collect_live_notifications_emits_disallowed_goal_on_score_regression_without_incident():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (1, 0)},
        is_bootstrapped=True,
    )
    event = _event_with_score(score=(0, 0), details=[])
    event["competitions"][0]["status"] = {"displayClock": "21'"}

    notifications, penalty_goal_keys = _collect_live_notifications([event], state)

    assert [notification[0] for notification in notifications] == [DISALLOWED_GOAL_NOTIFICATION]
    assert notifications[0][2]["source"] == "score-regression"
    assert notifications[0][2]["team"]["id"] == "home"
    assert penalty_goal_keys == set()
    assert state.score_snapshots["match-1"] == (0, 0)


def test_collect_live_notifications_emits_multiple_disallowed_goals_on_multi_goal_regression():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (2, 0)},
        is_bootstrapped=True,
    )
    event = _event_with_score(score=(0, 0), details=[])
    event["competitions"][0]["status"] = {"displayClock": "21'"}

    notifications, _ = _collect_live_notifications([event], state)

    assert [notification[0] for notification in notifications] == [
        DISALLOWED_GOAL_NOTIFICATION,
        DISALLOWED_GOAL_NOTIFICATION,
    ]
    assert [notification[2]["id"] for notification in notifications] == [
        "score-regression:home:2:0:0:0:0",
        "score-regression:home:2:0:0:0:1",
    ]


def test_collect_live_notifications_deduplicates_official_disallowed_after_score_regression():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (1, 0)},
        is_bootstrapped=True,
    )
    score_regression_event = _event_with_score(score=(0, 0), details=[])
    score_regression_event["competitions"][0]["status"] = {"displayClock": "21'"}
    official_disallowed = _disallowed_goal_detail()
    official_disallowed["team"] = {"id": "home"}
    official_disallowed["clock"] = {"value": 21, "displayValue": "21'"}
    official_event = _event_with_score(score=(0, 0), details=[])
    official_event["sofascoreIncidents"] = {"goals": [], "disallowedGoals": [official_disallowed], "redCards": []}

    first_notifications, _ = _collect_live_notifications([score_regression_event], state)
    second_notifications, _ = _collect_live_notifications([official_event], state)

    assert [notification[0] for notification in first_notifications] == [DISALLOWED_GOAL_NOTIFICATION]
    assert second_notifications == []


def test_collect_live_notifications_uses_sofascore_penalty():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 0)},
        is_bootstrapped=True,
    )
    detail = _penalty_detail(play_id="sofascore:penalty-1")
    detail["source"] = "sofascore"
    event = _event_with_score(score=(0, 0), details=[])
    event["sofascoreIncidents"] = {"goals": [], "penalties": [detail], "redCards": []}

    notifications, penalty_goal_keys = _collect_live_notifications([event], state)

    assert [notification[0] for notification in notifications] == [PENALTY_NOTIFICATION]
    assert notifications[0][2]["source"] == "sofascore"
    assert penalty_goal_keys == set()


def test_collect_live_notifications_ignores_var_checking_penalty_text():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 0)},
        is_bootstrapped=True,
    )
    event = _event_with_score(
        score=(0, 0),
        details=[
            {
                "id": "var-1",
                "team": {"id": "home"},
                "clock": {"value": 60, "displayValue": "60'"},
                "type": {"type": "var", "text": "VAR Checking"},
                "text": "VAR Checking: France Penalty.",
            }
        ],
    )

    notifications, penalty_goal_keys = _collect_live_notifications([event], state)

    assert notifications == []
    assert penalty_goal_keys == set()


def test_collect_live_notifications_deduplicates_score_change_when_sofascore_arrives_later():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 0)},
        is_bootstrapped=True,
    )
    score_change_event = _event_with_score(score=(1, 0), details=[])
    sofascore_detail = _goal_detail()
    sofascore_detail["id"] = "sofascore:goal-1"
    sofascore_detail["source"] = "sofascore"
    sofascore_detail["scoreAfter"] = "1:0"
    sofascore_event = _event_with_score(score=(1, 0), details=[])
    sofascore_event["sofascoreIncidents"] = {"goals": [sofascore_detail], "redCards": []}

    first_notifications, _ = _collect_live_notifications([score_change_event], state)
    second_notifications, _ = _collect_live_notifications([sofascore_event], state)

    assert [notification[0] for notification in first_notifications] == [GOAL_NOTIFICATION]
    assert second_notifications == []


def test_collect_live_notifications_skips_sofascore_goals_after_full_time():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (1, 1)},
        is_bootstrapped=True,
    )
    detail = _goal_detail()
    detail["source"] = "sofascore"
    detail["scoreAfter"] = "0:1"
    event = _event_with_score(score=(1, 1), details=[])
    event["competitions"][0]["status"] = {
        "displayClock": "FT",
        "type": {"state": "post", "completed": True, "shortDetail": "FT"},
    }
    event["sofascoreIncidents"] = {"goals": [detail], "redCards": []}

    notifications, _ = _collect_live_notifications([event], state)

    assert notifications == []
    assert state.seen_goal_ids


def test_collect_live_notifications_deduplicates_own_goal_when_team_differs_later():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 1)},
        is_bootstrapped=True,
    )
    score_change_event = _event_with_score(score=(1, 1), details=[])
    sofascore_detail = _goal_detail()
    sofascore_detail["id"] = "sofascore:own-goal-1"
    sofascore_detail["source"] = "sofascore"
    sofascore_detail["team"] = {"id": "away"}
    sofascore_detail["scoreAfter"] = "1:1"
    sofascore_detail["ownGoal"] = True
    sofascore_event = _event_with_score(score=(1, 1), details=[])
    sofascore_event["sofascoreIncidents"] = {"goals": [sofascore_detail], "redCards": []}

    first_notifications, _ = _collect_live_notifications([score_change_event], state)
    second_notifications, _ = _collect_live_notifications([sofascore_event], state)

    assert [notification[0] for notification in first_notifications] == [GOAL_NOTIFICATION]
    assert second_notifications == []


def test_collect_live_notifications_deduplicates_sofascore_penalty_updates():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 0)},
        is_bootstrapped=True,
    )
    first_detail = _penalty_detail(play_id="sofascore:penalty-1")
    first_detail["source"] = "sofascore"
    second_detail = _penalty_detail(play_id="sofascore:penalty-2", text="Penalty awarded after review")
    second_detail["source"] = "sofascore"
    first_event = _event_with_score(score=(0, 0), details=[])
    first_event["sofascoreIncidents"] = {"goals": [], "penalties": [first_detail], "redCards": []}
    second_event = _event_with_score(score=(0, 0), details=[])
    second_event["sofascoreIncidents"] = {"goals": [], "penalties": [second_detail], "redCards": []}

    first_notifications, _ = _collect_live_notifications([first_event], state)
    second_notifications, _ = _collect_live_notifications([second_event], state)

    assert [notification[0] for notification in first_notifications] == [PENALTY_NOTIFICATION]
    assert second_notifications == []
    assert len(state.seen_penalty_ids) == 1


def test_collect_live_notifications_deduplicates_penalty_result_minute_correction():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={"match-1": (0, 0)},
        is_bootstrapped=True,
    )
    cancelled_penalty = _penalty_detail(
        play_id="sofascore:penalty-1",
        team_id="home",
        clock_value=8,
        clock_display="8'",
    )
    cancelled_penalty["athletesInvolved"] = []
    awarded_penalty = _penalty_detail(
        play_id="sofascore:penalty-2",
        team_id="home",
        clock_value=10,
        clock_display="10'",
    )
    saved_penalty = _penalty_detail(
        play_id="sofascore:penalty-3",
        text="goalkeeperSave",
        team_id="home",
        clock_value=9,
        clock_display="9'",
    )
    first_event = _event_with_score(score=(0, 0), details=[])
    first_event["sofascoreIncidents"] = {"goals": [], "penalties": [cancelled_penalty], "redCards": []}
    second_event = _event_with_score(score=(0, 0), details=[])
    second_event["sofascoreIncidents"] = {"goals": [], "penalties": [awarded_penalty], "redCards": []}
    third_event = _event_with_score(score=(1, 0), details=[])
    third_event["sofascoreIncidents"] = {"goals": [], "penalties": [saved_penalty], "redCards": []}

    first_notifications, _ = _collect_live_notifications([first_event], state)
    second_notifications, _ = _collect_live_notifications([second_event], state)
    state.score_snapshots["match-1"] = (1, 0)
    third_notifications, _ = _collect_live_notifications([third_event], state)

    assert [notification[0] for notification in first_notifications] == [PENALTY_NOTIFICATION]
    assert [notification[0] for notification in second_notifications] == [PENALTY_NOTIFICATION]
    assert third_notifications == []


def test_collect_status_notifications_bootstrap_records_without_sending():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
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
    service = _FakeService()
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={},
        is_bootstrapped=True,
    )
    event = _status_event("post", completed=True)


    notifications = asyncio.run(_collect_status_notifications([event], state, service))

    assert len(notifications) == 1
    assert notifications[0][0] == FULL_TIME_NOTIFICATION
    assert notifications[0][1]["post_match_enriched"] is True
    assert state.seen_full_time_ids == {"match-1"}


def test_collect_status_notifications_sends_kickoff_once_after_bootstrap():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={},
        is_bootstrapped=True,
    )
    event = _status_event("in", short_detail="1'")

    first_notifications = asyncio.run(_collect_status_notifications([event], state, _FakeService()))
    second_notifications = asyncio.run(_collect_status_notifications([event], state, _FakeService()))

    assert [notification[0] for notification in first_notifications] == [KICKOFF_NOTIFICATION]
    assert second_notifications == []
    assert state.seen_kickoff_ids == {"match-1"}


def test_collect_status_notifications_bootstrap_records_kickoff_without_sending():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={},
        is_bootstrapped=False,
    )
    event = _status_event("in", short_detail="1'")

    notifications = asyncio.run(_collect_status_notifications([event], state, _FakeService()))

    assert notifications == []
    assert state.seen_kickoff_ids == {"match-1"}


def test_collect_status_notifications_does_not_send_kickoff_after_halftime_seen_first():
    state = LiveMonitorState(
        seen_goal_ids=set(),
        seen_penalty_ids=set(),
        seen_red_card_ids=set(),
        seen_pre_game_ids=set(),
        seen_kickoff_ids=set(),
        seen_halftime_ids=set(),
        seen_full_time_ids=set(),
        score_snapshots={},
        is_bootstrapped=False,
    )

    halftime_notifications = asyncio.run(
        _collect_status_notifications([_status_event("in", short_detail="HT")], state, _FakeService())
    )
    state.is_bootstrapped = True
    second_half_notifications = asyncio.run(
        _collect_status_notifications([_status_event("in", short_detail="46'")], state, _FakeService())
    )

    assert halftime_notifications == []
    assert second_half_notifications == []
    assert state.seen_kickoff_ids == {"match-1"}


def test_collect_status_notifications_ignores_extra_time_or_penalties():
    for short_detail in ("Extra Time", "Penalties"):
        state = LiveMonitorState(
            seen_goal_ids=set(),
            seen_penalty_ids=set(),
            seen_red_card_ids=set(),
            seen_pre_game_ids=set(),
            seen_kickoff_ids=set(),
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
        seen_kickoff_ids=set(),
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
        seen_kickoff_ids=set(),
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


def test_send_incident_notifications_suppresses_separate_penalty_award_when_goal_enabled():
    goal_detail = _goal_detail(play_type={"id": "70", "text": "Penalty Kick"})
    penalty_detail = _penalty_detail(team_id="home", clock_value=12, clock_display="12'")
    event = _event_with_score(score=(1, 0), details=[goal_detail, penalty_detail])
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: False})
    service = _FakeService()

    asyncio.run(
        _send_incident_notifications(
            app,
            [(PENALTY_NOTIFICATION, event, penalty_detail)],
            {_play_match_key(event, goal_detail)},
            preferences,
            service,
        )
    )

    assert [message["chat_id"] for message in app.bot.messages] == [2]


def test_send_incident_notifications_uses_goal_preference_for_disallowed_goal():
    detail = _disallowed_goal_detail()
    event = _event_with_score(score=(0, 0), details=[])
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    service = _FakeService()

    asyncio.run(
        _send_incident_notifications(
            app,
            [(DISALLOWED_GOAL_NOTIFICATION, event, detail)],
            set(),
            preferences,
            service,
        )
    )

    assert preferences.enabled_notification_types == [GOAL_NOTIFICATION]
    assert [message["chat_id"] for message in app.bot.messages] == [1, 2]
    assert "GOL ANULADO!" in app.bot.messages[0]["text"]
    assert "Player Two" in app.bot.messages[0]["text"]


def test_status_notifications_use_period_end_format_in_portuguese():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    service = _FakeService()
    event = _period_status_event("in", "HT")

    asyncio.run(_send_status_notifications(app, [(HALFTIME_NOTIFICATION, event)], preferences, service))

    assert app.bot.messages[0]["text"] == (
        "<b>⏰ Final do Primeiro Tempo</b>\n\n"
        "⚽️ 🇳🇱 Países Baixos 0 x 0 🇯🇵 Japão\n"
        "🕒 14/06 17:00\n"
        "🏟 Estádio: AT&amp;T Stadium"
    )


def test_halftime_notification_shows_current_score():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    service = _FakeService()
    event = _period_status_event("in", "HT")
    event["competitions"][0]["competitors"][0]["score"] = "0"
    event["competitions"][0]["competitors"][1]["score"] = "1"

    asyncio.run(_send_status_notifications(app, [(HALFTIME_NOTIFICATION, event)], preferences, service))

    assert "⚽️ 🇳🇱 Países Baixos 0 x 1 🇯🇵 Japão" in app.bot.messages[0]["text"]


def test_halftime_notifications_keep_win_probability_when_odds_exist():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    service = _FakeService()
    event = _period_status_event("in", "HT")
    event["winProbability"] = {"home": 34, "draw": 33, "away": 33}

    asyncio.run(_send_status_notifications(app, [(HALFTIME_NOTIFICATION, event)], preferences, service))

    assert "<b>📊 Probabilidade de vitória</b>" in app.bot.messages[0]["text"]
    assert "<blockquote>🇳🇱 Países Baixos 34%" in app.bot.messages[0]["text"]


def test_halftime_notification_shows_goal_scorers_before_win_probability():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    service = _FakeService()
    event = _period_status_event("in", "HT")
    event["competitions"][0]["details"] = [
        {
            "id": "goal-1",
            "scoringPlay": True,
            "team": {"id": "449"},
            "clock": {"displayValue": "36'"},
            "athletesInvolved": [{"id": "player-1", "displayName": "Nizar Al-Rashdan"}],
        }
    ]
    event["winProbability"] = {"home": 34, "draw": 33, "away": 33}

    asyncio.run(_send_status_notifications(app, [(HALFTIME_NOTIFICATION, event)], preferences, service))

    message = app.bot.messages[0]["text"]
    assert "<blockquote>⚽️ 🇳🇱 Nizar Al-Rashdan 36&#x27;</blockquote>" in message
    assert message.index("Nizar Al-Rashdan") < message.index("Probabilidade de vitória")


def test_kickoff_notifications_use_custom_emoji_and_win_probability_in_portuguese():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    service = _FakeService()
    event = _period_status_event("in", "1'")
    event["winProbability"] = {"home": 34, "draw": 33, "away": 33}

    asyncio.run(_send_status_notifications(app, [(KICKOFF_NOTIFICATION, event)], preferences, service))

    assert app.bot.messages[0]["text"] == (
        '<tg-emoji emoji-id="5264919878082509254">⚽️</tg-emoji> <b>Início de jogo!</b>\n\n'
        "⚽️ 🇳🇱 Países Baixos x 🇯🇵 Japão\n"
        "🕒 14/06 17:00\n"
        "🏟 Estádio: AT&amp;T Stadium\n\n"
        "<b>📊 Probabilidade de vitória</b>\n"
        "<blockquote>🇳🇱 Países Baixos 34%\n"
        "🤝 Empate 33%\n"
        "🇯🇵 Japão 33%</blockquote>"
    )


def test_full_time_notifications_use_second_half_end_format_in_portuguese():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    service = _FakeService()
    event = _period_status_event("post", "FT", completed=True)
    event["competitions"][0]["odds"] = [_even_moneyline_odds()]
    event["competitions"][0]["details"] = [
        {
            "id": "goal-1",
            "scoringPlay": True,
            "team": {"id": "449"},
            "scoreAfter": "1:0",
            "clock": {"displayValue": "31'"},
            "athletesInvolved": [{"id": "player-1", "displayName": "Cody Gakpo"}],
        },
        {
            "id": "goal-2",
            "scoringPlay": True,
            "team": {"id": "449"},
            "scoreAfter": "2:0",
            "clock": {"displayValue": "45'+2'"},
            "athletesInvolved": [{"id": "player-1", "displayName": "Cody Gakpo"}],
        },
        {
            "id": "goal-3",
            "scoringPlay": True,
            "team": {"id": "627"},
            "ownGoal": True,
            "scoreAfter": "3:0",
            "clock": {"displayValue": "60'"},
            "athletesInvolved": [{"id": "player-2", "displayName": "Ko Itakura"}],
        },
    ]
    event["competitions"][0]["competitors"][0]["score"] = "3"
    event["competitions"][0]["competitors"][1]["score"] = "0"

    asyncio.run(_send_status_notifications(app, [(FULL_TIME_NOTIFICATION, event)], preferences, service))

    html = app.bot.rich_messages[0]["rich_message"]["html"]
    assert "<b>⏰ Final do Segundo Tempo</b>" in html
    assert "⚽️ 🇳🇱 Países Baixos 3 x 0 🇯🇵 Japão" in html
    assert "🕒 14/06 17:00" in html
    assert "🏟 Estádio: AT&amp;T Stadium" in html
    assert "<blockquote>⚽️ 🇳🇱 Cody Gakpo 31&#x27;<br/>" in html
    assert "⚽️ 🇳🇱 Cody Gakpo 45&#x27;+2&#x27;<br/>" in html
    assert "⚽️ 🇳🇱 Ko Itakura 60&#x27; (GC)</blockquote>" in html
    assert "Probabilidade de vitória" not in html


def test_full_time_notification_shows_final_score():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    service = _FakeService()
    event = _period_status_event("post", "FT", completed=True)
    event["competitions"][0]["competitors"][0]["score"] = "1"
    event["competitions"][0]["competitors"][1]["score"] = "2"

    asyncio.run(_send_status_notifications(app, [(FULL_TIME_NOTIFICATION, event)], preferences, service))

    html = app.bot.rich_messages[0]["rich_message"]["html"]
    assert "⚽️ 🇳🇱 Países Baixos 1 x 2 🇯🇵 Japão" in html


def test_full_time_rich_failure_queues_available_player_ratings():
    app = _FakeApplication()
    app.bot.fail_rich_messages = True
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    service = _FakeService()
    event = _period_status_event("post", "FT", completed=True)
    event["sofascorePlayerRatings"] = _player_ratings()

    asyncio.run(_send_status_notifications(app, [(FULL_TIME_NOTIFICATION, event)], preferences, service))

    assert app.bot.messages
    assert set(app.bot_data["live_pending_player_ratings"]) == {"match-period"}


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


def test_pending_full_time_standings_send_after_snapshot_update_without_event_records():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True})
    event = _full_time_event_without_records()
    service = _FakeService(groups=[_standings_group(usa_record=(0, 0, 0, 0), par_record=(0, 0, 0, 0))])

    asyncio.run(_send_status_notifications(app, [(FULL_TIME_NOTIFICATION, event)], preferences, service))
    service.groups = [_standings_group(usa_record=(1, 1, 0, 0), par_record=(1, 0, 0, 1))]
    asyncio.run(_send_pending_full_time_standings(app, preferences, service))

    table_messages = [message for message in app.bot.rich_messages if "<table" in message["rich_message"]["html"]]
    assert [message["chat_id"] for message in table_messages] == [1, 2]
    assert app.bot_data[PENDING_FULL_TIME_STANDINGS_KEY] == {}


def test_pending_full_time_standings_send_when_api_already_updated_using_active_snapshot():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True})
    service = _FakeService(groups=[_standings_group(usa_record=(0, 0, 0, 0), par_record=(0, 0, 0, 0))])

    asyncio.run(_remember_active_standings_snapshots(app, [_in_progress_event_without_records()], service))
    service.groups = [_standings_group(usa_record=(1, 1, 0, 0), par_record=(1, 0, 0, 1))]
    asyncio.run(
        _send_status_notifications(app, [(FULL_TIME_NOTIFICATION, _full_time_event_without_records())], preferences, service)
    )
    asyncio.run(_send_pending_full_time_standings(app, preferences, service))

    table_messages = [message for message in app.bot.rich_messages if "<table" in message["rich_message"]["html"]]
    assert [message["chat_id"] for message in table_messages] == [1, 2]
    assert app.bot_data[PENDING_FULL_TIME_STANDINGS_KEY] == {}
    assert app.bot_data[STANDINGS_SNAPSHOTS_KEY] == {}


def test_pending_player_ratings_falls_back_to_plain_message_when_rich_fails():
    app = _FakeApplication()
    app.bot.fail_rich_messages = True
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    event = _period_status_event("post", "FT", completed=True)
    service = _FakeService(finished_event={**event, "sofascorePlayerRatings": _player_ratings()})
    app.bot_data["live_pending_player_ratings"] = {"match-period": {"event": event}}

    asyncio.run(_send_pending_player_ratings(app, preferences, service))

    assert app.bot_data["live_pending_player_ratings"] == {}
    assert app.bot.messages
    assert "Notas SofaScore" in app.bot.messages[0]["text"]


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


def _penalty_detail(
    play_id: str = "penalty-1",
    text: str = "Penalty awarded",
    team_id: str = "away",
    clock_value: int = 14,
    clock_display: str = "14'",
) -> dict[str, Any]:
    return {
        "id": play_id,
        "team": {"id": team_id},
        "clock": {"value": clock_value, "displayValue": clock_display},
        "type": {"id": "81", "type": "penalty", "text": "Penalty"},
        "athletesInvolved": [{"id": "player-2", "displayName": "Player Two"}],
        "text": text,
    }


def _disallowed_goal_detail() -> dict[str, Any]:
    return {
        "id": "sofascore:var-1",
        "source": "sofascore",
        "disallowedGoal": True,
        "team": {"id": "away"},
        "clock": {"value": 8, "displayValue": "8'"},
        "type": {"id": "goalNotAwarded", "type": "varDecision", "text": "Goal disallowed"},
        "athletesInvolved": [{"id": "player-2", "displayName": "Player Two"}],
        "text": "Goal disallowed after VAR review",
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


def _period_status_event(state: str, short_detail: str, completed: bool = False) -> dict[str, Any]:
    return {
        "id": "match-period",
        "date": "2026-06-14T17:00:00Z",
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
                    {
                        "homeAway": "home",
                        "team": {"id": "449", "displayName": "Netherlands", "abbreviation": "NED"},
                        "score": "0",
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "627", "displayName": "Japan", "abbreviation": "JPN"},
                        "score": "0",
                    },
                ],
                "venue": {"fullName": "AT&T Stadium"},
            }
        ],
    }


def _even_moneyline_odds() -> dict[str, Any]:
    return {
        "moneyline": {
            "home": {"current": {"odds": "+200"}},
            "draw": {"current": {"odds": "+200"}},
            "away": {"current": {"odds": "+200"}},
        }
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


def _full_time_event_without_records() -> dict[str, Any]:
    event = _full_time_event_with_records()
    for competitor in event["competitions"][0]["competitors"]:
        competitor.pop("records", None)
    return event


def _in_progress_event_without_records() -> dict[str, Any]:
    event = _full_time_event_without_records()
    event["competitions"][0]["status"] = {
        "displayClock": "58'",
        "type": {"state": "in", "completed": False, "shortDetail": "Second Half"},
    }
    return event


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


def _player_ratings() -> dict[str, list[dict[str, Any]]]:
    return {
        "home": [{"name": "Home Player", "shirtNumber": 8, "rating": 7.8}],
        "away": [{"name": "Away Player", "shirtNumber": 10, "rating": 7.2}],
    }


@dataclass
class _FakeSettings:
    live_notification_chat_ids: tuple[int, ...] = (1, 2)


class _FakeService:
    settings = _FakeSettings()
    bot_timezone = ZoneInfo("UTC")

    def __init__(
        self,
        groups: list[dict[str, Any]] | None = None,
        finished_event: dict[str, Any] | None = None,
        monitor_events: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.groups = groups or []
        self.finished_event = finished_event
        self.monitor_events = monitor_events or {"live_events": [], "status_events": []}
        self.monitor_event_calls: list[bool] = []

    async def get_sofascore_monitor_events(self, use_cache: bool = True) -> dict[str, list[dict[str, Any]]]:
        self.monitor_event_calls.append(use_cache)
        return self.monitor_events

    async def enrich_event_win_probability(self, event: dict[str, Any]) -> dict[str, Any]:
        return event

    async def enrich_event_sofascore_incidents(self, event: dict[str, Any]) -> dict[str, Any]:
        return event

    async def enrich_event_sofascore_post_match(self, event: dict[str, Any]) -> dict[str, Any]:
        event["post_match_enriched"] = True
        return event

    async def get_sofascore_standings_groups(self, use_cache: bool = True) -> list[dict[str, Any]]:
        del use_cache
        return self.groups

    async def get_sofascore_finished_event_details(self, event_id: str) -> dict[str, Any] | None:
        del event_id
        return self.finished_event


class _FakePreferences:
    def __init__(self, goal_enabled: dict[int, bool], language: str = "en"):
        self.goal_enabled = goal_enabled
        self.language = language
        self.enabled_notification_types: list[str] = []

    def has_recipients(self, _static_chat_ids: tuple[int, ...]) -> bool:
        return True

    def enabled_chat_ids(
        self,
        _notification_type: str,
        static_chat_ids: tuple[int, ...],
        team_ids: set[str] | None = None,
    ) -> list[int]:
        assert _notification_type != PRE_GAME_NOTIFICATION or team_ids is not None
        self.enabled_notification_types.append(_notification_type)
        return list(static_chat_ids)

    def get(self, chat_id: int) -> dict[str, bool]:
        return {GOAL_NOTIFICATION: self.goal_enabled[chat_id]}

    def get_language(self, _chat_id: int) -> str:
        return self.language


class _FakeApplication:
    def __init__(self) -> None:
        self.bot = _FakeBot()
        self.bot_data: dict[str, Any] = {}


class _FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.rich_messages: list[dict[str, Any]] = []
        self.fail_rich_messages = False

    async def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)

    async def do_api_request(self, _method: str, api_kwargs: dict[str, Any]) -> None:
        if self.fail_rich_messages:
            raise RuntimeError("rich failed")
        self.rich_messages.append(api_kwargs)
