"""Unit tests for SofaScore event normalization helpers."""

from __future__ import annotations

from worldcupquente.services import _normalize_sofascore_event


def test_normalize_sofascore_event_keeps_history_formatter_shape():
    event = _normalize_sofascore_event(
        {
            "id": 15186709,
            "startTimestamp": 1781715600,
            "status": {"type": "finished", "description": "Ended"},
            "homeTeam": {"id": 4704, "name": "Portugal", "nameCode": "POR", "country": {"alpha2": "PT"}},
            "awayTeam": {"id": 4752, "name": "DR Congo", "nameCode": "DCO", "country": {"alpha2": "CD"}},
            "homeScore": {"current": 1},
            "awayScore": {"current": 1},
            "venue": {"name": "NRG Stadium"},
        }
    )

    competition = event["competitions"][0]

    assert event["id"] == "15186709"
    assert event["source"] == "sofascore"
    assert competition["status"]["type"]["state"] == "post"
    assert competition["competitors"][0]["homeAway"] == "home"
    assert competition["competitors"][0]["score"] == "1"
    assert competition["competitors"][1]["team"]["name"] == "DR Congo"
    assert competition["venue"]["fullName"] == "NRG Stadium"


def test_normalize_sofascore_live_event_formats_match_minute_clock():
    event = _normalize_sofascore_event(
        {
            "id": 15186709,
            "startTimestamp": 1781715600,
            "status": {"type": "inprogress", "description": "2nd half"},
            "time": {"initial": 4080},
            "homeTeam": {"id": 4704, "name": "Portugal", "nameCode": "POR"},
            "awayTeam": {"id": 4752, "name": "DR Congo", "nameCode": "DCO"},
            "homeScore": {"current": 1},
            "awayScore": {"current": 1},
        }
    )

    status = event["competitions"][0]["status"]

    assert status["type"]["state"] == "in"
    assert status["displayClock"] == "69'"
