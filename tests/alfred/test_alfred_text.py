import pytest

from hoard.alfred.text import fold, matches, words


@pytest.mark.parametrize(
    "text, folded, why",
    [
        ("Réunion", "reunion", "accents come off"),
        ("ДОКИ", "доки", "Cyrillic folds case and keeps its letters"),
        ("Making API v1", "making api v1", "ASCII only lowers, so it stays fast"),
        ("ﬁle", "file", "compatibility ligatures decompose"),
    ],
)
def test_fold(text, folded, why):
    assert fold(text) == folded, why


def test_words_are_the_folded_word_characters():
    assert words("Delany, Samuel R. — Dhalgren (1975)") == ["delany", "samuel", "r", "dhalgren", "1975"], (
        "punctuation separates, every run of word characters is one word"
    )


@pytest.mark.parametrize(
    "query, text, hit",
    [
        ("making v1", "making API v1", True),
        ("api", "making API v1", True),
        ("api", "autotests", False),
        ("v1", "making API v10", True),
        ("v2", "making API v1", False),
        ("meeting l", "meeting with L", True),
        ("docs reading", "reading docs", True),
        ("", "anything", True),
        ("   ", "anything", True),
        ("réunion", "Reunion", True),
        ("reunion", "Réunion", True),
        ("ДОКИ", "читаю доки", True),
        ("make", "making API v1", False),
    ],
)
def test_every_typed_word_is_a_prefix_of_some_word(query, text, hit):
    assert matches(query, text) is hit, f"{query!r} should {'match' if hit else 'not match'} {text!r}"
