"""Background task monitor for live fixtures and game status updates."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from telegram.ext import Application

from worldcupquente.espn_events import event_from_summary, parse_espn_datetime
from worldcupquente.live_delivery import (
    KICKOFF_NOTIFICATION,
    _send_incident_notifications,
    _send_pending_full_time_standings,
    _send_pending_player_ratings,
    _send_pre_game_notifications,
    _send_status_notifications,
)
from worldcupquente.live_delivery import (
    PENDING_PLAYER_RATINGS_KEY as PENDING_PLAYER_RATINGS_KEY,
)
from worldcupquente.live_events import (
    _is_full_time_event,
    _is_halftime_event,
    _is_in_progress_event,
    _is_kickoff_event,
    _is_pre_game_event,
)
from worldcupquente.live_incidents import (
    DISALLOWED_GOAL_NOTIFICATION as DISALLOWED_GOAL_NOTIFICATION,
)
from worldcupquente.live_incidents import (
    _collect_live_notifications,
)
from worldcupquente.live_incidents import (
    _play_match_key as _play_match_key,
)
from worldcupquente.live_standings import (
    PENDING_FULL_TIME_STANDINGS_KEY as PENDING_FULL_TIME_STANDINGS_KEY,
)
from worldcupquente.live_standings import (
    STANDINGS_SNAPSHOTS_KEY as STANDINGS_SNAPSHOTS_KEY,
)
from worldcupquente.live_standings import (
    _remember_active_standings_snapshots,
)
from worldcupquente.notification_preferences import (
    FULL_TIME_NOTIFICATION,
    HALFTIME_NOTIFICATION,
    NotificationPreferences,
)
from worldcupquente.services import WorldCupService

logger = logging.getLogger(__name__)

SEEN_GOAL_IDS_KEY = "live_seen_goal_ids"
SEEN_PENALTY_IDS_KEY = "live_seen_penalty_ids"
SEEN_RED_CARD_IDS_KEY = "live_seen_red_card_ids"
SEEN_PRE_GAME_IDS_KEY = "live_seen_pre_game_ids"
SEEN_KICKOFF_IDS_KEY = "live_seen_kickoff_ids"
SEEN_HALFTIME_IDS_KEY = "live_seen_halftime_ids"
SEEN_FULL_TIME_IDS_KEY = "live_seen_full_time_ids"
LIVE_SCORE_SNAPSHOTS_KEY = "live_score_snapshots"
LIVE_MONITOR_TASK_KEY = "live_monitor_task"
NOTIFICATION_PREFERENCES_KEY = "notification_preferences"
PRE_GAME_NOTIFICATION_WINDOW = timedelta(minutes=5)


async def start_live_monitor(application: Application) -> None:
    task = asyncio.create_task(live_monitor_loop(application), name="live_monitor")
    application.bot_data[LIVE_MONITOR_TASK_KEY] = task


async def stop_live_monitor(application: Application) -> None:
    task = application.bot_data.pop(LIVE_MONITOR_TASK_KEY, None)
    if isinstance(task, asyncio.Task):
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def live_monitor_loop(application: Application) -> None:
    service = application.bot_data["world_cup_service"]
    if not isinstance(service, WorldCupService):
        raise RuntimeError("world_cup_service is not configured")

    await asyncio.sleep(5)
    while True:
        try:
            await poll_live_notifications(application)
        except Exception:
            logger.exception("Unexpected live monitor failure")
        await asyncio.sleep(service.settings.live_poll_interval_seconds)


async def poll_live_notifications(application: Application) -> None:
    service = application.bot_data["world_cup_service"]
    if not isinstance(service, WorldCupService):
        raise RuntimeError("world_cup_service is not configured")
    preferences = application.bot_data[NOTIFICATION_PREFERENCES_KEY]
    if not isinstance(preferences, NotificationPreferences):
        raise RuntimeError("notification_preferences is not configured")
    if not preferences.has_recipients(service.settings.live_notification_chat_ids):
        return

    try:
        live_events = await service.get_live_events(use_cache=False)
    except Exception:
        logger.exception("Failed to poll live games for notifications")
        return

    try:
        status_events = (await service.get_active_scoreboard(use_cache=False)).get("events", [])
    except Exception:
        logger.exception("Failed to poll game status for notifications")
        status_events = []

    state = _live_monitor_state(application)

    await _remember_active_standings_snapshots(application, status_events, service)

    notifications, penalty_goal_keys = _collect_live_notifications(live_events, state)
    pre_game_notifications = _collect_pre_game_notifications(status_events, state)
    status_notifications = await _collect_status_notifications(status_events, state, service)

    _mark_bootstrapped(application, state)

    await _send_incident_notifications(
        application,
        notifications,
        penalty_goal_keys,
        preferences,
        service,
    )
    await _send_status_notifications(
        application,
        status_notifications,
        preferences,
        service,
    )
    await _send_pending_full_time_standings(application, preferences, service)
    await _send_pending_player_ratings(application, preferences, service)
    await _send_pre_game_notifications(
        application,
        pre_game_notifications,
        preferences,
        service,
    )


@dataclass
class LiveMonitorState:
    seen_goal_ids: set[str]
    seen_penalty_ids: set[str]
    seen_red_card_ids: set[str]
    seen_pre_game_ids: set[str]
    seen_kickoff_ids: set[str]
    seen_halftime_ids: set[str]
    seen_full_time_ids: set[str]
    score_snapshots: dict[str, tuple[int, ...]]
    is_bootstrapped: bool


def _live_monitor_state(application: Application) -> LiveMonitorState:
    return LiveMonitorState(
        seen_goal_ids=application.bot_data.setdefault(SEEN_GOAL_IDS_KEY, set()),
        seen_penalty_ids=application.bot_data.setdefault(SEEN_PENALTY_IDS_KEY, set()),
        seen_red_card_ids=application.bot_data.setdefault(SEEN_RED_CARD_IDS_KEY, set()),
        seen_pre_game_ids=application.bot_data.setdefault(SEEN_PRE_GAME_IDS_KEY, set()),
        seen_kickoff_ids=application.bot_data.setdefault(SEEN_KICKOFF_IDS_KEY, set()),
        seen_halftime_ids=application.bot_data.setdefault(SEEN_HALFTIME_IDS_KEY, set()),
        seen_full_time_ids=application.bot_data.setdefault(SEEN_FULL_TIME_IDS_KEY, set()),
        score_snapshots=application.bot_data.setdefault(LIVE_SCORE_SNAPSHOTS_KEY, {}),
        is_bootstrapped=application.bot_data.get("live_is_bootstrapped", False),
    )


def _collect_pre_game_notifications(
    status_events: list[dict[str, Any]],
    state: LiveMonitorState,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    notifications: list[dict[str, Any]] = []
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    current_time = current_time.astimezone(UTC)

    for event in status_events:
        event_id = str(event.get("id", ""))
        if not event_id or event_id in state.seen_pre_game_ids or not _is_pre_game_event(event):
            continue
        event_time = parse_espn_datetime(event.get("date", ""), UTC)
        if event_time is None:
            continue
        time_until = event_time - current_time
        if timedelta(0) <= time_until <= PRE_GAME_NOTIFICATION_WINDOW:
            state.seen_pre_game_ids.add(event_id)
            notifications.append(event)

    return notifications


async def _collect_status_notifications(
    status_events: list[dict[str, Any]],
    state: LiveMonitorState,
    service: WorldCupService,
) -> list[tuple[str, dict[str, Any]]]:
    status_notifications: list[tuple[str, dict[str, Any]]] = []
    is_bootstrapped = state.is_bootstrapped
    seen_halftime_ids = state.seen_halftime_ids
    seen_full_time_ids = state.seen_full_time_ids
    seen_kickoff_ids = state.seen_kickoff_ids

    for event in status_events:
        event_id = str(event.get("id", ""))
        if not event_id:
            continue
        if _is_in_progress_event(event) and event_id not in seen_kickoff_ids:
            seen_kickoff_ids.add(event_id)
            if is_bootstrapped and _is_kickoff_event(event):
                status_notifications.append(
                    (KICKOFF_NOTIFICATION, await _hydrate_notification_event(service, event))
                )
        if _is_halftime_event(event) and event_id not in seen_halftime_ids:
            seen_halftime_ids.add(event_id)
            if is_bootstrapped:
                status_notifications.append(
                    (HALFTIME_NOTIFICATION, await _hydrate_notification_event(service, event))
                )
        if _is_full_time_event(event) and event_id not in seen_full_time_ids:
            seen_full_time_ids.add(event_id)
            if is_bootstrapped:
                status_notifications.append(
                    (FULL_TIME_NOTIFICATION, await _hydrate_notification_event(service, event))
                )

    return status_notifications


def _mark_bootstrapped(application: Application, state: LiveMonitorState) -> None:
    if not state.is_bootstrapped:
        application.bot_data["live_is_bootstrapped"] = True


async def _hydrate_notification_event(
    service: WorldCupService,
    event: dict[str, Any],
) -> dict[str, Any]:
    event_id = str(event.get("id", ""))
    if not event_id:
        return event
    try:
        summary = await service.get_event_summary(event_id)
    except Exception:
        logger.warning("Failed to hydrate notification event", extra={"event_id": event_id})
        return event
    hydrated = event_from_summary(summary, fallback_event=event)
    hydrated = await service.enrich_event_sofascore_incidents(hydrated)
    hydrated = await service.enrich_event_sofascore_post_match(hydrated)
    return await service.enrich_event_win_probability(hydrated)
