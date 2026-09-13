"""The warm library's matcher, pinned by what the golden set caught it doing.

`language/tools/golden_set.py` ran forty things somebody will really type at the building
through the local tier. Most of what it found was missing scenes, which are a taste call and
live in `docs/golden-set.md`. What it also found was a matcher confidently wrong: a word it
could not place, corrected into a word it could, and a whole scene chosen on the strength of
a colour. Those are bugs, they are fixed, and these are the tests that keep them fixed.

The service half has the same tests over its own copy (`language/tests/test_golden_set.py`).

    python -m pytest -q tests/test_library.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import library  # noqa: E402


# ------------------------------------------------------------------ colours decide nothing

@pytest.mark.parametrize("colour", sorted(library.COLOURS))
def test_a_colour_is_never_a_scene_on_its_own(colour):
    """Every scene has a palette, so a colour names all of them and therefore none.

    "red" used to reach *go sox* purely because that entry happened to list it, which put
    GO SOX! on the facade for "a red balloon" and for "red leaves".
    """
    assert colour not in library.INDEX, f"{colour!r} is a keyword for {library.INDEX[colour]!r}"


@pytest.mark.parametrize("phrase", [
    "a red balloon", "red leaves", "a gold medal", "an orange sky", "a grey day",
])
def test_a_phrase_that_is_only_a_colour_and_a_noun_misses_honestly(phrase):
    assert library.match(phrase) is None, f"{phrase!r} -> {library.match(phrase)}"


def test_a_colour_named_on_purpose_still_works():
    """The rule is about the *derived* index. An alias may name a colour deliberately."""
    assert library.match("red sox")[0] == "go sox"
    assert library.match("golden hour")[0] == "sunset"


# ------------------------------------------------------------------ the typo pass

@pytest.mark.parametrize("phrase, wrong", [
    ("i am tired", "i got the job"),     # tired -> hired
    ("shana tova", "merry christmas"),   # shana -> santa
    ("the t is late", "coffee"),         # late  -> latte
    ("a windy night", "i'm so happy"),   # night -> light
])
def test_an_ordinary_short_word_is_not_corrected_into_a_scene(phrase, wrong):
    """A five-letter word one letter off another scores exactly the cutoff.

    That is not a typo, it is English, and guessing at it is how HIRED! ends up on the
    building for somebody saying they are tired. A word we know and cannot place stays
    unplaced; the lexicon gives it a mood and the building is honest about the miss.
    """
    hit = library.match(phrase)
    assert hit is None or hit[0] != wrong, f"{phrase!r} -> {hit}"


@pytest.mark.parametrize("typo, key", [
    ("firewroks", "fireworks"), ("chirstmas", "merry christmas"), ("brithday", "birthday"),
    ("graduaton", "graduation"), ("lightining", "thunderstorm"), ("basketbal", "lebron dunk"),
])
def test_a_real_misspelling_is_still_forgiven(typo, key):
    hit = library.match(typo)
    assert hit is not None and hit[0] == key, f"{typo!r} -> {hit}"


def test_a_word_in_several_scenes_is_left_alone_rather_than_guessed_at():
    """"night" belongs to four scenes, so the index drops it. It must not come back by typo."""
    assert "night" not in library.INDEX
    assert "night" in library.AMBIGUOUS


# ------------------------------------------------------------------ the aliases the set added

@pytest.mark.parametrize("phrase, key", [
    ("marry me", "she said yes"),         # the proposal scene's own most likely sentence
    ("will you marry me", "she said yes"),
    ("dunkin", "coffee"),                 # in this city it is not a basketball move
    ("sundown", "sunset"),                # went to *snow day* on a fuzzy accident
    ("snowstorm", "snow day"),
    ("moonrise", "full moon"),
    ("its pouring", "it's raining"),
    ("drizzle", "it's raining"),
    ("the esplanade", "charles river"),
    ("the milky way", "take me to space"),
    ("fingers crossed", "good luck"),
    ("break a leg", "good luck"),
    ("congrats", "graduation"),
    ("boston", "city lights"),
    ("happy new year", "fireworks"),
])
def test_an_obvious_phrasing_reaches_the_scene_that_already_exists(phrase, key):
    hit = library.match(phrase)
    assert hit is not None and hit[0] == key, f"{phrase!r} -> {hit}"
