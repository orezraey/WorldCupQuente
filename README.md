# WorldCupQuente

[Português](README.pt-BR.md)

WorldCupQuente is a Telegram bot for following FIFA World Cup 2026 matches using public ESPN endpoints. It shows schedules, live matches, standings, teams, rosters, and automatic notifications for relevant match events.

## Features

- Today's matches.
- Live matches.
- Calendar navigation by date or team.
- Group-stage standings.
- Teams and rosters.
- Per-chat configurable notifications for match start, goals, penalties, red cards, halftime, and full time.
- Team notification scope: all teams by default, or followed teams selected through `/teams`.
- Per-chat language selection in English or Portuguese through `/config`.

## Bot Commands

- `/start` - shows quick help.
- `/today` - lists today's matches.
- `/live` - shows currently live matches.
- `/calendar` - opens the calendar by date or team.
- `/standings` - shows group-stage standings.
- `/teams` - lists teams and opens full rosters.
- `/config` - configures notifications and language for the current chat.

Portuguese aliases also remain available: `/hoje`, `/aovivo`, `/calendario`, `/tabela`, and `/selecoes`.

## Requirements

- Python 3.12 or later.
- A Telegram bot token created with BotFather.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

On Linux or macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Configuration

Edit `.env` and fill in the required variables.

```env
TELEGRAM_BOT_TOKEN=your_token
BOT_TIME_ZONE=America/Sao_Paulo
LIVE_NOTIFICATION_CHAT_IDS=123456789,-1001234567890
LIVE_POLL_INTERVAL_SECONDS=30
NOTIFICATION_CONFIG_PATH=notification_config.json
ESPN_TIMEOUT=30
ESPN_USER_AGENT=WorldCupQuente/0.1
LOG_LEVEL=INFO
```

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token. |
| `BOT_TIME_ZONE` | No | Time zone used to display dates and times. Defaults to `America/Sao_Paulo`. |
| `LIVE_NOTIFICATION_CHAT_IDS` | No | Comma-separated list of chats that receive automatic notifications. |
| `LIVE_POLL_INTERVAL_SECONDS` | No | Polling interval for the live monitor. The minimum applied value is 10 seconds. |
| `NOTIFICATION_CONFIG_PATH` | No | Local file path where per-chat preferences are saved. |
| `ESPN_TIMEOUT` | No | Timeout, in seconds, for ESPN requests. |
| `ESPN_USER_AGENT` | No | User-Agent used for HTTP requests. |
| `LOG_LEVEL` | No | Application log level, such as `INFO`, `WARNING`, or `DEBUG`. |

Do not commit `.env` or `notification_config.json`. They may contain tokens, chat IDs, and local user preferences. The project `.gitignore` already ignores these files.

## Language

English is the default language for new chats. Each chat can switch the bot to Portuguese in `/config`. The selected language is saved in the file configured by `NOTIFICATION_CONFIG_PATH`.

The default Telegram command menu is registered in English. When a chat switches language in `/config`, the bot also updates that chat's command menu to the selected language when Telegram supports the scoped command update.

## Running

```powershell
python -m worldcupquente --drop-pending-updates
```

Or, after installing the package in editable mode:

```powershell
worldcupquente --drop-pending-updates
```

The `--drop-pending-updates` option discards messages queued while the bot was offline.

## Notifications

The background monitor polls upcoming and active matches, then sends alerts to configured chats. Notifications are deduplicated in memory while the process is running.

By default, a chat receives notifications for all teams, including an alert about 5 minutes before kickoff. The `/config` command lets each chat switch between all teams and followed teams only, enable or disable specific alert types, and choose English or Portuguese.

When a chat is configured for followed teams only, open `/teams`, choose a team, and use the notification button on that team's roster screen. If the chat is configured for all teams, that button is hidden because following individual teams is not needed.

These preferences are saved to the path defined by `NOTIFICATION_CONFIG_PATH`.

For full-time notifications, the bot tries to use `sendRichMessage` when available in the Telegram environment being used. If that method fails, the application logs the error and sends a regular HTML message as fallback.

## Code Quality

Run tests:

```bash
python -m pytest
```

Run lint:

```bash
python -m ruff check .
```

## Data Source

Data is fetched from public ESPN endpoints. These endpoints are not an official versioned API for this project and may change without notice. If response structures change, parsers and formatters may need updates.

## License

This project is distributed under the MIT license. See `LICENSE` for details.
