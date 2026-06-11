"""Inline keyboards for the bot."""

from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from worldcupquente.team_translations import translated_team_name

TEAMS_PAGE_SIZE = 12


def build_teams_keyboard(
    teams: list[dict[str, Any]],
    page: int = 0,
    page_size: int = TEAMS_PAGE_SIZE,
) -> InlineKeyboardMarkup:
    teams = sorted(teams, key=lambda team: translated_team_name(team, include_emoji=False))
    total_pages = max(1, (len(teams) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_teams = teams[start : start + page_size]

    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(page_teams), 2):
        row = []
        for team in page_teams[index : index + 2]:
            row.append(
                InlineKeyboardButton(translated_team_name(team), callback_data=f"team:{team.get('id')}:{page}")
            )
        rows.append(row)

    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(InlineKeyboardButton("Anterior", callback_data=f"teams:{page - 1}"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton("Próxima", callback_data=f"teams:{page + 1}"))
    if navigation:
        rows.append(navigation)
    return InlineKeyboardMarkup(rows)


def build_back_to_teams_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Voltar para seleções", callback_data=f"teams:{page}")]]
    )
