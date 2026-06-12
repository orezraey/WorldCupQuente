"""Match incidents extraction utilities for goals, penalties, and red cards."""

from __future__ import annotations

from typing import Any


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


def penalty_plays_from_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    plays: list[dict[str, Any]] = []
    plays.extend(_penalty_plays_from_details(event))
    plays.extend(
        play
        for play in event.get("scoringPlays", [])
        if play.get("shootout") is not True and _is_penalty_play(play)
    )
    plays.extend(_penalty_plays_from_commentary(event))
    return _dedupe_event_plays(plays)


def red_cards_from_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    red_cards: list[dict[str, Any]] = []
    red_cards.extend(_red_cards_from_details(event))
    red_cards.extend(_red_cards_from_commentary(event))
    if not red_cards:
        red_cards.extend(_red_cards_from_rosters(event))
    return _dedupe_player_events(red_cards)


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


def _penalty_plays_from_details(event: dict[str, Any]) -> list[dict[str, Any]]:
    competition = (event.get("competitions") or [{}])[0]
    plays: list[dict[str, Any]] = []
    for detail in competition.get("details", []):
        if detail.get("shootout") is True:
            continue
        if not _is_penalty_play(detail):
            continue
        plays.append(detail)
    return plays


def _penalty_plays_from_commentary(event: dict[str, Any]) -> list[dict[str, Any]]:
    plays: list[dict[str, Any]] = []
    for item in event.get("commentary", []):
        play = item.get("play") or {}
        if play.get("shootout") is True:
            continue
        if not _is_penalty_play(play, fallback_text=item.get("text")):
            continue
        plays.append(
            {
                "id": play.get("id") or f"commentary:{item.get('sequence', '')}",
                "clock": play.get("clock") or item.get("time") or {},
                "team": _team_from_commentary_play(event, play),
                "type": play.get("type") or {},
                "text": play.get("text") or item.get("text"),
                "athletesInvolved": [
                    participant.get("athlete") or {}
                    for participant in play.get("participants") or []
                    if participant.get("athlete")
                ],
            }
        )
    return plays


def _is_penalty_play(play: dict[str, Any], fallback_text: Any = None) -> bool:
    play_type = play.get("type") or {}
    text = " ".join(
        str(part or "")
        for part in [
            play_type.get("type"),
            play_type.get("text"),
            play.get("text"),
            fallback_text,
        ]
    ).lower()
    return "penalty" in text


def _red_cards_from_details(event: dict[str, Any]) -> list[dict[str, Any]]:
    competition = (event.get("competitions") or [{}])[0]
    cards: list[dict[str, Any]] = []
    for detail in competition.get("details", []):
        detail_type = detail.get("type") or {}
        type_text = f"{detail_type.get('type', '')} {detail_type.get('text', '')}".lower()
        if detail.get("redCard") is not True and "red" not in type_text:
            continue
        athletes = detail.get("athletesInvolved") or [
            participant.get("athlete") or {}
            for participant in detail.get("participants", [])
            if participant.get("athlete")
        ]
        cards.append(
            {
                "id": detail.get("id"),
                "athlete": athletes[0] if athletes else {},
                "clock": detail.get("clock") or {},
                "team": detail.get("team") or {},
                "type": detail_type,
                "text": detail.get("text"),
            }
        )
    return cards


def _red_cards_from_commentary(event: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for item in event.get("commentary", []):
        play = item.get("play") or {}
        play_type = play.get("type") or {}
        type_text = f"{play_type.get('type', '')} {play_type.get('text', '')}".lower()
        if "red" not in type_text or "card" not in type_text:
            continue
        participants = play.get("participants") or []
        athlete = (participants[0].get("athlete") if participants else {}) or {}
        cards.append(
            {
                "id": play.get("id") or f"commentary:{item.get('sequence', '')}",
                "athlete": athlete,
                "clock": play.get("clock") or item.get("time") or {},
                "team": _team_from_commentary_play(event, play),
                "type": play_type,
                "text": play.get("text") or item.get("text"),
            }
        )
    return cards


def _red_cards_from_rosters(event: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for roster in event.get("rosters", []):
        for player in roster.get("roster", []):
            if _player_stat_value(player, "redCards") <= 0:
                continue
            cards.append({"athlete": player.get("athlete") or {}, "clock": {}})
    return cards


def _player_stat_value(player: dict[str, Any], stat_name: str) -> float:
    for stat in player.get("stats", []):
        if stat.get("name") != stat_name:
            continue
        try:
            return float(stat.get("value") or stat.get("displayValue") or 0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _dedupe_event_plays(plays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for play in plays:
        clock = play.get("clock") or {}
        play_type = play.get("type") or {}
        key = (
            str(play.get("id") or ""),
            str((play.get("team") or {}).get("id") or ""),
            str(clock.get("value") or clock.get("displayValue") or ""),
            str(play.get("text") or play_type.get("text") or play_type.get("type") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(play)
    return deduped


def _dedupe_player_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_ids: set[tuple[str, str]] = set()
    seen_names: set[tuple[str, str]] = set()
    for event in events:
        athlete = event.get("athlete") or {}
        clock = event.get("clock") or {}
        athlete_id = str(athlete.get("id") or "")
        athlete_name = str(athlete.get("displayName") or athlete.get("fullName") or "")
        minute = str(clock.get("displayValue") or "")
        id_key = (athlete_id, minute)
        name_key = (athlete_name, minute)
        if (athlete_id and id_key in seen_ids) or (athlete_name and name_key in seen_names):
            continue
        if athlete_id:
            seen_ids.add(id_key)
        if athlete_name:
            seen_names.add(name_key)
        deduped.append(event)
    return deduped


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
