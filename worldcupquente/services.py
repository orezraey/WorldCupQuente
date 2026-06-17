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
    event_state,
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
SOFASCORE_INCIDENTS_CACHE_SECONDS = 15
SOFASCORE_LINEUPS_CACHE_SECONDS = 60 * 5
SOFASCORE_STATISTICS_CACHE_SECONDS = 60 * 5
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
        hydrated = await self.enrich_events_sofascore_incidents(hydrated)
        return await self.enrich_events_win_probability(hydrated)

    async def enrich_events_sofascore_incidents(
        self,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return list(
            await asyncio.gather(
                *(self.enrich_event_sofascore_incidents(event) for event in events),
            )
        )

    async def enrich_event_sofascore_incidents(self, event: dict[str, Any]) -> dict[str, Any]:
        if event.get("sofascoreIncidents"):
            return event

        try:
            mapping = await self._sofascore_event_mapping(event)
            if mapping is None:
                return event

            incidents = await self._sofascore_match_incidents(mapping["event_id"])
            normalized = _normalize_sofascore_incidents(
                event,
                incidents,
                reversed_match=bool(mapping.get("reversed")),
            )
            if normalized["goals"] or normalized["disallowedGoals"] or normalized["penalties"] or normalized["redCards"]:
                event["sofascoreIncidents"] = normalized
        except Exception as e:
            logger.warning(f"Failed to enrich event with SofaScore incidents: {e}")
        return event

    async def enrich_event_sofascore_post_match(self, event: dict[str, Any]) -> dict[str, Any]:
        if event.get("sofascorePlayerRatings") and event.get("sofascoreStatistics"):
            return event

        try:
            mapping = await self._sofascore_event_mapping(event)
            if mapping is None:
                return event

            lineups, statistics = await asyncio.gather(
                self._sofascore_match_lineups(mapping["event_id"]),
                self._sofascore_match_statistics(mapping["event_id"]),
            )
            reversed_match = bool(mapping.get("reversed"))
            ratings = _normalize_sofascore_player_ratings(lineups, reversed_match=reversed_match)
            if ratings["home"] or ratings["away"]:
                event["sofascorePlayerRatings"] = ratings

            normalized_statistics = _normalize_sofascore_match_statistics(
                statistics,
                reversed_match=reversed_match,
            )
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
            mapping = await self._sofascore_event_mapping(event)
            if mapping is None:
                return event

            lineups = await self._sofascore_match_lineups(mapping["event_id"])
            ratings = _normalize_sofascore_player_ratings(
                lineups,
                reversed_match=bool(mapping.get("reversed")),
            )
            if ratings["home"] or ratings["away"]:
                event["sofascorePlayerRatings"] = ratings
        except Exception as e:
            logger.warning(f"Failed to enrich event with SofaScore player ratings: {e}")
        return event

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

    async def _sofascore_match_incidents(self, event_id: int | str) -> list[dict[str, Any]]:
        cache_key = f"sofascore:incidents:{event_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        incidents = await self.sofascore_client.get_match_incidents(event_id)
        self.cache.set(cache_key, incidents, SOFASCORE_INCIDENTS_CACHE_SECONDS)
        return incidents

    async def _sofascore_match_lineups(self, event_id: int | str) -> dict[str, Any]:
        cache_key = f"sofascore:lineups:{event_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        lineups = await self.sofascore_client.get_match_lineups(event_id)
        self.cache.set(cache_key, lineups, SOFASCORE_LINEUPS_CACHE_SECONDS)
        return lineups

    async def _sofascore_match_statistics(self, event_id: int | str) -> list[dict[str, Any]]:
        cache_key = f"sofascore:statistics:{event_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        statistics = await self.sofascore_client.get_match_statistics(event_id)
        self.cache.set(cache_key, statistics, SOFASCORE_STATISTICS_CACHE_SECONDS)
        return statistics

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

    async def get_finished_events(self) -> list[dict[str, Any]]:
        events = await self.get_schedule_events()
        return sorted(
            (event for event in events if _is_finished_event(event)),
            key=lambda event: _event_date_value(event),
            reverse=True,
        )

    async def get_finished_event_details(self, event_id: str) -> dict[str, Any] | None:
        fallback = next(
            (event for event in await self.get_schedule_events() if str(event.get("id", "")) == str(event_id)),
            None,
        )
        try:
            summary = await self.get_event_summary(event_id)
        except Exception:
            if fallback is None:
                return None
            event = fallback
        else:
            event = event_from_summary(summary, fallback_event=fallback)
        event = await self.enrich_event_sofascore_incidents(event)
        event = await self.enrich_event_sofascore_post_match(event)
        return event

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


def _is_finished_event(event: dict[str, Any]) -> bool:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    return event_state(event) == "post" or status_type.get("completed") is True


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
    return _espn_team_by_side(event, side) or {}


def _espn_team_by_side(event: dict[str, Any], side: str) -> dict[str, Any] | None:
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
        "yellowCards",
        "redCards",
    ]
    return [rows_by_key[key] for key in order if key in rows_by_key]


def _mapped_side(side: str, reversed_match: bool) -> str:
    if not reversed_match:
        return side
    return "away" if side == "home" else "home"
