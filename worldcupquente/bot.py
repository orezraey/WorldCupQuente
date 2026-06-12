"""Telegram bot entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import logging
from contextlib import suppress
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application

from worldcupquente.config import get_settings
from worldcupquente.formatters import format_goal_notification
from worldcupquente.handlers import get_handlers
from worldcupquente.services import WorldCupService, scoring_plays_from_event

logger = logging.getLogger(__name__)

SEEN_GOAL_IDS_KEY = "live_seen_goal_ids"
LIVE_SCORE_SNAPSHOTS_KEY = "live_score_snapshots"
LIVE_MONITOR_TASK_KEY = "live_monitor_task"


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    builder = Application.builder().token(settings.telegram_bot_token)
    if settings.live_notification_chat_ids:
        builder = builder.post_init(start_live_goal_monitor).post_shutdown(stop_live_goal_monitor)

    application = builder.build()
    application.bot_data["world_cup_service"] = WorldCupService(settings)
    application.bot_data[SEEN_GOAL_IDS_KEY] = set()
    application.bot_data[LIVE_SCORE_SNAPSHOTS_KEY] = {}
    application.bot_data["live_is_bootstrapped"] = False
    for handler in get_handlers():
        application.add_handler(handler)
    application.add_error_handler(error_handler)
    return application


async def start_live_goal_monitor(application: Application) -> None:
    task = asyncio.create_task(live_goal_monitor_loop(application), name="live_goal_monitor")
    application.bot_data[LIVE_MONITOR_TASK_KEY] = task


async def stop_live_goal_monitor(application: Application) -> None:
    task = application.bot_data.pop(LIVE_MONITOR_TASK_KEY, None)
    if isinstance(task, asyncio.Task):
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def live_goal_monitor_loop(application: Application) -> None:
    service = application.bot_data["world_cup_service"]
    if not isinstance(service, WorldCupService):
        raise RuntimeError("world_cup_service is not configured")

    await asyncio.sleep(5)
    while True:
        try:
            await poll_live_goal_notifications(application)
        except Exception:
            logger.exception("Unexpected live goal monitor failure")
        await asyncio.sleep(service.settings.live_poll_interval_seconds)


async def error_handler(update: object, context: Any) -> None:
    chat = update.effective_chat if isinstance(update, Update) else None
    logger.exception(
        "Unhandled Telegram update error",
        exc_info=context.error,
        extra={"chat_id": getattr(chat, "id", None), "chat_type": getattr(chat, "type", None)},
    )


async def poll_live_goal_notifications(application: Application) -> None:
    service = application.bot_data["world_cup_service"]
    if not isinstance(service, WorldCupService):
        raise RuntimeError("world_cup_service is not configured")

    try:
        live_events = await service.get_live_events(use_cache=False)
    except Exception:
        logger.exception("Failed to poll live games for goal notifications")
        return

    seen_goal_ids: set[str] = application.bot_data.setdefault(SEEN_GOAL_IDS_KEY, set())
    score_snapshots: dict[str, tuple[int, ...]] = application.bot_data.setdefault(
        LIVE_SCORE_SNAPSHOTS_KEY,
        {},
    )
    is_bootstrapped = application.bot_data.get("live_is_bootstrapped", False)
    notifications: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for event in live_events:
        event_id = str(event.get("id", ""))
        current_score = _event_score_snapshot(event)
        previous_score = score_snapshots.get(event_id)
        if current_score is not None and previous_score is not None and _score_regressed(previous_score, current_score):
            score_snapshots[event_id] = current_score
            continue
        if current_score is not None and previous_score is not None:
            for detail in _score_change_details(event, previous_score, current_score):
                goal_id = _goal_id(event, detail)
                if goal_id in seen_goal_ids:
                    continue
                seen_goal_ids.add(goal_id)
                if is_bootstrapped:
                    notifications.append((event, detail))
        if current_score is not None:
            score_snapshots[event_id] = current_score

    if not is_bootstrapped:
        application.bot_data["live_is_bootstrapped"] = True

    for event, detail in notifications:
        text = format_goal_notification(event, detail)
        for chat_id in service.settings.live_notification_chat_ids:
            try:
                await application.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
            except Exception:
                logger.exception("Failed to send goal notification", extra={"chat_id": chat_id})


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
                "displayValue": fallback_clock.get("displayClock") or "minuto indisponível",
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run WorldCupQuente Telegram bot")
    parser.add_argument(
        "--drop-pending-updates",
        action="store_true",
        help="Drop Telegram updates queued while the bot was offline.",
    )
    args = parser.parse_args()

    application = build_application()
    application.run_polling(drop_pending_updates=args.drop_pending_updates)
