"""Incident collection and deduplication for live monitoring."""

from __future__ import annotations

from typing import Any, Protocol

from worldcupquente.event_incidents import (
    penalty_plays_from_event,
    red_cards_from_event,
    scoring_plays_from_event,
)
from worldcupquente.live_events import _is_full_time_event
from worldcupquente.notification_preferences import (
    GOAL_NOTIFICATION,
    PENALTY_NOTIFICATION,
    RED_CARD_NOTIFICATION,
)

DISALLOWED_GOAL_NOTIFICATION = "disallowed_goal"


class _IncidentState(Protocol):
    seen_goal_ids: set[str]
    seen_penalty_ids: set[str]
    seen_red_card_ids: set[str]
    score_snapshots: dict[str, tuple[int, ...]]
    is_bootstrapped: bool


def _collect_live_notifications(
    live_events: list[dict[str, Any]],
    state: _IncidentState,
) -> tuple[list[tuple[str, dict[str, Any], dict[str, Any]]], set[tuple[str, str, str]]]:
    notifications: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    scored_penalty_goal_keys: set[tuple[str, str, str]] = set()
    is_bootstrapped = state.is_bootstrapped
    seen_goal_ids = state.seen_goal_ids
    seen_penalty_ids = state.seen_penalty_ids
    seen_red_card_ids = state.seen_red_card_ids
    score_snapshots = state.score_snapshots

    for event in live_events:
        event_id = str(event.get("id", ""))
        current_score = _event_score_snapshot(event)
        previous_score = score_snapshots.get(event_id)
        score_regressed = (
            current_score is not None
            and previous_score is not None
            and _score_regressed(previous_score, current_score)
        )
        official_goals = _sofascore_goal_details(event)
        disallowed_goals = _sofascore_disallowed_goal_details(event)
        if _is_full_time_event(event):
            for detail in official_goals:
                _remember_goal(seen_goal_ids, event, detail)
        elif official_goals:
            for detail in official_goals:
                if _is_penalty_detail(detail):
                    scored_penalty_goal_keys.add(_play_match_key(event, detail))
                if _goal_already_seen(seen_goal_ids, event, detail):
                    continue
                _remember_goal(seen_goal_ids, event, detail)
                if is_bootstrapped:
                    notifications.append((GOAL_NOTIFICATION, event, detail))
        elif current_score is not None and previous_score is not None and not score_regressed:
            for detail in _score_change_details(event, previous_score, current_score):
                if _is_penalty_detail(detail):
                    scored_penalty_goal_keys.add(_play_match_key(event, detail))
                if _goal_already_seen(seen_goal_ids, event, detail):
                    continue
                _remember_goal(seen_goal_ids, event, detail)
                if is_bootstrapped:
                    notifications.append((GOAL_NOTIFICATION, event, detail))
        if score_regressed:
            _evict_reverted_goal_score_keys(seen_goal_ids, event, previous_score, current_score)
        if score_regressed and not disallowed_goals:
            previously_seen_goal_ids = set(seen_goal_ids)
            for detail in _score_regression_disallowed_goal_details(event, previous_score, current_score):
                if _disallowed_goal_already_seen(previously_seen_goal_ids, event, detail):
                    continue
                _remember_disallowed_goal(seen_goal_ids, event, detail)
                if is_bootstrapped:
                    notifications.append((DISALLOWED_GOAL_NOTIFICATION, event, detail))
        if current_score is not None:
            score_snapshots[event_id] = current_score

        for detail in disallowed_goals:
            if _disallowed_goal_already_seen(seen_goal_ids, event, detail):
                continue
            if _disallowed_goal_matches_confirmed(detail, official_goals):
                continue
            _remember_disallowed_goal(seen_goal_ids, event, detail)
            if is_bootstrapped:
                notifications.append((DISALLOWED_GOAL_NOTIFICATION, event, detail))

        for detail in penalty_plays_from_event(event):
            if _penalty_already_seen(seen_penalty_ids, event, detail):
                continue
            _remember_penalty(seen_penalty_ids, event, detail)
            if is_bootstrapped:
                notifications.append((PENALTY_NOTIFICATION, event, detail))

        for detail in red_cards_from_event(event):
            red_card_id = _live_event_id(RED_CARD_NOTIFICATION, event, detail)
            if red_card_id in seen_red_card_ids:
                continue
            seen_red_card_ids.add(red_card_id)
            if is_bootstrapped:
                notifications.append((RED_CARD_NOTIFICATION, event, detail))

    return notifications, scored_penalty_goal_keys


