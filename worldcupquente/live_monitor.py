"""Background task monitor for live fixtures and game status updates."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from telegram.constants import ParseMode
from telegram.ext import Application

from worldcupquente.espn_events import event_from_summary
from worldcupquente.event_incidents import (
    penalty_plays_from_event,
    red_cards_from_event,
    scoring_plays_from_event,
)
from worldcupquente.formatters import (
    format_full_time_notification_rich,
    format_goal_notification,
    format_match_status_notification,
    format_penalty_notification,
    format_red_card_notification,
)
from worldcupquente.i18n import text
from worldcupquente.notification_preferences import (
    FULL_TIME_NOTIFICATION,
    GOAL_NOTIFICATION,
    HALFTIME_NOTIFICATION,
    PENALTY_NOTIFICATION,
    RED_CARD_NOTIFICATION,
    NotificationPreferences,
)
from worldcupquente.services import WorldCupService

logger = logging.getLogger(__name__)

SEEN_GOAL_IDS_KEY = "live_seen_goal_ids"
SEEN_PENALTY_IDS_KEY = "live_seen_penalty_ids"
SEEN_RED_CARD_IDS_KEY = "live_seen_red_card_ids"
SEEN_HALFTIME_IDS_KEY = "live_seen_halftime_ids"
SEEN_FULL_TIME_IDS_KEY = "live_seen_full_time_ids"
LIVE_SCORE_SNAPSHOTS_KEY = "live_score_snapshots"
LIVE_MONITOR_TASK_KEY = "live_monitor_task"
NOTIFICATION_PREFERENCES_KEY = "notification_preferences"


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

    notifications, penalty_goal_keys = _collect_live_notifications(live_events, state)
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


@dataclass
class LiveMonitorState:
    seen_goal_ids: set[str]
    seen_penalty_ids: set[str]
    seen_red_card_ids: set[str]
    seen_halftime_ids: set[str]
    seen_full_time_ids: set[str]
    score_snapshots: dict[str, tuple[int, ...]]
    is_bootstrapped: bool


def _live_monitor_state(application: Application) -> LiveMonitorState:
    return LiveMonitorState(
        seen_goal_ids=application.bot_data.setdefault(SEEN_GOAL_IDS_KEY, set()),
        seen_penalty_ids=application.bot_data.setdefault(SEEN_PENALTY_IDS_KEY, set()),
        seen_red_card_ids=application.bot_data.setdefault(SEEN_RED_CARD_IDS_KEY, set()),
        seen_halftime_ids=application.bot_data.setdefault(SEEN_HALFTIME_IDS_KEY, set()),
        seen_full_time_ids=application.bot_data.setdefault(SEEN_FULL_TIME_IDS_KEY, set()),
        score_snapshots=application.bot_data.setdefault(LIVE_SCORE_SNAPSHOTS_KEY, {}),
        is_bootstrapped=application.bot_data.get("live_is_bootstrapped", False),
    )


def _collect_live_notifications(
    live_events: list[dict[str, Any]],
    state: LiveMonitorState,
) -> tuple[list[tuple[str, dict[str, Any], dict[str, Any]]], set[tuple[str, str, str, str]]]:
    notifications: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    scored_penalty_goal_keys: set[tuple[str, str, str, str]] = set()
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


async def _collect_status_notifications(
    status_events: list[dict[str, Any]],
    state: LiveMonitorState,
    service: WorldCupService,
) -> list[tuple[str, dict[str, Any]]]:
    status_notifications: list[tuple[str, dict[str, Any]]] = []
    is_bootstrapped = state.is_bootstrapped
    seen_halftime_ids = state.seen_halftime_ids
    seen_full_time_ids = state.seen_full_time_ids

    for event in status_events:
        event_id = str(event.get("id", ""))
        if not event_id:
            continue
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
    scored_penalty_goal_keys: set[tuple[str, str, str, str]],
    preferences: NotificationPreferences,
    service: WorldCupService,
) -> None:
    for notification_type, event, detail in notifications:
        chat_ids = preferences.enabled_chat_ids(
            notification_type,
            service.settings.live_notification_chat_ids,
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
        chat_ids = preferences.enabled_chat_ids(
            notification_type,
            service.settings.live_notification_chat_ids,
        )
        full_time_html = None
        halftime_text = None
        if notification_type == FULL_TIME_NOTIFICATION:
            group = await _standings_group_for_event(service, event)
        else:
            group = None

        for chat_id in chat_ids:
            language = preferences.get_language(chat_id)
            if notification_type == FULL_TIME_NOTIFICATION:
                full_time_html = format_full_time_notification_rich(
                    event,
                    service.bot_timezone,
                    group,
                    language,
                )
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

    for group in groups:
        group_team_ids = {
            str(((entry.get("team") or {}).get("id")) or "")
            for entry in (group.get("standings") or {}).get("entries", [])
        }
        if team_ids.issubset(group_team_ids):
            return group
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


def _is_full_time_event(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    status_type = status.get("type") or {}
    return status_type.get("state") == "post" or status_type.get("completed") is True


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


def _play_match_key(event: dict[str, Any], detail: dict[str, Any]) -> tuple[str, str, str, str]:
    clock = detail.get("clock") or {}
    team = detail.get("team") or {}
    return (
        str(event.get("id", "")),
        str(detail.get("id", "")),
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
