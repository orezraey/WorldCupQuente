"""Inline keyboards for the bot."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from worldcupquente.notification_preferences import NOTIFICATION_LABELS, NOTIFICATION_TYPES
from worldcupquente.team_translations import translated_team_name

TEAMS_PAGE_SIZE = 12
CALENDAR_GAMES_PAGE_SIZE = 6


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


def build_calendar_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Datas", callback_data="cal:dates"),
                InlineKeyboardButton("Seleções", callback_data="cal:teams:0"),
            ]
        ]
    )


def build_live_stats_keyboard(show_stats: bool = False) -> InlineKeyboardMarkup:
    label = "Esconder estatísticas" if show_stats else "Estatísticas"
    action = "hide" if show_stats else "show"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"live:stats:{action}")]])


def build_notification_config_keyboard(settings: dict[str, bool]) -> InlineKeyboardMarkup:
    rows = []
    for notification_type in NOTIFICATION_TYPES:
        state = "ligado" if settings.get(notification_type, True) else "desligado"
        label = f"{NOTIFICATION_LABELS[notification_type]}: {state}"
        rows.append([InlineKeyboardButton(label, callback_data=f"config:toggle:{notification_type}")])
    return InlineKeyboardMarkup(rows)


def build_calendar_dates_keyboard(date_params: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("Todos", callback_data="cal:all:0")]
    ]

    dates = sorted(set(date_params))
    for index in range(0, len(dates), 2):
        rows.append(
            [
                InlineKeyboardButton(_format_date_label(date), callback_data=f"cal:date:{date}")
                for date in dates[index : index + 2]
            ]
        )

    rows.append([InlineKeyboardButton("Voltar", callback_data="cal:menu")])
    return InlineKeyboardMarkup(rows)


def build_calendar_all_games_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(InlineKeyboardButton("Anterior", callback_data=f"cal:all:{page - 1}"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton("Próxima", callback_data=f"cal:all:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("Voltar para datas", callback_data="cal:dates")])
    return InlineKeyboardMarkup(rows)


def build_calendar_back_to_dates_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Voltar para datas", callback_data="cal:dates")]]
    )


def build_calendar_teams_keyboard(
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
                InlineKeyboardButton(
                    translated_team_name(team),
                    callback_data=f"cal:team:{team.get('id')}:{page}",
                )
            )
        rows.append(row)

    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(InlineKeyboardButton("Anterior", callback_data=f"cal:teams:{page - 1}"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton("Próxima", callback_data=f"cal:teams:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("Voltar", callback_data="cal:menu")])
    return InlineKeyboardMarkup(rows)


def build_calendar_back_to_teams_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Voltar para seleções", callback_data=f"cal:teams:{page}")]]
    )


def _format_date_label(date_param: str) -> str:
    weekdays = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    try:
        date = datetime.strptime(date_param, "%Y%m%d")
    except ValueError:
        return date_param
    return f"{weekdays[date.weekday()]} {date.strftime('%d/%m')}"
