"""Pure logic for projecting the World Cup knockout bracket from current standings.

The SofaScore ``cuptrees`` endpoint exposes the official FIFA bracket template with
placeholder seeds such as ``1E`` (group E winner), ``2A`` (group A runner-up),
``3A/3B/3C/3D/3F`` (one of the best third-placed teams) and ``W74`` (winner of a
previous block). This module turns those placeholders into concrete teams using the
live group standings, without depending on network I/O.

The only non-trivial piece is resolving the eight third-place slots. Each slot
lists five candidate groups; we pick an assignment via bipartite matching that
respects every slot's candidates without repeating a group. For the vast majority
of combinations the solution is unique and therefore matches the official FIFA
table. In rare ambiguous cases we fall back to the lexicographically smallest
valid assignment, which stays deterministic across runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

GROUP_LETTERS: tuple[str, ...] = tuple("ABCDEFGHIJKL")
THIRD_PLACE_SLOT_COUNT = 8

_PLACEHOLDER_PATTERN = re.compile(
    r"^([12][A-L]|[A-L][12]|3[A-L](/3[A-L])*|W\d+|L\d+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GroupFirst:
    group: str


@dataclass(frozen=True)
class GroupSecond:
    group: str


@dataclass(frozen=True)
class ThirdPlaceCandidates:
    groups: frozenset[str]


@dataclass(frozen=True)
class WinnerReference:
    source_block_id: int


@dataclass(frozen=True)
class LoserReference:
    source_block_id: int


@dataclass(frozen=True)
class UnknownSeed:
    raw: str


@dataclass(frozen=True)
class ResolvedTeam:
    team: dict[str, Any]


Seed = (
    GroupFirst
    | GroupSecond
    | ThirdPlaceCandidates
    | WinnerReference
    | LoserReference
    | UnknownSeed
    | ResolvedTeam
)


@dataclass(frozen=True)
class ProjectedSide:
    """One side of a projected knockout match."""

    team: dict[str, Any] | None
    seed: str
    projected: bool = False
    ambiguous: bool = False
    candidate_teams: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProjectedMatch:
    order: int
    round_order: int
    round_name: str
    home: ProjectedSide
    away: ProjectedSide
    event_ids: tuple[int, ...]
    start_timestamp: int | None
    finished: bool
    block_id: int | None


@dataclass(frozen=True)
class ProjectedRound:
    order: int
    name: str
    matches: tuple[ProjectedMatch, ...]


@dataclass(frozen=True)
class PlayoffProjection:
    rounds: tuple[ProjectedRound, ...]
    third_place_qualified: tuple[dict[str, Any], ...]
    source: str = "sofascore"

    @property
    def round_of_32(self) -> ProjectedRound | None:
        return next((rnd for rnd in self.rounds if rnd.order == 1), None)


def parse_seed(name: str, source_block_id: int | None = None) -> Seed:
    """Parse a placeholder team name from the cup tree into a typed seed.

    Recognised forms (the API emits both ``1A`` and ``A1`` for group winners):
    ``1A``/``A1`` group winner, ``2A``/``A2`` runner-up,
    ``3A/3B/3C/3D/3F`` best-third candidates, ``W74``/``L101`` winner/loser of a
    previous block (linked via ``sourceBlockId``).
    """
    raw = str(name or "").strip()
    if not raw:
        return UnknownSeed("")
    upper = raw.upper()

    if re.fullmatch(r"W\d+", upper) and source_block_id is not None:
        return WinnerReference(source_block_id)
    if re.fullmatch(r"L\d+", upper) and source_block_id is not None:
        return LoserReference(source_block_id)

    if upper.startswith("3"):
        groups: set[str] = set()
        for part in raw.split("/"):
            token = part.strip().upper()
            if len(token) == 2 and token[0] == "3" and token[1] in GROUP_LETTERS:
                groups.add(token[1])
        if groups:
            return ThirdPlaceCandidates(frozenset(groups))

    match = re.fullmatch(r"([12])([A-L])", upper)
    if match:
        return GroupFirst(match.group(2)) if match.group(1) == "1" else GroupSecond(match.group(2))

    match = re.fullmatch(r"([A-L])([12])", upper)
    if match:
        return GroupFirst(match.group(1)) if match.group(2) == "1" else GroupSecond(match.group(1))

    return UnknownSeed(raw)


def is_seed_placeholder(name: str) -> bool:
    """Return True when a participant team name is still an unresolved seed."""
    return bool(_PLACEHOLDER_PATTERN.match(str(name or "").strip()))


def standings_group_letter(group: dict[str, Any]) -> str | None:
    name = str(group.get("name") or "")
    if name.startswith("Group ") and len(name) == len("Group X") and name[-1] in GROUP_LETTERS:
        return name[-1]
    abbreviation = str(group.get("abbreviation") or "")
    if len(abbreviation) == 1 and abbreviation in GROUP_LETTERS:
        return abbreviation
    return None


def is_third_place_table(group: dict[str, Any]) -> bool:
    name = str(group.get("name") or "").lower()
    return "third" in name and "place" in name


def entry_rank(entry: dict[str, Any]) -> int | None:
    for stat in entry.get("stats", []):
        if stat.get("name") == "rank":
            try:
                return int(stat.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def extract_group_teams(
    standings_groups: list[dict[str, Any]],
) -> dict[str, dict[int, dict[str, Any]]]:
    """Build ``{group_letter: {position: team}}`` from normalized standings groups."""
    by_group: dict[str, dict[int, dict[str, Any]]] = {}
    for group in standings_groups:
        letter = standings_group_letter(group)
        if letter is None:
            continue
        entries = (group.get("standings") or {}).get("entries", [])
        positions: dict[int, dict[str, Any]] = {}
        for entry in entries:
            rank = entry_rank(entry)
            if rank is None:
                continue
            positions[rank] = entry.get("team") or {}
        if positions:
            by_group[letter] = positions
    return by_group


def extract_qualified_thirds(
    standings_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the best eight third-placed teams, ranked, from the standings table.

    Falls back to ranking each group's third place by ``(points, goal diff)``
    when the dedicated third-placed table is not published by the API.
    """
    for group in standings_groups:
        if not is_third_place_table(group):
            continue
        entries = list((group.get("standings") or {}).get("entries", []))
        entries.sort(key=lambda entry: entry_rank(entry) or 999)
        teams = [entry.get("team") or {} for entry in entries[:THIRD_PLACE_SLOT_COUNT]]
        return [team for team in teams if team]

    return _fallback_rank_thirds(standings_groups)


