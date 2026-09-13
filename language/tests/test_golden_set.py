"""The golden set, run as a test rather than read as a report.

`tools/golden_set.py` is the tool a person runs and reads (`docs/golden-set.md` is what it
said). This file keeps three promises about it:

  - it still runs, offline, with no key, so it is usable on the night;
  - the matcher bugs it caught stay caught — a colour is not a scene, an ordinary short word
    is not corrected into one, and the phrasings it found missing still land;
  - it never quietly claims a rating that nobody has stood on the plaza and made.

The last one is the important one. The set's only real measure is whether a stranger 300 m
away can name what they are seeing, and that is the one number nothing here can compute. A
desk rating that drifts into being quoted as a measurement is worse than no set at all.

The pixel half has the matcher half of this over its own copy (`tests/test_library.py`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app import fallback

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import golden_set  # noqa: E402


@pytest.fixture(scope="module")
def rows():
    return [golden_set.run_one(p) for p in golden_set.GOLDEN]


# ------------------------------------------------------------------ the set itself

def test_there_are_forty_of_them():
    assert len(golden_set.GOLDEN) == 40
    assert len({p.text for p in golden_set.GOLDEN}) == 40, "a phrase is in the set twice"


def test_every_tier_is_exercised(rows):
    """A set that never falls through or never refuses is only testing the happy path."""
    tiers = {r["tier"] for r in rows}
    assert tiers == {"library", "lexicon", "blocked"}, tiers


def test_it_runs_with_no_key_and_no_network(rows):
    """`local_result` is the tier that answers when the model is off, unreachable or slow."""
    for r in rows:
        assert r["word"] == fallback.local_result(str(r["phrase"])).spec_draft["word"]


def test_a_refusal_is_never_given_a_recognizability_rating(rows):
    """Every refusal is the same grey six seconds, so there is nothing per-phrase to rate."""
    for r in rows:
        if r["tier"] == "blocked":
            assert r["rating"] is None, f"{r['phrase']!r} was rated"


def test_the_ratings_are_honest_about_who_made_them():
    """Two failure modes, both silent: an unexplained score, and a desk score worn as a fact."""
    for p in golden_set.GOLDEN:
        if p.rating is None:
            assert p.rated_by == "", f"{p.text!r} has a rater but no rating"
            continue
        assert 1 <= p.rating <= 5, f"{p.text!r} rated {p.rating}"
        assert p.rated_by in ("desk", "plaza", "river"), f"{p.text!r} rated by {p.rated_by!r}"
        assert len(p.note) > 20, f"{p.text!r} has a rating and no reason for it"


def test_every_finding_carries_its_argument(rows):
    """A row that did not land is the report's content, so it must say why it matters."""
    for r in rows:
        if r["verdict"]:
            assert len(str(r["note"])) > 40, f"{r['phrase']!r}: {r['verdict']} and no reasoning"


def test_no_scene_is_unreachable_by_any_phrasing(rows):
    """The forty do not have to touch all 33, but a plain phrasing must reach each one.

    A scene reachable only by typing its own key verbatim exists for the library listing and
    for nobody on the plaza.
    """
    missing = golden_set.unreached_scenes(rows)
    orphans = [k for k in missing if k not in golden_set.probe_reach(missing)]
    assert not orphans, f"no natural phrasing reaches {orphans}"


def test_the_report_prints(rows, capsys):
    golden_set.report(rows)
    out = capsys.readouterr().out
    assert "GOLDEN SET" in out and "library coverage" in out
    assert "PROVENANCE" in out, "the report must say out loud where its numbers came from"


# ------------------------------------------------ the matcher bugs the set caught

@pytest.mark.parametrize("colour", sorted(fallback.COLOURS))
def test_a_colour_is_never_a_scene_on_its_own(colour):
    assert colour not in fallback.INDEX, f"{colour!r} is a keyword for {fallback.INDEX[colour]!r}"


@pytest.mark.parametrize("phrase, wrong", [
    ("i am tired", "i got the job"),     # tired -> hired
    ("shana tova", "merry christmas"),   # shana -> santa
    ("the t is late", "coffee"),         # late  -> latte
    ("a windy night", "i'm so happy"),   # night -> light
    ("a red balloon", "go sox"),         # red   -> red sox
])
def test_an_ordinary_word_is_not_corrected_into_a_scene(phrase, wrong):
    hit = fallback.match(phrase)
    assert hit is None or hit[0] != wrong, f"{phrase!r} -> {hit}"


@pytest.mark.parametrize("typo, key", [
    ("firewroks", "fireworks"), ("chirstmas", "merry christmas"), ("brithday", "birthday"),
    ("graduaton", "graduation"), ("lightining", "thunderstorm"),
])
def test_a_real_misspelling_is_still_forgiven(typo, key):
    hit = fallback.match(typo)
    assert hit is not None and hit[0] == key, f"{typo!r} -> {hit}"


@pytest.mark.parametrize("phrase, key", [
    ("marry me", "she said yes"), ("dunkin", "coffee"), ("sundown", "sunset"),
    ("snowstorm", "snow day"), ("moonrise", "full moon"), ("its pouring", "it's raining"),
    ("the esplanade", "charles river"), ("the milky way", "take me to space"),
    ("fingers crossed", "good luck"), ("congrats", "graduation"),
    ("boston", "city lights"), ("happy new year", "fireworks"),
])
def test_an_obvious_phrasing_reaches_the_scene_that_already_exists(phrase, key):
    hit = fallback.match(phrase)
    assert hit is not None and hit[0] == key, f"{phrase!r} -> {hit}"
