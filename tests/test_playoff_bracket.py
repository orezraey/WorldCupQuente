"""Unit tests for the playoff bracket projection logic."""

from __future__ import annotations

from worldcupquente.playoff_bracket import (
    GroupFirst,
    GroupSecond,
    LoserReference,
    PlayoffProjection,
    ThirdPlaceCandidates,
    UnknownSeed,
    WinnerReference,
    build_projection,
    entry_rank,
    extract_group_teams,
    extract_qualified_thirds,
    is_seed_placeholder,
    is_third_place_table,
    parse_seed,
    resolve_third_place_slots,
    standings_group_letter,
    third_place_source_groups,
)


def test_parse_seed_group_first_standard_form():
    assert parse_seed("1E") == GroupFirst("E")


def test_parse_seed_group_first_swapped_form():
    assert parse_seed("H1") == GroupFirst("H")
    assert parse_seed("G1") == GroupFirst("G")


def test_parse_seed_group_second_standard_form():
    assert parse_seed("2A") == GroupSecond("A")


def test_parse_seed_group_second_swapped_form():
    assert parse_seed("H2") == GroupSecond("H")
    assert parse_seed("G2") == GroupSecond("G")


def test_parse_seed_third_place_candidates_preserves_groups():
    seed = parse_seed("3A/3B/3C/3D/3F")
    assert isinstance(seed, ThirdPlaceCandidates)
    assert seed.groups == frozenset({"A", "B", "C", "D", "F"})


def test_parse_seed_third_place_single_candidate():
    seed = parse_seed("3A")
    assert isinstance(seed, ThirdPlaceCandidates)
    assert seed.groups == frozenset({"A"})


def test_parse_seed_winner_reference_uses_source_block_id():
    assert parse_seed("W74", source_block_id=2218759) == WinnerReference(2218759)


def test_parse_seed_loser_reference_uses_source_block_id():
    assert parse_seed("L101", source_block_id=12345) == LoserReference(12345)


def test_parse_seed_winner_without_source_block_id_falls_back_to_unknown():
    assert isinstance(parse_seed("W74"), UnknownSeed)


def test_parse_seed_unknown_placeholder():
    assert isinstance(parse_seed("TBD"), UnknownSeed)


def test_parse_seed_empty_string():
    assert isinstance(parse_seed(""), UnknownSeed)
    assert isinstance(parse_seed("   "), UnknownSeed)


def test_is_seed_placeholder_flags_known_and_unknown():
    assert is_seed_placeholder("1E")
    assert is_seed_placeholder("3A/3B/3C")
    assert not is_seed_placeholder("Brazil")
    assert not is_seed_placeholder("")


def test_standings_group_letter_from_name():
    assert standings_group_letter({"name": "Group A"}) == "A"
    assert standings_group_letter({"name": "Group L"}) == "L"


def test_standings_group_letter_from_abbreviation():
    assert standings_group_letter({"name": "Other", "abbreviation": "B"}) == "B"


def test_standings_group_letter_returns_none_for_thirds_table():
    assert standings_group_letter({"name": "Third-placed teams"}) is None


def test_is_third_place_table_detection():
    assert is_third_place_table({"name": "Third-placed teams"})
    assert is_third_place_table({"name": "Best third-placed teams"})
    assert not is_third_place_table({"name": "Group A"})


def test_entry_rank_reads_rank_stat():
    entry = {"stats": [{"name": "rank", "value": 2}, {"name": "points", "value": 4}]}
    assert entry_rank(entry) == 2


def test_entry_rank_returns_none_when_missing():
    assert entry_rank({"stats": [{"name": "points", "value": 4}]}) is None
    assert entry_rank({}) is None


def test_extract_group_teams_maps_positions():
    groups = [
        {
            "name": "Group A",
            "standings": {
                "entries": [
                    {"team": {"id": "1", "name": "Mexico"}, "stats": [{"name": "rank", "value": 1}]},
                    {"team": {"id": "2", "name": "South Korea"}, "stats": [{"name": "rank", "value": 2}]},
                    {"team": {"id": "3", "name": "Czechia"}, "stats": [{"name": "rank", "value": 3}]},
                ]
            },
        }
    ]
    by_group = extract_group_teams(groups)
    assert by_group["A"][1]["name"] == "Mexico"
    assert by_group["A"][2]["name"] == "South Korea"
    assert by_group["A"][3]["name"] == "Czechia"


