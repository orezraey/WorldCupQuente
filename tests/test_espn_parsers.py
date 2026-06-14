"""Unit tests for ESPN data parsers and incident extraction utilities."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from worldcupquente.espn_events import event_from_summary, parse_espn_datetime
from worldcupquente.event_incidents import (
    penalty_plays_from_event,
    red_cards_from_event,
    scoring_plays_from_event,
)


def test_parse_espn_datetime_valid():
    tz = ZoneInfo("America/Sao_Paulo")
    # UTC time
    dt = parse_espn_datetime("2026-06-12T15:30:00Z", tz)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 6
    assert dt.day == 12
    # UTC 15:30 is 12:30 in Sao Paulo (GMT-3)
    assert dt.hour == 12
    assert dt.minute == 30
    assert dt.tzinfo == tz


def test_parse_espn_datetime_invalid():
    tz = ZoneInfo("UTC")
    assert parse_espn_datetime("", tz) is None
    assert parse_espn_datetime("invalid-date", tz) is None


def test_event_from_summary_merges_data():
    summary = {
        "header": {
            "id": "12345",
            "uid": "s:1~l:1~e:12345",
            "competitions": [
                {
                    "date": "2026-06-12T15:30:00Z",
                    "status": {
                        "type": {
                            "state": "in",
                            "detail": "85'",
                        }
                    }
                }
            ]
        },
        "gameInfo": {
            "venue": {
                "id": "1",
                "fullName": "Azteca"
            }
        },
        "boxscore": {"teams": []},
        "leaders": [{"team": {}}],
        "commentary": [{"text": "Kick off"}],
        "rosters": [{"team": {}}],
        "scoringPlays": [{"id": "play1"}]
    }

    fallback = {
        "id": "12345",
        "status": {
            "type": {
                "name": "STATUS_IN_PROGRESS",
                "state": "pre"  # Should be overridden by "in"
            }
        }
    }

    event = event_from_summary(summary, fallback_event=fallback)

    assert event["id"] == "12345"
    assert event["uid"] == "s:1~l:1~e:12345"
    assert event["date"] == "2026-06-12T15:30:00Z"
    assert event["venue"]["fullName"] == "Azteca"
    assert event["boxscore"] == {"teams": []}
    assert len(event["leaders"]) == 1
    assert len(event["commentary"]) == 1
    assert len(event["rosters"]) == 1
    assert len(event["scoringPlays"]) == 1

    # Check status merging
    status = event["status"]
    assert status["type"]["state"] == "in"
    assert status["type"]["name"] == "STATUS_IN_PROGRESS"
    assert status["type"]["detail"] == "85'"


def test_scoring_plays_from_event_details():
    event = {
        "competitions": [
            {
                "details": [
                    {
                        "scoringPlay": True,
                        "shootout": False,
                        "team": {"id": "home"},
                        "clock": {"displayValue": "12'"},
                        "athletesInvolved": [{"id": "1", "displayName": "Neymar"}],
                    },
                    {
                        "scoringPlay": True,
                        "shootout": True,  # shootout should be ignored
                        "team": {"id": "home"},
                        "clock": {"displayValue": "Pen 1'"},
                        "athletesInvolved": [{"id": "1", "displayName": "Neymar"}],
                    }
                ]
            }
        ],
        "scoringPlays": []
    }

    goals = scoring_plays_from_event(event)
    assert len(goals) == 1
    assert goals[0]["athletesInvolved"][0]["displayName"] == "Neymar"
    assert goals[0]["clock"]["displayValue"] == "12'"


def test_scoring_plays_deduplication():
    # Duplicate goal in details and scoringPlays
    event = {
        "competitions": [
            {
                "details": [
                    {
                        "scoringPlay": True,
                        "team": {"id": "home"},
                        "clock": {"displayValue": "45'"},
                        "athletesInvolved": [{"id": "2", "displayName": "Messi"}],
                    }
                ]
            }
        ],
        "scoringPlays": [
            {
                "team": {"id": "home"},
                "clock": {"displayValue": "45'"},
                "athletesInvolved": [{"id": "2", "displayName": "Messi"}],
            }
        ]
    }

    goals = scoring_plays_from_event(event)
    assert len(goals) == 1


def test_scoring_plays_from_commentary_fallback():
    # No goal in details or scoringPlays, but present in commentary
    event = {
        "competitions": [
            {
                "details": [],
                "competitors": [
                    {"team": {"id": "home", "displayName": "Brasil"}}
                ]
            }
        ],
        "scoringPlays": [],
        "commentary": [
            {
                "sequence": "10",
                "text": "Gol do Brasil!",
                "time": {"displayValue": "30'"},
                "play": {
                    "type": {"type": "goal", "text": "Goal"},
                    "text": "Gol de Vinicius Jr.",
                    "team": {"displayName": "Brasil"},
                    "participants": [
                        {"athlete": {"id": "10", "displayName": "Vini Jr"}}
                    ]
                }
            }
        ]
    }

    goals = scoring_plays_from_event(event)
    assert len(goals) == 1
    assert goals[0]["athletesInvolved"][0]["displayName"] == "Vini Jr"
    assert goals[0]["clock"]["displayValue"] == "30'"


def test_penalty_plays_from_event():
    event = {
        "competitions": [
            {
                "details": [
                    {
                        "type": {"type": "penalty", "text": "Penalty Kick"},
                        "team": {"id": "away"},
                        "clock": {"displayValue": "60'"},
                        "text": "Penalty scored by Kane",
                    }
                ]
            }
        ],
        "scoringPlays": []
    }

    penalties = penalty_plays_from_event(event)
    assert len(penalties) == 1
    assert penalties[0]["clock"]["displayValue"] == "60'"


def test_penalty_plays_deduplicates_same_minute_variants():
    event = {
        "competitions": [
            {
                "details": [
                    {
                        "type": {"type": "penalty", "text": "Penalty"},
                        "team": {"id": "home"},
                        "clock": {"displayValue": "14'"},
                        "text": "Penalty conceded by Mahmoud Abunada after a foul in the penalty area.",
                    },
                    {
                        "type": {"type": "penalty", "text": "Penalty"},
                        "team": {"id": "away"},
                        "clock": {"displayValue": "14'"},
                        "text": "Penalty Switzerland. Remo Freuler draws a foul in the penalty area.",
                    },
                ]
            }
        ],
        "scoringPlays": [],
    }

    penalties = penalty_plays_from_event(event)

    assert len(penalties) == 1
    assert penalties[0]["team"]["id"] == "away"


def test_penalty_plays_ignores_converted_penalty_goal():
    event = {
        "competitions": [
            {
                "details": [
                    {
                        "id": "goal-1",
                        "scoringPlay": True,
                        "type": {"type": "goal", "text": "Penalty Kick"},
                        "team": {"id": "away"},
                        "clock": {"displayValue": "17'"},
                        "text": "Goal! Qatar 0, Switzerland 1. Breel Embolo converts the penalty.",
                    }
                ]
            }
        ],
        "scoringPlays": [],
    }

    assert penalty_plays_from_event(event) == []


def test_red_cards_from_event_details():
    event = {
        "competitions": [
            {
                "details": [
                    {
                        "redCard": True,
                        "team": {"id": "home"},
                        "clock": {"displayValue": "75'"},
                        "athletesInvolved": [{"id": "5", "displayName": "Casemiro"}],
                        "text": "Casemiro sent off"
                    }
                ]
            }
        ]
    }

    cards = red_cards_from_event(event)
    assert len(cards) == 1
    assert cards[0]["athlete"]["displayName"] == "Casemiro"
    assert cards[0]["clock"]["displayValue"] == "75'"


def test_red_cards_from_roster_fallback():
    # Roster stat shows red card
    event = {
        "competitions": [{"details": []}],
        "rosters": [
            {
                "roster": [
                    {
                        "athlete": {"id": "8", "displayName": "Kroos"},
                        "stats": [
                            {"name": "redCards", "value": 1}
                        ]
                    }
                ]
            }
        ]
    }

    cards = red_cards_from_event(event)
    assert len(cards) == 1
    assert cards[0]["athlete"]["displayName"] == "Kroos"
