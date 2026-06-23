"""FIFA official lookup table for the 2026 World Cup knockout bracket.

This module wraps the 495-row table published by FIFA (Annex C of the
``Regulations FIFA World Cup 2026``) that maps every possible set of eight
third-placed qualifiers to the official assignment of those teams to the eight
``Round of 32`` slots that host a group winner.

The full table is generated from the data at
``https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage`` (which
reproduces the official FIFA table) and is exposed through :func:`lookup` which
takes the 8 qualifying group letters and returns ``{slot_order: group_letter}``.
"""

from __future__ import annotations

from worldcupquente.playoff_fifa_table_data import entries

_FIFA_TABLE: dict[frozenset[str], dict[int, str]] = {
    frozenset(qualified): {int(slot_order): group_letter for slot_order, group_letter in slot_assignment.items()}
    for qualified, slot_assignment in entries
}


def lookup(qualified_third_groups: list[str] | tuple[str, ...] | frozenset[str]) -> dict[int, str] | None:
    """Return the FIFA official assignment for a given set of 8 qualifying third-placed groups.

    The input must contain exactly 8 group letters (``A`` through ``L``). The
    return maps ``slot_order -> group_letter`` where ``slot_order`` is the
    ``order`` field of the round-of-32 block that hosts a third-placed team
    (i.e. ``1``, ``2``, ``7``, ``8``, ``11``, ``12``, ``15``, ``16``).
    """
    if isinstance(qualified_third_groups, str):
        return None
    key = frozenset(qualified_third_groups)
    return _FIFA_TABLE.get(key)


def is_available(qualified_third_groups: list[str] | tuple[str, ...] | frozenset[str]) -> bool:
    """Return True if the FIFA table has an entry for the given 8-group combination."""
    return lookup(qualified_third_groups) is not None


def table_size() -> int:
    """Return the number of entries loaded in the FIFA table (sanity check)."""
    return len(_FIFA_TABLE)
