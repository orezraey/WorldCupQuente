"""World Cup data service with ESPN-backed cache."""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
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
    parse_espn_datetime,
)
from worldcupquente.sofascore_client import SofaScoreClient

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
SOFASCORE_EVENTS_CACHE_SECONDS = 60 * 5
SOFASCORE_EVENT_MAPPING_CACHE_SECONDS = 60 * 60 * 12
SOFASCORE_WIN_PROBABILITY_CACHE_SECONDS = 30
SOFASCORE_EVENT_TIME_TOLERANCE_SECONDS = 60 * 60 * 6

logger = logging.getLogger(__name__)


class WorldCupService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ESPNClient(settings)
        self.sofascore_client = SofaScoreClient(settings.espn_timeout, settings.espn_user_agent)
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
        return await self.enrich_events_win_probability(hydrated)

    async def enrich_events_win_probability(
        self,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return list(
            await asyncio.gather(
                *(self.enrich_event_win_probability(event) for event in events),
            )
        )

    async def enrich_event_win_probability(self, event: dict[str, Any]) -> dict[str, Any]:
        if event.get("winProbability"):
            return event

        try:
            mapping = await self._sofascore_event_mapping(event)
            if mapping is None:
                return event

            probability = await self._sofascore_win_probability(mapping["event_id"])
            if probability is None:
                return event

            if mapping.get("reversed"):
                probability = {
                    "home": probability["away"],
                    "draw": probability["draw"],
                    "away": probability["home"],
                }
            event["winProbability"] = {**probability, "source": "sofascore"}
        except Exception as e:
            logger.warning(f"Failed to enrich event with SofaScore win probability: {e}")
        return event

    async def _sofascore_event_mapping(self, event: dict[str, Any]) -> dict[str, Any] | None:
        event_id = str(event.get("id", ""))
        cache_key = f"sofascore:event-map:{event_id}"
        if event_id:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        for date in _sofascore_candidate_dates(event, self.bot_timezone):
            candidates = await self._sofascore_events_by_date(date)
            mapping = _match_sofascore_event(event, candidates)
            if mapping is not None:
                if event_id:
                    self.cache.set(cache_key, mapping, SOFASCORE_EVENT_MAPPING_CACHE_SECONDS)
                return mapping
        return None

    async def _sofascore_events_by_date(self, date: str) -> list[dict[str, Any]]:
        cache_key = f"sofascore:events:{date}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        events = await self.sofascore_client.get_scheduled_events(date)
        self.cache.set(cache_key, events, SOFASCORE_EVENTS_CACHE_SECONDS)
        return events

    async def _sofascore_win_probability(self, event_id: int | str) -> dict[str, int] | None:
        cache_key = f"sofascore:win-probability:{event_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        probability = await self.sofascore_client.get_win_probability(event_id)
        if probability is not None:
            self.cache.set(cache_key, probability, SOFASCORE_WIN_PROBABILITY_CACHE_SECONDS)
        return probability

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


def _sofascore_candidate_dates(event: dict[str, Any], tz: ZoneInfo) -> list[str]:
    value = _event_date_value(event)
    if not value:
        return []

    dates = []
    for timezone in (ZoneInfo("UTC"), tz):
        event_time = parse_espn_datetime(value, timezone)
        if event_time is None:
            continue
        date = event_time.strftime("%Y-%m-%d")
        if date not in dates:
            dates.append(date)
    return dates


def _event_date_value(event: dict[str, Any]) -> str:
    competition = (event.get("competitions") or [{}])[0]
    return str(event.get("date") or competition.get("date") or "")


def _match_sofascore_event(
    espn_event: dict[str, Any],
    sofascore_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    home, away = _espn_home_away(espn_event)
    if not home or not away:
        return None

    event_time = parse_espn_datetime(_event_date_value(espn_event), ZoneInfo("UTC"))
    best_match: tuple[int, bool, float] | None = None

    for sofascore_event in sofascore_events:
        sofa_home = sofascore_event.get("homeTeam") or {}
        sofa_away = sofascore_event.get("awayTeam") or {}
        direct = _team_matches(home, sofa_home) and _team_matches(away, sofa_away)
        reversed_match = _team_matches(home, sofa_away) and _team_matches(away, sofa_home)
        if not direct and not reversed_match:
            continue

        time_diff = _sofascore_time_diff_seconds(event_time, sofascore_event)
        if time_diff is not None and time_diff > SOFASCORE_EVENT_TIME_TOLERANCE_SECONDS:
            continue

        score = time_diff if time_diff is not None else 0
        candidate = (int(sofascore_event.get("id", 0)), reversed_match, score)
        if candidate[0] and (best_match is None or candidate[2] < best_match[2]):
            best_match = candidate

    if best_match is None:
        return None
    return {"event_id": best_match[0], "reversed": best_match[1]}


def _espn_home_away(event: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    competition = (event.get("competitions") or [{}])[0]
    home = None
    away = None
    for competitor in competition.get("competitors", []):
        if competitor.get("homeAway") == "home":
            home = competitor.get("team") or {}
        elif competitor.get("homeAway") == "away":
            away = competitor.get("team") or {}
    return home, away


def _sofascore_time_diff_seconds(
    event_time: datetime | None,
    sofascore_event: dict[str, Any],
) -> float | None:
    if event_time is None:
        return None
    timestamp = sofascore_event.get("startTimestamp")
    if timestamp is None:
        return None
    try:
        sofascore_time = datetime.fromtimestamp(float(timestamp), tz=ZoneInfo("UTC"))
    except (TypeError, ValueError, OSError):
        return None
    return abs((sofascore_time - event_time).total_seconds())


def _team_matches(espn_team: dict[str, Any], sofascore_team: dict[str, Any]) -> bool:
    espn_names = _normalized_team_values(
        espn_team,
        ("displayName", "shortDisplayName", "name", "abbreviation", "location"),
    )
    sofascore_names = _normalized_team_values(
        sofascore_team,
        ("name", "shortName", "nameCode", "slug"),
    )
    if espn_names & sofascore_names:
        return True
    return any(_contains_team_name(left, right) for left in espn_names for right in sofascore_names)


def _normalized_team_values(team: dict[str, Any], keys: tuple[str, ...]) -> set[str]:
    return {_normalize_team_name(team.get(key)) for key in keys if _normalize_team_name(team.get(key))}


def _normalize_team_name(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _contains_team_name(left: str, right: str) -> bool:
    return len(left) > 3 and len(right) > 3 and (left in right or right in left)
