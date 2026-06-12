"""Unit tests for bot language support."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from worldcupquente.commands import build_bot_commands
from worldcupquente.formatters import format_today_games
from worldcupquente.keyboards import build_notification_config_keyboard
from worldcupquente.notification_preferences import LANGUAGE_KEY, NotificationPreferences
from worldcupquente.team_translations import translated_team_name


def test_notification_preferences_default_and_persisted_language():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        path = Path(temp_dir) / "notification_config.json"
        preferences = NotificationPreferences(path)

        assert preferences.get_language(123) == "en"

        settings = preferences.set_language(123, "pt")

        assert settings[LANGUAGE_KEY] == "pt"
        assert NotificationPreferences(path).get_language(123) == "pt"


def test_language_only_preference_does_not_subscribe_chat_to_notifications():
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        preferences = NotificationPreferences(Path(temp_dir) / "notification_config.json")

        preferences.set_language(123, "pt")

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
        "standings",
        "teams",
        "config",
    ]
    assert [command.command for command in portuguese_commands] == [
        "start",
        "hoje",
        "aovivo",
        "calendario",
        "tabela",
        "selecoes",
        "config",
    ]


def test_notification_config_keyboard_uses_selected_language():
    settings = NotificationPreferences._default_settings()
    settings[LANGUAGE_KEY] = "pt"

    keyboard = build_notification_config_keyboard(settings, "pt")

    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "Gol: ligado" in labels
    assert "Idioma" in labels
    assert "* 🇧🇷 Português" in labels


def test_team_names_are_localized():
    team = {"id": "481"}

    assert translated_team_name(team, include_emoji=False) == "Germany"
    assert translated_team_name(team, include_emoji=False, language="pt") == "Alemanha"


def test_today_games_defaults_to_english_and_supports_portuguese():
    scoreboard = {"events": []}

    assert format_today_games(scoreboard, ZoneInfo("UTC")) == "No World Cup match found for today."
    assert (
        format_today_games(scoreboard, ZoneInfo("UTC"), "pt")
        == "Nenhum jogo da Copa do Mundo encontrado para hoje."
    )
