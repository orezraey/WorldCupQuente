"""World Cup data service with ESPN-backed cache."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.cache import TTLCache
from worldcupquente.config import Settings
from worldcupquente.espn_client import ESPNClient

WORLD_CUP_SPORT = "soccer"
WORLD_CUP_LEAGUE = "fifa.world"
WORLD_CUP_START_DATE = "20260611"
WORLD_CUP_END_DATE = "20260719"

TODAY_GAMES_CACHE_SECONDS = 60
SCHEDULE_CACHE_SECONDS = 60
TEAMS_CACHE_SECONDS = 60 * 60 * 24
ROSTER_CACHE_SECONDS = 60 * 60 * 12


class WorldCupService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ESPNClient(settings)
        self.cache: TTLCache[Any] = TTLCache()

    @property
    def bot_timezone(self) -> ZoneInfo:
        return self.settings.zoneinfo

    def today_date_param(self) -> str:
        return datetime.now(tz=self.bot_timezone).strftime("%Y%m%d")

    async def get_games_by_date(self, date_param: str) -> dict[str, Any]:
        cache_key = f"scoreboard:{date_param}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        data = await self.client.get_scoreboard(
            WORLD_CUP_SPORT,
            WORLD_CUP_LEAGUE,
            date=date_param,
            limit=100,
        )
        self.cache.set(cache_key, data, TODAY_GAMES_CACHE_SECONDS)
        return data

    async def get_today_games(self) -> dict[str, Any]:
        return await self.get_games_by_date(self.today_date_param())

    async def get_schedule(self) -> dict[str, Any]:
        date_range = f"{WORLD_CUP_START_DATE}-{WORLD_CUP_END_DATE}"
        cache_key = f"scoreboard:{date_range}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        data = await self.client.get_scoreboard(
            WORLD_CUP_SPORT,
            WORLD_CUP_LEAGUE,
            date=date_range,
            limit=500,
        )
        self.cache.set(cache_key, data, SCHEDULE_CACHE_SECONDS)
        return data

    async def get_schedule_events(self) -> list[dict[str, Any]]:
        schedule = await self.get_schedule()
        return schedule.get("events", [])

    async def get_schedule_events_by_date(self, date_param: str) -> list[dict[str, Any]]:
        events = await self.get_schedule_events()
        return [
            event
            for event in events
            if _event_local_date_param(event, self.bot_timezone) == date_param
        ]

    async def get_schedule_events_by_team(self, team_id: str) -> list[dict[str, Any]]:
        events = await self.get_schedule_events()
        return [event for event in events if _event_has_team(event, team_id)]

    async def get_teams(self) -> list[dict[str, Any]]:
        cached = self.cache.get("teams")
        if cached is not None:
            return cached

        data = await self.client.get_teams(WORLD_CUP_SPORT, WORLD_CUP_LEAGUE, limit=100)
        teams = data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
        parsed = [item.get("team", item) for item in teams]
        self.cache.set("teams", parsed, TEAMS_CACHE_SECONDS)
        return parsed

    async def get_team_roster(self, team_id: str) -> dict[str, Any]:
        cache_key = f"roster:{team_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        data = await self.client.get_team_roster(WORLD_CUP_SPORT, WORLD_CUP_LEAGUE, team_id)
        self.cache.set(cache_key, data, ROSTER_CACHE_SECONDS)
        return data


def parse_espn_datetime(value: str, tz: ZoneInfo) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(tz)


def _event_local_date_param(event: dict[str, Any], tz: ZoneInfo) -> str:
    event_time = parse_espn_datetime(event.get("date", ""), tz)
    return event_time.strftime("%Y%m%d") if event_time else ""


def _event_has_team(event: dict[str, Any], team_id: str) -> bool:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    for competitor in competitors:
        team = competitor.get("team", {}) or {}
        if str(team.get("id", "")) == str(team_id):
            return True
    return False
