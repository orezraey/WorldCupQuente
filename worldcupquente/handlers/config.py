"""Notification preferences configuration handlers."""

from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.handlers.utils import _get_notification_preferences, _log_command
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
    settings = preferences.ensure_chat(chat_id)
    text = "<b>Notificações ao vivo</b>\nEscolha quais alertas este chat deve receber."
    await send_message(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_notification_config_keyboard(settings),
    )


async def _toggle_notification_config(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.message is None:
        return
    notification_type = query.data.rsplit(":", maxsplit=1)[-1]
    preferences = _get_notification_preferences(context)
    try:
        settings = preferences.toggle(query.message.chat_id, notification_type)
    except ValueError:
        await query.edit_message_text("Configuração inválida.")
        return

    text = "<b>Notificações ao vivo</b>\nEscolha quais alertas este chat deve receber."
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_notification_config_keyboard(settings),
    )


async def handle_config_callback(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    if query.data.startswith("config:toggle:"):
        await _toggle_notification_config(query, context)
