"""Minimal async client for SofaScore public endpoints used as enrichment data."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from curl_cffi import requests

logger = logging.getLogger(__name__)


class SofaScoreClient:
    base_url = "https://api.sofascore.com/api/v1"

    def __init__(self, timeout: float, user_agent: str) -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    async def get_json(self, path: str, *, quiet_statuses: tuple[int, ...] = ()) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Referer": "https://www.sofascore.com/",
            "x-requested-with": "XMLHttpRequest",
            "User-Agent": self.user_agent,
        }
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                async with requests.AsyncSession(impersonate="chrome", timeout=self.timeout) as client:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    return response.json()
            except requests.errors.RequestsError as exc:
                last_error = exc
                status_code = getattr(exc.response, "status_code", 0) if hasattr(exc, "response") else 0
                error_name = f"{status_code}" if status_code else type(exc).__name__
                if status_code not in quiet_statuses:
                    logger.warning(
                        f"SofaScore request failed ({error_name})",
                        extra={"url": url, "attempt": attempt + 1},
                    )
                if status_code in (401, 403, 404):
                    break
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
            except ValueError as exc:
                last_error = exc
                logger.warning(f"SofaScore request failed ({type(exc).__name__})", extra={"url": url, "attempt": attempt + 1})
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))

        raise RuntimeError(f"SofaScore request failed: {url}") from last_error

    async def get_world_cup_teams(self, unique_tournament_id: int | str, season_id: int | str) -> list[dict[str, Any]]:
        try:
            data = await self.get_json(f"/unique-tournament/{unique_tournament_id}/season/{season_id}/teams")
        except RuntimeError:
            return []
        teams = data.get("teams", [])
        return teams if isinstance(teams, list) else []

    async def get_tournament_standings(self, unique_tournament_id: int | str, season_id: int | str) -> list[dict[str, Any]]:
        try:
            data = await self.get_json(f"/unique-tournament/{unique_tournament_id}/season/{season_id}/standings/total")
        except RuntimeError:
            return []
        standings = data.get("standings", [])
        return standings if isinstance(standings, list) else []

    async def get_cup_trees(self, unique_tournament_id: int | str, season_id: int | str) -> list[dict[str, Any]]:
        try:
            data = await self.get_json(
                f"/unique-tournament/{unique_tournament_id}/season/{season_id}/cuptrees"
            )
        except RuntimeError:
            return []
        cup_trees = data.get("cupTrees", [])
        return cup_trees if isinstance(cup_trees, list) else []

    async def get_tournament_events(
        self,
        unique_tournament_id: int | str,
        season_id: int | str,
        direction: str,
        page: int = 0,
        suppress_errors: bool = True,
    ) -> dict[str, Any]:
        if direction not in {"last", "next"}:
            return {"events": [], "hasNextPage": False}
        try:
            data = await self.get_json(
                f"/unique-tournament/{unique_tournament_id}/season/{season_id}/events/{direction}/{page}",
                quiet_statuses=(404,),
            )
        except RuntimeError:
            if not suppress_errors:
                raise
            return {"events": [], "hasNextPage": False}
        events = data.get("events", [])
        return {
            "events": events if isinstance(events, list) else [],
            "hasNextPage": data.get("hasNextPage") is True,
        }

    async def get_event(self, event_id: int | str, suppress_errors: bool = True) -> dict[str, Any]:
        try:
            data = await self.get_json(f"/event/{event_id}")
        except RuntimeError:
            if not suppress_errors:
                raise
            return {}
        event = data.get("event", data)
        return event if isinstance(event, dict) else {}

    async def get_team_profile(self, team_id: int | str) -> dict[str, Any]:
        try:
            return await self.get_json(f"/team/{team_id}")
        except RuntimeError:
            return {}

    async def get_team_players(self, team_id: int | str) -> list[dict[str, Any]]:
        try:
            data = await self.get_json(f"/team/{team_id}/players")
        except RuntimeError:
            return []
        players = data.get("players", [])
        return players if isinstance(players, list) else []

    async def get_team_events(self, team_id: int | str, direction: str, page: int = 0) -> list[dict[str, Any]]:
        if direction not in {"last", "next"}:
            return []
        try:
            data = await self.get_json(f"/team/{team_id}/events/{direction}/{page}")
        except RuntimeError:
            return []
        events = data.get("events", [])
        return events if isinstance(events, list) else []

    async def get_team_achievements(self, team_id: int | str) -> dict[str, Any]:
        try:
            return await self.get_json(f"/team/{team_id}/achievements")
        except RuntimeError:
            return {}

    async def get_team_statistics_seasons(self, team_id: int | str) -> dict[str, Any]:
        try:
            return await self.get_json(f"/team/{team_id}/team-statistics/seasons")
        except RuntimeError:
            return {}

    async def get_team_statistics(
        self,
        team_id: int | str,
        unique_tournament_id: int | str,
        season_id: int | str,
        statistics_type: str = "overall",
    ) -> dict[str, Any]:
        try:
            return await self.get_json(
                f"/team/{team_id}/unique-tournament/{unique_tournament_id}/season/{season_id}/statistics/{statistics_type}",
                quiet_statuses=(404,),
            )
        except RuntimeError:
            return {}

    async def get_match_incidents(self, event_id: int | str) -> list[dict[str, Any]]:
        try:
            data = await self.get_json(f"/event/{event_id}/incidents", quiet_statuses=(404,))
        except RuntimeError:
            return []
        incidents = data.get("incidents", [])
        return incidents if isinstance(incidents, list) else []

    async def get_match_lineups(self, event_id: int | str) -> dict[str, Any]:
        try:
            return await self.get_json(f"/event/{event_id}/lineups", quiet_statuses=(404,))
        except RuntimeError:
            return {}

    async def get_match_statistics(self, event_id: int | str) -> list[dict[str, Any]]:
        try:
            data = await self.get_json(f"/event/{event_id}/statistics", quiet_statuses=(404,))
        except RuntimeError:
            return []
        statistics = data.get("statistics", [])
        return statistics if isinstance(statistics, list) else []

    async def get_win_probability(self, event_id: int | str) -> dict[str, int] | None:
        try:
            data = await self.get_json(
                f"/event/{event_id}/win-probability",
                quiet_statuses=(404,),
            )
        except RuntimeError:
            data = {}
        probabilities = data.get("winProbability") or {}
        normalized = normalize_win_probability(probabilities)
        if normalized is not None:
            return normalized
        return await self.get_odds_win_probability(event_id)

    async def get_odds_win_probability(self, event_id: int | str) -> dict[str, int] | None:
        try:
            data = await self.get_json(f"/event/{event_id}/odds/1/all", quiet_statuses=(404,))
        except RuntimeError:
            return None
        return normalize_odds_win_probability(data)

    async def get_player_detail(self, player_id: int | str) -> dict[str, Any]:
        try:
            data = await self.get_json(f"/player/{player_id}", quiet_statuses=(404,))
        except RuntimeError:
            return {}
        player = data.get("player", data)
        return player if isinstance(player, dict) else {}

    async def get_player_image(self, player_id: int | str) -> bytes | None:
        url = f"{self.base_url}/player/{player_id}/image"
        headers = {
            "Accept": "image/*",
            "Referer": "https://www.sofascore.com/",
            "User-Agent": self.user_agent,
        }
        try:
            async with requests.AsyncSession(impersonate="chrome", timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    return None
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    return None
                content = bytes(response.content or b"")
                return content or None
        except requests.errors.RequestsError:
            return None


def normalize_win_probability(data: dict[str, Any]) -> dict[str, int] | None:
    values = {
        "home": _float_value(data.get("homeWin")),
        "draw": _float_value(data.get("draw")),
        "away": _float_value(data.get("awayWin")),
    }
    if any(value is None for value in values.values()):
        return None

    probabilities = {key: float(value) for key, value in values.items() if value is not None}
    if max(probabilities.values()) <= 1:
        probabilities = {key: value * 100 for key, value in probabilities.items()}
    return _normalize_percentages(probabilities)


def normalize_odds_win_probability(data: dict[str, Any]) -> dict[str, int] | None:
    markets = data.get("markets")
    if not isinstance(markets, list):
        return None

    sorted_markets = sorted(
        (market for market in markets if isinstance(market, dict)),
        key=lambda market: not bool(market.get("isLive")),
    )
    for market in sorted_markets:
        if market.get("marketGroup") != "1X2" or market.get("suspended"):
            continue
        probabilities = _probabilities_from_1x2_choices(market.get("choices"))
        if probabilities is not None:
            return _normalize_percentages(probabilities)
    return None


def _probabilities_from_1x2_choices(choices: Any) -> dict[str, float] | None:
    if not isinstance(choices, list):
        return None

    by_name = {
        str(choice.get("name")): choice
        for choice in choices
        if isinstance(choice, dict) and choice.get("name") is not None
    }
    values = {
        "home": _choice_implied_probability(by_name.get("1")),
        "draw": _choice_implied_probability(by_name.get("X")),
        "away": _choice_implied_probability(by_name.get("2")),
    }
    if any(value is None for value in values.values()):
        return None
    return {key: value for key, value in values.items() if value is not None}


def _choice_implied_probability(choice: dict[str, Any] | None) -> float | None:
    if not choice:
        return None

    fractional = choice.get("fractionalValue")
    probability = _fractional_implied_probability(fractional)
    if probability is not None:
        return probability

    decimal = _float_value(choice.get("decimalValue"))
    if decimal is not None and decimal > 1:
        return 1 / decimal

    american = _float_value(choice.get("americanValue"))
    if american is None:
        return None
    if american > 0:
        return 100 / (american + 100)
    if american < 0:
        return abs(american) / (abs(american) + 100)
    return None


def _fractional_implied_probability(value: Any) -> float | None:
    if not isinstance(value, str) or "/" not in value:
        return None
    numerator_text, denominator_text = value.split("/", 1)
    numerator = _float_value(numerator_text)
    denominator = _float_value(denominator_text)
    if numerator is None or denominator is None or denominator <= 0:
        return None
    decimal = (numerator / denominator) + 1
    if decimal <= 1:
        return None
    return 1 / decimal


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_percentages(probabilities: dict[str, float]) -> dict[str, int] | None:
    total = sum(probabilities.values())
    if total <= 0:
        return None

    normalized = {side: (probability / total) * 100 for side, probability in probabilities.items()}
    rounded = {side: int(value) for side, value in normalized.items()}
    remaining = 100 - sum(rounded.values())

    remainders = sorted(
        normalized,
        key=lambda side: normalized[side] - rounded[side],
        reverse=True,
    )
    for side in remainders[:remaining]:
        rounded[side] += 1
    return rounded
