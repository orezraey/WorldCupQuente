"""World Cup data service with ESPN-backed cache."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta, tzinfo
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
LIVE_STATUS_FALLBACK_WINDOW = timedelta(hours=3)

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

    async def get_live_events(self, use_cache: bool = True) -> list[dict[str, Any]]:
        scoreboard = await self.get_today_games(use_cache=use_cache)
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


def parse_espn_datetime(value: str, tz: tzinfo) -> datetime | None:
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


def live_events_from_scoreboard(
    scoreboard: dict[str, Any],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    return [event for event in scoreboard.get("events", []) if is_live_event(event, current_time)]


def is_live_event(event: dict[str, Any], now: datetime | None = None) -> bool:
    state = event_state(event)
    if state == "in":
        return True
    if state != "pre":
        return False

    event_time = parse_espn_datetime(event.get("date", ""), UTC)
    if event_time is None:
        return False

    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    current_time = current_time.astimezone(UTC)

    return event_time <= current_time <= event_time + LIVE_STATUS_FALLBACK_WINDOW


def event_state(event: dict[str, Any]) -> str:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    return str((status.get("type") or {}).get("state") or "")


def event_from_summary(
    summary: dict[str, Any],
    fallback_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback_event = fallback_event or {}
    header = summary.get("header") or {}
    competition = ((header.get("competitions") or [{}])[0]).copy()
    if not competition:
        return fallback_event

    fallback_competition = (fallback_event.get("competitions") or [{}])[0]
    fallback_status = fallback_competition.get("status") or fallback_event.get("status") or {}
    competition_status = competition.get("status") or {}
    if competition_status or fallback_status:
        competition["status"] = _merge_status(competition_status, fallback_status)

    venue = ((summary.get("gameInfo") or {}).get("venue") or fallback_event.get("venue") or {}).copy()
    if venue:
        competition.setdefault("venue", venue)

    event = fallback_event.copy()
    event.update(
        {
            "id": header.get("id") or fallback_event.get("id"),
            "uid": header.get("uid") or fallback_event.get("uid"),
            "date": competition.get("date") or fallback_event.get("date"),
            "competitions": [competition],
            "status": competition.get("status") or fallback_event.get("status"),
            "venue": venue or fallback_event.get("venue"),
            "boxscore": summary.get("boxscore") or {},
            "leaders": summary.get("leaders") or [],
            "commentary": summary.get("commentary") or [],
            "rosters": summary.get("rosters") or [],
            "scoringPlays": summary.get("scoringPlays") or [],
        }
    )
    return event


def _merge_status(status: dict[str, Any], fallback_status: dict[str, Any]) -> dict[str, Any]:
    merged = fallback_status.copy()
    merged.update(status)

    fallback_type = fallback_status.get("type") or {}
    status_type = status.get("type") or {}
    if fallback_type or status_type:
        merged["type"] = {**fallback_type, **status_type}
    return merged


def scoring_plays_from_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    competition = (event.get("competitions") or [{}])[0]
    plays = [
        detail
        for detail in competition.get("details", [])
        if detail.get("scoringPlay") is True and detail.get("shootout") is not True
    ]
    plays.extend(
        play
        for play in event.get("scoringPlays", [])
        if play.get("shootout") is not True
    )
    if plays:
        return _dedupe_goal_plays(plays)

    plays.extend(_goal_plays_from_commentary(event))
    return _dedupe_goal_plays(plays)


def _dedupe_goal_plays(plays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for play in plays:
        athletes = play.get("athletesInvolved") or [
            participant.get("athlete") or {}
            for participant in play.get("participants", [])
            if participant.get("athlete")
        ]
        scorer = (athletes or [{}])[0]
        clock = play.get("clock") or {}
        key = (
            str((play.get("team") or {}).get("id", "")),
            str(clock.get("value") or clock.get("displayValue") or ""),
            str(scorer.get("id") or scorer.get("displayName") or scorer.get("fullName") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(play)
    return deduped


def _goal_plays_from_commentary(event: dict[str, Any]) -> list[dict[str, Any]]:
    goal_plays: list[dict[str, Any]] = []
    for item in event.get("commentary", []):
        play = item.get("play") or {}
        play_type = play.get("type") or {}
        if play_type.get("type") != "goal" and play_type.get("text") != "Goal":
            continue

        participants = play.get("participants") or []
        goal_plays.append(
            {
                "id": play.get("id") or f"commentary:{item.get('sequence', '')}",
                "clock": play.get("clock") or item.get("time") or {},
                "team": _team_from_commentary_play(event, play),
                "type": play_type,
                "text": play.get("text") or item.get("text"),
                "scoreValue": 1,
                "athletesInvolved": [
                    participant.get("athlete") or {}
                    for participant in participants
                    if participant.get("athlete")
                ],
            }
        )
    return goal_plays


def _team_from_commentary_play(event: dict[str, Any], play: dict[str, Any]) -> dict[str, Any]:
    play_team_name = str((play.get("team") or {}).get("displayName") or "")
    competition = (event.get("competitions") or [{}])[0]
    for competitor in competition.get("competitors", []):
        team = competitor.get("team") or {}
        names = {
            str(team.get("displayName") or ""),
            str(team.get("shortDisplayName") or ""),
            str(team.get("name") or ""),
        }
        if play_team_name in names:
            return team
    return play.get("team") or {}