def test_extract_qualified_thirds_uses_thirds_table_when_available():
    groups = [
        {"name": "Third-placed teams", "standings": {"entries": [
            {"team": {"id": "10", "name": "Sweden"}, "stats": [{"name": "rank", "value": 1}]},
            {"team": {"id": "20", "name": "Scotland"}, "stats": [{"name": "rank", "value": 2}]},
            {"team": {"id": "30", "name": "Algeria"}, "stats": [{"name": "rank", "value": 3}]},
            {"team": {"id": "40", "name": "Paraguay"}, "stats": [{"name": "rank", "value": 4}]},
            {"team": {"id": "50", "name": "Ecuador"}, "stats": [{"name": "rank", "value": 5}]},
            {"team": {"id": "60", "name": "Belgium"}, "stats": [{"name": "rank", "value": 6}]},
            {"team": {"id": "70", "name": "Cabo Verde"}, "stats": [{"name": "rank", "value": 7}]},
            {"team": {"id": "80", "name": "Senegal"}, "stats": [{"name": "rank", "value": 8}]},
            {"team": {"id": "90", "name": "Bosnia"}, "stats": [{"name": "rank", "value": 9}]},
        ]}},
    ]
    thirds = extract_qualified_thirds(groups)
    assert [team["name"] for team in thirds] == [
        "Sweden", "Scotland", "Algeria", "Paraguay",
        "Ecuador", "Belgium", "Cabo Verde", "Senegal",
    ]


def test_extract_qualified_thirds_falls_back_to_ranking_by_points():
    groups = [
        {
            "name": "Group A",
            "standings": {"entries": [
                {"team": {"id": "1"}, "stats": [{"name": "rank", "value": 3}, {"name": "points", "value": 4}, {"name": "pointDifferential", "value": "+2"}]},
            ]},
        },
        {
            "name": "Group B",
            "standings": {"entries": [
                {"team": {"id": "2"}, "stats": [{"name": "rank", "value": 3}, {"name": "points", "value": 6}, {"name": "pointDifferential", "value": "+5"}]},
            ]},
        },
    ]
    thirds = extract_qualified_thirds(groups)
    assert len(thirds) == 2
    assert thirds[0]["id"] == "2"


def test_resolve_third_place_slots_returns_valid_unique_assignment():
    slot_candidates = {
        1: ("A", "B", "C", "D", "F"),
        2: ("C", "D", "F", "G", "H"),
        7: ("B", "E", "F", "I", "J"),
        8: ("A", "E", "H", "I", "J"),
        11: ("C", "E", "F", "H", "I"),
        12: ("E", "H", "I", "J", "K"),
        15: ("E", "F", "G", "I", "J"),
        16: ("D", "E", "I", "J", "L"),
    }
    qualified = ["A", "B", "C", "D", "E", "F", "G", "H"]

    assignment = resolve_third_place_slots(slot_candidates, qualified)

    assert assignment is not None
    assigned_groups = list(assignment.values())
    assert sorted(assigned_groups) == sorted(qualified)
    assert set(assignment.keys()) == set(slot_candidates.keys())


def test_resolve_third_place_slots_uses_fifa_table_when_combo_present():
    """For combinations the FIFA table covers, the assignment matches the table."""
    from worldcupquente.playoff_fifa_table import lookup

    qualified = ["A", "C", "D", "F", "G", "H", "J", "K"]
    slot_candidates = {
        1: ("A", "B", "C", "D", "F"),
        2: ("C", "D", "F", "G", "H"),
        7: ("B", "E", "F", "I", "J"),
        8: ("A", "E", "H", "I", "J"),
        11: ("C", "E", "F", "H", "I"),
        12: ("E", "H", "I", "J", "K"),
        15: ("E", "F", "G", "I", "J"),
        16: ("D", "E", "I", "J", "L"),
    }

    assignment = resolve_third_place_slots(slot_candidates, qualified)
    expected = lookup(qualified)

    assert expected is not None
    assert assignment == expected


def test_resolve_third_place_slots_falls_back_to_bipartite_when_combo_missing():
    """When the FIFA table has no entry, the bipartite fallback still resolves."""
    from unittest.mock import patch

    slot_candidates = {
        1: ("A", "B"),
        2: ("A", "B"),
    }

    with patch("worldcupquente.playoff_fifa_table.lookup", return_value=None):
        # Two slots both only accept A or B, but only one group qualified
        assert resolve_third_place_slots(slot_candidates, ["A"]) is None
        # If we provide a fully-qualified combination that the fallback can match:
        assert resolve_third_place_slots({1: ("A",), 2: ("B",)}, ["A", "B"]) == {1: "A", 2: "B"}


