"""Runtime settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    bot_time_zone: str = "America/Sao_Paulo"
    espn_timeout: float = 30.0
    espn_user_agent: str = "WorldCupQuente/0.1"
    log_level: str = "INFO"

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
    )
