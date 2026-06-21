"""Start command and general query callback routing handlers."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.handlers.calendar import handle_calendar_callback
from worldcupquente.handlers.config import handle_config_callback
from worldcupquente.handlers.history import handle_history_callback
from worldcupquente.handlers.inline import handle_inline_callback
from worldcupquente.handlers.live import handle_live_callback
from worldcupquente.handlers.standings import handle_standings_callback
from worldcupquente.handlers.teams import handle_teams_callback
from worldcupquente.handlers.utils import _get_chat_language, _log_command
from worldcupquente.i18n import text


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "start")
    message = update.effective_message
    if message is None:
        return
    language = _get_chat_language(update, context)
    message_text = (
        f"<b>{text('bot_title', language)}</b>\n\n"
        f"{text('commands_available', language)}\n"
        f"{text('start_today', language)}\n"
        f"{text('start_live', language)}\n"
        f"{text('start_calendar', language)}\n"
        f"{text('start_history', language)}\n"
        f"{text('start_standings', language)}\n"
        f"{text('start_teams', language)}\n"
        f"{text('start_config', language)}"
    )
    await message.reply_text(message_text, parse_mode=ParseMode.HTML)


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    data = query.data
    if data.startswith(("teams:", "team:")):
        await handle_teams_callback(query, context)
    elif data.startswith("cal:"):
        await handle_calendar_callback(query, context)
    elif data.startswith("hist:"):
        await handle_history_callback(query, context)
    elif data.startswith("table:"):
        await handle_standings_callback(query, context)
    elif data.startswith("live:"):
        await handle_live_callback(query, context)
    elif data.startswith("config:"):
        await handle_config_callback(query, context)
    elif data.startswith("inl:"):
        await handle_inline_callback(query, context)
