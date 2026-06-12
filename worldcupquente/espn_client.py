"""Minimal async client for ESPN public endpoints used by the bot."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from worldcupquente.config import Settings

logger = logging.getLogger(__name__)


class ESPNClient:
    site_base_url = "https://site.api.espn.com"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.site_base_url}{path}"
        headers = {"User-Agent": self.settings.espn_user_agent}
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.settings.espn_timeout, headers=headers) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                logger.warning("ESPN request failed", extra={"url": url, "attempt": attempt + 1})
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))

        raise RuntimeError(f"ESPN request failed: {url}") from last_error

    async def get_scoreboard(self, sport: str, league: str, date: str, limit: int = 100) -> dict[str, Any]:
        return await self.get_json(
            f"/apis/site/v2/sports/{sport}/{league}/scoreboard",
            params={"dates": date, "limit": limit},
        )

    async def get_summary(self, sport: str, league: str, event_id: str) -> dict[str, Any]:
        return await self.get_json(
            f"/apis/site/v2/sports/{sport}/{league}/summary",
            params={"event": event_id},
        )

    async def get_teams(self, sport: str, league: str, limit: int = 100) -> dict[str, Any]:
        return await self.get_json(
            f"/apis/site/v2/sports/{sport}/{league}/teams",
            params={"limit": limit},
        )

    async def get_team_roster(self, sport: str, league: str, team_id: str) -> dict[str, Any]:
        return await self.get_json(f"/apis/site/v2/sports/{sport}/{league}/teams/{team_id}/roster")

    async def get_standings(self, sport: str, league: str, season: int) -> dict[str, Any]:
        return await self.get_json(
            f"/apis/v2/sports/{sport}/{league}/standings",
            params={"season": season},
        )
