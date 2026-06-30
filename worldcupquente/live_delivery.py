"""Telegram delivery helpers for live monitor notifications."""

from __future__ import annotations

import logging
from typing import Any

from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import Application

from worldcupquente.formatters import (
    format_disallowed_goal_notification,
    format_full_time_notification_rich,
    format_goal_notification,
    format_history_player_ratings,
    format_kickoff_notification,
    format_match_status_notification,
    format_penalty_notification,
    format_player_ratings_table,
    format_pre_game_notification,
    format_red_card_notification,
    format_standings_group_table,
)
from worldcupquente.i18n import text
from worldcupquente.live_events import _event_team_ids
from worldcupquente.live_incidents import (
    DISALLOWED_GOAL_NOTIFICATION,
    _is_penalty_detail,
    _play_match_key,
)
from worldcupquente.live_standings import (
    PENDING_FULL_TIME_STANDINGS_KEY,
    _standings_group_for_event,
    _standings_snapshots,
    _standings_total_records,
    _updated_standings_group_for_event,
)
from worldcupquente.notification_preferences import (
    FULL_TIME_NOTIFICATION,
    GOAL_NOTIFICATION,
    PENALTY_NOTIFICATION,
    PRE_GAME_NOTIFICATION,
    RED_CARD_NOTIFICATION,
    NotificationPreferences,
)
from worldcupquente.services import WorldCupService

logger = logging.getLogger(__name__)

KICKOFF_NOTIFICATION = "kickoff"
PENDING_PLAYER_RATINGS_KEY = "live_pending_player_ratings"
PENDING_CHAT_IDS_KEY = "pending_chat_ids"


def _is_permanent_telegram_error(exc: BaseException) -> bool:
    if isinstance(exc, Forbidden):
        return True
    return isinstance(exc, BadRequest) and "chat not found" in str(exc).lower()


async def _send_incident_notifications(
    application: Application,
    notifications: list[tuple[str, dict[str, Any], dict[str, Any]]],
    scored_penalty_goal_keys: set[tuple[str, str, str]],
    preferences: NotificationPreferences,
    service: WorldCupService,
) -> None:
    for notification_type, event, detail in notifications:
        preference_type = GOAL_NOTIFICATION if notification_type == DISALLOWED_GOAL_NOTIFICATION else notification_type
        chat_ids = preferences.enabled_chat_ids(
            preference_type,
            service.settings.live_notification_chat_ids,
            _event_team_ids(event),
        )
        if (
            notification_type == PENALTY_NOTIFICATION
            and _is_penalty_detail(detail)
            and _play_match_key(event, detail) in scored_penalty_goal_keys
        ):
            chat_ids = [
                chat_id
                for chat_id in chat_ids
                if not preferences.get(chat_id).get(GOAL_NOTIFICATION, True)
            ]
        for chat_id in chat_ids:
            language = preferences.get_language(chat_id)
            notification_text = _format_live_notification(notification_type, event, detail, language)
            try:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=notification_text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as exc:
                _handle_delivery_failure(
                    exc,
                    preferences,
                    chat_id,
                    "Failed to send live notification",
                    {"notification_type": notification_type},
                )


