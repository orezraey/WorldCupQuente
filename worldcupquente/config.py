"""Runtime settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

type ChatId = int | str


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    bot_time_zone: str = "America/Sao_Paulo"
    espn_timeout: float = 30.0
    espn_user_agent: str = "WorldCupQuente/0.1"
    log_level: str = "INFO"
    live_notification_chat_ids: tuple[ChatId, ...] = ()
    live_poll_interval_seconds: int = 30
    notification_config_path: Path = BASE_DIR / "notification_config.json"

    @property
    def zoneinfo(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.bot_time_zone)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")


def get_settings() -> Settings:
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        bot_time_zone=os.getenv("BOT_TIME_ZONE", "America/Sao_Paulo"),
        espn_timeout=float(os.getenv("ESPN_TIMEOUT", "30")),
        espn_user_agent=os.getenv("ESPN_USER_AGENT", "WorldCupQuente/0.1"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        live_notification_chat_ids=_parse_chat_ids(os.getenv("LIVE_NOTIFICATION_CHAT_IDS", "")),
        live_poll_interval_seconds=max(10, int(os.getenv("LIVE_POLL_INTERVAL_SECONDS", "30"))),
        notification_config_path=Path(
            os.getenv("NOTIFICATION_CONFIG_PATH", str(BASE_DIR / "notification_config.json"))
        ),
    )


def _parse_chat_ids(value: str) -> tuple[ChatId, ...]:
    chat_ids: list[ChatId] = []
    for raw_chat_id in value.split(","):
        chat_id = raw_chat_id.strip()
        if not chat_id:
            continue
        chat_ids.append(int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id)
    return tuple(chat_ids)