def test_resolve_third_place_slots_is_deterministic():
    slot_candidates = {
        1: ("A", "B", "C", "D", "F"),
        2: ("C", "D", "F", "G", "H"),
        7: ("B", "E", "F", "I", "J"),
        8: ("A", "E", "H", "I", "J"),
        11: ("C", "E", "F", "H", "I"),
        12: ("E", "H", "I", "J", "K"),
        15: ("E", "F", "G", "I", "J"),
        16: ("D", "E", "I", "J", "L"),
    }
    qualified = ["A", "C", "E", "F", "H", "I", "J", "K"]

    first = resolve_third_place_slots(slot_candidates, qualified)
    second = resolve_third_place_slots(slot_candidates, qualified)
    assert first == second
    assert first is not None


def test_resolve_third_place_slots_returns_none_when_unfeasible():
    slot_candidates = {
        1: ("A", "B"),
        2: ("A", "B"),
    }
    # Two slots both only accept A or B, but only one group qualified.
    assert resolve_third_place_slots(slot_candidates, ["A"]) is None


def test_third_place_source_groups_extracts_only_round_one_third_slots():
    rounds = [
        {
            "order": 1,
            "blocks": [
                {"order": 1, "participants": [
                    {"team": {"name": "1E"}},
                    {"team": {"name": "3A/3B/3C/3D/3F"}},
                ]},
                {"order": 3, "participants": [
                    {"team": {"name": "2A"}},
                    {"team": {"name": "2B"}},
                ]},
                {"order": 7, "participants": [
                    {"team": {"name": "1D"}},
                    {"team": {"name": "3B/3E/3F/3I/3J"}},
                ]},
            ],
        },
        {"order": 2, "blocks": [{"order": 1, "participants": [{"team": {"name": "W74"}}]}]},
    ]

    slots = third_place_source_groups(rounds)
    assert slots == {1: ("A", "B", "C", "D", "F"), 7: ("B", "E", "F", "I", "J")}


def test_build_projection_resolves_round_of_32_with_group_winners_and_runners_up():
    cup_tree = {
        "rounds": [
            {
                "order": 1,
                "description": "Round of 32",
                "blocks": [
                    {
                        "order": 9,
                        "finished": False,
                        "blockId": 2218775,
                        "events": [12813012],
                        "seriesStartDateTimestamp": 1782765000,
                        "participants": [
                            {"team": {"name": "1C"}, "winner": False},
                            {"team": {"name": "2F"}, "winner": False},
                        ],
                    },
                    {
                        "order": 3,
                        "finished": False,
                        "blockId": 2218763,
                        "events": [12813000],
                        "seriesStartDateTimestamp": 1782766000,
                        "participants": [
                            {"team": {"name": "2A"}, "winner": False},
                            {"team": {"name": "2B"}, "winner": False},
                        ],
                    },
                ],
            }
        ]
    }
    standings = _standings_fixture()

    projection = build_projection(cup_tree, standings)

    assert isinstance(projection, PlayoffProjection)
    round_of_32 = projection.round_of_32
    assert round_of_32 is not None
    by_order = {match.order: match for match in round_of_32.matches}

    assert by_order[9].home.team["name"] == "Brazil"
    assert by_order[9].home.seed == "1C"
    assert by_order[9].away.team["name"] == "Japan"
    assert by_order[9].away.seed == "2F"
    assert by_order[9].home.projected is True

    assert by_order[3].home.team["name"] == "South Korea"
    assert by_order[3].away.team["name"] == "Switzerland"


