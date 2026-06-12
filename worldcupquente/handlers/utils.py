"""Shared utilities and context helpers for Telegram handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from worldcupquente.notification_preferences import NotificationPreferences
from worldcupquente.services import WorldCupService

logger = logging.getLogger(__name__)


def _log_command(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str) -> None:
    logger.info(
        "Command received",
        extra={
            "command": command,
            "chat_id": getattr(update.effective_chat, "id", None),
            "chat_type": getattr(update.effective_chat, "type", None),
        },
    )


def _get_service(context: ContextTypes.DEFAULT_TYPE) -> WorldCupService:
    service = context.application.bot_data["world_cup_service"]
    if not isinstance(service, WorldCupService):
        raise RuntimeError("world_cup_service is not configured")
    return service


def _get_notification_preferences(context: ContextTypes.DEFAULT_TYPE) -> NotificationPreferences:
    preferences = context.application.bot_data["notification_preferences"]
    if not isinstance(preferences, NotificationPreferences):
        raise RuntimeError("notification_preferences is not configured")
    return preferences
