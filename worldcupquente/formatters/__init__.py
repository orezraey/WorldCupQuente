"""Telegram message formatters package."""

from __future__ import annotations

from worldcupquente.formatters.games import (
    format_games,
    format_history_game_details,
    format_history_games,
    format_history_player_ratings,
    format_history_statistics,
    format_live_games,
    format_live_games_rich,
    format_player_ratings_table,
    format_today_games,
)
from worldcupquente.formatters.notifications import (
    format_full_time_notification_rich,
    format_goal_notification,
    format_kickoff_notification,
    format_match_status_notification,
    format_penalty_notification,
    format_pre_game_notification,
    format_red_card_notification,
)
from worldcupquente.formatters.rosters import format_team_roster
from worldcupquente.formatters.standings import format_standings_group_table
from worldcupquente.formatters.utils import split_telegram_message

__all__ = [
    "split_telegram_message",
    "format_today_games",
    "format_live_games",
    "format_live_games_rich",
    "format_history_games",
    "format_history_game_details",
    "format_history_statistics",
    "format_history_player_ratings",
    "format_player_ratings_table",
    "format_games",
    "format_standings_group_table",
    "format_team_roster",
    "format_match_status_notification",
    "format_full_time_notification_rich",
    "format_goal_notification",
    "format_kickoff_notification",
    "format_penalty_notification",
    "format_pre_game_notification",
    "format_red_card_notification",
]
