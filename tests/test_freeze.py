"""The kill switch: "stop showing anything, right now".

A freeze has to work from any phase, take effect on the next frame, survive the phase
changing underneath it, and come back to a sane building. The facade it leaves behind has
to read as deliberate rather than broken, which here means: lit, flat, dim, and moving
slowly enough that nothing about it is a scene.

    python -m pytest -q tests/test_freeze.py
"""

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

import app as app_module  # noqa: E402
import freeze as freeze_module  # noqa: E402
from common.canvas import Canvas  # noqa: E402
from common.displays import NullDisplay  # noqa: E402
from common.engine import Context  # noqa: E402
from common.inputs import InputBus  # noqa: E402
from common.webserver import ControlServer, secret  # noqa: E402
from dream import compose_offline  # noqa: E402
from library import LIBRARY  # noqa: E402
from main import APP  # noqa: E402
from scene import validate  # noqa: E402

FPS = 30.0
DT = 1.0 / FPS


class _Args:
    offline = True
    time_scale = 1.0
    start_hour = 12.0
    journal = os.path.join(tempfile.gettempdir(), "greendream_test_journal")
    freeze_file = ""          # the watcher thread is driven by hand in these tests


def _app(hour=12.0):
    gd = APP()
    bus = InputBus()
    args = _Args()
    args.start_hour = hour
    ctx = Context(display=NullDisplay(), bus=bus, args=args, server=None)
    gd.setup(ctx)
    return gd, ctx


def _tick(gd, ctx, frames=1, t0=None):
    """Run the frame loop by hand; return the last canvas drawn."""
    t = ctx.t if t0 is None else t0
    cv = Canvas()
    for _ in range(frames):
        t += DT
        ctx.t = t
        cv = Canvas()
        gd.update(DT, t, cv, ctx)
        ctx.frame_index += 1
    return cv


def _spec_event(**over):
    return dict({"type": "spec", "text": "thunderstorm", "spec": validate(LIBRARY["thunderstorm"]),
                 "tier": "library", "source": "pedestal", "priority": "live"}, **over)


def _is_standby(px) -> bool:
    """The frozen field: every window the same colour, dim, lit, and warm."""
    flat = px.reshape(-1, 3)
    return bool(flat.min() > 0.0
                and flat.std(axis=0).max() < 1e-6
                and px.mean() < 0.2
                and flat[0][0] > flat[0][2])


# ------------------------------------------------------------------ what frozen looks like

def test_standby_is_lit_flat_and_dim_not_a_black_tower():
    gd, ctx = _app()
    gd.on_event({"type": "freeze", "on": True}, ctx)
    px = _tick(gd, ctx).px
    assert _is_standby(px), "a dark tower reads as broken; standby has to read as deliberate"
    assert px.mean() < 0.15, "calm: the same band as the building's own resting states"
    assert px.min() > 0.01 and px[..., 0].min() > 0.05, "...and no window is off"


def test_standby_breathes_so_it_is_not_a_stuck_frame():
    gd, ctx = _app()
    gd.on_event({"type": "freeze", "on": True}, ctx)
    levels = [_tick(gd, ctx).px.mean() for _ in range(int(app_module.FREEZE_BREATH_S * FPS) + 2)]
    assert max(levels) - min(levels) > 0.01, "it has to be visibly alive"
    per_frame = max(abs(b - a) for a, b in zip(levels, levels[1:]))
    assert per_frame < 0.01, "and slow enough that --gentle never has to touch it"


def test_standby_does_not_look_like_the_sleeping_building():
    # An operator reading the facade from the plaza must be able to tell held from asleep.
    gd, ctx = _app(hour=23.0)
    night = _tick(gd, ctx, frames=30).px
    gd.on_event({"type": "freeze", "on": True}, ctx)
    held = _tick(gd, ctx).px
    assert held[..., 0].mean() > held[..., 2].mean(), "standby is warm"
    assert night[..., 2].mean() > night[..., 0].mean(), "the night is cold"
    assert app_module.FREEZE_BREATH_S != 8.0, "a different breath period from _render_night's"


# ------------------------------------------------------------------ freezing from any phase

def test_freeze_takes_effect_on_the_very_next_frame():
    gd, ctx = _app()
    gd.on_event(_spec_event(), ctx)
    _tick(gd, ctx, frames=20)
    assert gd.current is not None, "mid-performance"
    gd.on_event({"type": "freeze", "on": True}, ctx)
    assert _is_standby(_tick(gd, ctx, frames=1).px), "one frame, not a fade"


