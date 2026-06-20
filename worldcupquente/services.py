"""World Cup data service backed by SofaScore."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from worldcupquente.cache import TTLCache
from worldcupquente.config import Settings
from worldcupquente.event_utils import (
    _event_has_team,
    _event_local_date_param,
    event_state,
)
from worldcupquente.sofascore_client import SofaScoreClient
from worldcupquente.team_translations import sofascore_legacy_team_id

WORLD_CUP_SEASON = 2026
SOFASCORE_WORLD_CUP_TOURNAMENT_ID = 16
SOFASCORE_WORLD_CUP_SEASON_ID = 58210

TEAMS_CACHE_SECONDS = 60 * 60 * 24
SOFASCORE_EVENTS_CACHE_SECONDS = 60 * 5
SOFASCORE_INCIDENTS_CACHE_SECONDS = 15
SOFASCORE_LINEUPS_CACHE_SECONDS = 60 * 5
SOFASCORE_STATISTICS_CACHE_SECONDS = 60 * 5
SOFASCORE_HISTORY_CACHE_SECONDS = 60 * 5
SOFASCORE_SCHEDULE_CACHE_SECONDS = 60 * 5
SOFASCORE_EVENT_DETAIL_CACHE_SECONDS = 60 * 5
SOFASCORE_STANDINGS_CACHE_SECONDS = 60
SOFASCORE_TEAM_PROFILE_CACHE_SECONDS = 60 * 60 * 6
SOFASCORE_TEAM_PLAYERS_CACHE_SECONDS = 60 * 60 * 6
SOFASCORE_TEAM_EVENTS_CACHE_SECONDS = 60 * 5
SOFASCORE_TEAM_ACHIEVEMENTS_CACHE_SECONDS = 60 * 60 * 24
SOFASCORE_TEAM_STATISTICS_CACHE_SECONDS = 60 * 60
SOFASCORE_WIN_PROBABILITY_CACHE_SECONDS = 30
SOFASCORE_PLAYER_DETAIL_CACHE_SECONDS = 60 * 60
SOFASCORE_PLAYER_IMAGE_CACHE_SECONDS = 60 * 60 * 24

logger = logging.getLogger(__name__)


class WorldCupService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sofascore_client = SofaScoreClient(settings.request_timeout, settings.http_user_agent)
        self.cache: TTLCache[Any] = TTLCache()

    @property
    def bot_timezone(self) -> ZoneInfo:
        return self.settings.zoneinfo

    def today_date_param(self) -> str:
        return datetime.now(tz=self.bot_timezone).strftime("%Y%m%d")

    def sofascore_date_param_for_offset(self, days: int = 0) -> str:
        return (datetime.now(tz=self.bot_timezone) + timedelta(days=days)).strftime("%Y-%m-%d")

    async def get_sofascore_games_by_date(self, date_param: str, use_cache: bool = True) -> list[dict[str, Any]]:
        cache_key = f"sofascore:scheduled-events:{date_param}"
        cached = self.cache.get(cache_key) if use_cache else None
        if cached is not None:
            return cached

        events = await self.sofascore_client.get_scheduled_events(date_param)
        requested_date = date_param.replace("-", "")
        normalized = []
        for raw_event in events:
            if not _is_sofascore_world_cup_event(raw_event):
                continue
            event = _normalize_sofascore_event(raw_event)
            if _event_local_date_param(event, self.bot_timezone) != requested_date:
                continue
            normalized.append(event)
        normalized = sorted(normalized, key=_event_date_value)
        normalized = await self._hydrate_sofascore_event_venues(normalized, use_cache=use_cache)
        if use_cache:
            self.cache.set(cache_key, normalized, SOFASCORE_EVENTS_CACHE_SECONDS)
        return normalized

    async def get_sofascore_today_games(self, use_cache: bool = True) -> dict[str, Any]:
        events = await self.get_sofascore_games_by_date(self.sofascore_date_param_for_offset(), use_cache=use_cache)
        return {"events": events}

    async def get_sofascore_live_events(
        self,
        use_cache: bool = True,
        include_statistics: bool = False,
    ) -> list[dict[str, Any]]:
        events = await self._sofascore_events_for_offsets((-1, 0, 1), use_cache=use_cache)
        live_events = [event for event in events if event_state(event) == "in"]
        return await self.enrich_sofascore_live_events(sorted(live_events, key=_event_date_value), include_statistics=include_statistics)

    async def get_sofascore_monitor_events(self, use_cache: bool = True) -> dict[str, list[dict[str, Any]]]:
        events = await self._sofascore_events_for_offsets((-1, 0, 1), use_cache=use_cache)
        live_events = [event for event in events if event_state(event) == "in"]
        enriched_live_events = await self.enrich_sofascore_live_events(sorted(live_events, key=_event_date_value))
        return {
            "live_events": enriched_live_events,
            "status_events": sorted(events, key=_event_date_value),
        }

    async def _sofascore_events_for_offsets(
        self,
        offsets: tuple[int, ...],
        *,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        events_by_date = await asyncio.gather(
            *(self.get_sofascore_games_by_date(self.sofascore_date_param_for_offset(offset), use_cache=use_cache) for offset in offsets)
        )
        events: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for day_events in events_by_date:
            for event in day_events:
                event_id = str(event.get("id") or "")
                if event_id and event_id in seen_ids:
                    continue
                if event_id:
                    seen_ids.add(event_id)
                events.append(event)
        return events

    async def enrich_sofascore_live_events(
        self,
        events: list[dict[str, Any]],
        *,
        include_statistics: bool = False,
    ) -> list[dict[str, Any]]:
        return list(await asyncio.gather(*(self.enrich_sofascore_live_event(event, include_statistics=include_statistics) for event in events)))

    async def enrich_sofascore_live_event(
        self,
        event: dict[str, Any],
        *,
        include_statistics: bool = False,
    ) -> dict[str, Any]:
        event_id = str(event.get("id") or "")
        if not event_id:
            return event

        incidents, probability = await asyncio.gather(
            self._sofascore_match_incidents(event_id),
            self._sofascore_win_probability(event_id),
        )

        normalized_incidents = _normalize_sofascore_incidents(event, incidents)
        if any(normalized_incidents.values()):
            event["sofascoreIncidents"] = normalized_incidents

        if include_statistics:
            statistics = await self._sofascore_match_statistics(event_id)
            _apply_sofascore_live_statistics(event, statistics)
        if probability is not None:
            event["winProbability"] = {**probability, "source": "sofascore"}
        return event

    async def enrich_event_sofascore_incidents(self, event: dict[str, Any]) -> dict[str, Any]:
        if event.get("sofascoreIncidents"):
            return event

        try:
            event_id = str(event.get("id") or "")
            if not event_id:
                return event
            incidents = await self._sofascore_match_incidents(event_id)
            normalized = _normalize_sofascore_incidents(event, incidents)
            if normalized["goals"] or normalized["disallowedGoals"] or normalized["penalties"] or normalized["redCards"]:
                event["sofascoreIncidents"] = normalized
        except Exception as e:
            logger.warning(f"Failed to enrich event with SofaScore incidents: {e}")
        return event

    async def enrich_event_sofascore_post_match(self, event: dict[str, Any]) -> dict[str, Any]:
        if event.get("sofascorePlayerRatings") and event.get("sofascoreStatistics"):
            return event

        try:
            event_id = str(event.get("id") or "")
            if not event_id:
                return event
            lineups, statistics = await asyncio.gather(
                self._sofascore_match_lineups(event_id),
                self._sofascore_match_statistics(event_id),
            )
            ratings = _normalize_sofascore_player_ratings(lineups)
            normalized_statistics = _normalize_sofascore_match_statistics(statistics)
            if ratings["home"] or ratings["away"]:
                event["sofascorePlayerRatings"] = ratings
            if normalized_statistics:
                event["sofascoreStatistics"] = normalized_statistics
        except Exception as e:
            logger.warning(f"Failed to enrich event with SofaScore post-match data: {e}")
        return event

    async def enrich_events_sofascore_player_ratings(
        self,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return list(
            await asyncio.gather(
                *(self.enrich_event_sofascore_player_ratings(event) for event in events),
            )
        )

    async def enrich_event_sofascore_player_ratings(self, event: dict[str, Any]) -> dict[str, Any]:
        if event.get("sofascorePlayerRatings"):
            return event

        try:
            event_id = str(event.get("id") or "")
            if not event_id:
                return event
            lineups = await self._sofascore_match_lineups(event_id)
            ratings = _normalize_sofascore_player_ratings(lineups)
            if ratings["home"] or ratings["away"]:
                event["sofascorePlayerRatings"] = ratings
        except Exception as e:
            logger.warning(f"Failed to enrich event with SofaScore player ratings: {e}")
        return event

    async def enrich_event_win_probability(self, event: dict[str, Any]) -> dict[str, Any]:
        if event.get("winProbability"):
            return event

        try:
            event_id = str(event.get("id") or "")
            if not event_id:
                return event
            probability = await self._sofascore_win_probability(event_id)
            if probability is None:
                return event
            event["winProbability"] = {**probability, "source": "sofascore"}
        except Exception as e:
            logger.warning(f"Failed to enrich event with SofaScore win probability: {e}")
        return event

    async def _sofascore_win_probability(self, event_id: int | str) -> dict[str, int] | None:
        cache_key = f"sofascore:win-probability:{event_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        probability = await self.sofascore_client.get_win_probability(event_id)
        if probability is not None:
            self.cache.set(cache_key, probability, SOFASCORE_WIN_PROBABILITY_CACHE_SECONDS)
        return probability

    async def _sofascore_match_incidents(self, event_id: int | str) -> list[dict[str, Any]]:
        cache_key = f"sofascore:incidents:{event_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        incidents = await self.sofascore_client.get_match_incidents(event_id)
        self.cache.set(cache_key, incidents, SOFASCORE_INCIDENTS_CACHE_SECONDS)
        return incidents

    async def _hydrate_sofascore_event_venues(
        self,
        events: list[dict[str, Any]],
        *,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        missing_venue_events = [event for event in events if not _event_venue_name(event) and event.get("id")]
        if not missing_venue_events:
            return events

        details = await asyncio.gather(
            *(self._sofascore_event_detail(str(event["id"]), use_cache=use_cache) for event in missing_venue_events),
            return_exceptions=True,
        )
        for event, detail in zip(missing_venue_events, details, strict=True):
            if isinstance(detail, Exception) or not detail:
                continue
            venue = _normalize_sofascore_venue(detail.get("venue") or {})
            if venue:
                _apply_event_venue(event, venue)
        return events

    async def _sofascore_event_detail(self, event_id: int | str, *, use_cache: bool = True) -> dict[str, Any]:
        cache_key = f"sofascore:event:{event_id}:detail"
        cached = self.cache.get(cache_key) if use_cache else None
        if cached is not None:
            return cached

        detail = await self.sofascore_client.get_event(event_id)
        if use_cache and detail:
            self.cache.set(cache_key, detail, SOFASCORE_EVENT_DETAIL_CACHE_SECONDS)
        return detail

    async def _sofascore_match_lineups(self, event_id: int | str) -> dict[str, Any]:
        cache_key = f"sofascore:lineups:{event_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        lineups = await self.sofascore_client.get_match_lineups(event_id)
        self.cache.set(cache_key, lineups, SOFASCORE_LINEUPS_CACHE_SECONDS)
        return lineups

    async def get_sofascore_match_lineups(self, event_id: int | str) -> dict[str, Any]:
        return await self._sofascore_match_lineups(event_id)

    async def _sofascore_player_detail(self, player_id: int | str) -> dict[str, Any]:
        cache_key = f"sofascore:player:{player_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        detail = await self.sofascore_client.get_player_detail(player_id)
        self.cache.set(cache_key, detail, SOFASCORE_PLAYER_DETAIL_CACHE_SECONDS)
        return detail

    async def get_sofascore_player_detail(self, player_id: int | str) -> dict[str, Any]:
        return await self._sofascore_player_detail(player_id)

    async def get_sofascore_player_image(self, player_id: int | str) -> bytes | None:
        cache_key = f"sofascore:player-image:{player_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        image = await self.sofascore_client.get_player_image(player_id)
        if image:
            self.cache.set(cache_key, image, SOFASCORE_PLAYER_IMAGE_CACHE_SECONDS)
        return image

    async def _sofascore_match_statistics(self, event_id: int | str) -> list[dict[str, Any]]:
        cache_key = f"sofascore:statistics:{event_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        statistics = await self.sofascore_client.get_match_statistics(event_id)
        self.cache.set(cache_key, statistics, SOFASCORE_STATISTICS_CACHE_SECONDS)
        return statistics

    async def get_sofascore_finished_events(self) -> list[dict[str, Any]]:
        cache_key = f"sofascore:history:{SOFASCORE_WORLD_CUP_TOURNAMENT_ID}:{SOFASCORE_WORLD_CUP_SEASON_ID}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        events: list[dict[str, Any]] = []
        page = 0
        while True:
            data = await self.sofascore_client.get_tournament_events(
                SOFASCORE_WORLD_CUP_TOURNAMENT_ID,
                SOFASCORE_WORLD_CUP_SEASON_ID,
                "last",
                page,
                suppress_errors=False,
            )
            page_events = data.get("events") or []
            events.extend(_normalize_sofascore_event(event) for event in page_events if _is_sofascore_finished_event(event))
            if not data.get("hasNextPage") or page >= 10:
                break
            page += 1

        events = sorted(events, key=_event_date_value, reverse=True)
        self.cache.set(cache_key, events, SOFASCORE_HISTORY_CACHE_SECONDS)
        return events

    async def get_sofascore_finished_event_details(self, event_id: str) -> dict[str, Any] | None:
        cache_key = f"sofascore:history:event:{event_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        event_data = await self.sofascore_client.get_event(event_id, suppress_errors=False)
        if not event_data:
            event_data = next(
                (event for event in await self._sofascore_tournament_events("last") if str(event.get("id", "")) == str(event_id)),
                {},
            )
        if not event_data:
            return None

        event = _normalize_sofascore_event(event_data)
        incidents, lineups, statistics = await asyncio.gather(
            self._sofascore_match_incidents(event_id),
            self._sofascore_match_lineups(event_id),
            self._sofascore_match_statistics(event_id),
        )
        normalized_incidents = _normalize_sofascore_incidents(event, incidents)
        if any(normalized_incidents.values()):
            event["sofascoreIncidents"] = normalized_incidents

        ratings = _normalize_sofascore_player_ratings(lineups)
        if ratings["home"] or ratings["away"]:
            event["sofascorePlayerRatings"] = ratings

        normalized_statistics = _normalize_sofascore_match_statistics(statistics)
        if normalized_statistics:
            event["sofascoreStatistics"] = normalized_statistics

        self.cache.set(cache_key, event, SOFASCORE_EVENT_DETAIL_CACHE_SECONDS)
        return event

    async def _sofascore_tournament_events(self, direction: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        page = 0
        while True:
            data = await self.sofascore_client.get_tournament_events(
                SOFASCORE_WORLD_CUP_TOURNAMENT_ID,
                SOFASCORE_WORLD_CUP_SEASON_ID,
                direction,
                page,
                suppress_errors=False,
            )
            events.extend(data.get("events") or [])
            if not data.get("hasNextPage") or page >= 10:
                break
            page += 1
        return events

    async def get_sofascore_schedule_events(self) -> list[dict[str, Any]]:
        cache_key = f"sofascore:schedule:{SOFASCORE_WORLD_CUP_TOURNAMENT_ID}:{SOFASCORE_WORLD_CUP_SEASON_ID}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        raw_events = []
        for direction in ("last", "next"):
            raw_events.extend(await self._sofascore_tournament_events(direction))

        events: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for raw_event in raw_events:
            event = _normalize_sofascore_event(raw_event)
            event_id = str(event.get("id") or "")
            if event_id and event_id in seen_ids:
                continue
            if event_id:
                seen_ids.add(event_id)
            events.append(event)

        events = sorted(events, key=_event_date_value)
        self.cache.set(cache_key, events, SOFASCORE_SCHEDULE_CACHE_SECONDS)
        return events

    async def get_sofascore_schedule_events_by_date(self, date_param: str) -> list[dict[str, Any]]:
        events = await self.get_sofascore_schedule_events()
        return [event for event in events if _event_local_date_param(event, self.bot_timezone) == date_param]

    async def get_sofascore_schedule_events_by_team(self, team_id: str) -> list[dict[str, Any]]:
        events = await self.get_sofascore_schedule_events()
        return [event for event in events if _event_has_team(event, team_id)]

    async def get_sofascore_world_cup_teams(self) -> list[dict[str, Any]]:
        cache_key = f"sofascore:teams:{SOFASCORE_WORLD_CUP_TOURNAMENT_ID}:{SOFASCORE_WORLD_CUP_SEASON_ID}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        teams = await self.sofascore_client.get_world_cup_teams(
            SOFASCORE_WORLD_CUP_TOURNAMENT_ID,
            SOFASCORE_WORLD_CUP_SEASON_ID,
        )
        self.cache.set(cache_key, teams, TEAMS_CACHE_SECONDS)
        return teams

    async def get_sofascore_team_id_mapping(self) -> dict[str, str]:
        teams = await self.get_sofascore_world_cup_teams()
        mapping: dict[str, str] = {}
        for team in teams:
            sofascore_id = str(team.get("id") or "")
            if not sofascore_id:
                continue
            legacy_id = sofascore_legacy_team_id(team)
            if legacy_id:
                mapping[legacy_id] = sofascore_id
        return mapping

    async def get_sofascore_team_profile(self, team_id: str) -> dict[str, Any]:
        cache_key = f"sofascore:team:{team_id}:profile"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        data = await self.sofascore_client.get_team_profile(team_id)
        self.cache.set(cache_key, data, SOFASCORE_TEAM_PROFILE_CACHE_SECONDS)
        return data

    async def get_sofascore_team_players(self, team_id: str) -> list[dict[str, Any]]:
        cache_key = f"sofascore:team:{team_id}:players"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        players = await self.sofascore_client.get_team_players(team_id)
        self.cache.set(cache_key, players, SOFASCORE_TEAM_PLAYERS_CACHE_SECONDS)
        return players

    async def get_sofascore_team_events(self, team_id: str, direction: str, page: int = 0) -> list[dict[str, Any]]:
        cache_key = f"sofascore:team:{team_id}:events:{direction}:{page}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        events = await self.sofascore_client.get_team_events(team_id, direction, page)
        self.cache.set(cache_key, events, SOFASCORE_TEAM_EVENTS_CACHE_SECONDS)
        return events

    async def get_sofascore_team_achievements(self, team_id: str) -> dict[str, Any]:
        cache_key = f"sofascore:team:{team_id}:achievements"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        data = await self.sofascore_client.get_team_achievements(team_id)
        self.cache.set(cache_key, data, SOFASCORE_TEAM_ACHIEVEMENTS_CACHE_SECONDS)
        return data

    async def get_sofascore_team_statistics_summary(self, team_id: str) -> dict[str, Any]:
        cache_key = f"sofascore:team:{team_id}:statistics-summary"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        seasons_data = await self.sofascore_client.get_team_statistics_seasons(team_id)
        selection = _select_sofascore_team_statistics_season(seasons_data)
        if selection is None:
            summary: dict[str, Any] = {}
        else:
            tournament, season = selection
            statistics = await self.sofascore_client.get_team_statistics(team_id, tournament["id"], season["id"])
            summary = {"tournament": tournament, "season": season, "statistics": statistics.get("statistics") or {}}
        self.cache.set(cache_key, summary, SOFASCORE_TEAM_STATISTICS_CACHE_SECONDS)
        return summary

    async def get_sofascore_standings_groups(self, use_cache: bool = True) -> list[dict[str, Any]]:
        cache_key = f"sofascore:standings:{SOFASCORE_WORLD_CUP_TOURNAMENT_ID}:{SOFASCORE_WORLD_CUP_SEASON_ID}"
        cached = self.cache.get(cache_key) if use_cache else None
        if cached is not None:
            return cached

        standings = await self.sofascore_client.get_tournament_standings(
            SOFASCORE_WORLD_CUP_TOURNAMENT_ID,
            SOFASCORE_WORLD_CUP_SEASON_ID,
        )
        groups = [_normalize_sofascore_standings_group(group, index) for index, group in enumerate(standings, start=1)]
        groups = [group for group in groups if group.get("standings", {}).get("entries")]
        if use_cache:
            self.cache.set(cache_key, groups, SOFASCORE_STANDINGS_CACHE_SECONDS)
        return groups

    async def get_sofascore_standings_group(self, group_id: str, use_cache: bool = True) -> dict[str, Any] | None:
        groups = await self.get_sofascore_standings_groups(use_cache=use_cache)
        return next((group for group in groups if str(group.get("id", "")) == str(group_id)), None)

def _normalize_sofascore_standings_group(group: dict[str, Any], index: int) -> dict[str, Any]:
    group_sign = str(group.get("groupSign") or "").strip()
    group_id = _sofascore_group_id(group_sign, index)
    group_name = str(group.get("name") or group.get("groupName") or f"Group {group_sign or group_id}")

    return {
        "id": str(group_id),
        "name": group_name,
        "abbreviation": group_sign or str(group_id),
        "source": "sofascore",
        "standings": {
            "entries": [_normalize_sofascore_standings_entry(row) for row in group.get("rows") or []],
        },
    }


def _normalize_sofascore_standings_entry(row: dict[str, Any]) -> dict[str, Any]:
    team = row.get("team") or {}
    goals_for = _sofascore_int(row.get("scoresFor"))
    goals_against = _sofascore_int(row.get("scoresAgainst"))
    goal_diff = row.get("scoreDiffFormatted")
    if goal_diff in (None, "") and goals_for is not None and goals_against is not None:
        goal_diff = goals_for - goals_against

    return {
        "team": _normalize_sofascore_team(team),
        "stats": [
            _standings_stat_item("rank", row.get("position")),
            _standings_stat_item("points", row.get("points")),
            _standings_stat_item("gamesPlayed", row.get("matches")),
            _standings_stat_item("wins", row.get("wins")),
            _standings_stat_item("ties", row.get("draws")),
            _standings_stat_item("losses", row.get("losses")),
            _standings_stat_item("pointsFor", goals_for),
            _standings_stat_item("pointsAgainst", goals_against),
            _standings_stat_item("pointDifferential", goal_diff),
        ],
    }


def _standings_stat_item(name: str, value: Any) -> dict[str, Any]:
    display_value = "-" if value is None or value == "" else str(value)
    return {"name": name, "value": value, "displayValue": display_value}


def _sofascore_group_id(group_sign: str, index: int) -> int:
    if len(group_sign) == 1 and group_sign.isalpha():
        return ord(group_sign.upper()) - ord("A") + 1
    return index


def _sofascore_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_sofascore_world_cup_event(event: dict[str, Any]) -> bool:
    tournament = event.get("tournament") or {}
    unique_tournament = tournament.get("uniqueTournament") or {}
    season = event.get("season") or {}
    tournament_ids = {str(tournament.get("id") or ""), str(unique_tournament.get("id") or "")}
    season_id = str(season.get("id") or "")
    if str(SOFASCORE_WORLD_CUP_TOURNAMENT_ID) not in tournament_ids:
        return False
    return not season_id or season_id == str(SOFASCORE_WORLD_CUP_SEASON_ID)


def _apply_sofascore_live_statistics(event: dict[str, Any], statistics: list[dict[str, Any]]) -> None:
    home_stats, away_stats = _normalize_sofascore_live_team_statistics(statistics)
    if not home_stats and not away_stats:
        return

    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors") or []
    for competitor, stats in zip(competitors, (home_stats, away_stats), strict=False):
        if stats:
            competitor["statistics"] = stats


def _normalize_sofascore_live_team_statistics(statistics: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = _normalize_sofascore_match_statistics(statistics)
    home_stats: list[dict[str, Any]] = []
    away_stats: list[dict[str, Any]] = []
    for row in rows:
        stat_name = _SOFASCORE_LIVE_STAT_NAMES.get(row["key"])
        if not stat_name:
            continue
        home_stats.append(_live_stat_item(stat_name, row.get("home")))
        away_stats.append(_live_stat_item(stat_name, row.get("away")))
    return home_stats, away_stats


def _live_stat_item(name: str, value: Any) -> dict[str, Any]:
    display_value = "-" if value is None or value == "" else str(value)
    return {"name": name, "value": display_value, "displayValue": display_value}


_SOFASCORE_LIVE_STAT_NAMES = {
    "ballPossession": "possessionPct",
    "totalShotsOnGoal": "totalShots",
    "shotsOnGoal": "shotsOnTarget",
    "goalkeeperSaves": "saves",
    "cornerKicks": "wonCorners",
    "fouls": "foulsCommitted",
    "passes": "totalPasses",
    "accuratePasses": "accuratePasses",
    "accurateCross": "accurateCrosses",
    "totalTackle": "totalTackles",
    "yellowCards": "yellowCards",
    "redCards": "redCards",
}


def _normalize_sofascore_event(event: dict[str, Any]) -> dict[str, Any]:
    home_team = event.get("homeTeam") or {}
    away_team = event.get("awayTeam") or {}
    status = event.get("status") or {}
    state = _sofascore_status_state(status)
    completed = state == "post"
    home_score = (event.get("homeScore") or {}).get("current")
    away_score = (event.get("awayScore") or {}).get("current")
    venue = event.get("venue") or {}
    tournament = event.get("tournament") or {}
    timestamp = event.get("startTimestamp")

    return {
        "id": str(event.get("id") or ""),
        "date": _sofascore_event_date(timestamp),
        "name": event.get("slug") or event.get("customId") or "",
        "source": "sofascore",
        "status": {
            "displayClock": _sofascore_display_clock(event),
            "type": {
                "state": state,
                "completed": completed,
                "description": status.get("description") or status.get("type") or "",
                "detail": status.get("description") or status.get("type") or "",
                "shortDetail": _sofascore_short_status(status),
            },
        },
        "competitions": [
            {
                "id": str(event.get("id") or ""),
                "date": _sofascore_event_date(timestamp),
                "status": {
                    "displayClock": _sofascore_display_clock(event),
                    "type": {
                        "state": state,
                        "completed": completed,
                        "description": status.get("description") or status.get("type") or "",
                        "detail": status.get("description") or status.get("type") or "",
                        "shortDetail": _sofascore_short_status(status),
                    },
                },
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": _normalize_sofascore_team(home_team),
                        "score": _score_text(home_score),
                    },
                    {
                        "homeAway": "away",
                        "team": _normalize_sofascore_team(away_team),
                        "score": _score_text(away_score),
                    },
                ],
                "venue": _normalize_sofascore_venue(venue),
                "tournament": tournament,
            }
        ],
        "venue": _normalize_sofascore_venue(venue),
        "tournament": tournament,
    }


def _normalize_sofascore_team(team: dict[str, Any]) -> dict[str, Any]:
    name = team.get("name") or team.get("shortName") or team.get("slug") or ""
    return {
        "id": str(team.get("id") or ""),
        "displayName": str(name),
        "shortDisplayName": str(team.get("shortName") or name),
        "name": str(name),
        "abbreviation": str(team.get("nameCode") or ""),
        "country": team.get("country") or {},
        "source": "sofascore",
    }


def _normalize_sofascore_venue(venue: dict[str, Any]) -> dict[str, Any]:
    stadium = venue.get("stadium") or {}
    name = venue.get("name") or stadium.get("name")
    return {"fullName": name, "displayName": name} if name else {}


def _event_venue_name(event: dict[str, Any]) -> str:
    competition = (event.get("competitions") or [{}])[0]
    venue = competition.get("venue") or event.get("venue") or {}
    return str(venue.get("fullName") or venue.get("displayName") or "")


def _apply_event_venue(event: dict[str, Any], venue: dict[str, Any]) -> None:
    event["venue"] = venue
    competitions = event.get("competitions") or []
    if competitions:
        competitions[0]["venue"] = venue


def _sofascore_event_date(timestamp: Any) -> str:
    try:
        return datetime.fromtimestamp(float(timestamp), tz=ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError):
        return ""


def _sofascore_status_state(status: dict[str, Any]) -> str:
    status_type = str(status.get("type") or "").lower()
    if status_type in {"finished", "ended"} or status.get("code") == 100:
        return "post"
    if status_type in {"inprogress", "live", "halftime"}:
        return "in"
    return "pre"


def _sofascore_short_status(status: dict[str, Any]) -> str:
    if _sofascore_status_state(status) == "post":
        return "FT"
    return str(status.get("description") or status.get("type") or "")


def _sofascore_display_clock(event: dict[str, Any]) -> str:
    status = event.get("status") or {}
    if _sofascore_status_state(status) == "post":
        return "FT"
    if _sofascore_status_state(status) == "in":
        minute = _sofascore_match_minute(event)
        if minute:
            return f"{minute}'"
    return str(status.get("description") or status.get("type") or "")


def _sofascore_match_minute(event: dict[str, Any]) -> int | None:
    time_data = event.get("time") or {}
    initial = _sofascore_float(time_data.get("initial"))
    elapsed_seconds = initial if initial is not None else float(_sofascore_period_offset_seconds(event.get("status") or {}))
    period_start = _sofascore_float(time_data.get("currentPeriodStartTimestamp"))

    if period_start is not None:
        elapsed_seconds += max(0.0, datetime.now(tz=ZoneInfo("UTC")).timestamp() - period_start)

    if elapsed_seconds <= 0:
        return None
    return max(1, int(elapsed_seconds // 60) + 1)


def _sofascore_period_offset_seconds(status: dict[str, Any]) -> int:
    description = str(status.get("description") or status.get("type") or "").lower()
    if "2nd" in description or "second" in description:
        return 45 * 60
    if "extra" in description:
        return 90 * 60
    return 0


def _sofascore_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_text(score: Any) -> str:
    return "-" if score is None else str(score)


def _is_sofascore_finished_event(event: dict[str, Any]) -> bool:
    return _sofascore_status_state(event.get("status") or {}) == "post"


def _select_sofascore_team_statistics_season(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    tournaments = data.get("uniqueTournamentSeasons") or []
    types_map = data.get("typesMap") or {}
    candidates: list[tuple[int, dict[str, Any], dict[str, Any]]] = []

    for item in tournaments:
        if not isinstance(item, dict):
            continue
        tournament = item.get("uniqueTournament") or {}
        tournament_id = str(tournament.get("id", ""))
        for season in item.get("seasons") or []:
            if not isinstance(season, dict):
                continue
            season_id = str(season.get("id", ""))
            if not _sofascore_has_team_statistics(types_map, tournament_id, season_id):
                continue
            candidates.append((_sofascore_statistics_season_priority(tournament, season), tournament, season))

    if not candidates:
        return None
    _, tournament, season = min(candidates, key=lambda candidate: candidate[0])
    return tournament, season


def _sofascore_has_team_statistics(types_map: Any, tournament_id: str, season_id: str) -> bool:
    if not isinstance(types_map, dict):
        return True
    tournament_types = types_map.get(tournament_id)
    if not isinstance(tournament_types, dict):
        return False
    stat_types = tournament_types.get(season_id)
    return isinstance(stat_types, list) and "overall" in stat_types


def _sofascore_statistics_season_priority(tournament: dict[str, Any], season: dict[str, Any]) -> int:
    tournament_id = str(tournament.get("id", ""))
    season_id = str(season.get("id", ""))
    year = str(season.get("year") or "")
    if tournament_id == str(SOFASCORE_WORLD_CUP_TOURNAMENT_ID) and season_id == str(SOFASCORE_WORLD_CUP_SEASON_ID):
        return 0
    if tournament_id == str(SOFASCORE_WORLD_CUP_TOURNAMENT_ID) and year == str(WORLD_CUP_SEASON):
        return 1
    if year == str(WORLD_CUP_SEASON):
        return 2
    try:
        return 10_000 - int(year)
    except ValueError:
        return 10_000


def _event_date_value(event: dict[str, Any]) -> str:
    competition = (event.get("competitions") or [{}])[0]
    return str(event.get("date") or competition.get("date") or "")


def _normalize_sofascore_incidents(
    event: dict[str, Any],
    incidents: list[dict[str, Any]],
    *,
    reversed_match: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    goals: list[dict[str, Any]] = []
    disallowed_goals: list[dict[str, Any]] = []
    penalties: list[dict[str, Any]] = []
    red_cards: list[dict[str, Any]] = []
    for incident in incidents:
        incident_type = str(_incident_value(incident, "type", "incidentType", "incident_type") or "")
        if incident_type == "goal":
            goals.append(_normalize_sofascore_goal(event, incident, reversed_match))
        elif _is_sofascore_disallowed_goal(incident_type, incident):
            disallowed_goals.append(_normalize_sofascore_disallowed_goal(event, incident, reversed_match))
        elif _is_sofascore_penalty(incident_type, incident):
            penalties.append(_normalize_sofascore_penalty(event, incident, reversed_match))
        elif incident_type == "card" and _is_sofascore_red_card(incident):
            red_cards.append(_normalize_sofascore_red_card(event, incident, reversed_match))

    return {
        "goals": sorted(goals, key=_goal_clock_sort_key),
        "disallowedGoals": sorted(disallowed_goals, key=_goal_clock_sort_key),
        "penalties": sorted(penalties, key=_goal_clock_sort_key),
        "redCards": sorted(red_cards, key=_goal_clock_sort_key),
    }


def _normalize_sofascore_goal(
    event: dict[str, Any],
    incident: dict[str, Any],
    reversed_match: bool,
) -> dict[str, Any]:
    detail = _sofascore_incident_detail(incident)
    is_penalty = "penalty" in detail
    is_own_goal = "own" in detail
    text = "Penalty Kick" if is_penalty else "Own Goal" if is_own_goal else "Goal"
    player = _sofascore_player(incident)
    return {
        "id": _sofascore_incident_id(incident, "goal"),
        "source": "sofascore",
        "scoringPlay": True,
        "shootout": False,
        "team": _sofascore_incident_team(event, incident, reversed_match),
        "clock": _sofascore_incident_clock(incident),
        "type": {"id": detail or "goal", "type": "goal", "text": text},
        "scoreValue": 1,
        "scoreAfter": _sofascore_score_after(incident, reversed_match),
        "athletesInvolved": [player] if player else [],
        "text": text,
        "ownGoal": is_own_goal,
    }


def _normalize_sofascore_disallowed_goal(
    event: dict[str, Any],
    incident: dict[str, Any],
    reversed_match: bool,
) -> dict[str, Any]:
    player = _sofascore_player(incident)
    return {
        "id": _sofascore_incident_id(incident, "disallowed-goal"),
        "source": "sofascore",
        "disallowedGoal": True,
        "shootout": False,
        "team": _sofascore_incident_team(event, incident, reversed_match),
        "clock": _sofascore_incident_clock(incident),
        "type": {"id": "goalNotAwarded", "type": "varDecision", "text": "Goal disallowed"},
        "athletesInvolved": [player] if player else [],
        "text": "Goal disallowed after VAR review",
    }


def _normalize_sofascore_red_card(
    event: dict[str, Any],
    incident: dict[str, Any],
    reversed_match: bool,
) -> dict[str, Any]:
    detail = _sofascore_incident_detail(incident)
    text = "Second Yellow" if "yellow" in detail else "Red Card"
    return {
        "id": _sofascore_incident_id(incident, "card"),
        "source": "sofascore",
        "redCard": True,
        "athlete": _sofascore_player(incident),
        "clock": _sofascore_incident_clock(incident),
        "team": _sofascore_incident_team(event, incident, reversed_match),
        "type": {"id": detail or "red", "type": "card", "text": text},
        "text": text,
    }


def _normalize_sofascore_penalty(
    event: dict[str, Any],
    incident: dict[str, Any],
    reversed_match: bool,
) -> dict[str, Any]:
    text = _sofascore_penalty_text(incident)
    player = _sofascore_player(incident)
    return {
        "id": _sofascore_incident_id(incident, "penalty"),
        "source": "sofascore",
        "shootout": False,
        "team": _sofascore_incident_team(event, incident, reversed_match),
        "clock": _sofascore_incident_clock(incident),
        "type": {"id": "penalty", "type": "penalty", "text": "Penalty"},
        "athletesInvolved": [player] if player else [],
        "text": text,
    }


def _is_sofascore_penalty(incident_type: str, incident: dict[str, Any]) -> bool:
    normalized_type = re.sub(r"[^a-z]", "", incident_type.lower())
    detail = _sofascore_incident_detail(incident)
    if normalized_type == "ingamepenalty":
        return True
    return normalized_type == "vardecision" and detail in {"penaltyawarded", "penaltygiven"}


def _is_sofascore_disallowed_goal(incident_type: str, incident: dict[str, Any]) -> bool:
    normalized_type = re.sub(r"[^a-z]", "", incident_type.lower())
    return normalized_type == "vardecision" and _sofascore_incident_detail(incident) in {
        "goalnotawarded",
        "goaldisallowed",
    }


def _sofascore_penalty_text(incident: dict[str, Any]) -> str:
    reason = _incident_value(incident, "reason", "description")
    if reason:
        return str(reason)
    detail = _sofascore_incident_detail(incident)
    if detail == "penaltyawarded":
        return "Penalty awarded after VAR review"
    return "Penalty awarded"


def _is_sofascore_red_card(incident: dict[str, Any]) -> bool:
    detail = _sofascore_incident_detail(incident)
    return detail in {"red", "redcard", "yellowred", "secondyellow", "secondyellowcard"}


def _sofascore_incident_detail(incident: dict[str, Any]) -> str:
    raw_detail = _incident_value(incident, "incidentClass", "incident_class", "details", "detail")
    return re.sub(r"[^a-z]", "", str(raw_detail or "").lower())


def _sofascore_incident_id(incident: dict[str, Any], prefix: str) -> str:
    incident_id = _incident_value(incident, "id")
    if incident_id is not None:
        return f"sofascore:{incident_id}"
    player = _sofascore_player(incident) or {}
    clock = _sofascore_incident_clock(incident)
    return ":".join(
        [
            "sofascore",
            prefix,
            str(clock.get("displayValue", "")),
            str(player.get("id") or player.get("displayName") or ""),
        ]
    )


def _sofascore_incident_clock(incident: dict[str, Any]) -> dict[str, Any]:
    seconds = _incident_int_value(incident, "timeInSeconds", "time_in_seconds", "timeSeconds")
    minute = _incident_int_value(incident, "time", "minute")
    added_time = _incident_int_value(incident, "addedTime", "added_time")
    return {
        "value": minute,
        "seconds": seconds,
        "displayValue": _sofascore_display_minute(minute, added_time),
    }


def _sofascore_display_minute(minute: int | None, added_time: int | None) -> str:
    if minute is None:
        return ""
    if added_time and added_time > 0:
        return f"{minute}'+{added_time}'"
    return f"{minute}'"


def _sofascore_score_after(incident: dict[str, Any], reversed_match: bool) -> str:
    home_score = _incident_value(incident, "homeScore", "home_score")
    away_score = _incident_value(incident, "awayScore", "away_score")
    if home_score is None or away_score is None:
        return ""
    if reversed_match:
        home_score, away_score = away_score, home_score
    return f"{home_score}:{away_score}"


def _sofascore_player(incident: dict[str, Any]) -> dict[str, Any]:
    player = _incident_value(incident, "player")
    if not isinstance(player, dict):
        player = {}
    player_name = (
        player.get("name")
        or player.get("shortName")
        or player.get("slug")
        or _incident_value(incident, "playerName", "player_name")
    )
    if not player and not player_name:
        return {}
    return {
        "id": str(player.get("id") or ""),
        "displayName": str(player_name or ""),
        "fullName": str(player.get("name") or player_name or ""),
    }


def _sofascore_incident_team(
    event: dict[str, Any],
    incident: dict[str, Any],
    reversed_match: bool,
) -> dict[str, Any]:
    is_home = _incident_bool_value(incident, "isHome", "is_home")
    if is_home is None:
        return {}
    side = "home" if is_home else "away"
    if reversed_match:
        side = "away" if side == "home" else "home"
    return _event_team_by_side(event, side) or {}


def _event_team_by_side(event: dict[str, Any], side: str) -> dict[str, Any] | None:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    for competitor in competitors:
        if competitor.get("homeAway") == side:
            return competitor.get("team") or {}
    index = 0 if side == "home" else 1
    if index < len(competitors):
        return competitors[index].get("team") or {}
    return None


def _goal_clock_sort_key(detail: dict[str, Any]) -> float:
    clock = detail.get("clock") or {}
    try:
        return float(clock.get("seconds") or clock.get("value") or 0)
    except (TypeError, ValueError):
        return 0.0


def _incident_value(incident: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in incident:
            return incident[key]
    return None


def _incident_int_value(incident: dict[str, Any], *keys: str) -> int | None:
    value = _incident_value(incident, *keys)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _incident_bool_value(incident: dict[str, Any], *keys: str) -> bool | None:
    value = _incident_value(incident, *keys)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _normalize_sofascore_player_ratings(
    lineups: dict[str, Any],
    *,
    reversed_match: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    ratings = {"home": [], "away": []}
    if not isinstance(lineups, dict):
        return ratings

    for sofa_side in ("home", "away"):
        side = _mapped_side(sofa_side, reversed_match)
        team_lineup = lineups.get(sofa_side) or {}
        players = team_lineup.get("players") or []
        if not isinstance(players, list):
            continue
        for item in players:
            rating = _player_rating_value(item)
            if rating is None:
                continue
            player = item.get("player") or {}
            player_name = player.get("name") or player.get("shortName") or item.get("playerName")
            if not player_name:
                continue
            ratings[side].append(
                {
                    "id": str(player.get("id") or ""),
                    "name": str(player_name),
                    "shirtNumber": item.get("shirtNumber") or item.get("jerseyNumber"),
                    "position": item.get("position") or player.get("position"),
                    "substitute": item.get("substitute") is True,
                    "rating": rating,
                }
            )

    for side in ratings:
        ratings[side].sort(key=lambda player: float(player["rating"]), reverse=True)
    return ratings


def _player_rating_value(item: dict[str, Any]) -> float | None:
    statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
    value = statistics.get("rating") or item.get("rating")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_sofascore_match_statistics(
    statistics: list[dict[str, Any]],
    *,
    reversed_match: bool = False,
) -> list[dict[str, str]]:
    period = next(
        (item for item in statistics if str(item.get("period") or "").upper() == "ALL"),
        statistics[0] if statistics else {},
    )
    groups = period.get("groups") or []
    if not isinstance(groups, list):
        return []

    rows_by_key: dict[str, dict[str, str]] = {}
    wanted_keys = {
        "ballPossession",
        "expectedGoals",
        "bigChanceCreated",
        "totalShotsOnGoal",
        "shotsOnGoal",
        "goalkeeperSaves",
        "cornerKicks",
        "fouls",
        "passes",
        "accuratePasses",
        "accurateCross",
        "totalTackle",
        "finalThirdEntries",
        "accurateLongBalls",
        "interceptionWon",
        "ballRecovery",
        "totalClearance",
        "yellowCards",
        "redCards",
    }
    for group in groups:
        items = group.get("statisticsItems") or []
        if not isinstance(items, list):
            continue
        for item in items:
            key = str(item.get("key") or "")
            if key not in wanted_keys or key in rows_by_key:
                continue
            home = item.get("home")
            away = item.get("away")
            if home is None and away is None:
                continue
            if reversed_match:
                home, away = away, home
            rows_by_key[key] = {
                "key": key,
                "name": str(item.get("name") or key),
                "home": str(home) if home is not None else "-",
                "away": str(away) if away is not None else "-",
            }

    order = [
        "ballPossession",
        "expectedGoals",
        "bigChanceCreated",
        "totalShotsOnGoal",
        "shotsOnGoal",
        "goalkeeperSaves",
        "cornerKicks",
        "fouls",
        "passes",
        "accuratePasses",
        "accurateCross",
        "totalTackle",
        "finalThirdEntries",
        "accurateLongBalls",
        "interceptionWon",
        "ballRecovery",
        "totalClearance",
        "yellowCards",
        "redCards",
    ]
    return [rows_by_key[key] for key in order if key in rows_by_key]


def _mapped_side(side: str, reversed_match: bool) -> str:
    if not reversed_match:
        return side
    return "away" if side == "home" else "home"
