"""Standings snapshots and update matching for live monitoring."""

from __future__ import annotations

import logging
from typing import Any

from telegram.ext import Application

from worldcupquente.live_events import _event_team_ids, _is_in_progress_event
from worldcupquente.services import WorldCupService

logger = logging.getLogger(__name__)

PENDING_FULL_TIME_STANDINGS_KEY = "live_pending_full_time_standings"
STANDINGS_SNAPSHOTS_KEY = "live_standings_snapshots"


def _standings_snapshots(application: Application) -> dict[str, dict[str, tuple[int, int, int, int]]]:
    return application.bot_data.setdefault(STANDINGS_SNAPSHOTS_KEY, {})


async def _remember_active_standings_snapshots(
    application: Application,
    status_events: list[dict[str, Any]],
    service: WorldCupService,
) -> None:
    active_events = [event for event in status_events if _is_in_progress_event(event)]
    if not active_events:
        return
    try:
        groups = await service.get_sofascore_standings_groups(use_cache=False)
    except Exception:
        logger.warning("Failed to fetch standings snapshots")
        return

    snapshots = _standings_snapshots(application)
    for event in active_events:
        event_id = str(event.get("id", ""))
        if not event_id or event_id in snapshots:
            continue
        group = _standings_group_from_groups(groups, event)
        records = _standings_total_records(group) if group is not None else {}
        if records:
            snapshots[event_id] = records


async def _updated_standings_group_for_event(
    service: WorldCupService,
    event: dict[str, Any],
    initial_records: dict[str, tuple[int, int, int, int]] | None = None,
) -> dict[str, Any] | None:
    group = await _standings_group_for_event(service, event)
    if group is None:
        return None
    if _standings_group_matches_event(group, event):
        return group
    if initial_records and _standings_group_matches_snapshot_update(group, event, initial_records):
        return group
    return None


async def _standings_group_for_event(
    service: WorldCupService,
    event: dict[str, Any],
) -> dict[str, Any] | None:
    team_ids = _event_team_ids(event)
    if not team_ids:
        return None
    try:
        groups = await service.get_sofascore_standings_groups(use_cache=False)
    except Exception:
        logger.warning("Failed to fetch standings for full-time notification")
        return None

    return _standings_group_from_groups(groups, event)


def _standings_group_from_groups(
    groups: list[dict[str, Any]],
    event: dict[str, Any],
) -> dict[str, Any] | None:
    team_ids = _event_team_ids(event)
    if not team_ids:
        return None

    for group in groups:
        group_team_ids = {
            str(((entry.get("team") or {}).get("id")) or "")
            for entry in (group.get("standings") or {}).get("entries", [])
        }
        if team_ids.issubset(group_team_ids):
            return group
    return None


def _standings_group_matches_event(group: dict[str, Any], event: dict[str, Any]) -> bool:
    event_records = _event_total_records(event)
    if not event_records:
        return False

    standings_records = _standings_total_records(group)
    return all(standings_records.get(team_id) == record for team_id, record in event_records.items())


def _standings_group_matches_snapshot_update(
    group: dict[str, Any],
    event: dict[str, Any],
    initial_records: dict[str, tuple[int, int, int, int]],
) -> bool:
    event_record_deltas = _event_record_deltas(event)
    if not event_record_deltas:
        return False

    standings_records = _standings_total_records(group)
    for team_id, delta in event_record_deltas.items():
        initial_record = initial_records.get(team_id)
        current_record = standings_records.get(team_id)
        if initial_record is None or current_record is None:
            return False
        expected_record = tuple(initial + added for initial, added in zip(initial_record, delta, strict=True))
        if current_record != expected_record:
            return False
    return True


def _event_record_deltas(event: dict[str, Any]) -> dict[str, tuple[int, int, int, int]]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    if len(competitors) != 2:
        return {}

    scores: list[tuple[str, int]] = []
    for competitor in competitors:
        team_id = str(((competitor.get("team") or {}).get("id")) or "")
        if not team_id:
            return {}
        try:
            score = int(competitor.get("score"))
        except (TypeError, ValueError):
            return {}
        scores.append((team_id, score))

    first_team_id, first_score = scores[0]
    second_team_id, second_score = scores[1]
    if first_score == second_score:
        return {
            first_team_id: (1, 0, 1, 0),
            second_team_id: (1, 0, 1, 0),
        }
    if first_score > second_score:
        return {
            first_team_id: (1, 1, 0, 0),
            second_team_id: (1, 0, 0, 1),
        }
    return {
        first_team_id: (1, 0, 0, 1),
        second_team_id: (1, 1, 0, 0),
    }


def _event_total_records(event: dict[str, Any]) -> dict[str, tuple[int, int, int, int]]:
    competition = (event.get("competitions") or [{}])[0]
    records: dict[str, tuple[int, int, int, int]] = {}
    for competitor in competition.get("competitors", []):
        team_id = str(((competitor.get("team") or {}).get("id")) or "")
        if not team_id:
            continue
        record = _competitor_total_record(competitor)
        if record is None:
            return {}
        records[team_id] = record
    return records


def _competitor_total_record(competitor: dict[str, Any]) -> tuple[int, int, int, int] | None:
    for record in competitor.get("records", []):
        record_type = str(record.get("type") or "").lower()
        record_name = str(record.get("name") or "").lower()
        record_abbreviation = str(record.get("abbreviation") or "").lower()
        if record_type != "total" and record_name != "all splits" and record_abbreviation != "total":
            continue
        return _parse_total_record(record.get("summary") or record.get("displayValue"))
    return None


def _parse_total_record(value: Any) -> tuple[int, int, int, int] | None:
    parts = str(value or "").split("-")
    if len(parts) != 3:
        return None
    try:
        wins, draws, losses = (int(part) for part in parts)
    except ValueError:
        return None
    return (wins + draws + losses, wins, draws, losses)


def _standings_total_records(group: dict[str, Any]) -> dict[str, tuple[int, int, int, int]]:
    records: dict[str, tuple[int, int, int, int]] = {}
    for entry in (group.get("standings") or {}).get("entries", []):
        team_id = str(((entry.get("team") or {}).get("id")) or "")
        if not team_id:
            continue
        stats = entry.get("stats", [])
        games_played = _standings_int_stat(stats, "gamesPlayed")
        wins = _standings_int_stat(stats, "wins")
        draws = _standings_int_stat(stats, "ties")
        losses = _standings_int_stat(stats, "losses")
        if None in (games_played, wins, draws, losses):
            continue
        records[team_id] = (games_played, wins, draws, losses)
    return records


def _standings_int_stat(stats: list[dict[str, Any]], name: str) -> int | None:
    for stat in stats:
        if stat.get("name") != name:
            continue
        value = stat.get("value")
        if value is None or value == "":
            value = stat.get("displayValue")
        try:
            return int(float(str(value).replace("+", "")))
        except (TypeError, ValueError):
            return None
    return None