def test_frozen_mid_performance_drops_the_scene_and_its_queue():
    gd, ctx = _app()
    for _ in range(3):
        gd.on_event(_spec_event(), ctx)
    _tick(gd, ctx, frames=20)
    assert gd.current is not None and gd.queue

    gd.on_event({"type": "freeze", "on": True}, ctx)
    assert gd.current is None and not gd.queue, "whatever was up is the thing that was wrong"
    for _ in range(60):
        assert _is_standby(_tick(gd, ctx).px)


def _dreaming(gd, ctx):
    """Get a dream actually playing: the real composer runs on a thread against the global
    bus, so the script is composed here and handed in as the event that thread would push."""
    gd.on_event(_spec_event(source="web", priority="dream"), ctx)
    gd.on_event({"type": "phase", "name": "night"}, ctx)
    _tick(gd, ctx, frames=2)                       # descent takes the snapshot and asks
    script = compose_offline(gd.dream_material, seed=7, cycle=1)
    gd.on_event({"type": "dream_script", "script": script, "tier": "offline", "cycle": 1}, ctx)
    for _ in range(int(FPS * 12)):                 # descent holds for 6 s before it plays
        _tick(gd, ctx)
        if gd.dream is not None:
            return
    raise AssertionError("no dream started; this test cannot say anything without one")


def test_frozen_mid_dream_drops_the_dream():
    gd, ctx = _app()
    _dreaming(gd, ctx)
    assert gd.dream_stage == "dream"

    gd.on_event({"type": "freeze", "on": True}, ctx)
    assert gd.dream is None
    assert _is_standby(_tick(gd, ctx).px)


def test_frozen_while_idle_and_while_waking():
    for hour, phase in ((12.0, "DAY"), (6.4, "DAWN"), (19.0, "DUSK"), (2.0, "NIGHT")):
        gd, ctx = _app(hour=hour)
        _tick(gd, ctx, frames=3)
        assert gd.phase == phase, f"{hour} should be {phase}, got {gd.phase}"
        gd.on_event({"type": "freeze", "on": True}, ctx)
        assert _is_standby(_tick(gd, ctx).px), phase


def test_the_shimmer_and_the_marquee_do_not_show_through():
    gd, ctx = _app()
    gd.on_event({"type": "freeze", "on": True}, ctx)
    gd.pending = 1                                    # a prompt is in flight
    gd.marquee = app_module.Marquee("HELLO", (1.0, 1.0, 1.0), speed=7.0)
    assert _is_standby(_tick(gd, ctx).px), "nothing draws on top of a held facade"
    assert gd.marquee is None, "and a marquee is dropped rather than saved for the thaw"


# ------------------------------------------------------------------ it is not a phase

def test_freeze_survives_the_phase_changing_underneath_it():
    gd, ctx = _app(hour=12.0)
    _tick(gd, ctx, frames=3)
    gd.on_event({"type": "freeze", "on": True}, ctx)
    gd.on_event({"type": "phase", "name": "night"}, ctx)
    _tick(gd, ctx, frames=int(FPS * 5))
    assert gd.frozen is True, "a phase override is not a thaw"
    assert gd.phase == "NIGHT", "the phase machine kept running underneath"
    assert _is_standby(_tick(gd, ctx).px)


def test_the_clock_keeps_running_while_frozen():
    gd, ctx = _app(hour=12.0)
    gd.scale = 3600.0                                  # one second of real time is one hour
    gd.on_event({"type": "freeze", "on": True}, ctx)
    before = gd.hour
    _tick(gd, ctx, frames=int(FPS * 2))
    assert gd.hour > before + 1.0, "it knows what time it is; it is just not showing it"


def test_skip_and_dream_now_cannot_lift_a_freeze():
    gd, ctx = _app()
    gd.on_event({"type": "freeze", "on": True}, ctx)
    for ev in ({"type": "skip"}, {"type": "phase", "name": "night"}, {"type": "set_hour", "hour": 8}):
        gd.on_event(ev, ctx)
        assert gd.frozen is True and _is_standby(_tick(gd, ctx).px), ev


def test_freezing_twice_is_not_a_new_freeze():
    gd, ctx = _app()
    gd.on_event({"type": "freeze", "on": True}, ctx)
    _tick(gd, ctx, frames=10)
    t0 = gd.freeze_t0
    gd.on_event({"type": "freeze", "on": True}, ctx)
    assert gd.freeze_t0 == t0, "the swell does not restart because somebody pressed it again"


def test_a_toggle_flips_whatever_it_finds():
    gd, ctx = _app()
    gd.on_event({"type": "freeze", "toggle": True}, ctx)
    assert gd.frozen is True
    gd.on_event({"type": "freeze", "toggle": True}, ctx)
    assert gd.frozen is False


