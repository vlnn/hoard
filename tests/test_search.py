from __future__ import annotations

import pytest

from hoard import _search


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("", ""),
        ("dune", '"dune"*'),
        ("  frank   dune ", '"frank"* "dune"*'),
        ('say "hi"', '"say"* """hi"""*'),
        ("- dune", '"dune"*'),
        ("— ...", ""),
        ("brontë", '"brontë"*'),
    ],
)
def test_match_expression_prefix_matches_every_word(typed, expected):
    assert _search.match_expression(typed) == expected, "each word should become a quoted prefix term"


@pytest.mark.parametrize(
    "typed, first_word, rest",
    [
        ("", "", []),
        ("update", "update", []),
        ("update now please", "update", ["now", "please"]),
        ("  Dune  ", "dune", []),
    ],
)
def test_split_command_separates_the_first_word(typed, first_word, rest):
    assert _search.split_command(typed) == (first_word, rest), "the first word should be split off, lowercased"
