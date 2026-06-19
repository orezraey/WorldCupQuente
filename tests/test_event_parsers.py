"""Unit tests for event parsers and incident extraction utilities."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from worldcupquente.event_incidents import (
    penalty_plays_from_event,
    red_cards_from_event,
    scoring_plays_from_event,
)
from worldcupquente.event_utils import parse_event_datetime


def test_parse_event_datetime_valid():
    tz = ZoneInfo("America/Sao_Paulo")
    # UTC time
    dt = parse_event_datetime("2026-06-12T15:30:00Z", tz)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 6
    assert dt.day == 12
    # UTC 15:30 is 12:30 in Sao Paulo (GMT-3)
    assert dt.hour == 12
    assert dt.minute == 30
    assert dt.tzinfo == tz


def test_parse_event_datetime_invalid():
    tz = ZoneInfo("UTC")
    assert parse_event_datetime("", tz) is None
    assert parse_event_datetime("invalid-date", tz) is None


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


def test_penalty_plays_ignores_plain_penalty_text_without_sofascore():
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

    assert penalty_plays_from_event(event) == []


def test_penalty_plays_ignores_var_checking_penalty_text():
    event = {
        "competitions": [
            {
                "details": [
                    {
                        "type": {"type": "var", "text": "VAR Checking"},
                        "team": {"id": "home"},
                        "clock": {"displayValue": "60'"},
                        "text": "VAR Checking: France Penalty.",
                    },
                ]
            }
        ],
        "scoringPlays": [],
    }

    assert penalty_plays_from_event(event) == []


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