# ------------------------------------------------------------------ prompts during a freeze

def test_a_prompt_arriving_frozen_is_kept_but_never_performed():
    gd, ctx = _app()
    gd.on_event({"type": "freeze", "on": True}, ctx)
    gd.on_event(_spec_event(text="rocket launch"), ctx)

    assert gd.day[-1]["text"] == "rocket launch", "nobody's words are thrown away"
    assert not gd.queue, "but nothing is owed to the facade when it comes back"
    assert gd.mumble is None, "and a held building does not acknowledge it either"
    assert _is_standby(_tick(gd, ctx).px)


def test_what_was_said_during_a_freeze_still_reaches_the_night():
    gd, ctx = _app()
    gd.on_event({"type": "freeze", "on": True}, ctx)
    gd.on_event(_spec_event(text="snow day"), ctx)
    gd.on_event({"type": "freeze", "on": False}, ctx)
    gd.on_event({"type": "phase", "name": "night"}, ctx)
    _tick(gd, ctx, frames=int(FPS * 2))

    assert [d["text"] for d in gd.dream_material] == ["snow day"], \
        "the words were held; only the performance was dropped"


def test_a_freeze_does_not_close_intake():
    # Two separate switches, deliberately: the service's gate is the intake kill switch and
    # this is the display one. A frozen facade still collects the day.
    gd, ctx = _app()
    gd.on_event({"type": "freeze", "on": True}, ctx)
    gd.on_event({"type": "text", "text": "thunderstorm"}, ctx)
    assert gd.pending == 1, "the request still goes out; it just has nowhere to be shown"


def test_the_queue_does_not_refill_itself_from_the_day():
    gd, ctx = _app()
    for i in range(4):
        gd.on_event(_spec_event(text=f"prompt {i}"), ctx)
    gd.on_event({"type": "freeze", "on": True}, ctx)
    gd.on_event({"type": "freeze", "on": False}, ctx)
    _tick(gd, ctx, frames=int(FPS * 3))
    assert not gd.queue and gd.current is None, "no backlog is dumped onto the facade on thaw"


# ------------------------------------------------------------------ coming back

def test_thawing_fades_up_into_whatever_is_running_now():
    gd, ctx = _app()
    gd.on_event({"type": "freeze", "on": True}, ctx)
    held = _tick(gd, ctx, frames=10).px.copy()
    gd.on_event({"type": "freeze", "on": False}, ctx)

    first = _tick(gd, ctx, frames=1).px
    assert np.allclose(first, held, atol=0.02), "no jump cut on the way back"
    mid = _tick(gd, ctx, frames=int(FPS * app_module.THAW_S / 2)).px
    assert not _is_standby(mid), "it is on its way out"
    after = _tick(gd, ctx, frames=int(FPS * app_module.THAW_S) + 4).px
    assert not _is_standby(after) and after.max() > 0.1, "and it is the awake building again"


def test_thawing_lands_in_the_phase_the_clock_actually_reached():
    gd, ctx = _app(hour=12.0)
    _tick(gd, ctx, frames=3)
    gd.on_event({"type": "freeze", "on": True}, ctx)
    gd.on_event({"type": "phase", "name": "night"}, ctx)
    _tick(gd, ctx, frames=int(FPS * 2))
    gd.on_event({"type": "freeze", "on": False}, ctx)
    _tick(gd, ctx, frames=int(FPS * 2))
    assert gd.phase == "NIGHT" and gd.dream_stage == "descent", \
        "it resumes into now, from the top of the cycle, rather than into where it was"


def test_thawing_at_night_starts_a_cycle_rather_than_a_half_dream():
    gd, ctx = _app()
    _dreaming(gd, ctx)
    gd.on_event({"type": "freeze", "on": True}, ctx)
    gd.on_event({"type": "freeze", "on": False}, ctx)
    assert gd.dream is None and gd.dream_stage == "descent"
    _tick(gd, ctx, frames=int(FPS * 2))
    assert gd.phase == "NIGHT", "and it is still night"


def test_frozen_frames_are_valid_and_cheap():
    gd, ctx = _app()
    gd.on_event({"type": "freeze", "on": True}, ctx)
    for _ in range(300):
        px = _tick(gd, ctx).px
        assert float(px.min()) >= 0.0 and float(px.max()) <= 1.0


# ------------------------------------------------------------------ getting to the switch

@pytest.fixture
def sentinel(tmp_path):
    path = tmp_path / "FREEZE"
    bus = InputBus()
    yield freeze_module.FreezeWatcher(bus, path=str(path), poll_s=0.01), path, bus