def _goal_id(event: dict[str, Any], detail: dict[str, Any]) -> str:
    athletes = detail.get("athletesInvolved") or [
        participant.get("athlete") or {}
        for participant in detail.get("participants", [])
        if participant.get("athlete")
    ]
    athlete_ids = ",".join(str(athlete.get("id", "")) for athlete in athletes)
    clock = detail.get("clock") or {}
    detail_type = detail.get("type") or {}
    team = detail.get("team") or {}
    return ":".join(
        [
            str(event.get("id", "")),
            str(detail.get("id", "")),
            str(team.get("id", "")),
            str(clock.get("value", "")),
            str(clock.get("displayValue", "")),
            athlete_ids,
            str(detail_type.get("id", "")),
            str(detail.get("scoreValue", "")),
            str(detail.get("scoreAfter", "")),
        ]
    )


def _goal_already_seen(
    seen_goal_ids: set[str],
    event: dict[str, Any],
    detail: dict[str, Any],
) -> bool:
    return any(goal_id in seen_goal_ids for goal_id in _goal_tracking_ids(event, detail))


def _remember_goal(
    seen_goal_ids: set[str],
    event: dict[str, Any],
    detail: dict[str, Any],
) -> None:
    seen_goal_ids.update(_goal_tracking_ids(event, detail))


def _evict_reverted_goal_score_keys(
    seen_goal_ids: set[str],
    event: dict[str, Any],
    previous_score: tuple[int, ...],
    current_score: tuple[int, ...],
) -> None:
    event_id = str(event.get("id", ""))
    if not event_id:
        return
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    for index, current in enumerate(current_score):
        previous = previous_score[index] if index < len(previous_score) else 0
        if previous <= current:
            continue
        team = (competitors[index].get("team") or {}) if index < len(competitors) else {}
        team_id = str(team.get("id", ""))
        for reverted_score in range(current + 1, previous + 1):
            score_after = list(previous_score)
            score_after[index] = reverted_score
            score_key = ":".join(str(score) for score in score_after)
            seen_goal_ids.discard(f"goal-score:{event_id}:{score_key}")
            if team_id:
                seen_goal_ids.discard(f"goal-score:{event_id}:{team_id}:{score_key}")


def _goal_tracking_ids(event: dict[str, Any], detail: dict[str, Any]) -> set[str]:
    ids = {_goal_id(event, detail)}
    event_id = str(event.get("id", ""))
    team_id = str((detail.get("team") or {}).get("id", ""))
    score_after = _goal_score_after_key(detail)
    if event_id and score_after:
        ids.add(f"goal-score:{event_id}:{score_after}")
    if event_id and team_id and score_after:
        ids.add(f"goal-score:{event_id}:{team_id}:{score_after}")

    clock = detail.get("clock") or {}
    minute = str(clock.get("value") or clock.get("displayValue") or "")
    scorer = _goal_scorer_key(detail)
    if event_id and team_id and minute and scorer:
        ids.add(f"goal-minute:{event_id}:{team_id}:{minute}:{scorer}")
    return ids


def _goal_score_after_key(detail: dict[str, Any]) -> str:
    score_after = detail.get("scoreAfter")
    if isinstance(score_after, str):
        return score_after.strip()
    if isinstance(score_after, (list, tuple)) and len(score_after) >= 2:
        return f"{score_after[0]}:{score_after[1]}"
    if isinstance(score_after, dict):
        home = _first_score_value(score_after, "home", "homeScore")
        away = _first_score_value(score_after, "away", "awayScore")
        if home is not None and away is not None:
            return f"{home}:{away}"
    return ""


