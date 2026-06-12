"""World Cup data service with ESPN-backed cache."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.cache import TTLCache
from worldcupquente.config import Settings
from worldcupquente.espn_client import ESPNClient
from worldcupquente.espn_events import (
    _event_has_team,
    _event_local_date_param,
    event_from_summary,
    live_events_from_scoreboard,
)

WORLD_CUP_SPORT = "soccer"
WORLD_CUP_LEAGUE = "fifa.world"
WORLD_CUP_SEASON = 2026
WORLD_CUP_START_DATE = "20260611"
WORLD_CUP_END_DATE = "20260719"

TODAY_GAMES_CACHE_SECONDS = 60
SCHEDULE_CACHE_SECONDS = 60
STANDINGS_CACHE_SECONDS = 60
TEAMS_CACHE_SECONDS = 60 * 60 * 24
ROSTER_CACHE_SECONDS = 60 * 60 * 12

logger = logging.getLogger(__name__)


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

    async def get_games_by_date(self, date_param: str, use_cache: bool = True) -> dict[str, Any]:
        cache_key = f"scoreboard:{date_param}"
        cached = self.cache.get(cache_key) if use_cache else None
        if cached is not None:
            return cached

        data = await self.client.get_scoreboard(
            WORLD_CUP_SPORT,
            WORLD_CUP_LEAGUE,
            date=date_param,
            limit=100,
        )
        if use_cache:
            self.cache.set(cache_key, data, TODAY_GAMES_CACHE_SECONDS)
        return data

    async def get_today_games(self, use_cache: bool = True) -> dict[str, Any]:
        return await self.get_games_by_date(self.today_date_param(), use_cache=use_cache)

    def date_param_for_offset(self, days: int) -> str:
        return (datetime.now(tz=self.bot_timezone) + timedelta(days=days)).strftime("%Y%m%d")

    async def get_active_scoreboard(self, use_cache: bool = True) -> dict[str, Any]:
        yesterday = self.date_param_for_offset(-1)
        tomorrow = self.date_param_for_offset(1)
        date_range = f"{yesterday}-{tomorrow}"
        return await self.get_games_by_date(date_range, use_cache=use_cache)

    async def get_live_events(self, use_cache: bool = True) -> list[dict[str, Any]]:
        scoreboard = await self.get_active_scoreboard(use_cache=use_cache)
        live_events = live_events_from_scoreboard(scoreboard)
        return await self._hydrate_live_events(live_events)

    async def get_event_summary(self, event_id: str) -> dict[str, Any]:
        return await self.client.get_summary(WORLD_CUP_SPORT, WORLD_CUP_LEAGUE, event_id)

    async def _hydrate_live_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not events:
            return events

        summaries = await asyncio.gather(
            *(self.get_event_summary(str(event.get("id", ""))) for event in events),
            return_exceptions=True,
        )

        hydrated: list[dict[str, Any]] = []
        for event, summary in zip(events, summaries, strict=True):
            if isinstance(summary, Exception):
                logger.warning("Failed to fetch live event summary", extra={"event_id": event.get("id")})
                hydrated.append(event)
                continue
            hydrated.append(event_from_summary(summary, fallback_event=event))
        return hydrated

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

    async def get_standings(self, use_cache: bool = True) -> dict[str, Any]:
        cached = self.cache.get("standings") if use_cache else None
        if cached is not None:
            return cached

        data = await self.client.get_standings(WORLD_CUP_SPORT, WORLD_CUP_LEAGUE, WORLD_CUP_SEASON)
        if use_cache:
            self.cache.set("standings", data, STANDINGS_CACHE_SECONDS)
        return data

    async def get_standings_groups(self, use_cache: bool = True) -> list[dict[str, Any]]:
        standings = await self.get_standings(use_cache=use_cache)
        return standings.get("children", [])

    async def get_standings_group(self, group_id: str, use_cache: bool = True) -> dict[str, Any] | None:
        groups = await self.get_standings_groups(use_cache=use_cache)
        return next((group for group in groups if str(group.get("id", "")) == str(group_id)), None)
