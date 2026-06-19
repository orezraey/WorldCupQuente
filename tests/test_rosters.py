"""Unit tests for team roster and SofaScore team formatters."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from worldcupquente.formatters import format_sofascore_team_events


def test_sofascore_last_games_can_render_newest_first():
    events = [
        _event("Older", 1_700_000_000),
        _event("Newest", 1_800_000_000),
    ]

    message = format_sofascore_team_events(
        events,
        {"name": "Brazil", "country": {"alpha2": "BR"}},
        ZoneInfo("UTC"),
        "Last games",
        "No games",
        newest_first=True,
    )

    assert message.index("Newest") < message.index("Older")


def _event(home_name: str, timestamp: int) -> dict:
    return {
        "startTimestamp": timestamp,
        "homeTeam": {"name": home_name},
        "awayTeam": {"name": "Away"},
        "homeScore": {"current": 1},
        "awayScore": {"current": 0},
        "status": {"type": "finished", "description": "Ended"},
    }
