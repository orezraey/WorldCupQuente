"""Start command and general query callback routing handlers."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from worldcupquente.handlers.calendar import handle_calendar_callback
from worldcupquente.handlers.config import handle_config_callback
from worldcupquente.handlers.live import handle_live_callback
from worldcupquente.handlers.standings import handle_standings_callback
from worldcupquente.handlers.teams import handle_teams_callback
from worldcupquente.handlers.utils import _log_command


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_command(update, context, "start")
    message = update.effective_message
    if message is None:
        return
    text = (
        "<b>Copa do Mundo 2026</b>\n\n"
        "Comandos disponíveis:\n"
        "/hoje - jogos de hoje\n"
        "/aovivo - partidas ao vivo\n"
        "/calendario - calendário de jogos por data ou seleção\n"
        "/tabela - classificação por grupo\n"
        "/selecoes - lista de seleções e elencos\n"
        "/config - configurar notificações ao vivo"
    )
    await message.reply_text(text, parse_mode=ParseMode.HTML)


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
    elif data.startswith("table:"):
        await handle_standings_callback(query, context)
    elif data.startswith("live:"):
        await handle_live_callback(query, context)
    elif data.startswith("config:"):
        await handle_config_callback(query, context)
