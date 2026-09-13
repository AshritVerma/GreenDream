"""The night side: every dream op renders, scenes end on time, and a prompt keeps
the channel it arrived on.

    python -m pytest -q
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dream import DREAM_OPS, DreamPlayer, DreamScene, compose_offline, dream_spec  # noqa: E402
from genie import request_async  # noqa: E402
from library import LIBRARY  # noqa: E402
from common.inputs import InputBus  # noqa: E402
from scene import validate  # noqa: E402


def _play(scene, dur, fps=30):
    """Render until the scene says it is done; return the elapsed time and peak brightness."""
    t, peak = 0.0, 0.0
    while not scene.done and t < dur * 4:
        peak = max(peak, float(scene.render(t, 1 / fps).px.max()))
        t += 1 / fps
    return t, peak


def _day(n=6):
    return [{"when": "09:00", "text": k, "spec": validate(v), "channel": "web"}
            for k, v in list(LIBRARY.items())[:n]]


def test_every_op_renders_and_ends_on_time():
    rng = random.Random(4)
    base, partner = validate(LIBRARY["rocket launch"]), validate(LIBRARY["birthday"])
    for op in DREAM_OPS:
        spec = dream_spec(base, op, rng, partner=partner)
        spec["duration_s"] = 7.0
        elapsed, peak = _play(DreamScene(spec, 0.0, 11), 7.0)
        assert abs(elapsed - 7.0) < 0.5, f"op {op} ended at {elapsed:.1f}s, expected ~7s"
        assert peak > 0.05, f"op {op} rendered a dark building"


def test_loop_op_restarts_its_own_clock():
    """'loop' is the stutter: the picture keeps restarting while the scene still ends on time."""
    spec = dream_spec(validate(LIBRARY["rocket launch"]), "loop", random.Random(1))
    spec["duration_s"] = 8.0
    scene = DreamScene(spec, 0.0, 7)
    assert scene._elapsed(7.0) < 7.0, "the loop clock never wrapped"
    elapsed, _ = _play(scene, 8.0)
    assert abs(elapsed - 8.0) < 0.5, f"looped scene ended at {elapsed:.1f}s, expected ~8s"


def test_offline_script_plays_end_to_end():
    day = _day()
    script = compose_offline(day, seed=3, cycle=1)
    player = DreamPlayer(script, day, 0.0, 5)
    n_scenes = sum(len(a["scenes"]) for a in script["acts"])
    t = 0.0
    while not player.done and t < 600:
        player.render(t, 1 / 30, depth=0.4)
        t += 1 / 30
    assert player.done, "the dream never finished"
    assert n_scenes >= 5


def test_empty_day_still_dreams():
    script = compose_offline([], seed=1, cycle=1)
    assert script["acts"] and script["acts"][0]["scenes"]
    player = DreamPlayer(script, [], 0.0, 2)
    player.render(0.0, 1 / 30)   # must not raise on a scene with no sources


def test_prompt_keeps_its_channel():
    """Two overlapping prompts must not swap sources (they used to share one field)."""
    bus = InputBus()
    request_async("thunderstorm", bus, offline=True, source="phone")
    request_async("calm ocean", bus, offline=True, source="pedestal")
    deadline = time.time() + 5
    specs = []
    while time.time() < deadline and len(specs) < 2:
        specs += [e for e in bus.poll() if e.get("type") == "spec"]
        time.sleep(0.02)
    assert len(specs) == 2, f"only got {len(specs)} specs"
    got = {e["text"]: e["source"] for e in specs}
    assert got == {"thunderstorm": "phone", "calm ocean": "pedestal"}, got
