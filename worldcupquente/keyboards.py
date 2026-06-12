"""Inline keyboards for the bot."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from worldcupquente.i18n import LANGUAGE_LABELS, text
from worldcupquente.notification_preferences import (
    LANGUAGE_KEY,
    NOTIFICATION_TYPES,
    TEAM_SCOPE_ALL,
    TEAM_SCOPE_FOLLOWED,
    TEAM_SCOPE_KEY,
)
from worldcupquente.team_translations import translated_team_name

TEAMS_PAGE_SIZE = 12
CALENDAR_GAMES_PAGE_SIZE = 6


def build_standings_groups_keyboard(
    groups: list[dict[str, Any]],
    language: str = "en",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    buttons = [
        InlineKeyboardButton(
            _standings_group_label(group, language), callback_data=f"table:group:{group.get('id')}"
        )
        for group in sorted(groups, key=_standings_group_sort_key)
        if group.get("id")
    ]
    for index in range(0, len(buttons), 4):
        rows.append(buttons[index : index + 4])
    return InlineKeyboardMarkup(rows)


def build_standings_back_keyboard(language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text("back_to_groups", language), callback_data="table:menu")]]
    )


def build_teams_keyboard(
    teams: list[dict[str, Any]],
    page: int = 0,
    page_size: int = TEAMS_PAGE_SIZE,
    language: str = "en",
) -> InlineKeyboardMarkup:
    teams = sorted(teams, key=lambda team: translated_team_name(team, include_emoji=False, language=language))
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
                    translated_team_name(team, language=language),
                    callback_data=f"team:{team.get('id')}:{page}",
                )
            )
        rows.append(row)

    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text("previous", language), callback_data=f"teams:{page - 1}"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton(text("next", language), callback_data=f"teams:{page + 1}"))
    if navigation:
        rows.append(navigation)
    return InlineKeyboardMarkup(rows)


def build_back_to_teams_keyboard(
    page: int = 0,
    language: str = "en",
    team_id: str | None = None,
    show_notifications_button: bool = False,
    is_following: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if show_notifications_button and team_id:
        label_key = "team_notifications_disable" if is_following else "team_notifications_enable"
        rows.append(
            [InlineKeyboardButton(text(label_key, language), callback_data=f"team:notify:{team_id}:{page}")]
        )
    rows.append([InlineKeyboardButton(text("back_to_teams", language), callback_data=f"teams:{page}")])
    return InlineKeyboardMarkup(rows)


def build_calendar_menu_keyboard(language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text("dates", language), callback_data="cal:dates"),
                InlineKeyboardButton(text("teams", language), callback_data="cal:teams:0"),
            ]
        ]
    )


def build_live_stats_keyboard(show_stats: bool = False, language: str = "en") -> InlineKeyboardMarkup:
    label = text("hide_stats" if show_stats else "stats", language)
    action = "hide" if show_stats else "show"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"live:stats:{action}")]])


def build_notification_config_keyboard(settings: dict[str, Any], language: str = "en") -> InlineKeyboardMarkup:
    rows = []
    selected_scope = settings.get(TEAM_SCOPE_KEY, TEAM_SCOPE_ALL)
    rows.append([InlineKeyboardButton(text("config_team_scope", language), callback_data="config:noop")])
    rows.append(
        [
            InlineKeyboardButton(
                f"{'* ' if selected_scope == TEAM_SCOPE_ALL else ''}{text('team_scope_all', language)}",
                callback_data=f"config:team_scope:{TEAM_SCOPE_ALL}",
            ),
            InlineKeyboardButton(
                f"{'* ' if selected_scope == TEAM_SCOPE_FOLLOWED else ''}{text('team_scope_followed', language)}",
                callback_data=f"config:team_scope:{TEAM_SCOPE_FOLLOWED}",
            ),
        ]
    )
    for notification_type in NOTIFICATION_TYPES:
        state = text("state_on" if settings.get(notification_type, True) else "state_off", language)
        label = f"{text(f'notification_{notification_type}', language)}: {state}"
        rows.append([InlineKeyboardButton(label, callback_data=f"config:toggle:{notification_type}")])
    rows.append([InlineKeyboardButton(text("config_language", language), callback_data="config:noop")])
    rows.append(
        [
            InlineKeyboardButton(
                f"{'* ' if settings.get(LANGUAGE_KEY) == language_code else ''}{label}",
                callback_data=f"config:language:{language_code}",
            )
            for language_code, label in LANGUAGE_LABELS.items()
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_calendar_dates_keyboard(date_params: list[str], language: str = "en") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text("all", language), callback_data="cal:all:0")]
    ]

    dates = sorted(set(date_params))
    for index in range(0, len(dates), 2):
        rows.append(
            [
                InlineKeyboardButton(
                    _format_date_label(date, language), callback_data=f"cal:date:{date}"
                )
                for date in dates[index : index + 2]
            ]
        )

    rows.append([InlineKeyboardButton(text("back", language), callback_data="cal:menu")])
    return InlineKeyboardMarkup(rows)


def build_calendar_all_games_keyboard(page: int, total_pages: int, language: str = "en") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text("previous", language), callback_data=f"cal:all:{page - 1}"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton(text("next", language), callback_data=f"cal:all:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text("back_to_dates", language), callback_data="cal:dates")])
    return InlineKeyboardMarkup(rows)


def build_calendar_back_to_dates_keyboard(language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text("back_to_dates", language), callback_data="cal:dates")]]
    )


def build_calendar_teams_keyboard(
    teams: list[dict[str, Any]],
    page: int = 0,
    page_size: int = TEAMS_PAGE_SIZE,
    language: str = "en",
) -> InlineKeyboardMarkup:
    teams = sorted(teams, key=lambda team: translated_team_name(team, include_emoji=False, language=language))
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
                    translated_team_name(team, language=language),
                    callback_data=f"cal:team:{team.get('id')}:{page}",
                )
            )
        rows.append(row)

    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text("previous", language), callback_data=f"cal:teams:{page - 1}"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton(text("next", language), callback_data=f"cal:teams:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text("back", language), callback_data="cal:menu")])
    return InlineKeyboardMarkup(rows)


def build_calendar_back_to_teams_keyboard(page: int = 0, language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text("back_to_teams", language), callback_data=f"cal:teams:{page}")]]
    )


def _format_date_label(date_param: str, language: str = "en") -> str:
    weekdays = text("weekdays", language).split(",")
    try:
        date = datetime.strptime(date_param, "%Y%m%d")
    except ValueError:
        return date_param
    return f"{weekdays[date.weekday()]} {date.strftime('%d/%m')}"


def _standings_group_label(group: dict[str, Any], language: str = "en") -> str:
    name = str(group.get("name") or group.get("abbreviation") or group.get("id") or "")
    if name.startswith("Group "):
        return f"{text('group', language)} {name.removeprefix('Group ')}"
    return name


def _standings_group_sort_key(group: dict[str, Any]) -> int:
    group_id = str(group.get("id") or "")
    return int(group_id) if group_id.isdigit() else 999
