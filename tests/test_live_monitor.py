"""Unit tests for live notification collection and delivery helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.live_monitor import (
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
    _send_status_notifications,
)
from worldcupquente.notification_preferences import (
    FULL_TIME_NOTIFICATION,
    GOAL_NOTIFICATION,
    HALFTIME_NOTIFICATION,
    PENALTY_NOTIFICATION,
    PRE_GAME_NOTIFICATION,
)


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
    assert len(state.seen_goal_ids) == 1
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


def test_collect_live_notifications_deduplicates_penalty_text_updates():
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
    first_event = _event_with_score(
        score=(0, 0),
        details=[
            _penalty_detail(
                play_id="penalty-1",
                text="Penalty Switzerland. Remo Freuler draws a foul in the penalty area.",
            )
        ],
    )
    second_event = _event_with_score(
        score=(0, 0),
        details=[
            _penalty_detail(
                play_id="penalty-2",
                text="Penalty Switzerland. Remo Freuler draws a foul in the penalty area after review.",
            )
        ],
    )

    first_notifications, _ = _collect_live_notifications([first_event], state)
    second_notifications, _ = _collect_live_notifications([second_event], state)

    assert [notification[0] for notification in first_notifications] == [PENALTY_NOTIFICATION]
    assert second_notifications == []
    assert len(state.seen_penalty_ids) == 1


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


    notifications = asyncio.run(_collect_status_notifications([event], state, _FakeService()))

    assert len(notifications) == 1
    assert notifications[0][0] == FULL_TIME_NOTIFICATION
    assert notifications[0][1]["boxscore"] == {"teams": []}
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


def test_status_notifications_use_period_end_format_in_portuguese():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    service = _FakeService()
    event = _period_status_event("in", "HT")

    asyncio.run(_send_status_notifications(app, [(HALFTIME_NOTIFICATION, event)], preferences, service))

    assert app.bot.messages[0]["text"] == (
        "<b>⏰ Final do Primeiro Tempo</b>\n\n"
        "⚽️ 🇳🇱 Países Baixos x 🇯🇵 Japão\n"
        "🕒 14/06 17:00\n"
        "🏟 Estádio: AT&amp;T Stadium"
    )


def test_halftime_notifications_keep_win_probability_when_odds_exist():
    app = _FakeApplication()
    preferences = _FakePreferences(goal_enabled={1: True, 2: True}, language="pt")
    service = _FakeService()
    event = _period_status_event("in", "HT")
    event["winProbability"] = {"home": 34, "draw": 33, "away": 33}

    asyncio.run(_send_status_notifications(app, [(HALFTIME_NOTIFICATION, event)], preferences, service))

    assert "<b>📊 Probabilidade de vitória</b>" in app.bot.messages[0]["text"]
    assert "<blockquote>🇳🇱 Países Baixos 34%" in app.bot.messages[0]["text"]


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
            "clock": {"displayValue": "31'"},
            "athletesInvolved": [{"id": "player-1", "displayName": "Cody Gakpo"}],
        },
        {
            "id": "goal-2",
            "scoringPlay": True,
            "clock": {"displayValue": "45'+2'"},
            "athletesInvolved": [{"id": "player-1", "displayName": "Cody Gakpo"}],
        },
        {
            "id": "goal-3",
            "scoringPlay": True,
            "ownGoal": True,
            "clock": {"displayValue": "60'"},
            "athletesInvolved": [{"id": "player-2", "displayName": "Ko Itakura"}],
        },
    ]

    asyncio.run(_send_status_notifications(app, [(FULL_TIME_NOTIFICATION, event)], preferences, service))

    html = app.bot.rich_messages[0]["rich_message"]["html"]
    assert "<b>⏰ Final do Segundo Tempo</b>" in html
    assert "⚽️ 🇳🇱 Países Baixos x 🇯🇵 Japão" in html
    assert "🕒 14/06 17:00" in html
    assert "🏟 Estádio: AT&amp;T Stadium" in html
    assert "⚽️ Cody Gakpo 31&#x27;, ⚽️ 45&#x27;+2&#x27;" in html
    assert "⚽️ Ko Itakura 60&#x27; (GC)" in html
    assert "Probabilidade de vitória" not in html


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


@dataclass
class _FakeSettings:
    live_notification_chat_ids: tuple[int, ...] = (1, 2)


class _FakeService:
    settings = _FakeSettings()
    bot_timezone = ZoneInfo("UTC")

    def __init__(self, groups: list[dict[str, Any]] | None = None) -> None:
        self.groups = groups or []

    async def enrich_event_win_probability(self, event: dict[str, Any]) -> dict[str, Any]:
        return event

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
    def __init__(self, goal_enabled: dict[int, bool], language: str = "en"):
        self.goal_enabled = goal_enabled
        self.language = language

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
        return self.language


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
