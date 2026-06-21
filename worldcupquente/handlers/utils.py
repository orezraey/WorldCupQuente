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


def _get_chat_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    chat = update.effective_chat
    if chat is None:
        return "en"
    preferences = _get_notification_preferences(context)
    preferences.ensure_chat(chat.id)
    return preferences.get_language(chat.id)


def _get_query_language(query: object, context: ContextTypes.DEFAULT_TYPE) -> str:
    message = getattr(query, "message", None)
    chat_id = getattr(message, "chat_id", None)
    if chat_id is None:
        return "en"
    preferences = _get_notification_preferences(context)
    preferences.ensure_chat(chat_id)
    return preferences.get_language(chat_id)


def _get_inline_query_language(update: Update) -> str:
    """Language for an inline query (no chat): derive from the user's client language."""
    inline_query = getattr(update, "inline_query", None)
    return _user_language(getattr(inline_query, "from_user", None))


def _get_inline_callback_language(query: object) -> str:
    """Language for a callback originating from an inline (via-bot) message."""
    return _user_language(getattr(query, "from_user", None))


def _user_language(user: object) -> str:
    language_code = getattr(user, "language_code", None)
    if isinstance(language_code, str) and language_code.lower().startswith("pt"):
        return "pt"
    return "en"