def _first_score_value(score: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in score:
            return score[key]
    return None


def _goal_scorer_key(detail: dict[str, Any]) -> str:
    athletes = detail.get("athletesInvolved") or [
        participant.get("athlete") or {}
        for participant in detail.get("participants", [])
        if participant.get("athlete")
    ]
    scorer = (athletes or [{}])[0]
    return str(scorer.get("id") or scorer.get("displayName") or scorer.get("fullName") or "")


def _disallowed_goal_matches_confirmed(
    detail: dict[str, Any],
    official_goals: list[dict[str, Any]],
) -> bool:
    team_id = str((detail.get("team") or {}).get("id", ""))
    clock = detail.get("clock") or {}
    minute = str(clock.get("value") or clock.get("displayValue") or "")
    scorer = _goal_scorer_key(detail)
    if not (team_id and minute and scorer):
        return False
    for goal in official_goals:
        goal_team = str((goal.get("team") or {}).get("id", ""))
        goal_clock = goal.get("clock") or {}
        goal_minute = str(goal_clock.get("value") or goal_clock.get("displayValue") or "")
        goal_scorer = _goal_scorer_key(goal)
        if team_id == goal_team and minute == goal_minute and scorer == goal_scorer:
            return True
    return False


def _disallowed_goal_already_seen(
    seen_goal_ids: set[str],
    event: dict[str, Any],
    detail: dict[str, Any],
) -> bool:
    return any(goal_id in seen_goal_ids for goal_id in _disallowed_goal_tracking_ids(event, detail))


def _remember_disallowed_goal(
    seen_goal_ids: set[str],
    event: dict[str, Any],
    detail: dict[str, Any],
) -> None:
    seen_goal_ids.update(_disallowed_goal_tracking_ids(event, detail))


def _disallowed_goal_tracking_ids(event: dict[str, Any], detail: dict[str, Any]) -> set[str]:
    ids = {_live_event_id(DISALLOWED_GOAL_NOTIFICATION, event, detail)}
    event_id = str(event.get("id", ""))
    team_id = str((detail.get("team") or {}).get("id", ""))
    clock = detail.get("clock") or {}
    minute = _clock_minute_key(clock)
    scorer = _goal_scorer_key(detail)
    if event_id and team_id and minute:
        ids.add(f"disallowed-goal-minute:{event_id}:{team_id}:{minute}")
        if scorer:
            ids.add(f"disallowed-goal-minute:{event_id}:{team_id}:{minute}:{scorer}")
        # Fuzzy minute matching: if the minute is within a small window,
        # consider it the same event to avoid duplicate notifications
        # caused by API minute fluctuations (e.g., 8' vs 9').
        try:
            numeric_minute = int(minute)
            for offset in (-1, 1):
                ids.add(f"disallowed-goal-minute:{event_id}:{team_id}:{numeric_minute + offset}")
        except (TypeError, ValueError):
            pass
    score_before = detail.get("scoreBefore")
    score_after = detail.get("scoreAfter")
    if event_id and team_id and score_before and score_after:
        ids.add(f"disallowed-goal-score:{event_id}:{team_id}:{score_before}>{score_after}")
    return ids


def _live_event_id(notification_type: str, event: dict[str, Any], detail: dict[str, Any]) -> str:
    if notification_type == PENALTY_NOTIFICATION:
        return _penalty_event_id(event, detail)

    athletes = detail.get("athletesInvolved") or [
        participant.get("athlete") or {}
        for participant in detail.get("participants", [])
        if participant.get("athlete")
    ]
    athlete = detail.get("athlete")
    if athlete:
        athletes = [*athletes, athlete]
    athlete_ids = ",".join(
        str(athlete.get("id") or athlete.get("displayName") or athlete.get("fullName") or "")
        for athlete in athletes
    )
    clock = detail.get("clock") or {}
    detail_type = detail.get("type") or {}
    team = detail.get("team") or {}
    return ":".join(
        [
            notification_type,
            str(event.get("id", "")),
            str(detail.get("id", "")),
            str(team.get("id", "")),
            str(clock.get("value", "")),
            str(clock.get("displayValue", "")),
            athlete_ids,
            str(detail_type.get("id", "")),
            str(detail_type.get("type", "")),
            str(detail_type.get("text", "")),
            str(detail.get("text", "")),
        ]
    )


def _penalty_event_id(event: dict[str, Any], detail: dict[str, Any]) -> str:
    event_id, team_id, minute_key, player_key, _minute_value = _penalty_tracking_values(
        event,
        detail,
    )
    return ":".join([PENALTY_NOTIFICATION, event_id, team_id, minute_key, player_key])


def _penalty_already_seen(
    seen_penalty_ids: set[str],
    event: dict[str, Any],
    detail: dict[str, Any],
) -> bool:
    penalty_id = _penalty_event_id(event, detail)
    if penalty_id in seen_penalty_ids:
        return True

    event_id, team_id, minute_key, player_key, minute_value = _penalty_tracking_values(
        event,
        detail,
    )
    for seen_id in seen_penalty_ids:
        seen_values = _parse_penalty_event_id(seen_id)
        if seen_values is None:
            continue
        seen_event_id, seen_team_id, seen_minute_key, seen_player_key = seen_values
        if seen_event_id != event_id or seen_team_id != team_id:
            continue
        if player_key and seen_player_key and player_key == seen_player_key:
            seen_minute_value = _numeric_minute(seen_minute_key)
            if (
                minute_value is not None
                and seen_minute_value is not None
                and abs(minute_value - seen_minute_value) <= 1
            ):
                return True
        elif minute_key and minute_key == seen_minute_key:
            return True
    return False


def _remember_penalty(
    seen_penalty_ids: set[str],
    event: dict[str, Any],
    detail: dict[str, Any],
) -> None:
    seen_penalty_ids.add(_penalty_event_id(event, detail))


def _penalty_tracking_values(
    event: dict[str, Any],
    detail: dict[str, Any],
) -> tuple[str, str, str, str, float | None]:
    clock = detail.get("clock") or {}
    minute_key = str(clock.get("displayValue") or clock.get("value") or detail.get("id") or "")
    athletes = detail.get("athletesInvolved") or [
        participant.get("athlete") or {}
        for participant in detail.get("participants", [])
        if participant.get("athlete")
    ]
    athlete = (athletes or [{}])[0]
    player_key = str(athlete.get("id") or athlete.get("displayName") or athlete.get("fullName") or "")
    return (
        str(event.get("id", "")),
        str((detail.get("team") or {}).get("id", "")),
        minute_key,
        player_key,
        _numeric_minute(clock.get("value") or clock.get("displayValue")),
    )


def _parse_penalty_event_id(penalty_id: str) -> tuple[str, str, str, str] | None:
    parts = penalty_id.split(":", 4)
    if len(parts) != 5 or parts[0] != PENALTY_NOTIFICATION:
        return None
    return parts[1], parts[2], parts[3], parts[4]


def _numeric_minute(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        digits = ""
        for character in str(value):
            if character.isdigit() or character == ".":
                digits += character
                continue
            break
        if not digits:
            return None
        try:
            return float(digits)
        except ValueError:
            return None


def _clock_minute_key(clock: dict[str, Any]) -> str:
    value = clock.get("value") or clock.get("displayValue")
    numeric = _numeric_minute(value)
    if numeric is None:
        return str(value or "")
    if numeric.is_integer():
        return str(int(numeric))
    return str(numeric)


def _is_penalty_detail(detail: dict[str, Any]) -> bool:
    detail_type = detail.get("type") or {}
    text = " ".join(
        str(part or "")
        for part in [
            detail_type.get("type"),
            detail_type.get("text"),
            detail.get("text"),
        ]
    ).lower()
    return "penalty" in text


def _sofascore_goal_details(event: dict[str, Any]) -> list[dict[str, Any]]:
    incidents = event.get("sofascoreIncidents") or {}
    goals = incidents.get("goals", []) if isinstance(incidents, dict) else []
    return goals if isinstance(goals, list) else []


def _sofascore_disallowed_goal_details(event: dict[str, Any]) -> list[dict[str, Any]]:
    incidents = event.get("sofascoreIncidents") or {}
    goals = incidents.get("disallowedGoals", []) if isinstance(incidents, dict) else []
    return goals if isinstance(goals, list) else []


def _play_match_key(event: dict[str, Any], detail: dict[str, Any]) -> tuple[str, str, str]:
    clock = detail.get("clock") or {}
    team = detail.get("team") or {}
    return (
        str(event.get("id", "")),
        str(team.get("id", "")),
        str(clock.get("value") or clock.get("displayValue") or ""),
    )


def _event_score_snapshot(event: dict[str, Any]) -> tuple[int, ...] | None:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    scores: list[int] = []
    for competitor in competitors:
        score = competitor.get("score")
        try:
            scores.append(int(score))
        except (TypeError, ValueError):
            return None
    return tuple(scores) if scores else None


def _score_regressed(previous_score: tuple[int, ...], current_score: tuple[int, ...]) -> bool:
    return any(current < previous for previous, current in zip(previous_score, current_score, strict=False))


def _score_change_details(
    event: dict[str, Any],
    previous_score: tuple[int, ...],
    current_score: tuple[int, ...],
) -> list[dict[str, Any]]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    status = competition.get("status") or event.get("status") or {}
    details: list[dict[str, Any]] = []
    for index, current in enumerate(current_score):
        previous = previous_score[index] if index < len(previous_score) else 0
        score_delta = current - previous
        if score_delta <= 0 or index >= len(competitors):
            continue
        team = competitors[index].get("team") or {}
        details.extend(
            _scoring_details_for_score_change(
                event,
                team,
                score_delta,
                fallback_clock=status,
                score_after=current_score,
            )
        )
    return details


def _score_regression_disallowed_goal_details(
    event: dict[str, Any],
    previous_score: tuple[int, ...],
    current_score: tuple[int, ...],
) -> list[dict[str, Any]]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    status = competition.get("status") or event.get("status") or {}
    details: list[dict[str, Any]] = []
    for index, current in enumerate(current_score):
        previous = previous_score[index] if index < len(previous_score) else 0
        score_delta = previous - current
        if score_delta <= 0 or index >= len(competitors):
            continue
        team = competitors[index].get("team") or {}
        details.extend(
            _disallowed_goal_details_for_score_regression(
                team,
                score_delta,
                fallback_clock=status,
                score_before=previous_score,
                score_after=current_score,
            )
        )
    return details


def _disallowed_goal_details_for_score_regression(
    team: dict[str, Any],
    score_delta: int,
    fallback_clock: dict[str, Any],
    score_before: tuple[int, ...],
    score_after: tuple[int, ...],
) -> list[dict[str, Any]]:
    team_id = str(team.get("id", ""))
    score_before_key = ":".join(str(score) for score in score_before)
    score_after_key = ":".join(str(score) for score in score_after)
    return [
        {
            "id": f"score-regression:{team_id}:{score_before_key}:{score_after_key}:{index}",
            "source": "score-regression",
            "disallowedGoal": True,
            "shootout": False,
            "clock": {
                "value": fallback_clock.get("clock"),
                "displayValue": fallback_clock.get("displayClock") or "",
            },
            "team": team,
            "type": {"id": "score-regression", "type": "varDecision", "text": "Goal disallowed"},
            "scoreBefore": score_before_key,
            "scoreAfter": score_after_key,
            "athletesInvolved": [],
            "text": "Goal disallowed after score correction",
        }
        for index in range(score_delta)
    ]


def _scoring_details_for_score_change(
    event: dict[str, Any],
    team: dict[str, Any],
    score_delta: int,
    fallback_clock: dict[str, Any],
    score_after: tuple[int, ...],
) -> list[dict[str, Any]]:
    team_id = str(team.get("id", ""))
    team_plays = [
        play
        for play in scoring_plays_from_event(event)
        if str((play.get("team") or {}).get("id", "")) == team_id
    ]
    team_plays = sorted(team_plays, key=_goal_clock_value)
    if len(team_plays) >= score_delta:
        return team_plays[-score_delta:]

    missing_goals = score_delta - len(team_plays)
    fallback_details = [
        {
            "id": f"score-change:{team_id}:{':'.join(str(score) for score in score_after)}:{index}",
            "clock": {
                "value": fallback_clock.get("clock"),
                "displayValue": fallback_clock.get("displayClock") or "",
            },
            "team": team,
            "type": {"id": "score-change", "text": "Goal"},
            "scoreValue": 1,
            "scoreAfter": ":".join(str(score) for score in score_after),
            "athletesInvolved": [],
        }
        for index in range(missing_goals)
    ]
    return [*team_plays, *fallback_details]


def _goal_clock_value(detail: dict[str, Any]) -> float:
    clock = detail.get("clock") or {}
    try:
        return float(clock.get("value") or 0)
    except (TypeError, ValueError):
        return 0.0