def _fallback_rank_thirds(
    standings_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ranked: list[tuple[tuple[int, int], dict[str, Any]]] = []
    for group in standings_groups:
        letter = standings_group_letter(group)
        if letter is None:
            continue
        entries = (group.get("standings") or {}).get("entries", [])
        third = next((e for e in entries if entry_rank(e) == 3), None)
        if not third:
            continue
        points = _stat_int(third, "points")
        diff = _stat_int(third, "pointDifferential")
        ranked.append(((points, diff), third.get("team") or {}))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [team for _, team in ranked[:THIRD_PLACE_SLOT_COUNT] if team]


def _stat_int(entry: dict[str, Any], name: str) -> int:
    for stat in entry.get("stats", []):
        if stat.get("name") == name:
            try:
                return int(float(str(stat.get("value")).replace("+", "")))
            except (TypeError, ValueError):
                return 0
    return 0


def resolve_third_place_slots(
    slot_candidates: dict[int, tuple[str, ...]],
    qualified_third_groups: list[str],
) -> dict[int, str] | None:
    """Assign each third-place slot a single source group via the FIFA table.

    ``slot_candidates`` is kept for API compatibility but ignored: the FIFA
    lookup table published by FIFA (Annex C of the regulations) is fully
    authoritative, so we resolve slots directly from the table. The
    :func:`playoff_fifa_table.lookup` is consulted first; the bipartite
    matching fallback only kicks in when the combination has no published entry.
    """
    from worldcupquente.playoff_fifa_table import lookup

    official = lookup(qualified_third_groups)
    if official is not None:
        return dict(official)
    return _bipartite_match(slot_candidates, qualified_third_groups)


def _bipartite_match(
    slot_candidates: dict[int, tuple[str, ...]],
    qualified_third_groups: list[str],
) -> dict[int, str] | None:
    """Fallback bipartite matching used when the FIFA table lacks an entry."""
    slot_ids = sorted(slot_candidates)
    qualified_set = set(qualified_third_groups)
    assignment: dict[int, str] = {}

    def can_extend(index: int, used: set[str]) -> bool:
        if index == len(slot_ids):
            return True
        slot_id = slot_ids[index]
        for candidate in slot_candidates[slot_id]:
            if candidate not in qualified_set or candidate in used:
                continue
            assignment[slot_id] = candidate
            used.add(candidate)
            if can_extend(index + 1, used):
                return True
            used.discard(candidate)
            assignment.pop(slot_id, None)
        return False

    if can_extend(0, set()):
        return dict(assignment)
    return None


def third_place_source_groups(
    rounds: list[dict[str, Any]],
) -> dict[int, tuple[str, ...]]:
    """Collect the ordered candidate groups for every third-place slot of round 1.

    Slots are keyed by their block ``order`` within round 1. The candidate order
    matches the API placeholder (``3A/3B/3C/3D/3F`` -> ``("A","B","C","D","F")``),
    which keeps the matching deterministic and aligned with the FIFA table.
    """
    if not rounds:
        return {}
    round_one = rounds[0]
    slots: dict[int, tuple[str, ...]] = {}
    for block in round_one.get("blocks", []):
        order = block.get("order")
        if order is None:
            continue
        for participant in block.get("participants", []):
            name = (participant.get("team") or {}).get("name") or ""
            seed = parse_seed(name)
            if isinstance(seed, ThirdPlaceCandidates):
                slots[int(order)] = tuple(sorted(seed.groups, key=GROUP_LETTERS.index))
                break
    return slots


def _participant_seed(participant: dict[str, Any]) -> Seed:
    team = participant.get("team") or {}
    name = team.get("name") or ""
    if is_seed_placeholder(name):
        return parse_seed(name, participant.get("sourceBlockId"))
    return ResolvedTeam(team)


def _winner_team_of_block(block: dict[str, Any]) -> dict[str, Any] | None:
    if not block.get("finished"):
        return None
    for participant in block.get("participants", []):
        if participant.get("winner"):
            return participant.get("team") or {}
    return None


def _loser_team_of_block(block: dict[str, Any]) -> dict[str, Any] | None:
    if not block.get("finished"):
        return None
    losers = [participant.get("team") or {} for participant in block.get("participants", []) if not participant.get("winner")]
    return losers[0] if losers else None


def _block_by_id(rounds: list[dict[str, Any]], block_id: int | None) -> dict[str, Any] | None:
    if block_id is None:
        return None
    for rnd in rounds:
        for block in rnd.get("blocks", []):
            if block.get("blockId") == block_id:
                return block
    return None


def resolve_side(
    seed: Seed,
    *,
    group_teams: dict[str, dict[int, dict[str, Any]]],
    third_assignment: dict[int, str],
    slot_order: int,
    rounds: list[dict[str, Any]],
    third_index_by_group: dict[str, int],
) -> ProjectedSide:
    """Resolve a single seed into a :class:`ProjectedSide`."""
    seed_text = _seed_display(seed)

    if isinstance(seed, GroupFirst):
        team = group_teams.get(seed.group, {}).get(1)
        return ProjectedSide(team=team, seed=seed_text, projected=team is not None)

    if isinstance(seed, GroupSecond):
        team = group_teams.get(seed.group, {}).get(2)
        return ProjectedSide(team=team, seed=seed_text, projected=team is not None)

    if isinstance(seed, ThirdPlaceCandidates):
        assigned = third_assignment.get(slot_order)
        if assigned:
            team = group_teams.get(assigned, {}).get(3)
            return ProjectedSide(team=team, seed=seed_text, projected=True)
        return ProjectedSide(
            team=None,
            seed=seed_text,
            projected=True,
            ambiguous=True,
        )

    if isinstance(seed, WinnerReference):
        block = _block_by_id(rounds, seed.source_block_id)
        team = _winner_team_of_block(block) if block else None
        return ProjectedSide(team=team, seed=seed_text, projected=False)

    if isinstance(seed, LoserReference):
        block = _block_by_id(rounds, seed.source_block_id)
        team = _loser_team_of_block(block) if block else None
        return ProjectedSide(team=team, seed=seed_text, projected=False)

    if isinstance(seed, ResolvedTeam):
        return ProjectedSide(team=seed.team, seed=seed_text, projected=False)

    return ProjectedSide(team=None, seed=seed_text, projected=False)


def _seed_display(seed: Seed) -> str:
    if isinstance(seed, GroupFirst):
        return f"1{seed.group}"
    if isinstance(seed, GroupSecond):
        return f"2{seed.group}"
    if isinstance(seed, ThirdPlaceCandidates):
        ordered = sorted(seed.groups, key=GROUP_LETTERS.index)
        return "/".join("3" + group for group in ordered)
    if isinstance(seed, WinnerReference):
        return f"W{seed.source_block_id}"
    if isinstance(seed, LoserReference):
        return f"L{seed.source_block_id}"
    if isinstance(seed, UnknownSeed):
        return seed.raw
    return ""


def build_projection(
    cup_tree: dict[str, Any],
    standings_groups: list[dict[str, Any]],
) -> PlayoffProjection:
    """Combine a cup tree payload and normalized standings into a projection."""
    rounds_raw = cup_tree.get("rounds", []) if cup_tree else []
    group_teams = extract_group_teams(standings_groups)
    qualified_thirds = extract_qualified_thirds(standings_groups)

    third_index_by_group = _third_group_membership(group_teams, qualified_thirds)
    slot_candidates = third_place_source_groups(rounds_raw)
    qualified_third_groups = [grp for grp in third_index_by_group if third_index_by_group[grp] is not None]
    qualified_third_groups.sort(key=lambda grp: third_index_by_group[grp] or 999)
    third_assignment = resolve_third_place_slots(slot_candidates, qualified_third_groups) or {}

    projected_rounds: list[ProjectedRound] = []
    for rnd in rounds_raw:
        round_order = int(rnd.get("order") or 0)
        round_name = str(rnd.get("description") or rnd.get("name") or f"Round {round_order}")
        matches: list[ProjectedMatch] = []
        for block in rnd.get("blocks", []):
            participants = list(block.get("participants", []))
            order = int(block.get("order") or 0)
            seeds = [_participant_seed(p) for p in participants]
            home_seed, away_seed = (seeds + [UnknownSeed(""), UnknownSeed("")])[:2]

            home = resolve_side(
                home_seed,
                group_teams=group_teams,
                third_assignment=third_assignment,
                slot_order=order,
                rounds=rounds_raw,
                third_index_by_group=third_index_by_group,
            )
            away = resolve_side(
                away_seed,
                group_teams=group_teams,
                third_assignment=third_assignment,
                slot_order=order,
                rounds=rounds_raw,
                third_index_by_group=third_index_by_group,
            )

            event_ids = tuple(int(event_id) for event_id in (block.get("events") or []) if event_id)
            start_timestamp = block.get("seriesStartDateTimestamp")
            matches.append(
                ProjectedMatch(
                    order=order,
                    round_order=round_order,
                    round_name=round_name,
                    home=home,
                    away=away,
                    event_ids=event_ids,
                    start_timestamp=int(start_timestamp) if start_timestamp else None,
                    finished=bool(block.get("finished")),
                    block_id=block.get("blockId"),
                )
            )
        matches.sort(key=lambda m: m.order)
        projected_rounds.append(ProjectedRound(order=round_order, name=round_name, matches=tuple(matches)))

    return PlayoffProjection(
        rounds=tuple(projected_rounds),
        third_place_qualified=tuple(qualified_thirds),
    )


def _third_group_membership(
    group_teams: dict[str, dict[int, dict[str, Any]]],
    qualified_thirds: list[dict[str, Any]],
) -> dict[str, int | None]:
    """Map each group letter to the 1-based rank of its third-placed team, or None."""
    team_id_to_group: dict[str, str] = {}
    for letter, positions in group_teams.items():
        third = positions.get(3)
        if third:
            team_id = str(third.get("id") or "")
            if team_id:
                team_id_to_group[team_id] = letter

    membership: dict[str, int | None] = dict.fromkeys(GROUP_LETTERS, None)
    for rank, team in enumerate(qualified_thirds, start=1):
        team_id = str(team.get("id") or "")
        letter = team_id_to_group.get(team_id)
        if letter:
            membership[letter] = rank
    return membership
