"""Notification preferences configuration handlers."""

from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.commands import set_chat_commands
from worldcupquente.handlers.utils import _get_notification_preferences, _log_command
from worldcupquente.i18n import text
from worldcupquente.keyboards import build_notification_config_keyboard


async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "config")
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return
    await _send_notification_config(message.reply_text, context, chat.id)


async def _send_notification_config(
    send_message: Any,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> None:
    preferences = _get_notification_preferences(context)
    settings = preferences.get(chat_id)
    language = preferences.get_language(chat_id)
    await send_message(
        _config_text(language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_notification_config_keyboard(settings, language),
    )


async def _toggle_notification_config(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.message is None:
        return
    notification_type = query.data.rsplit(":", maxsplit=1)[-1]
    preferences = _get_notification_preferences(context)
    try:
        settings = preferences.toggle(query.message.chat_id, notification_type)
    except ValueError:
        await query.edit_message_text(text("config_invalid", preferences.get_language(query.message.chat_id)))
        return

    language = preferences.get_language(query.message.chat_id)
    await query.edit_message_text(
        _config_text(language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_notification_config_keyboard(settings, language),
    )


async def _set_config_language(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.message is None:
        return
    language = query.data.rsplit(":", maxsplit=1)[-1]
    preferences = _get_notification_preferences(context)
    settings = preferences.set_language(query.message.chat_id, language)
    selected_language = preferences.get_language(query.message.chat_id)
    await set_chat_commands(context.bot, query.message.chat_id, selected_language)
    await query.edit_message_text(
        _config_text(selected_language),
        parse_mode=ParseMode.HTML,
        reply_markup=build_notification_config_keyboard(settings, selected_language),
    )


def _config_text(language: str) -> str:
    return f"<b>{text('config_title', language)}</b>\n{text('config_body', language)}"


async def handle_config_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.data.startswith("config:toggle:"):
        await _toggle_notification_config(query, context)
    elif query.data.startswith("config:language:"):
        await _set_config_language(query, context)