def test_the_sentinel_file_freezes_and_thaws(sentinel):
    watcher, path, bus = sentinel
    assert watcher.poll_once() is False and bus.poll() == [], "no file, nothing to say"

    path.write_text("")
    assert watcher.poll_once() is True
    assert [(e["type"], e["on"], e["source"]) for e in bus.poll()] == [("freeze", True, "file")]
    assert watcher.poll_once() is False, "edge triggered, not a repeat every 250 ms"

    path.unlink()
    assert watcher.poll_once() is True
    assert [(e["type"], e["on"]) for e in bus.poll()] == [("freeze", False)]


def test_a_file_left_in_place_survives_a_restart(tmp_path):
    # A crash-restart during an incident must come back held, not come back showing it.
    path = tmp_path / "FREEZE"
    path.write_text("")
    bus = InputBus()
    watcher = freeze_module.FreezeWatcher(bus, path=str(path))
    assert watcher.poll_once() is True
    assert bus.poll()[0]["on"] is True


def test_the_signal_handler_only_sets_a_flag(sentinel):
    # It must not touch the bus's lock: a handler that can deadlock against poll() is not a
    # kill switch. The watcher thread does the push, one tick later.
    watcher, _path, bus = sentinel
    freeze_module._on_signal()
    assert bus.poll() == [], "nothing was pushed from the handler itself"
    assert watcher.poll_once() is True
    ev = bus.poll()[0]
    assert ev["toggle"] is True and ev["source"] == "signal"
    assert freeze_module._toggle_pending is False


def test_an_empty_freeze_file_path_disables_the_watcher():
    watcher = freeze_module.FreezeWatcher(InputBus(), path="")
    assert watcher.present() is False and watcher.poll_once() is False


# ------------------------------------------------------------------ over the wire

@pytest.fixture
def server():
    srv = ControlServer(port=0, host="127.0.0.1", bus=InputBus())
    srv.start()
    srv.port = srv._server.server_address[1]
    yield srv
    srv.stop()


def _post(srv, payload, token=None):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/input",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"X-Input-Token": token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _get(srv, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{srv.port}{path}", timeout=5) as r:
        return json.loads(r.read().decode())


def test_freeze_over_input_needs_the_operator_token(server):
    server.input_token = "s3cret"
    assert _post(server, {"type": "freeze", "on": True})[0] == 401
    assert _post(server, {"type": "freeze", "on": True}, token="s3cret")[0] == 200
    assert [e["type"] for e in server.bus.poll()] == ["freeze"]


def test_healthz_says_whether_the_building_is_held(server):
    assert _get(server, "/healthz")["frozen"] is False
    server.frozen = True
    assert _get(server, "/healthz")["frozen"] is True


def test_the_app_publishes_frozen_to_healthz(server):
    gd, ctx = _app()
    ctx.server = server
    gd.on_event({"type": "freeze", "on": True}, ctx)
    assert server.frozen is True, "confirmable with one GET from a phone"
    gd.on_event({"type": "freeze", "on": False}, ctx)
    assert server.frozen is False


# ------------------------------------------------------------------ tokens off the command line

def test_a_token_can_come_from_a_file_instead_of_the_environment(tmp_path, monkeypatch):
    path = tmp_path / "input.token"
    path.write_text("from-a-file\n", encoding="utf-8")
    monkeypatch.delenv("GD_TEST_TOKEN", raising=False)
    monkeypatch.setenv("GD_TEST_TOKEN_FILE", str(path))
    assert secret("GD_TEST_TOKEN") == "from-a-file", "trailing newline stripped"

    monkeypatch.setenv("GD_TEST_TOKEN", "from-the-environment")
    assert secret("GD_TEST_TOKEN") == "from-the-environment", "what works today keeps working"


def test_an_unreadable_token_file_does_not_quietly_open_the_building(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GD_TEST_TOKEN", raising=False)
    monkeypatch.setenv("GD_TEST_TOKEN_FILE", str(tmp_path / "nope"))
    assert secret("GD_TEST_TOKEN") == ""
    assert "unreadable" in capsys.readouterr().out, "it says so instead of shrugging"


def test_the_server_reads_its_token_from_a_file(tmp_path, monkeypatch):
    path = tmp_path / "op.token"
    path.write_text("file-secret", encoding="utf-8")
    monkeypatch.delenv("GREENDREAM_INPUT_TOKEN", raising=False)
    monkeypatch.setenv("GREENDREAM_INPUT_TOKEN_FILE", str(path))
    srv = ControlServer(port=0, host="127.0.0.1", bus=InputBus())
    assert srv.input_token == "file-secret"
    assert srv.authorized("file-secret") and not srv.authorized("wrong")
