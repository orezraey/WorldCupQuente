"""Unit tests for live lineups and player detail formatters."""

from __future__ import annotations

from worldcupquente.formatters.players import (
    format_match_lineups,
    format_player_detail_caption,
    format_player_match_statistics,
    lineup_player_rating,
)


def test_format_match_lineups_shows_formation_and_starters():
    lineups = {
        "confirmed": True,
        "home": {
            "formation": "4-3-3",
            "players": [
                {
                    "player": {"id": 1, "name": "Home Starter", "shortName": "H. Starter"},
                    "shirtNumber": 10,
                    "substitute": False,
                    "statistics": {"rating": 7.2},
                },
            ],
        },
        "away": {"formation": "5-4-1", "players": []},
    }

    body = format_match_lineups(lineups, "USA", "Australia", language="pt")

    assert "USA (4-3-3)" in body
    assert "Australia (5-4-1)" in body
    assert "H. Starter" in body
    assert "7.2" in body
    assert "Reservas" not in body


def test_format_match_lineups_includes_subs_when_toggled():
    lineups = {
        "confirmed": True,
        "home": {
            "formation": "4-3-3",
            "players": [
                {
                    "player": {"id": 1, "name": "Starter"},
                    "shirtNumber": 1,
                    "substitute": False,
                    "statistics": {"rating": 6.5},
                },
                {
                    "player": {"id": 2, "name": "Sub Guy"},
                    "shirtNumber": 12,
                    "substitute": True,
                    "statistics": {"rating": 6.0},
                },
            ],
        },
        "away": {"players": []},
    }

    body = format_match_lineups(lineups, "A", "B", show_subs=True, language="en")

    assert "Substitutes" in body
    assert "Sub Guy" in body


def test_format_match_lineups_empty_when_no_players():
    body = format_match_lineups({"home": {"players": []}}, "A", "B", language="en")
    assert "not available" in body.lower()


def test_format_player_detail_caption_renders_personal_data():
    detail = {
        "shortName": "M. Freese",
        "position": "G",
        "team": {"shortName": "NY City", "name": "New York City FC"},
        "country": {"name": "USA"},
        "height": 193,
        "weight": 88,
        "preferredFoot": "Right",
        "dateOfBirthTimestamp": 904694400,
        "shirtNumber": 24,
    }

    caption = format_player_detail_caption(detail, rating=6.8, language="pt")

    assert "M. Freese" in caption
    assert "Nota SofaScore" in caption
    assert "6.8" in caption
    assert "193 cm" in caption
    assert "88 kg" in caption
    assert "Direito" in caption
    assert "USA" in caption
    assert "Goleiro" in caption
    assert "02/09/1998" in caption


def test_format_player_detail_caption_handles_missing_data():
    caption = format_player_detail_caption({}, language="en")
    assert "unavailable" in caption.lower()


def test_format_player_match_statistics_lists_all_keys():
    item = {
        "statistics": {
            "minutesPlayed": 90,
            "goals": 1,
            "totalPass": 45,
            "expectedGoals": 0.34,
            "ratingVersions": {"original": 7.5},
            "statisticsType": {"sportSlug": "football"},
            "saves": None,
        }
    }

    body = format_player_match_statistics(item, language="pt")

    assert "Minutos jogados: 90" in body
    assert "Gols: 1" in body
    assert "Passes: 45" in body
    assert "Gols esperados" in body
    assert "ratingVersions" not in body
    assert "statisticsType" not in body
    assert "Saves" not in body


def test_format_player_match_statistics_unknown_key_falls_back_to_humanized():
    body = format_player_match_statistics({"statistics": {"someNewMetric": 3}}, language="en")
    assert "Some new metric: 3" in body


def test_format_player_match_statistics_empty_when_no_statistics():
    body = format_player_match_statistics({}, language="en")
    assert "No match statistics" in body


def test_lineup_player_rating_reads_statistics_block():
    assert lineup_player_rating({"statistics": {"rating": 7.4}}) == 7.4
    assert lineup_player_rating({"rating": 6.9}) == 6.9
    assert lineup_player_rating({}) is None
