"""Unit tests for bot language support."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from worldcupquente.commands import build_bot_commands
from worldcupquente.formatters import format_games, format_today_games
from worldcupquente.keyboards import (
    build_back_to_teams_keyboard,
    build_notification_config_keyboard,
    build_sofascore_teams_keyboard,
)
from worldcupquente.notification_preferences import (
    LANGUAGE_KEY,
    PRE_GAME_NOTIFICATION,
    TEAM_SCOPE_ALL,
    TEAM_SCOPE_FOLLOWED,
    NotificationPreferences,
)
from worldcupquente.team_translations import (
    translated_sofascore_team_name,
    translated_team_name,
    translated_team_name_html,
)


def test_notification_preferences_default_and_persisted_language():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        path = Path(temp_dir) / "notification_config.json"
        preferences = NotificationPreferences(path)

        assert preferences.get_language(123) == "en"

        settings = preferences.set_language(123, "pt")

        assert settings[LANGUAGE_KEY] == "pt"
        assert NotificationPreferences(path).get_language(123) == "pt"


def test_language_update_registers_chat_with_default_notifications():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        preferences = NotificationPreferences(Path(temp_dir) / "notification_config.json")

        preferences.set_language(123, "pt")

        assert preferences.configured_chat_ids() == [123]
        assert preferences.has_recipients(())
        assert preferences.get(123)[PRE_GAME_NOTIFICATION] is True
        assert preferences.get_team_scope(123) == TEAM_SCOPE_ALL


def test_legacy_language_only_preference_does_not_subscribe_chat_to_notifications():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        path = Path(temp_dir) / "notification_config.json"
        path.write_text(json.dumps({"chats": {"123": {"language": "pt"}}}), encoding="utf-8")

        preferences = NotificationPreferences(path)

        assert preferences.configured_chat_ids() == []
        assert not preferences.has_recipients(())


def test_legacy_notification_preferences_default_to_portuguese():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        path = Path(temp_dir) / "notification_config.json"
        path.write_text(
            json.dumps({"chats": {"123": {"goal": True, "penalty": False, "red_card": True}}}),
            encoding="utf-8",
        )

        preferences = NotificationPreferences(path)

        assert preferences.get_language(123) == "pt"
        assert preferences.configured_chat_ids() == [123]


def test_bot_commands_are_localized():
    english_commands = build_bot_commands("en")
    portuguese_commands = build_bot_commands("pt")

    assert [command.command for command in english_commands] == [
        "start",
        "today",
        "live",
        "calendar",
        "history",
        "standings",
        "playoff",
        "teams",
        "config",
    ]
    assert [command.command for command in portuguese_commands] == [
        "start",
        "hoje",
        "aovivo",
        "calendario",
        "historico",
        "tabela",
        "matamata",
        "selecoes",
        "config",
    ]


def test_notification_config_keyboard_uses_selected_language():
    settings = NotificationPreferences._default_settings()
    settings[LANGUAGE_KEY] = "pt"

    keyboard = build_notification_config_keyboard(settings, "pt")

    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "Seleções" in labels
    assert "* Todas" in labels
    assert "Jogo começando: ligado" in labels
    assert "Gol: ligado" in labels
    assert "Idioma" in labels
    assert "* 🇧🇷 Português" in labels


def test_team_scope_filters_enabled_chat_ids_by_followed_teams():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        preferences = NotificationPreferences(Path(temp_dir) / "notification_config.json")
        preferences.ensure_chat(123)
        preferences.ensure_chat(456)
        preferences.set_team_scope(456, TEAM_SCOPE_FOLLOWED)
        preferences.toggle_followed_team(456, "bra")

        assert preferences.enabled_chat_ids(PRE_GAME_NOTIFICATION, (), {"bra", "arg"}) == [123, 456]
        assert preferences.enabled_chat_ids(PRE_GAME_NOTIFICATION, (), {"arg"}) == [123]


def test_migrate_followed_team_ids_replaces_legacy_ids_with_sofascore():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        path = Path(temp_dir) / "notification_config.json"
        preferences = NotificationPreferences(path)
        preferences.set_team_scope(123, TEAM_SCOPE_FOLLOWED)
        preferences.toggle_followed_team(123, "205")
        preferences.toggle_followed_team(123, "482")

        migrated = preferences.migrate_followed_team_ids({"205": "4748", "482": "4704"})

        assert migrated == 2
        assert preferences.followed_team_ids(123) == ["4704", "4748"]


def test_migrate_followed_team_ids_preserves_already_sofascore_ids():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        path = Path(temp_dir) / "notification_config.json"
        preferences = NotificationPreferences(path)
        preferences.set_team_scope(123, TEAM_SCOPE_FOLLOWED)
        preferences.toggle_followed_team(123, "4748")

        migrated = preferences.migrate_followed_team_ids({"205": "4748"})

        assert migrated == 0
        assert preferences.followed_team_ids(123) == ["4748"]


def test_migrate_followed_team_ids_skips_when_already_migrated():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        path = Path(temp_dir) / "notification_config.json"
        preferences = NotificationPreferences(path)
        preferences.set_team_scope(123, TEAM_SCOPE_FOLLOWED)
        preferences.toggle_followed_team(123, "205")

        preferences.migrate_followed_team_ids({"205": "4748"})
        migrated_again = preferences.migrate_followed_team_ids({"205": "4748"})

        assert migrated_again == 0
        assert preferences.followed_team_ids(123) == ["4748"]


def test_migrated_followed_team_ids_persist_to_disk():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        path = Path(temp_dir) / "notification_config.json"
        preferences = NotificationPreferences(path)
        preferences.set_team_scope(123, TEAM_SCOPE_FOLLOWED)
        preferences.toggle_followed_team(123, "205")

        preferences.migrate_followed_team_ids({"205": "4748"})

        reloaded = NotificationPreferences(path)
        assert reloaded.followed_team_ids(123) == ["4748"]


def test_team_notifications_button_only_when_requested():
    keyboard = build_back_to_teams_keyboard(
        language="pt",
        team_id="bra",
        show_notifications_button=True,
        is_following=False,
    )
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "Habilitar notificações" in labels
    assert "Voltar para seleções" in labels

    keyboard = build_back_to_teams_keyboard(language="pt", team_id="bra", show_notifications_button=False)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert labels == ["Voltar para seleções"]


def test_team_names_are_localized():
    team = {"id": "481"}

    assert translated_team_name(team, include_emoji=False) == "Germany"
    assert translated_team_name(team, include_emoji=False, language="pt") == "Alemanha"


def test_sofascore_team_names_are_localized():
    brazil = {"id": 4748, "name": "Brazil", "country": {"alpha2": "BR"}}
    canada = {"id": 4722, "name": "Canada", "country": {"alpha2": "CA"}}

    assert translated_sofascore_team_name(brazil, include_emoji=False, language="pt") == "Brasil"
    assert translated_sofascore_team_name(canada, include_emoji=False, language="pt") == "Canadá"

    keyboard = build_sofascore_teams_keyboard([brazil, canada], language="pt")
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "🇧🇷 Brasil" in labels
    assert "🇨🇦 Canadá" in labels


def test_sofascore_team_translation_prefers_name_over_legacy_id_collision():
    paraguay = {
        "id": "4789",
        "name": "Paraguay",
        "displayName": "Paraguay",
        "country": {"alpha2": "PY"},
        "source": "sofascore",
    }

    assert translated_team_name(paraguay, language="pt") == "🇵🇾 Paraguai"
    assert translated_team_name_html(paraguay, language="pt") == "🇵🇾 Paraguai"


def test_format_games_uses_sofascore_team_name_for_legacy_id_collision():
    event = {
        "date": "2026-06-20T03:00:00Z",
        "status": {"type": {"state": "post", "shortDetail": "FT"}, "displayClock": "FT"},
        "competitions": [
            {
                "status": {"type": {"state": "post", "shortDetail": "FT"}, "displayClock": "FT"},
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {
                            "id": "4700",
                            "name": "Turkiye",
                            "displayName": "Turkiye",
                            "country": {"alpha2": "TR"},
                            "source": "sofascore",
                        },
                        "score": "0",
                    },
                    {
                        "homeAway": "away",
                        "team": {
                            "id": "4789",
                            "name": "Paraguay",
                            "displayName": "Paraguay",
                            "country": {"alpha2": "PY"},
                            "source": "sofascore",
                        },
                        "score": "1",
                    },
                ],
            }
        ],
    }

    output = format_games([event], ZoneInfo("America/Sao_Paulo"), "Hoje", language="pt")

    assert "🇹🇷 Turquia 0 x 1 🇵🇾 Paraguai" in output
    assert "Costa do Marfim" not in output


def test_today_games_defaults_to_english_and_supports_portuguese():
    scoreboard = {"events": []}

    assert format_today_games(scoreboard, ZoneInfo("UTC")) == "No World Cup match found for today."
    assert (
        format_today_games(scoreboard, ZoneInfo("UTC"), "pt")
        == "Nenhum jogo da Copa do Mundo encontrado para hoje."
    )


def test_format_games_hides_not_started_status():
    event = _formatted_game_event(state="pre", short_detail="Not started")

    output = format_games([event], ZoneInfo("UTC"), "Calendário", language="pt")

    assert "Status:" not in output
    assert "Not started" not in output


def test_format_games_prefers_live_match_minute_status():
    event = _formatted_game_event(state="in", short_detail="2nd half", display_clock="69'")

    output = format_games([event], ZoneInfo("UTC"), "Ao vivo", language="pt")

    assert "Status: 69&#x27;" in output
    assert "2nd half" not in output


def test_format_games_translates_live_period_status_without_minute():
    event = _formatted_game_event(state="in", short_detail="2nd half", display_clock="")

    output = format_games([event], ZoneInfo("UTC"), "Ao vivo", language="pt")

    assert "Status: Segundo tempo" in output
    assert "2nd half" not in output


def test_live_games_formatting_includes_blank_line_before_goals():
    from worldcupquente.formatters import format_live_games, format_live_games_rich

    event = {
        "date": "2026-06-12T19:00:00Z",
        "status": {
            "type": {
                "state": "in",
                "shortDetail": "First Half",
                "detail": "First Half",
            },
            "displayClock": "22'",
        },
        "competitions": [
            {
                "status": {
                    "type": {
                        "state": "in",
                        "shortDetail": "First Half",
                        "detail": "First Half",
                    },
                    "displayClock": "22'",
                },
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "can", "name": "Canada", "abbreviation": "CAN"},
                        "score": "0"
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "bih", "name": "Bosnia", "abbreviation": "BIH"},
                        "score": "1"
                    }
                ],
                "venue": {"fullName": "BMO Field"},
            }
        ],
        "scoringPlays": [
            {
                "athletesInvolved": [{"displayName": "Jovo Lukic"}],
                "clock": {"displayValue": "21'"},
            }
        ]
    }

    # Verify plain text/HTML output (format_live_games)
    plain_output = format_live_games([event], ZoneInfo("UTC"), language="pt")
    assert "🏟 Estádio: BMO Field\n\n⚽️ Jovo Lukic 21&#x27;" in plain_output

    # Verify rich HTML output (format_live_games_rich)
    rich_output = format_live_games_rich([event], ZoneInfo("UTC"), language="pt", show_ratings=True)
    assert "🏟 Estádio: BMO Field<br/><br/>⚽️ Jovo Lukic 21&#x27;" in rich_output


def test_live_games_rich_includes_sofascore_rating_table_with_emojis():
    from worldcupquente.formatters import format_live_games_rich

    event = _live_event_with_ratings()

    rich_output = format_live_games_rich([event], ZoneInfo("UTC"), language="pt", show_ratings=True)

    assert '<tg-emoji emoji-id="5431497092281421497">⭐</tg-emoji> Notas SofaScore' in rich_output
    assert '<tg-emoji emoji-id="5283257193708147680">⭐</tg-emoji> #8 Home Player' in rich_output
    assert '<tg-emoji emoji-id="5280826091894755088">⭐</tg-emoji> #10 Away Player' in rich_output
    assert "#8 Home Player" in rich_output
    assert "#10 Away Player (res)" in rich_output


def test_live_games_groups_scorer_goals_and_separates_red_cards():
    from worldcupquente.formatters import format_live_games

    event = {
        "date": "2026-06-13T01:00:00Z",
        "competitions": [
            {
                "status": {
                    "type": {"state": "post", "shortDetail": "FT", "detail": "FT"},
                    "displayClock": "90'+9'",
                },
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "660", "displayName": "United States", "abbreviation": "USA"},
                        "score": "4",
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "210", "displayName": "Paraguay", "abbreviation": "PAR"},
                        "score": "1",
                    },
                ],
                "venue": {"fullName": "SoFi Stadium"},
                "details": [
                    {
                        "scoringPlay": True,
                        "ownGoal": True,
                        "type": {"text": "Own Goal"},
                        "clock": {"displayValue": "7'"},
                        "athletesInvolved": [{"id": "301516", "displayName": "Damián Bobadilla"}],
                    },
                    {
                        "scoringPlay": True,
                        "clock": {"displayValue": "31'"},
                        "athletesInvolved": [{"id": "282643", "displayName": "Folarin Balogun"}],
                    },
                    {
                        "scoringPlay": True,
                        "clock": {"displayValue": "45'+5'"},
                        "athletesInvolved": [{"id": "282643", "displayName": "Folarin Balogun"}],
                    },
                    {
                        "redCard": True,
                        "clock": {"displayValue": "52'"},
                        "athletesInvolved": [{"id": "123", "displayName": "Tim Ream"}],
                    },
                ],
            }
        ],
        "scoringPlays": [],
    }

    output = format_live_games([event], ZoneInfo("UTC"), language="pt")

    assert "⚽️ Damián Bobadilla 7&#x27; (GC)" in output
    assert "⚽️ Folarin Balogun 31&#x27;, ⚽️ 45&#x27;+5&#x27;" in output
    assert "⚽️ Folarin Balogun 31&#x27;\n⚽️ Folarin Balogun 45&#x27;+5&#x27;" not in output
    assert "⚽️ Folarin Balogun 31&#x27;, ⚽️ 45&#x27;+5&#x27;\n\n" in output
    assert "Tim Ream 52&#x27;" in output


def test_win_probability_is_included_in_live_games_from_top_level_odds():
    from worldcupquente.formatters import format_live_games

    output = format_live_games([_win_probability_event(top_level_odds=True)], ZoneInfo("UTC"))

    assert "📊 Win Probability" in output
    assert "<b>📊 Win Probability</b>\n<blockquote>🇩🇪 Germany 34%" in output
    assert "🤝 Draw 33%" in output
    assert "🇨🇼 Curacao 33%</blockquote>" in output


def test_win_probability_is_localized_in_notifications():
    from worldcupquente.formatters import format_goal_notification, format_pre_game_notification

    event = _win_probability_event(state="pre")
    goal = {
        "clock": {"displayValue": "12'"},
        "athletesInvolved": [{"displayName": "Player One"}],
    }

    pre_game_output = format_pre_game_notification(event, ZoneInfo("UTC"), language="pt")
    goal_output = format_goal_notification(event, goal, language="pt")

    for output in (pre_game_output, goal_output):
        assert "📊 Probabilidade de vitória" in output
        assert "<b>📊 Probabilidade de vitória</b>\n<blockquote>🇩🇪 Alemanha 34%" in output
        assert "🤝 Empate 33%" in output
        assert "🇨🇼 Curaçao 33%</blockquote>" in output


def test_goal_notification_uses_incident_score_after_when_event_score_lags():
    from worldcupquente.formatters import format_goal_notification

    event = _win_probability_event()
    event["competitions"][0]["competitors"][0]["score"] = "0"
    event["competitions"][0]["competitors"][1]["score"] = "0"
    goal = {
        "team": {"id": "11678"},
        "clock": {"displayValue": "20'"},
        "athletesInvolved": [{"displayName": "Emam Ashour"}],
        "scoreAfter": {"home": 0, "away": 1},
    }

    output = format_goal_notification(event, goal, language="pt")

    assert "⚽️ <b>GOL!</b> 🇨🇼 Curaçao" in output
    assert "🇩🇪 Alemanha 0 x 1 🇨🇼 Curaçao" in output
    assert "🇩🇪 Alemanha 0 x 0 🇨🇼 Curaçao" not in output


def test_own_goal_notification_shows_benefiting_team():
    from worldcupquente.formatters import format_goal_notification
    from worldcupquente.services import _normalize_sofascore_incidents

    event = {
        "competitions": [
            {
                "status": {"type": {"state": "in"}},
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "482", "displayName": "Portugal", "abbreviation": "POR"},
                        "score": "4",
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "2570", "displayName": "Uzbekistan", "abbreviation": "UZB"},
                        "score": "0",
                    },
                ],
            }
        ],
    }
    normalized = _normalize_sofascore_incidents(
        event,
        [
            {
                "id": 99,
                "incidentType": "goal",
                "incidentClass": "ownGoal",
                "time": 60,
                "isHome": True,
                "homeScore": 4,
                "awayScore": 0,
                "player": {"id": 1, "name": "Abduvokhid Nematov"},
            }
        ],
    )
    goal = normalized["goals"][0]

    output = format_goal_notification(event, goal, language="pt")

    assert "⚽️ <b>GOL CONTRA!</b> 🇵🇹 Portugal" in output
    assert "Uzbequist" not in output.split("\n", 1)[0]
    assert "Abduvokhid Nematov" in output
    assert "🇵🇹 Portugal 4 x 0 🇺🇿 Uzbequistão" in output


def test_win_probability_is_omitted_when_odds_are_null():
    from worldcupquente.formatters import format_live_games

    event = _win_probability_event()
    event.pop("winProbability", None)
    event["competitions"][0]["odds"] = [None]

    output = format_live_games([event], ZoneInfo("UTC"))

    assert "Win Probability" not in output


def _formatted_game_event(
    *,
    state: str,
    short_detail: str,
    display_clock: str = "",
) -> dict[str, object]:
    status = {
        "type": {"state": state, "shortDetail": short_detail, "detail": short_detail},
        "displayClock": display_clock,
    }
    return {
        "date": "2026-06-17T17:00:00Z",
        "status": status,
        "competitions": [
            {
                "status": status,
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "4748", "displayName": "Brazil", "abbreviation": "BRA"},
                        "score": "1" if state == "in" else "-",
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "4704", "displayName": "Portugal", "abbreviation": "POR"},
                        "score": "0" if state == "in" else "-",
                    },
                ],
                "venue": {"fullName": "NRG Stadium"},
            }
        ],
    }


def _win_probability_event(state: str = "in", top_level_odds: bool = False) -> dict[str, object]:
    win_probability = {"home": 34, "draw": 33, "away": 33}
    competition = {
        "status": {
            "type": {"state": state, "shortDetail": "First Half" if state == "in" else "Scheduled"},
            "displayClock": "12'" if state == "in" else None,
        },
        "competitors": [
            {
                "homeAway": "home",
                "team": {"id": "481", "displayName": "Germany", "abbreviation": "GER"},
                "score": "0",
            },
            {
                "homeAway": "away",
                "team": {"id": "11678", "displayName": "Curacao", "abbreviation": "CUW"},
                "score": "0",
            },
        ],
        "venue": {"fullName": "Hard Rock Stadium"},
    }
    event = {
        "date": "2026-06-14T19:00:00Z",
        "status": competition["status"],
        "competitions": [competition],
        "winProbability": win_probability,
    }
    return event


def _live_event_with_ratings() -> dict[str, object]:
    return {
        "date": "2026-06-12T19:00:00Z",
        "competitions": [
            {
                "status": {
                    "type": {"state": "in", "shortDetail": "First Half"},
                    "displayClock": "22'",
                },
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "home", "displayName": "Netherlands", "abbreviation": "NED"},
                        "score": "1",
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "away", "displayName": "Japan", "abbreviation": "JPN"},
                        "score": "0",
                    },
                ],
                "venue": {"fullName": "BMO Field"},
            }
        ],
        "sofascorePlayerRatings": {
            "home": [
                {"name": "Home Player", "shirtNumber": 8, "substitute": False, "rating": 7.8},
            ],
            "away": [
                {"name": "Away Player", "shirtNumber": 10, "substitute": True, "rating": 10.0},
            ],
        },
    }
