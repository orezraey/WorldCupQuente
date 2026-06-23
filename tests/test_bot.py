"""Unit tests for bot initialization and setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.ext import Application

from worldcupquente.bot import post_init


@pytest.mark.asyncio
async def test_post_init_sets_commands_and_starts_monitor(mocker):
    # Mock start_live_monitor
    mock_start_live_monitor = mocker.patch(
        "worldcupquente.bot.start_live_monitor", new_callable=AsyncMock
    )

    # Mock application and bot
    mock_app = MagicMock(spec=Application)
    mock_app.bot = MagicMock()
    mock_app.bot.set_my_commands = AsyncMock()

    # Call post_init
    await post_init(mock_app)

    # Assert set_my_commands was called with expected commands
    mock_app.bot.set_my_commands.assert_called_once()
    called_commands = mock_app.bot.set_my_commands.call_args[0][0]

    assert len(called_commands) == 9
    assert called_commands[0].command == "start"
    assert called_commands[0].description == "Start the bot and see commands"
    assert called_commands[1].command == "today"
    assert called_commands[2].command == "live"
    assert called_commands[3].command == "calendar"
    assert called_commands[4].command == "history"
    assert called_commands[5].command == "standings"
    assert called_commands[6].command == "playoff"
    assert called_commands[7].command == "teams"
    assert called_commands[8].command == "config"

    # Assert start_live_monitor was called
    mock_start_live_monitor.assert_called_once_with(mock_app)


@pytest.mark.asyncio
async def test_post_init_handles_exception_and_still_starts_monitor(mocker):
    # Mock start_live_monitor
    mock_start_live_monitor = mocker.patch(
        "worldcupquente.bot.start_live_monitor", new_callable=AsyncMock
    )

    # Mock application and bot to raise error
    mock_app = MagicMock(spec=Application)
    mock_app.bot = MagicMock()
    mock_app.bot.set_my_commands = AsyncMock(side_effect=Exception("API Error"))

    # Call post_init (should not raise)
    await post_init(mock_app)

    # Assert start_live_monitor was still called
    mock_app.bot.set_my_commands.assert_called_once()
    mock_start_live_monitor.assert_called_once_with(mock_app)
