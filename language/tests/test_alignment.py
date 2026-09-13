"""The two halves must agree about what a scene is.

This service decides what five words mean; GreenDream turns the answer into light. The warm
library is duplicated on purpose - neither repo should import the other - so the copies can
drift, and a drifted copy means the preview someone approved is not the scene that plays.

These tests read GreenDream's `library.py` and `scene.py` directly and compare. Both halves
now live in one repo — this service is the `language/` subdirectory of it — so the pixel side
is always there and a missing one is a failure rather than a skip.

Point GREENDREAM_PATH at a checkout to compare against a different one.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Optional

import pytest

from app import fallback, spec as spec_mod

HERE = Path(__file__).resolve().parent.parent


def _greendream_root() -> Optional[Path]:
    """The pixel half: the repo this service is a subdirectory of, or GREENDREAM_PATH."""
    env = os.environ.get("GREENDREAM_PATH")
    candidates = [Path(env)] if env else []
    candidates.append(HERE.parent)
    for path in candidates:
        if (path / "library.py").is_file() and (path / "scene.py").is_file():
            return path
    return None


ROOT = _greendream_root()
assert ROOT is not None, (
    f"the pixel half is not at {HERE.parent} (library.py, scene.py). This service lives inside "
    "the GreenDream repo; set GREENDREAM_PATH to compare against a checkout elsewhere."
)


def _load(name: str):
    """Import a GreenDream module by path ("library", "sensors/llm"), with its root importable.

    Appended, never prepended: the repo root holds a top-level `app.py` and this service holds a
    top-level `app/` package, so putting the root first would silently shadow our own `app`.
    """
    if str(ROOT) not in sys.path:
        sys.path.append(str(ROOT))
    path = ROOT.joinpath(*f"{name}.py".split("/"))
    spec = importlib.util.spec_from_file_location("_gd_" + name.replace("/", "_"), path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gd_library():
    return _load("library")


@pytest.fixture(scope="module")
def gd_scene():
    return _load("scene")


# --------------------------------------------------------------------------- the library

def test_the_two_libraries_hold_the_same_scenes(gd_library):
    assert set(fallback.LIBRARY) == set(gd_library.ENTRIES), \
        "a scene exists on one side only, so a preview would not match the performance"


def test_every_scene_is_identical_field_for_field(gd_library):
    for key in fallback.LIBRARY:
        mine, theirs = fallback.LIBRARY[key], gd_library.ENTRIES[key]
        assert mine["theme"] == theirs["theme"], key
        assert mine["keywords"] == theirs["keywords"], key
        assert mine["spec"] == theirs["spec"], f"{key}: the scene itself differs"


def test_the_choreography_is_identical(gd_library):
    assert fallback.BEATS == gd_library.BEATS, "the same scene would be paced differently"


def test_the_aliases_are_identical(gd_library):
    assert fallback.ALIASES == gd_library.ALIASES, "the same words would reach different scenes"
    assert fallback.SURPRISE == gd_library.SURPRISE


def test_the_matcher_agrees_on_what_people_say(gd_library):
    phrases = ["thunderstorm", "a huge THUNDERSTORM!!", "lebron dunk as 76er", "happy birthday mom",
               "the charles river", "it is raining outside", "go celtics", "not snow",
               "supper", "quixotic parsnip", "i love you", "thundrstorm", "no rain please",
               "my exhausted heart is racing", "storm dunk 76er", "coffee please", "the moon"]
    for phrase in phrases:
        mine = fallback.match(phrase)
        theirs = gd_library.match(phrase)
        assert (mine is None) == (theirs is None), f"{phrase!r}: one side matched and the other did not"
        if mine and theirs:
            assert mine[0] == theirs[0], f"{phrase!r}: {mine[0]} here, {theirs[0]} there"


def test_every_advertised_scene_is_reachable():
    """`/api/library` publishes these keys, so each must be reachable by saying it.

    The old matcher advertised scenes that no natural phrasing could reach, which made the
    endpoint a promise the service could not keep.
    """
    for key in fallback.LIBRARY:
        hit = fallback.lookup(key)
        assert hit is not None, f"{key!r} is advertised but matches nothing"
        assert hit[0] == key, f"saying {key!r} gives {hit[0]!r}"


def test_every_alias_reaches_the_scene_it_names():
    for alias, key in fallback.ALIASES.items():
        hit = fallback.lookup(alias)
        assert hit is not None and hit[0] == key, f"{alias!r} -> {hit and hit[0]}, expected {key}"


def test_normalize_agrees(gd_library):
    for raw in ("lebron dunk as 76er", "IT'S RAINING!", "  a   storm  ", "señor", "<script>"):
        assert fallback.normalize(raw) == gd_library.normalize(raw), raw


# --------------------------------------------------------------------------- the spec

def test_the_vocabularies_are_the_same(gd_scene):
    assert set(spec_mod.WORLD_NAMES) == set(gd_scene.WORLD_NAMES)
    assert spec_mod.MOTIONS == gd_scene.MOTIONS
    assert spec_mod.PARTICLES == gd_scene.PARTICLES
    assert spec_mod.FLASHES == gd_scene.FLASHES
    assert spec_mod.SPRITE_ANIMS == gd_scene.SPRITE_ANIMS
    assert spec_mod.MAX_BEATS == gd_scene.MAX_BEATS
    assert spec_mod.BEAT_FLOOR == gd_scene.BEAT_FLOOR
    assert (spec_mod.ROWS, spec_mod.COLS) == (gd_scene.ROWS, gd_scene.COLS)


def test_a_draft_from_here_survives_the_renderer_unchanged(gd_scene):
    """The whole contract: what we produce is what it plays.

    The renderer drops `schema_version` (it rebuilds from known fields), so that one key is
    allowed to differ. Everything that decides what the windows do must not.
    """
    for key in fallback.LIBRARY:
        ours = fallback.local_result(key).spec_draft
        theirs = gd_scene.validate(ours)
        mine = {k: v for k, v in ours.items() if k != "schema_version"}
        assert mine == theirs, f"{key}: the renderer changed our draft"


def test_a_model_shaped_draft_also_survives(gd_scene):
    raw = {"ok": True, "title": "a test", "duration_s": 11, "world": "aurora",
           "palette": {"base": "#010203", "accent": "#0a0b0c", "glow": "#ffffff"},
           "motion": {"kind": "sweep", "speed": 0.4, "amount": 0.6},
           "particles": {"kind": "snow", "density": 0.5, "direction": "down"},
           "tempo_bpm": 88, "flash": {"kind": "burst", "rate": 0.4},
           "sprite": {"rows": fallback.HEART, "anim": "pulse", "color": "#ff0000"},
           "word": "HI", "mood": {"valence": 0.5, "arousal": 0.5},
           "beats": [{"at": 0, "label": "in", "brightness": 0.4, "word": None},
                     {"at": 0.6, "label": "out", "brightness": 1.0}]}
    ours = spec_mod.validate(raw)
    theirs = gd_scene.validate(ours)
    assert {k: v for k, v in ours.items() if k != "schema_version"} == theirs


def test_the_shrug_is_the_same_refusal(gd_scene):
    ours = spec_mod.shrug()
    theirs = gd_scene.SHRUG
    assert ours["word"] == theirs["word"] == "HMM?"
    assert ours["ok"] is theirs["ok"] is False, "both sides must call a refusal a refusal"
    assert ours["palette"] == theirs["palette"] and ours["beats"] == theirs["beats"] == []


def test_the_word_cleaner_agrees(gd_scene):
    for raw in ("hello there", "123", "hi!", "<script>", "", None, "a much longer phrase"):
        assert spec_mod.clean_word(raw) == gd_scene.clean_word(raw), repr(raw)


def test_the_blocklist_agrees_on_the_cases_that_matter():
    """Both sides screen, so both must screen the same things.

    The runner's list exists for prompts typed straight at it; this one for everything that
    arrives over the web. They are separate regexes, and these are the phrases where a
    disagreement would actually let something through.
    """
    genie = _load("genie")
    blocked = ["kill everyone", "i want to kill someone", "kill myself", "i want to die",
               "nazi rally", "vote for someone", "buy bitcoin now", "fuck this",
               "she is a whore", "call me 555 1234"]
    allowed = ["thunderstorm", "kill the lights", "my heart is racing", "lebron dunk",
               "a killer bassline", "go celtics", "sunset over boston"]
    for phrase in blocked:
        assert fallback.is_blocked(phrase), f"the service let {phrase!r} through"
        assert genie.BLOCKLIST.search(phrase), f"the runner let {phrase!r} through"
    for phrase in allowed:
        assert not fallback.is_blocked(phrase), f"the service refused {phrase!r}"
        assert not genie.BLOCKLIST.search(phrase), f"the runner refused {phrase!r}"


def test_the_lexicon_agrees_on_mood():
    module = _load("sensors/llm")
    for phrase in ("i am so happy", "not happy at all", "finals week", "the T is late", "wow!"):
        mine = fallback.lexicon_affect(phrase)
        theirs = module.lexicon_affect(phrase)
        assert mine["emotion"] == theirs["emotion"], phrase
        assert abs(mine["valence"] - theirs["valence"]) < 0.01, phrase
        assert abs(mine["arousal"] - theirs["arousal"]) < 0.01, phrase
    assert fallback.EMOTION_WORD == module.EMOTION_WORD
