"""Unit tests for SofaScore incident normalization."""

from __future__ import annotations

from worldcupquente.event_incidents import red_cards_from_event, scoring_plays_from_event
from worldcupquente.services import (
    _normalize_sofascore_incidents,
    _normalize_sofascore_match_statistics,
    _normalize_sofascore_player_ratings,
)


def test_normalize_sofascore_goal_and_red_card_incidents():
    event = _event()
    normalized = _normalize_sofascore_incidents(
        event,
        [
            {
                "id": 20,
                "incidentType": "card",
                "incidentClass": "yellowRed",
                "time": 68,
                "timeSeconds": 4080,
                "isHome": False,
                "player": {"id": 2, "name": "Player Two"},
            },
            {
                "id": 10,
                "incidentType": "goal",
                "incidentClass": "penalty",
                "time": 12,
                "timeSeconds": 720,
                "addedTime": 1,
                "isHome": True,
                "homeScore": 1,
                "awayScore": 0,
                "player": {"id": 1, "name": "Player One"},
            },
        ],
    )

    event["sofascoreIncidents"] = normalized
    goals = scoring_plays_from_event(event)
    cards = red_cards_from_event(event)

    assert goals[0]["id"] == "sofascore:10"
    assert goals[0]["source"] == "sofascore"
    assert goals[0]["team"]["id"] == "home"
    assert goals[0]["clock"]["seconds"] == 720
    assert goals[0]["clock"]["displayValue"] == "12'+1'"
    assert goals[0]["type"]["text"] == "Penalty Kick"
    assert goals[0]["scoreAfter"] == "1:0"
    assert goals[0]["athletesInvolved"][0]["displayName"] == "Player One"

    assert cards[0]["id"] == "sofascore:20"
    assert cards[0]["redCard"] is True
    assert cards[0]["team"]["id"] == "away"
    assert cards[0]["athlete"]["displayName"] == "Player Two"
    assert cards[0]["type"]["text"] == "Second Yellow"


def test_normalize_sofascore_reversed_match_swaps_side_and_score():
    normalized = _normalize_sofascore_incidents(
        _event(),
        [
            {
                "id": 10,
                "type": "goal",
                "incidentClass": "regular",
                "time": 30,
                "isHome": True,
                "homeScore": 1,
                "awayScore": 2,
                "playerName": "Player One",
            }
        ],
        reversed_match=True,
    )

    goal = normalized["goals"][0]

    assert goal["team"]["id"] == "away"
    assert goal["scoreAfter"] == "2:1"


def test_sofascore_incidents_are_preferred_over_espn_heuristics():
    event = _event()
    event["competitions"][0]["details"] = [
        {
            "id": "espn-goal",
            "scoringPlay": True,
            "team": {"id": "home"},
            "clock": {"displayValue": "10'"},
            "athletesInvolved": [{"id": "espn-player", "displayName": "ESPN Player"}],
        }
    ]
    event["sofascoreIncidents"] = {
        "goals": [
            {
                "id": "sofascore:10",
                "source": "sofascore",
                "scoringPlay": True,
                "team": {"id": "away"},
                "clock": {"displayValue": "12'"},
                "athletesInvolved": [{"id": "sofa-player", "displayName": "Sofa Player"}],
            }
        ],
        "redCards": [],
    }

    goals = scoring_plays_from_event(event)

    assert len(goals) == 1
    assert goals[0]["id"] == "sofascore:10"


def test_normalize_sofascore_player_ratings_sorts_by_rating():
    ratings = _normalize_sofascore_player_ratings(
        {
            "home": {
                "players": [
                    {
                        "player": {"id": 1, "name": "Player One"},
                        "shirtNumber": 10,
                        "position": "M",
                        "substitute": False,
                        "statistics": {"rating": 7.2},
                    },
                    {
                        "player": {"id": 2, "name": "Player Two"},
                        "shirtNumber": 11,
                        "position": "F",
                        "substitute": True,
                        "statistics": {"rating": 8.4},
                    },
                ]
            },
            "away": {"players": []},
        }
    )

    assert [player["name"] for player in ratings["home"]] == ["Player Two", "Player One"]
    assert ratings["home"][0]["substitute"] is True


def test_normalize_sofascore_match_statistics_keeps_key_rows():
    statistics = [
        {
            "period": "ALL",
            "groups": [
                {
                    "statisticsItems": [
                        {"key": "expectedGoals", "name": "Expected goals", "home": "2.29", "away": "0.30"},
                        {"key": "totalShotsOnGoal", "name": "Total shots", "home": "27", "away": "6"},
                    ]
                }
            ],
        }
    ]

    rows = _normalize_sofascore_match_statistics(statistics)

    assert rows == [
        {"key": "expectedGoals", "name": "Expected goals", "home": "2.29", "away": "0.30"},
        {"key": "totalShotsOnGoal", "name": "Total shots", "home": "27", "away": "6"},
    ]


def _event() -> dict:
    return {
        "id": "match-1",
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "team": {"id": "home", "displayName": "Home"}},
                    {"homeAway": "away", "team": {"id": "away", "displayName": "Away"}},
                ],
                "details": [],
            }
        ],
        "scoringPlays": [],
    }