async def _send_status_notifications(
    application: Application,
    status_notifications: list[tuple[str, dict[str, Any]]],
    preferences: NotificationPreferences,
    service: WorldCupService,
) -> None:
    for notification_type, event in status_notifications:
        preference_type = PRE_GAME_NOTIFICATION if notification_type == KICKOFF_NOTIFICATION else notification_type
        chat_ids = preferences.enabled_chat_ids(
            preference_type,
            service.settings.live_notification_chat_ids,
            _event_team_ids(event),
        )
        pending_payload = None
        if notification_type == FULL_TIME_NOTIFICATION and chat_ids:
            initial_group = await _standings_group_for_event(service, event)
            event_id = str(event.get("id", ""))
            standings_snapshot = _standings_snapshots(application).get(event_id, {})
            pending_payload = {
                "event": event,
                "initial_records": standings_snapshot
                or (_standings_total_records(initial_group) if initial_group else {}),
            }
        full_time_html = None
        halftime_text = None

        for chat_id in chat_ids:
            language = preferences.get_language(chat_id)
            if notification_type == FULL_TIME_NOTIFICATION:
                full_time_html = format_full_time_notification_rich(
                    event,
                    service.bot_timezone,
                    None,
                    language,
                )
            elif notification_type == KICKOFF_NOTIFICATION:
                halftime_text = format_kickoff_notification(event, service.bot_timezone, language)
            else:
                halftime_text = format_match_status_notification(event, service.bot_timezone, language)
            try:
                if notification_type == FULL_TIME_NOTIFICATION:
                    try:
                        await application.bot.do_api_request(
                            "sendRichMessage",
                            api_kwargs={
                                "chat_id": chat_id,
                                "rich_message": {
                                    "html": full_time_html,
                                    "skip_entity_detection": True,
                                },
                            },
                        )
                    except Exception as exc:
                        if not _handle_delivery_failure(
                            exc,
                            preferences,
                            chat_id,
                            "Failed to send rich full-time notification",
                            {"notification_type": notification_type},
                        ):
                            continue
                        if event.get("sofascorePlayerRatings"):
                            _enqueue_pending_player_ratings(
                                application, str(event.get("id", "")), event, [chat_id]
                            )
                        await application.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                f"{format_match_status_notification(event, service.bot_timezone, language)}\n\n"
                                f"{text('full_time_fallback', language)}"
                            ),
                            parse_mode=ParseMode.HTML,
                        )
                    continue

                await application.bot.send_message(
                    chat_id=chat_id,
                    text=halftime_text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as exc:
                _handle_delivery_failure(
                    exc,
                    preferences,
                    chat_id,
                    "Failed to send game status notification",
                    {"notification_type": notification_type},
                )
        if notification_type == FULL_TIME_NOTIFICATION and chat_ids:
            event_id = str(event.get("id", ""))
            if event_id:
                standings_entry = pending_payload or {"event": event, "initial_records": {}}
                standings_entry[PENDING_CHAT_IDS_KEY] = list(chat_ids)
                _pending_full_time_standings(application)[event_id] = standings_entry
                if not event.get("sofascorePlayerRatings"):
                    _enqueue_pending_player_ratings(application, event_id, event, chat_ids)


async def _send_pending_full_time_standings(
    application: Application,
    preferences: NotificationPreferences,
    service: WorldCupService,
) -> None:
    pending = _pending_full_time_standings(application)
    for event_id, pending_item in list(pending.items()):
        event = pending_item.get("event", {})
        initial_records = pending_item.get("initial_records", {})
        chat_ids = _resolve_pending_chat_ids(pending_item, preferences, service, event)
        if not chat_ids:
            pending.pop(event_id, None)
            _standings_snapshots(application).pop(event_id, None)
            continue

        group = await _updated_standings_group_for_event(service, event, initial_records)
        if group is None:
            continue

        remaining: list[Any] = []
        for chat_id in chat_ids:
            language = preferences.get_language(chat_id)
            try:
                await application.bot.do_api_request(
                    "sendRichMessage",
                    api_kwargs={
                        "chat_id": chat_id,
                        "rich_message": {
                            "html": format_standings_group_table(group, language),
                            "skip_entity_detection": True,
                        },
                    },
                )
            except Exception as exc:
                if _handle_delivery_failure(
                    exc, preferences, chat_id, "Failed to send updated full-time standings"
                ):
                    remaining.append(chat_id)
        if remaining:
            pending_item[PENDING_CHAT_IDS_KEY] = remaining
        else:
            pending.pop(event_id, None)
            _standings_snapshots(application).pop(event_id, None)


async def _send_pending_player_ratings(
    application: Application,
    preferences: NotificationPreferences,
    service: WorldCupService,
) -> None:
    pending = _pending_player_ratings(application)
    for event_id, pending_item in list(pending.items()):
        fallback_event = pending_item.get("event", {})
        chat_ids = _resolve_pending_chat_ids(pending_item, preferences, service, fallback_event)
        if not chat_ids:
            pending.pop(event_id, None)
            continue

        try:
            event = await service.get_sofascore_finished_event_details(event_id)
        except Exception:
            logger.warning("Failed to fetch pending player ratings", extra={"event_id": event_id})
            continue
        if not event or not event.get("sofascorePlayerRatings"):
            continue

        remaining: list[Any] = []
        for chat_id in chat_ids:
            language = preferences.get_language(chat_id)
            try:
                await _send_player_ratings_notification(application, chat_id, event, language)
            except Exception as exc:
                if _handle_delivery_failure(
                    exc, preferences, chat_id, "Failed to send pending player ratings"
                ):
                    remaining.append(chat_id)
        if remaining:
            pending_item[PENDING_CHAT_IDS_KEY] = remaining
        else:
            pending.pop(event_id, None)


async def _send_player_ratings_notification(
    application: Application,
    chat_id: int | str,
    event: dict[str, Any],
    language: str,
) -> None:
    ratings_table = format_player_ratings_table(event, language=language)
    if ratings_table:
        try:
            await application.bot.do_api_request(
                "sendRichMessage",
                api_kwargs={
                    "chat_id": chat_id,
                    "rich_message": {
                        "html": ratings_table,
                        "skip_entity_detection": True,
                    },
                },
            )
            return
        except Exception as exc:
            if _is_permanent_telegram_error(exc):
                raise
            logger.exception("Failed to send rich player ratings notification")

    await application.bot.send_message(
        chat_id=chat_id,
        text=format_history_player_ratings(event, language),
        parse_mode=ParseMode.HTML,
    )


def _pending_full_time_standings(application: Application) -> dict[str, dict[str, Any]]:
    return application.bot_data.setdefault(PENDING_FULL_TIME_STANDINGS_KEY, {})


def _pending_player_ratings(application: Application) -> dict[str, dict[str, Any]]:
    return application.bot_data.setdefault(PENDING_PLAYER_RATINGS_KEY, {})


def _enqueue_pending_player_ratings(
    application: Application,
    event_id: str,
    event: dict[str, Any],
    chat_ids: list[Any],
) -> None:
    if not event_id:
        return
    pending = _pending_player_ratings(application)
    entry = pending.get(event_id)
    if entry is None:
        entry = {"event": event}
        pending[event_id] = entry
    else:
        entry["event"] = event
    stored = entry.setdefault(PENDING_CHAT_IDS_KEY, [])
    for chat_id in chat_ids:
        if chat_id not in stored:
            stored.append(chat_id)


def _resolve_pending_chat_ids(
    pending_item: dict[str, Any],
    preferences: NotificationPreferences,
    service: WorldCupService,
    event: dict[str, Any],
) -> list[Any]:
    enabled = preferences.enabled_chat_ids(
        FULL_TIME_NOTIFICATION,
        service.settings.live_notification_chat_ids,
        _event_team_ids(event),
    )
    stored = pending_item.get(PENDING_CHAT_IDS_KEY)
    if not stored:
        return list(enabled)
    enabled_set = set(enabled)
    return [chat_id for chat_id in stored if chat_id in enabled_set]


def _handle_delivery_failure(
    exc: BaseException,
    preferences: NotificationPreferences,
    chat_id: Any,
    error_label: str,
    extra: dict[str, Any] | None = None,
) -> bool:
    log_extra = {"chat_id": chat_id, **(extra or {})}
    if _is_permanent_telegram_error(exc):
        preferences.disable_chat(chat_id)
        logger.warning(
            "Disabled notifications for unreachable chat",
            extra=log_extra,
        )
        return False
    logger.exception(error_label, extra=log_extra)
    return True


async def _send_pre_game_notifications(
    application: Application,
    pre_game_notifications: list[dict[str, Any]],
    preferences: NotificationPreferences,
    service: WorldCupService,
) -> None:
    for event in pre_game_notifications:
        event = await service.enrich_event_win_probability(event)
        chat_ids = preferences.enabled_chat_ids(
            PRE_GAME_NOTIFICATION,
            service.settings.live_notification_chat_ids,
            _event_team_ids(event),
        )
        for chat_id in chat_ids:
            language = preferences.get_language(chat_id)
            try:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=format_pre_game_notification(event, service.bot_timezone, language),
                    parse_mode=ParseMode.HTML,
                )
            except Exception as exc:
                _handle_delivery_failure(
                    exc,
                    preferences,
                    chat_id,
                    "Failed to send pre-game notification",
                    {"notification_type": PRE_GAME_NOTIFICATION},
                )


def _format_live_notification(
    notification_type: str,
    event: dict[str, Any],
    detail: dict[str, Any],
    language: str = "en",
) -> str:
    if notification_type == GOAL_NOTIFICATION:
        return format_goal_notification(event, detail, language)
    if notification_type == DISALLOWED_GOAL_NOTIFICATION:
        return format_disallowed_goal_notification(event, detail, language)
    if notification_type == PENALTY_NOTIFICATION:
        return format_penalty_notification(event, detail, language)
    if notification_type == RED_CARD_NOTIFICATION:
        return format_red_card_notification(event, detail, language)
    raise ValueError(f"Invalid notification type: {notification_type}")
