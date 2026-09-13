"""Smoke tests: the app must run headless, at speed, and actually light the building.

    python -m pytest -q
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from common.canvas import COLS, ROWS, Canvas  # noqa: E402
from common.displays import NullDisplay, RecordingDisplay, frame_to_uint8  # noqa: E402
from common.engine import build_parser, run  # noqa: E402
from common.inputs import BUS  # noqa: E402
from main import APP  # noqa: E402

APP_TEST_ARGS = ["--offline", "--journal", os.path.join(tempfile.gettempdir(), "greendream_journal")]


def _run(extra, frames=90, fps=30):
    BUS.clear()
    args = build_parser(APP).parse_args(["--display", "null", "--frames", str(frames), "--fps", str(fps)] + extra)
    rec = RecordingDisplay(fps=fps)
    ctx = run(APP(), args, display=rec)
    return ctx, rec


def test_runs_headless_and_lights_up():
    ctx, rec = _run(["--demo"] + APP_TEST_ARGS, frames=120)
    assert ctx.frame_index == 120
    assert len(rec.frames) >= 120
    lit = [f for f in rec.frames if f.count("000000") < ROWS * COLS]
    assert len(lit) > 60, "the building stayed dark"
    for f in rec.frames[::10]:
        assert len(f) == ROWS * COLS * 6
        int(f, 16)  # valid hex


def test_frame_values_in_range():
    ctx, rec = _run(APP_TEST_ARGS, frames=30)
    from utilities.display import Frame

    fr = Frame()
    cv = Canvas()
    app = APP()
    app.setup(ctx)
    app.update(1 / 30, 0.5, cv, ctx)
    cv.clip()
    cv.to_frame(fr)
    u8 = frame_to_uint8(fr)
    assert u8.shape == (ROWS, COLS, 3)
    assert u8.dtype == np.uint8


def test_keeps_up_with_30fps():
    import time

    t0 = time.perf_counter()
    ctx, rec = _run(["--demo"] + APP_TEST_ARGS, frames=60)
    elapsed = time.perf_counter() - t0
    assert elapsed < 6.0, f"60 frames took {elapsed:.1f}s"
