"""The digest + render path: five words in, a playable clip out, without the API.

    python -m pytest -q tests/test_render.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.canvas import COLS, ROWS  # noqa: E402
from common.displays import frame_to_hex  # noqa: E402
from genie import MAX_WORDS, clip_words  # noqa: E402
from render import (DECIMATE, RENDER_FPS, Budget, Service, SpecCache,  # noqa: E402
                    canvas_hex, digest, render_spec, seed_for)
from scene import Performance, validate  # noqa: E402


def _short(**over):
    return validate(dict({"duration_s": 6}, **over))


# ------------------------------------------------------------------ five words

def test_clip_words_keeps_five():
    assert clip_words("one two three four five six seven") == "one two three four five"
    assert len(clip_words("a b c d e f g").split()) == MAX_WORDS


def test_clip_words_survives_junk():
    assert clip_words("   spaced    out   ") == "spaced out"
    assert clip_words("") == ""
    assert clip_words(None) == ""


def test_digest_clips_before_answering():
    spec, _ = digest("one two three four five six seven eight", offline=True)
    assert spec["ok"] and spec["title"]


# ---------------------------------------------------------------------- digest

def test_library_phrase_is_free_and_instant():
    spec, tier = digest("thunderstorm", offline=True)
    assert tier == "library"
    assert spec["world"] == "storm"


def test_unknown_phrase_falls_to_lexicon_offline():
    spec, tier = digest("quixotic parsnip vestibule", offline=True)
    assert tier == "lexicon"
    assert spec["ok"] and 6 <= spec["duration_s"] <= 20


def test_blocklist_is_enforced_here_not_only_in_genie():
    # lookup() and lexicon_spec() never check it, and this is the one path where a
    # phrase becomes pixels without the model getting a chance to refuse.
    spec, tier = digest("kill everyone", offline=True)
    assert tier == "blocked"
    assert spec["title"] == "shrug"


def test_empty_text_does_not_explode():
    spec, tier = digest("   ", offline=True)
    assert tier == "empty" and spec["ok"]


# ---------------------------------------------------------------------- render

def test_fast_hex_matches_the_display_path_exactly():
    # canvas_hex skips Frame/Color for speed; if it ever stops agreeing with the
    # path that actually drives the building, every archived clip is subtly wrong.
    from utilities.display import Frame

    perf = Performance(_short(particles={"kind": "snow", "density": 0.7, "direction": "down"}), 0.0, seed=5)
    frame = Frame()
    for i in range(20):
        cv = perf.render(i / 30.0, 1 / 30.0)
        assert canvas_hex(cv) == frame_to_hex(cv.to_frame(frame))


def test_recording_shape_and_hex():
    rec = render_spec(_short(), seed=1)
    assert rec["rows"] == ROWS and rec["cols"] == COLS
    assert rec["frames"], "nothing was rendered"
    for hx in rec["frames"][::10]:
        assert len(hx) == ROWS * COLS * 6
        int(hx, 16)


def test_generated_at_30_then_decimated():
    # Particles.update spawns per call, so generating below 30 fps thins the rain.
    # Playback is halved on the way out, which must not change the wall-clock length.
    spec = _short()
    rec = render_spec(spec, seed=1)
    assert rec["fps"] == RENDER_FPS / DECIMATE
    expected = round(spec["duration_s"] * RENDER_FPS) // DECIMATE
    assert abs(len(rec["frames"]) - expected) <= 1
    assert abs(len(rec["frames"]) / rec["fps"] - spec["duration_s"]) < 0.2


def test_same_seed_renders_the_same_clip():
    spec = _short(particles={"kind": "rain", "density": 0.8, "direction": "down"})
    assert render_spec(spec, seed=7)["frames"] == render_spec(spec, seed=7)["frames"]


def test_seed_is_derived_from_the_phrase():
    assert seed_for("calm ocean") == seed_for("Calm Ocean!")
    assert seed_for("calm ocean") != seed_for("thunderstorm")


def test_something_actually_lights_up():
    rec = render_spec(_short(world="none"), seed=3)
    lit = [f for f in rec["frames"] if f.count("000000") < ROWS * COLS]
    assert len(lit) > len(rec["frames"]) // 2, "the building stayed dark"


# ----------------------------------------------------------------------- cache

def test_cache_round_trips_and_normalizes():
    c = SpecCache()
    spec, _ = digest("thunderstorm", offline=True)
    c.put("thunderstorm", spec, "library")
    assert c.get("  Thunderstorm ")[1] == "library"


def test_lexicon_answers_are_not_cached():
    # Caching one would make a temporary API outage permanent.
    c = SpecCache()
    spec, tier = digest("quixotic parsnip vestibule", offline=True)
    c.put("quixotic parsnip vestibule", spec, tier)
    assert c.get("quixotic parsnip vestibule") is None


def test_cache_evicts_oldest():
    c = SpecCache(cap=2)
    for name in ("a", "b", "c"):
        c.put(name, _short(), "library")
    assert len(c) == 2
    assert c.get("a") is None


# ---------------------------------------------------------------------- budget

def test_per_ip_burst_trips():
    b = Budget(daily_model_calls=10, per_ip_per_min=2)
    assert b.allow_ip("1.2.3.4") and b.allow_ip("1.2.3.4")
    assert not b.allow_ip("1.2.3.4")
    assert b.allow_ip("5.6.7.8"), "one visitor must not lock out everyone"


def test_daily_cap_degrades_instead_of_failing():
    b = Budget(daily_model_calls=0, per_ip_per_min=99)
    assert not b.take_model_call()
    # With no model calls left the digest still answers, one tier down.
    spec, tier = digest("quixotic parsnip vestibule", offline=False, budget=b)
    assert tier == "lexicon" and spec["ok"]


def test_library_hits_do_not_spend_budget():
    b = Budget(daily_model_calls=1, per_ip_per_min=99)
    digest("thunderstorm", offline=True, budget=b)
    assert b.state()["model_calls_used"] == 0


# ---------------------------------------------------------------------- service

def test_service_preview_is_playable_and_caches():
    s = Service(offline=True)
    first = s.preview("thunderstorm")
    assert first["ok"] and first["rec"]["frames"] and first["cached"] is False
    assert first["seed"] == seed_for("thunderstorm")
    again = s.preview("Thunderstorm")
    assert again["cached"] is True
    assert again["rec"]["frames"] == first["rec"]["frames"]


def test_service_reports_the_clipped_phrase():
    s = Service(offline=True)
    out = s.preview("one two three four five six")
    assert out["text"] == "one two three four five"


def test_clip_cache_is_bounded():
    s = Service(offline=True, clip_cap=2)
    for phrase in ("thunderstorm", "calm ocean", "birthday"):
        s.preview(phrase)
    assert len(s._clips) == 2


def test_warm_makes_the_library_instant():
    s = Service(offline=True)
    assert s.warm(["thunderstorm", "birthday"]) == 2
    assert s.preview("thunderstorm")["cached"] is True
    assert s.preview("thunderstorm")["ms"] < 200, "a warmed phrase should not re-render"
