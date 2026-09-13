"""The scene contract: beats put a scene in time, validate() never trusts its input,
and the matcher hears what people actually say.

    python -m pytest -q tests/test_scene.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from library import (ALIASES, BEATS, ENTRIES, INDEX, LIBRARY, library_spec,  # noqa: E402
                     lookup, match, normalize)
from scene import (BEAT_FLOOR, MAX_BEATS, SHRUG, Performance, clean_word,  # noqa: E402
                   validate)


# ------------------------------------------------------------------------ beats

def test_a_scene_is_an_event_in_time():
    beats = validate(library_spec("lebron dunk"))["beats"]
    assert [b["label"] for b in beats] == ["the approach", "the leap", "it lands", "the crowd"]
    assert [b["at"] for b in beats] == sorted(b["at"] for b in beats)
    assert beats[0]["brightness"] < beats[2]["brightness"] == 1.0, "the impact is the bright moment"
    assert beats[0]["word"] is None and beats[2]["word"] == "DUNK!", "the word waits for the landing"


def test_a_beat_inherits_what_it_does_not_name():
    spec = validate({
        "motion": {"kind": "sweep", "speed": 0.4, "amount": 0.9},
        "particles": {"kind": "snow", "density": 0.6, "direction": "down"},
        "word": "HELLO",
        "beats": [{"at": 0, "brightness": 0.5}, {"at": 0.5, "motion": {"speed": 1.0}}],
    })
    first, second = spec["beats"]
    assert first["motion"] == spec["motion"], "named nothing, so it is the scene"
    assert second["motion"] == {"kind": "sweep", "speed": 1.0, "amount": 0.9}, "only speed changed"
    assert second["particles"]["kind"] == "snow"
    assert first["word"] == "HELLO", "an absent word inherits"
    assert validate({"word": "HI", "beats": [{"at": 0, "word": None}, {"at": 0.5}]})["beats"][0]["word"] is None, \
        "an explicit null is a deliberate silence"


@pytest.mark.parametrize("raw, why", [
    ("nonsense", "not a list"),
    ([], "empty"),
    ([{"at": 0}], "one phase is not a timeline"),
    (["x", 3], "no usable entries"),
])
def test_unusable_beats_degrade_to_a_held_scene(raw, why):
    assert validate({"beats": raw})["beats"] == [], why


def test_beats_are_ordered_clamped_and_never_collide():
    ats = [b["at"] for b in validate({"beats": [{"at": 9}, {"at": 0.4}, {"at": 0.4}, {"at": -2}]})["beats"]]
    assert ats[0] == 0.0, "the first beat opens the scene"
    assert ats == sorted(ats) and len(set(ats)) == len(ats), "two beats cannot land on one instant"
    assert all(0.0 <= a <= 1.0 for a in ats)
    assert len(validate({"beats": [{"at": i / 10} for i in range(9)]})["beats"]) == MAX_BEATS


def test_no_beat_leaves_the_tower_looking_switched_off():
    # From the street a near-black facade reads as broken, not as a quiet moment.
    beats = validate({"beats": [{"at": 0, "brightness": 0.0}, {"at": 0.5, "brightness": 0.01}]})["beats"]
    assert all(b["brightness"] >= BEAT_FLOOR for b in beats)


def test_beats_actually_drive_the_render():
    quiet = validate(dict(library_spec("lebron dunk"), duration_s=10))
    perf = Performance(quiet, 0.0, seed=3)
    opening = max(float(perf.render(t / 30.0, 1 / 30.0).px.max()) for t in range(0, 45))
    perf2 = Performance(quiet, 0.0, seed=3)
    for t in range(0, 190):        # play up to the landing
        cv = perf2.render(t / 30.0, 1 / 30.0)
    impact = float(cv.px.max())
    assert impact > opening, f"the impact ({impact:.2f}) should outshine the approach ({opening:.2f})"


def test_a_scene_with_beats_still_ends_on_time():
    spec = validate(dict(library_spec("thunderstorm"), duration_s=7))
    perf = Performance(spec, 0.0, seed=1)
    t = 0.0
    while not perf.done and t < 30:
        perf.render(t, 1 / 30)
        t += 1 / 30
    assert abs(t - 7.0) < 0.5


# -------------------------------------------------------------------- validate

def test_validate_is_idempotent_and_drops_foreign_keys():
    once = validate(dict(library_spec("thunderstorm"), schema_version="spec-v1", _echo=True, junk=1))
    assert validate(once) == once
    assert "_echo" not in once and "junk" not in once and "schema_version" not in once


def test_validate_clamps_hostile_input():
    spec = validate({"title": "x" * 200, "duration_s": 9999, "world": "moon", "tempo_bpm": -5,
                     "palette": {"base": "nope", "accent": "#GGGGGG"},
                     "motion": {"kind": "teleport", "speed": 12, "amount": -3},
                     "particles": {"kind": "frogs", "density": 5, "direction": "sideways"},
                     "word": "hello there friend", "mood": {"valence": 9, "arousal": -9}})
    assert len(spec["title"]) <= 40
    assert 6 <= spec["duration_s"] <= 20 and 30 <= spec["tempo_bpm"] <= 200
    assert spec["world"] == "none" and spec["motion"]["kind"] == "breathe"
    assert spec["palette"]["base"].startswith("#") and len(spec["palette"]["base"]) == 7
    assert 0 <= spec["motion"]["speed"] <= 1 and 0 <= spec["particles"]["density"] <= 1
    assert len(spec["word"]) <= 7
    assert -1 <= spec["mood"]["valence"] <= 1 and 0 <= spec["mood"]["arousal"] <= 1


def test_garbage_is_still_a_playable_spec():
    for junk in (None, [], "text", 7, {"beats": "no"}):
        spec = validate(junk)
        assert Performance(spec, 0.0).render(0.0, 1 / 30) is not None


def test_the_facade_never_shows_raw_text():
    # Whatever arrives, what comes out is at most 7 characters of A-Z, space, ! and ?.
    # There is no input that gets more than that onto the windows.
    for raw in ("hi there!", "123 456", "<script>alert(1)</script>", "Kill them all",
                "señor", "a much longer sentence than fits", "!!!", "  ", None, 7, ["HI"]):
        w = clean_word(raw)
        assert w is None or (len(w) <= 7 and re.fullmatch(r"[A-Z!? ]+", w)), repr(raw)
    assert clean_word("hi there!") == "HI THER"
    assert clean_word("123 456") is None, "digits are not displayable, so nothing is left"
    assert clean_word(None) is None and clean_word("") is None


def test_not_ok_becomes_a_shrug_and_the_shrug_is_a_fixed_point():
    assert validate({"ok": False, "title": "something"})["title"] == "shrug"
    assert validate(SHRUG) == SHRUG
    assert SHRUG["ok"] is False, "a refusal must be distinguishable from a scene"
    assert SHRUG["beats"] == [], "we are not choreographing a refusal"


# --------------------------------------------------------------------- matcher

def test_every_library_entry_is_a_valid_scene():
    for key in ENTRIES:
        spec = validate(library_spec(key))
        assert spec["ok"] and spec["title"], key
        assert spec["beats"] == validate(library_spec(key))["beats"], key
        if key in BEATS:
            assert len(spec["beats"]) >= 2, f"{key} declares beats but they did not survive validation"


def test_every_alias_points_somewhere_real():
    for alias, key in ALIASES.items():
        assert key in ENTRIES, f"{alias} -> {key} is a dangling alias"


@pytest.mark.parametrize("phrase, key", [
    ("thunderstorm", "thunderstorm"),
    ("a huge THUNDERSTORM!!", "thunderstorm"),
    ("it is raining outside", "it's raining"),
    ("lebron dunk as 76er", "lebron dunk"),
    ("happy birthday mom", "birthday"),
    ("go celtics", "go celtics"),
    ("the charles river", "charles river"),
    ("i love you", "i love you"),
    ("thundrstorm", "thunderstorm"),          # a typo is still the word it meant
    ("take me to space", "take me to space"),
])
def test_the_matcher_hears_the_phrase(phrase, key):
    hit = match(phrase)
    assert hit is not None, f"{phrase!r} matched nothing"
    assert hit[0] == key, f"{phrase!r} -> {hit[0]}, expected {key}"


def test_a_phrase_beats_a_word_inside_it():
    # "no rain" is about rain only if you ignore the "no"; the phrase pass must win first.
    assert match("charles river")[0] == "charles river"
    assert match("river")[0] == "charles river"


def test_negated_words_do_not_match():
    assert match("not snow") is None or match("not snow")[0] != "snow day"
    assert match("no rain please") is None or match("no rain please")[0] != "it's raining"


def test_a_bare_substring_is_not_a_match():
    # the old matcher used `phrase in text`, so "supper" contained "up" and became an arrow.
    hit = match("supper")
    assert hit is None or hit[0] != "go up"


def test_lookup_returns_a_spec_with_its_choreography():
    spec = lookup("lebron dunk")
    assert spec is not None and spec["beats"], "the scene lost its beats on the way out"
    assert validate(spec)["title"] == LIBRARY["lebron dunk"]["title"]


def test_nothing_matches_nonsense():
    assert lookup("quixotic parsnip vestibule") is None
    assert lookup("") is None and lookup("   ") is None


def test_normalize_keeps_digits_and_apostrophes():
    assert normalize("lebron dunk as 76er") == "lebron dunk as 76er"
    assert normalize("IT'S RAINING!") == "it's raining"


def test_surprise_me_is_a_scene_and_is_stable_within_a_day():
    hit = match("surprise me")
    assert hit is not None and hit[1] == "surprise"
    assert hit[0] in ENTRIES
    assert match("surprise me")[0] == hit[0], "the cache would defeat a per-request random anyway"


def test_the_index_never_points_at_a_missing_entry():
    for word, key in INDEX.items():
        assert key in ENTRIES, f"{word} -> {key}"
