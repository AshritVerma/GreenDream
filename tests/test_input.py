"""The way in: what ``POST /input`` accepts, and what the app does with a spec it
did not produce itself.

The runner drives a building. Everything that arrives over HTTP is treated as input,
including a spec that claims to have been validated somewhere else.

    python -m pytest -q tests/test_input.py
"""

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from common.displays import NullDisplay  # noqa: E402
from common.engine import Context  # noqa: E402
from common.inputs import InputBus  # noqa: E402
from common.webserver import ControlServer  # noqa: E402
from main import APP  # noqa: E402
from scene import SHRUG  # noqa: E402


# --------------------------------------------------------------------- the app

class _Args:
    offline = True
    time_scale = 1.0
    start_hour = 12.0
    journal = os.path.join(tempfile.gettempdir(), "greendream_test_journal")


def _app():
    app = APP()
    bus = InputBus()
    ctx = Context(display=NullDisplay(), bus=bus, args=_Args(), server=None)
    app.setup(ctx)
    return app, ctx


def _post_spec(app, ctx, **over):
    ev = dict({"type": "spec", "text": "thunderstorm", "spec": {"title": "storm"}, "tier": "test"}, **over)
    app.on_event(ev, ctx)
    return app.day[-1] if app.day else None


def test_a_pushed_spec_is_revalidated_before_it_reaches_the_windows():
    # The one rule that matters: nothing draws from an unvalidated dict. A hostile
    # spec is coerced, not rejected, so a buggy sender still gets a show.
    app, ctx = _app()
    entry = _post_spec(app, ctx, spec={"title": "x" * 500, "world": "moon", "duration_s": 1e9,
                                       "word": "raw user text here", "motion": {"kind": "teleport"},
                                       "palette": {"base": "javascript:alert(1)"}})
    spec = entry["spec"]
    assert spec["world"] == "none" and spec["motion"]["kind"] == "breathe"
    assert len(spec["title"]) <= 40 and 6 <= spec["duration_s"] <= 20
    assert spec["palette"]["base"].startswith("#")
    assert spec["word"] is None or len(spec["word"]) <= 7
    assert list(app.queue)[-1] is spec, "the queue holds the validated spec, not the input"


def test_a_spec_event_carries_its_channel_tier_and_latency_into_the_journal():
    app, ctx = _app()
    entry = _post_spec(app, ctx, source="pedestal", tier="gpt-6-astra", latency_ms=1234)
    assert entry["channel"] == "pedestal" and entry["tier"] == "gpt-6-astra"
    assert entry["latency_ms"] == 1234
    assert app.journal_json()["prompts"][-1]["tier"] == "gpt-6-astra"


def test_dream_priority_is_material_for_tonight_not_a_performance_now():
    # Presence is the price of immediacy: a remote prompt is dreamt, not played.
    app, ctx = _app()
    app.phase = "DAY"
    _post_spec(app, ctx, priority="dream", source="web")
    assert not app.queue, "a remote prompt must not interrupt the plaza"
    assert app.day[-1]["priority"] == "dream", "but it is still material for tonight"
    _post_spec(app, ctx, priority="live", source="pedestal")
    assert len(app.queue) == 1


def test_an_unknown_priority_is_not_trusted():
    app, ctx = _app()
    assert _post_spec(app, ctx, priority="urgent!!")["priority"] == "live"


def test_text_longer_than_five_words_is_clipped_in_the_journal():
    app, ctx = _app()
    entry = _post_spec(app, ctx, text="one two three four five six seven")
    assert entry["text"] == "one two three four five"


def test_a_refusal_is_never_dream_material():
    app, ctx = _app()
    _post_spec(app, ctx, spec=dict(SHRUG), tier="blocked")
    assert app.day[-1]["spec"]["ok"] is False
    # the descent snapshot skips it, so the night is not built out of things we refused
    material = [d for d in app.day if d["spec"]["ok"]]
    assert material == []


def test_only_our_own_genie_clears_the_thinking_shimmer():
    # `pending` counts requests this process started. A spec pushed in by the service
    # was never pending here, and must not cancel the shimmer for a prompt that is.
    app, ctx = _app()
    app.pending = 1
    _post_spec(app, ctx, source="web")
    assert app.pending == 1
    _post_spec(app, ctx, origin="genie")
    assert app.pending == 0


# ------------------------------------------------------------------ the server

@pytest.fixture
def server():
    srv = ControlServer(port=0, host="127.0.0.1", bus=InputBus())
    srv.start()
    srv.port = srv._server.server_address[1]
    yield srv
    srv.stop()


def _post(srv, payload, token=None, path="/input"):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{path}",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"X-Input-Token": token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def test_a_prompt_needs_no_token(server):
    server.text_gap_s = 0
    code, body = _post(server, {"type": "text", "text": "thunderstorm"})
    assert code == 200 and body["ok"] is True
    assert [e["type"] for e in server.bus.poll()] == ["text"]


def test_a_prompt_is_rate_limited_per_client(server):
    server.text_gap_s = 60
    assert _post(server, {"type": "text", "text": "one"})[0] == 200
    code, body = _post(server, {"type": "text", "text": "two"})
    assert code == 429 and "moment" in body["error"]


def test_events_that_drive_the_building_need_the_operator_token(server):
    server.input_token = "s3cret"
    for ev in ({"type": "phase", "name": "night"}, {"type": "spec", "spec": {}},
               {"type": "set_hour", "hour": 3}, {"type": "dream_script", "script": {}}):
        assert _post(server, ev)[0] == 401, ev
        assert _post(server, ev, token="wrong")[0] == 401, ev
        assert _post(server, ev, token="s3cret")[0] == 200, ev


def test_without_a_token_configured_everything_is_open(server):
    # The default is a laptop on a desk, not a tunnel to the internet.
    server.input_token = ""
    assert _post(server, {"type": "phase", "name": "dawn"})[0] == 200


def test_junk_is_rejected_rather_than_queued(server):
    assert _post(server, {"nope": 1})[0] == 400
    assert _post(server, [1, 2, 3])[0] == 400
    assert server.bus.poll() == []


def test_health_reports_the_policy_without_leaking_the_token(server):
    server.input_token = "s3cret"
    server.text_gap_s = 7
    with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/healthz", timeout=5) as r:
        body = json.loads(r.read().decode())
    assert body["locked"] is True and body["text_gap_s"] == 7
    assert "s3cret" not in json.dumps(body), "the whole point is to not need the token to ask"


def test_the_token_may_ride_in_the_query_string(server):
    # so that opening /?key=... in a browser makes the control panel work
    server.input_token = "s3cret"
    code, _ = _post(server, {"type": "phase", "name": "day"}, path="/input?key=s3cret")
    assert code == 200
