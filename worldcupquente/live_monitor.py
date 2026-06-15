"""Background task monitor for live fixtures and game status updates."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from telegram.constants import ParseMode
from telegram.ext import Application

from worldcupquente.espn_events import event_from_summary, parse_espn_datetime
from worldcupquente.event_incidents import (
    penalty_plays_from_event,
    red_cards_from_event,
    scoring_plays_from_event,
)
from worldcupquente.formatters import (
    format_full_time_notification_rich,
    format_goal_notification,
    format_kickoff_notification,
    format_match_status_notification,
    format_penalty_notification,
    format_pre_game_notification,
    format_red_card_notification,
    format_standings_group_table,
)
from worldcupquente.i18n import text
from worldcupquente.notification_preferences import (
    FULL_TIME_NOTIFICATION,
    GOAL_NOTIFICATION,
    HALFTIME_NOTIFICATION,
    PENALTY_NOTIFICATION,
    PRE_GAME_NOTIFICATION,
    RED_CARD_NOTIFICATION,
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
PENDING_FULL_TIME_STANDINGS_KEY = "live_pending_full_time_standings"
STANDINGS_SNAPSHOTS_KEY = "live_standings_snapshots"
PRE_GAME_NOTIFICATION_WINDOW = timedelta(minutes=5)
KICKOFF_NOTIFICATION = "kickoff"


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


def _collect_live_notifications(
    live_events: list[dict[str, Any]],
    state: LiveMonitorState,
) -> tuple[list[tuple[str, dict[str, Any], dict[str, Any]]], set[tuple[str, str, str]]]:
    notifications: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    scored_penalty_goal_keys: set[tuple[str, str, str]] = set()
    is_bootstrapped = state.is_bootstrapped
    seen_goal_ids = state.seen_goal_ids
    seen_penalty_ids = state.seen_penalty_ids
    seen_red_card_ids = state.seen_red_card_ids
    score_snapshots = state.score_snapshots

    for event in live_events:
        event_id = str(event.get("id", ""))
        current_score = _event_score_snapshot(event)
        previous_score = score_snapshots.get(event_id)
        score_regressed = (
            current_score is not None
            and previous_score is not None
            and _score_regressed(previous_score, current_score)
        )
        if score_regressed:
            score_snapshots[event_id] = current_score
        elif current_score is not None and previous_score is not None:
            for detail in _score_change_details(event, previous_score, current_score):
                goal_id = _goal_id(event, detail)
                if _is_penalty_detail(detail):
                    scored_penalty_goal_keys.add(_play_match_key(event, detail))
                if goal_id in seen_goal_ids:
                    continue
                seen_goal_ids.add(goal_id)
                if is_bootstrapped:
                    notifications.append((GOAL_NOTIFICATION, event, detail))
        if current_score is not None:
            score_snapshots[event_id] = current_score

        for detail in penalty_plays_from_event(event):
            penalty_id = _live_event_id(PENALTY_NOTIFICATION, event, detail)
            if penalty_id in seen_penalty_ids:
                continue
            seen_penalty_ids.add(penalty_id)
            if is_bootstrapped:
                notifications.append((PENALTY_NOTIFICATION, event, detail))

        for detail in red_cards_from_event(event):
            red_card_id = _live_event_id(RED_CARD_NOTIFICATION, event, detail)
            if red_card_id in seen_red_card_ids:
                continue
            seen_red_card_ids.add(red_card_id)
            if is_bootstrapped:
                notifications.append((RED_CARD_NOTIFICATION, event, detail))

    return notifications, scored_penalty_goal_keys


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


async def _send_incident_notifications(
    application: Application,
    notifications: list[tuple[str, dict[str, Any], dict[str, Any]]],
    scored_penalty_goal_keys: set[tuple[str, str, str]],
    preferences: NotificationPreferences,
    service: WorldCupService,
) -> None:
    for notification_type, event, detail in notifications:
        chat_ids = preferences.enabled_chat_ids(
            notification_type,
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
            except Exception:
                logger.exception(
                    "Failed to send live notification",
                    extra={"chat_id": chat_id, "notification_type": notification_type},
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
                    except Exception:
                        logger.exception("Failed to send rich full-time notification")
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
            except Exception:
                logger.exception(
                    "Failed to send game status notification",
                    extra={"chat_id": chat_id, "notification_type": notification_type},
                )
        if notification_type == FULL_TIME_NOTIFICATION and chat_ids:
            event_id = str(event.get("id", ""))
            if event_id:
                _pending_full_time_standings(application)[event_id] = pending_payload or {
                    "event": event,
                    "initial_records": {},
                }


async def _send_pending_full_time_standings(
    application: Application,
    preferences: NotificationPreferences,
    service: WorldCupService,
) -> None:
    pending = _pending_full_time_standings(application)
    for event_id, pending_item in list(pending.items()):
        event = pending_item.get("event", {})
        initial_records = pending_item.get("initial_records", {})
        chat_ids = preferences.enabled_chat_ids(
            FULL_TIME_NOTIFICATION,
            service.settings.live_notification_chat_ids,
            _event_team_ids(event),
        )
        if not chat_ids:
            pending.pop(event_id, None)
            _standings_snapshots(application).pop(event_id, None)
            continue

        group = await _updated_standings_group_for_event(service, event, initial_records)
        if group is None:
            continue

        failed = False
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
            except Exception:
                failed = True
                logger.exception("Failed to send updated full-time standings")
        if not failed:
            pending.pop(event_id, None)
            _standings_snapshots(application).pop(event_id, None)


def _pending_full_time_standings(application: Application) -> dict[str, dict[str, Any]]:
    return application.bot_data.setdefault(PENDING_FULL_TIME_STANDINGS_KEY, {})


def _standings_snapshots(application: Application) -> dict[str, dict[str, tuple[int, int, int, int]]]:
    return application.bot_data.setdefault(STANDINGS_SNAPSHOTS_KEY, {})


async def _remember_active_standings_snapshots(
    application: Application,
    status_events: list[dict[str, Any]],
    service: WorldCupService,
) -> None:
    active_events = [event for event in status_events if _is_in_progress_event(event)]
    if not active_events:
        return
    try:
        groups = await service.get_standings_groups(use_cache=False)
    except Exception:
        logger.warning("Failed to fetch standings snapshots")
        return

    snapshots = _standings_snapshots(application)
    for event in active_events:
        event_id = str(event.get("id", ""))
        if not event_id or event_id in snapshots:
            continue
        group = _standings_group_from_groups(groups, event)
        records = _standings_total_records(group) if group is not None else {}
        if records:
            snapshots[event_id] = records


async def _send_pre_game_notifications(
    application: Application,
    pre_game_notifications: list[dict[str, Any]],
    preferences: NotificationPreferences,
    service: WorldCupService,
) -> None:
    for event in pre_game_notifications:
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
            except Exception:
                logger.exception(
                    "Failed to send pre-game notification",
                    extra={"chat_id": chat_id, "notification_type": PRE_GAME_NOTIFICATION},
                )


def _format_live_notification(
    notification_type: str,
    event: dict[str, Any],
    detail: dict[str, Any],
    language: str = "en",
) -> str:
    if notification_type == GOAL_NOTIFICATION:
        return format_goal_notification(event, detail, language)
    if notification_type == PENALTY_NOTIFICATION:
        return format_penalty_notification(event, detail, language)
    if notification_type == RED_CARD_NOTIFICATION:
        return format_red_card_notification(event, detail, language)
    raise ValueError(f"Invalid notification type: {notification_type}")


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
    return event_from_summary(summary, fallback_event=event)


async def _updated_standings_group_for_event(
    service: WorldCupService,
    event: dict[str, Any],
    initial_records: dict[str, tuple[int, int, int, int]] | None = None,
) -> dict[str, Any] | None:
    group = await _standings_group_for_event(service, event)
    if group is None:
        return None
    if _standings_group_matches_event(group, event):
        return group
    if initial_records and _standings_group_matches_snapshot_update(group, event, initial_records):
        return group
    return None


async def _standings_group_for_event(
    service: WorldCupService,
    event: dict[str, Any],
) -> dict[str, Any] | None:
    team_ids = _event_team_ids(event)
    if not team_ids:
        return None
    try:
        groups = await service.get_standings_groups(use_cache=False)
    except Exception:
        logger.warning("Failed to fetch standings for full-time notification")
        return None

    return _standings_group_from_groups(groups, event)


def _standings_group_from_groups(
    groups: list[dict[str, Any]],
    event: dict[str, Any],
) -> dict[str, Any] | None:
    team_ids = _event_team_ids(event)
    if not team_ids:
        return None

    for group in groups:
        group_team_ids = {
            str(((entry.get("team") or {}).get("id")) or "")
            for entry in (group.get("standings") or {}).get("entries", [])
        }
        if team_ids.issubset(group_team_ids):
            return group
    return None


def _standings_group_matches_event(group: dict[str, Any], event: dict[str, Any]) -> bool:
    event_records = _event_total_records(event)
    if not event_records:
        return False

    standings_records = _standings_total_records(group)
    return all(standings_records.get(team_id) == record for team_id, record in event_records.items())


def _standings_group_matches_snapshot_update(
    group: dict[str, Any],
    event: dict[str, Any],
    initial_records: dict[str, tuple[int, int, int, int]],
) -> bool:
    event_record_deltas = _event_record_deltas(event)
    if not event_record_deltas:
        return False

    standings_records = _standings_total_records(group)
    for team_id, delta in event_record_deltas.items():
        initial_record = initial_records.get(team_id)
        current_record = standings_records.get(team_id)
        if initial_record is None or current_record is None:
            return False
        expected_record = tuple(initial + added for initial, added in zip(initial_record, delta, strict=True))
        if current_record != expected_record:
            return False
    return True


def _event_record_deltas(event: dict[str, Any]) -> dict[str, tuple[int, int, int, int]]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    if len(competitors) != 2:
        return {}

    scores: list[tuple[str, int]] = []
    for competitor in competitors:
        team_id = str(((competitor.get("team") or {}).get("id")) or "")
        if not team_id:
            return {}
        try:
            score = int(competitor.get("score"))
        except (TypeError, ValueError):
            return {}
        scores.append((team_id, score))

    first_team_id, first_score = scores[0]
    second_team_id, second_score = scores[1]
    if first_score == second_score:
        return {
            first_team_id: (1, 0, 1, 0),
            second_team_id: (1, 0, 1, 0),
        }
    if first_score > second_score:
        return {
            first_team_id: (1, 1, 0, 0),
            second_team_id: (1, 0, 0, 1),
        }
    return {
        first_team_id: (1, 0, 0, 1),
        second_team_id: (1, 1, 0, 0),
    }


def _event_total_records(event: dict[str, Any]) -> dict[str, tuple[int, int, int, int]]:
    competition = (event.get("competitions") or [{}])[0]
    records: dict[str, tuple[int, int, int, int]] = {}
    for competitor in competition.get("competitors", []):
        team_id = str(((competitor.get("team") or {}).get("id")) or "")
        if not team_id:
            continue
        record = _competitor_total_record(competitor)
        if record is None:
            return {}
        records[team_id] = record
    return records


def _competitor_total_record(competitor: dict[str, Any]) -> tuple[int, int, int, int] | None:
    for record in competitor.get("records", []):
        record_type = str(record.get("type") or "").lower()
        record_name = str(record.get("name") or "").lower()
        record_abbreviation = str(record.get("abbreviation") or "").lower()
        if record_type != "total" and record_name != "all splits" and record_abbreviation != "total":
            continue
        return _parse_total_record(record.get("summary") or record.get("displayValue"))
    return None


def _parse_total_record(value: Any) -> tuple[int, int, int, int] | None:
    parts = str(value or "").split("-")
    if len(parts) != 3:
        return None
    try:
        wins, draws, losses = (int(part) for part in parts)
    except ValueError:
        return None
    return (wins + draws + losses, wins, draws, losses)


def _standings_total_records(group: dict[str, Any]) -> dict[str, tuple[int, int, int, int]]:
    records: dict[str, tuple[int, int, int, int]] = {}
    for entry in (group.get("standings") or {}).get("entries", []):
        team_id = str(((entry.get("team") or {}).get("id")) or "")
        if not team_id:
            continue
        stats = entry.get("stats", [])
        games_played = _standings_int_stat(stats, "gamesPlayed")
        wins = _standings_int_stat(stats, "wins")
        draws = _standings_int_stat(stats, "ties")
        losses = _standings_int_stat(stats, "losses")
        if None in (games_played, wins, draws, losses):
            continue
        records[team_id] = (games_played, wins, draws, losses)
    return records


def _standings_int_stat(stats: list[dict[str, Any]], name: str) -> int | None:
    for stat in stats:
        if stat.get("name") != name:
            continue
        value = stat.get("value")
        if value is None or value == "":
            value = stat.get("displayValue")
        try:
            return int(float(str(value).replace("+", "")))
        except (TypeError, ValueError):
            return None
    return None


def _event_team_ids(event: dict[str, Any]) -> set[str]:
    competition = (event.get("competitions") or [{}])[0]
    return {
        str(((competitor.get("team") or {}).get("id")) or "")
        for competitor in competition.get("competitors", [])
        if ((competitor.get("team") or {}).get("id"))
    }


def _is_halftime_event(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    status_type = status.get("type") or {}
    if status_type.get("state") != "in":
        return False
    return any(part == "HT" or "HALFTIME" in part.upper() for part in _status_text_parts(status))


def _is_kickoff_event(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    status_type = status.get("type") or {}
    if status_type.get("state") != "in":
        return False
    return not _is_halftime_event(event)


def _is_full_time_event(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    status_type = status.get("type") or {}
    if status_type.get("state") != "post" and status_type.get("completed") is not True:
        return False
    return not _is_extra_time_or_penalties_status(status)


def _is_in_progress_event(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    status_type = status.get("type") or {}
    return status_type.get("state") == "in"


def _is_extra_time_or_penalties_status(status: dict[str, Any]) -> bool:
    for part in _status_text_parts(status):
        normalized = part.upper().replace("-", " ")
        if "FINAL" in normalized or normalized.startswith("FT") or normalized == "AET":
            continue
        if "EXTRA TIME" in normalized or normalized in {"ET", "1ET", "2ET"}:
            return True
        if "PENALT" in normalized or "PENS" in normalized or "SHOOTOUT" in normalized:
            return True
    return False


def _is_pre_game_event(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    status_type = status.get("type") or {}
    return status_type.get("state") == "pre"


def _event_status(event: dict[str, Any]) -> dict[str, Any]:
    competition = (event.get("competitions") or [{}])[0]
    return competition.get("status") or event.get("status") or {}


def _status_text_parts(status: dict[str, Any]) -> set[str]:
    status_type = status.get("type") or {}
    return {
        str(part)
        for part in [
            status.get("displayClock"),
            status_type.get("name"),
            status_type.get("description"),
            status_type.get("detail"),
            status_type.get("shortDetail"),
        ]
        if part
    }


def _goal_id(event: dict[str, Any], detail: dict[str, Any]) -> str:
    athletes = detail.get("athletesInvolved") or [
        participant.get("athlete") or {}
        for participant in detail.get("participants", [])
        if participant.get("athlete")
    ]
    athlete_ids = ",".join(str(athlete.get("id", "")) for athlete in athletes)
    clock = detail.get("clock") or {}
    detail_type = detail.get("type") or {}
    team = detail.get("team") or {}
    return ":".join(
        [
            str(event.get("id", "")),
            str(detail.get("id", "")),
            str(team.get("id", "")),
            str(clock.get("value", "")),
            str(clock.get("displayValue", "")),
            athlete_ids,
            str(detail_type.get("id", "")),
            str(detail.get("scoreValue", "")),
            str(detail.get("scoreAfter", "")),
        ]
    )


def _live_event_id(notification_type: str, event: dict[str, Any], detail: dict[str, Any]) -> str:
    if notification_type == PENALTY_NOTIFICATION:
        return _penalty_event_id(event, detail)

    athletes = detail.get("athletesInvolved") or [
        participant.get("athlete") or {}
        for participant in detail.get("participants", [])
        if participant.get("athlete")
    ]
    athlete = detail.get("athlete")
    if athlete:
        athletes = [*athletes, athlete]
    athlete_ids = ",".join(
        str(athlete.get("id") or athlete.get("displayName") or athlete.get("fullName") or "")
        for athlete in athletes
    )
    clock = detail.get("clock") or {}
    detail_type = detail.get("type") or {}
    team = detail.get("team") or {}
    return ":".join(
        [
            notification_type,
            str(event.get("id", "")),
            str(detail.get("id", "")),
            str(team.get("id", "")),
            str(clock.get("value", "")),
            str(clock.get("displayValue", "")),
            athlete_ids,
            str(detail_type.get("id", "")),
            str(detail_type.get("type", "")),
            str(detail_type.get("text", "")),
            str(detail.get("text", "")),
        ]
    )


def _penalty_event_id(event: dict[str, Any], detail: dict[str, Any]) -> str:
    clock = detail.get("clock") or {}
    return ":".join(
        [
            PENALTY_NOTIFICATION,
            str(event.get("id", "")),
            str(clock.get("displayValue") or clock.get("value") or detail.get("id") or ""),
        ]
    )


def _is_penalty_detail(detail: dict[str, Any]) -> bool:
    detail_type = detail.get("type") or {}
    text = " ".join(
        str(part or "")
        for part in [
            detail_type.get("type"),
            detail_type.get("text"),
            detail.get("text"),
        ]
    ).lower()
    return "penalty" in text


def _play_match_key(event: dict[str, Any], detail: dict[str, Any]) -> tuple[str, str, str]:
    clock = detail.get("clock") or {}
    team = detail.get("team") or {}
    return (
        str(event.get("id", "")),
        str(team.get("id", "")),
        str(clock.get("value") or clock.get("displayValue") or ""),
    )


def _event_score_snapshot(event: dict[str, Any]) -> tuple[int, ...] | None:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    scores: list[int] = []
    for competitor in competitors:
        score = competitor.get("score")
        try:
            scores.append(int(score))
        except (TypeError, ValueError):
            return None
    return tuple(scores) if scores else None


def _score_regressed(previous_score: tuple[int, ...], current_score: tuple[int, ...]) -> bool:
    return any(current < previous for previous, current in zip(previous_score, current_score, strict=False))


def _score_change_details(
    event: dict[str, Any],
    previous_score: tuple[int, ...],
    current_score: tuple[int, ...],
) -> list[dict[str, Any]]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    status = competition.get("status") or event.get("status") or {}
    details: list[dict[str, Any]] = []
    for index, current in enumerate(current_score):
        previous = previous_score[index] if index < len(previous_score) else 0
        score_delta = current - previous
        if score_delta <= 0 or index >= len(competitors):
            continue
        team = competitors[index].get("team") or {}
        details.extend(
            _scoring_details_for_score_change(
                event,
                team,
                score_delta,
                fallback_clock=status,
                score_after=current_score,
            )
        )
    return details


def _scoring_details_for_score_change(
    event: dict[str, Any],
    team: dict[str, Any],
    score_delta: int,
    fallback_clock: dict[str, Any],
    score_after: tuple[int, ...],
) -> list[dict[str, Any]]:
    team_id = str(team.get("id", ""))
    team_plays = [
        play
        for play in scoring_plays_from_event(event)
        if str((play.get("team") or {}).get("id", "")) == team_id
    ]
    team_plays = sorted(team_plays, key=_goal_clock_value)
    if len(team_plays) >= score_delta:
        return team_plays[-score_delta:]

    missing_goals = score_delta - len(team_plays)
    fallback_details = [
        {
            "id": f"score-change:{team_id}:{':'.join(str(score) for score in score_after)}:{index}",
                "clock": {
                    "value": fallback_clock.get("clock"),
                    "displayValue": fallback_clock.get("displayClock") or "",
                },
            "team": team,
            "type": {"id": "score-change", "text": "Goal"},
            "scoreValue": 1,
            "scoreAfter": ":".join(str(score) for score in score_after),
            "athletesInvolved": [],
        }
        for index in range(missing_goals)
    ]
    return [*team_plays, *fallback_details]


def _goal_clock_value(detail: dict[str, Any]) -> float:
    clock = detail.get("clock") or {}
    try:
        return float(clock.get("value") or 0)
    except (TypeError, ValueError):
        return 0.0