def test_build_projection_marks_third_place_slots_resolved_or_ambiguous():
    cup_tree = {
        "rounds": [
            {
                "order": 1,
                "description": "Round of 32",
                "blocks": [
                    {
                        "order": 1,
                        "finished": False,
                        "blockId": 2218759,
                        "events": [12813014],
                        "seriesStartDateTimestamp": 1782765000,
                        "participants": [
                            {"team": {"name": "1E"}, "winner": False},
                            {"team": {"name": "3A/3B/3C/3D/3F"}, "winner": False},
                        ],
                    },
                ],
            }
        ]
    }
    # Only group A among the candidates has a third place that qualified.
    standings = [
        {
            "name": "Group A",
            "standings": {"entries": [
                {"team": {"id": "100", "name": "Mexico"}, "stats": [{"name": "rank", "value": 1}]},
                {"team": {"id": "101", "name": "South Korea"}, "stats": [{"name": "rank", "value": 2}]},
                {"team": {"id": "102", "name": "Czechia"}, "stats": [{"name": "rank", "value": 3}]},
            ]},
        },
        {
            "name": "Group E",
            "standings": {"entries": [
                {"team": {"id": "200", "name": "Germany"}, "stats": [{"name": "rank", "value": 1}]},
                {"team": {"id": "201", "name": "Ivory Coast"}, "stats": [{"name": "rank", "value": 2}]},
                {"team": {"id": "202", "name": "Ecuador"}, "stats": [{"name": "rank", "value": 3}]},
            ]},
        },
        {
            "name": "Third-placed teams",
            "standings": {"entries": [
                {"team": {"id": "102", "name": "Czechia"}, "stats": [{"name": "rank", "value": 1}]},
            ]},
        },
    ]

    projection = build_projection(cup_tree, standings)
    match = projection.round_of_32.matches[0]

    assert match.home.team["name"] == "Germany"
    assert match.away.team["name"] == "Czechia"
    assert match.away.seed == "3A/3B/3C/3D/3F"
    assert match.away.projected is True
    assert match.away.ambiguous is False


def test_build_projection_propagates_winners_from_finished_blocks():
    cup_tree = {
        "rounds": [
            {
                "order": 1,
                "description": "Round of 32",
                "blocks": [
                    {
                        "order": 9,
                        "finished": True,
                        "blockId": 2218775,
                        "events": [12813012],
                        "seriesStartDateTimestamp": 1782765000,
                        "participants": [
                            {"team": {"id": "205", "name": "Brazil"}, "winner": True},
                            {"team": {"id": "627", "name": "Japan"}, "winner": False},
                        ],
                    },
                ],
            },
            {
                "order": 2,
                "description": "Round of 16",
                "blocks": [
                    {
                        "order": 1,
                        "finished": False,
                        "blockId": 2218791,
                        "events": [12813010],
                        "seriesStartDateTimestamp": 1783198800,
                        "participants": [
                            {"team": {"name": "W74"}, "sourceBlockId": 2218775, "winner": False},
                            {"team": {"name": "W77"}, "sourceBlockId": 2218761, "winner": False},
                        ],
                    },
                ],
            },
        ]
    }

    projection = build_projection(cup_tree, [])

    round_of_16 = projection.rounds[1]
    match = round_of_16.matches[0]
    assert match.home.team["name"] == "Brazil"
    assert match.away.team is None


def test_build_projection_empty_cup_tree_returns_empty_projection():
    projection = build_projection({}, [])
    assert projection.rounds == ()
    assert projection.round_of_32 is None


def _standings_fixture() -> list[dict]:
    return [
        {
            "name": "Group A",
            "standings": {"entries": [
                {"team": {"id": "203", "name": "Mexico"}, "stats": [{"name": "rank", "value": 1}]},
                {"team": {"id": "451", "name": "South Korea"}, "stats": [{"name": "rank", "value": 2}]},
                {"team": {"id": "450", "name": "Czechia"}, "stats": [{"name": "rank", "value": 3}]},
            ]},
        },
        {
            "name": "Group B",
            "standings": {"entries": [
                {"team": {"id": "206", "name": "Canada"}, "stats": [{"name": "rank", "value": 1}]},
                {"team": {"id": "475", "name": "Switzerland"}, "stats": [{"name": "rank", "value": 2}]},
                {"team": {"id": "452", "name": "Bosnia"}, "stats": [{"name": "rank", "value": 3}]},
            ]},
        },
        {
            "name": "Group C",
            "standings": {"entries": [
                {"team": {"id": "205", "name": "Brazil"}, "stats": [{"name": "rank", "value": 1}]},
                {"team": {"id": "2869", "name": "Morocco"}, "stats": [{"name": "rank", "value": 2}]},
                {"team": {"id": "580", "name": "Scotland"}, "stats": [{"name": "rank", "value": 3}]},
            ]},
        },
        {
            "name": "Group F",
            "standings": {"entries": [
                {"team": {"id": "449", "name": "Netherlands"}, "stats": [{"name": "rank", "value": 1}]},
                {"team": {"id": "627", "name": "Japan"}, "stats": [{"name": "rank", "value": 2}]},
                {"team": {"id": "466", "name": "Sweden"}, "stats": [{"name": "rank", "value": 3}]},
            ]},
        },
    ]
