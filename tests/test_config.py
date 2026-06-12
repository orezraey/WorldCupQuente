"""Unit tests for environment-backed settings parsing."""

from __future__ import annotations

from worldcupquente.config import get_settings


def test_get_settings_uses_defaults_for_invalid_numeric_values(monkeypatch):
    monkeypatch.setenv("ESPN_TIMEOUT", "invalid")
    monkeypatch.setenv("LIVE_POLL_INTERVAL_SECONDS", "invalid")

    settings = get_settings()

    assert settings.espn_timeout == 30.0
    assert settings.live_poll_interval_seconds == 30


def test_get_settings_enforces_minimum_live_poll_interval(monkeypatch):
    monkeypatch.setenv("LIVE_POLL_INTERVAL_SECONDS", "5")

    settings = get_settings()

    assert settings.live_poll_interval_seconds == 10
