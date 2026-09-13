"""The 30 FPS loop, the App base class and the shared command line.

An app is a *body*: it senses (inputs / sensors), keeps an internal state, and
expresses that state on the canvas every frame. ``run()`` paces the loop with
``time.sleep`` (no busy-wait), converts the canvas to a repo ``Frame`` and
hands it to ``Display.send`` at most 30 times a second.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from utilities.display import Display, Frame

from .canvas import Canvas
from .displays import RecordingDisplay, make_display
from .inputs import BUS, InputBus, Timeline


@dataclass
class Context:
    display: Display
    bus: InputBus
    args: argparse.Namespace
    server: Any = None            # ControlServer when the web simulator is on
    fps: int = 30
    t: float = 0.0
    frame_index: int = 0
    demo: bool = False
    extras: Dict[str, Any] = field(default_factory=dict)

    def set_status(self, **kw) -> None:
        if self.server:
            self.server.set_status(**kw)

    def set_controls(self, controls: List[dict]) -> None:
        if self.server:
            self.server.set_controls(controls)

    def add_page(self, path: str, html: str) -> None:
        if self.server:
            self.server.add_page(path, html)

    @property
    def url(self) -> Optional[str]:
        return self.server.url if self.server else None


class App:
    """Subclass this. Override ``setup``, ``update`` (and optionally ``on_event``)."""

    name = "app"
    title = "Untitled"
    description = ""

    def setup(self, ctx: Context) -> None:  # noqa: D401
        pass

    def on_event(self, ev: dict, ctx: Context) -> None:
        pass

    def update(self, dt: float, t: float, canvas: Canvas, ctx: Context) -> None:
        raise NotImplementedError

    def teardown(self, ctx: Context) -> None:
        pass

    # Optional: scripted inputs used for hardware-free demos / recordings
    def demo_script(self) -> Optional[Timeline]:
        return None

    # Optional: extra CLI flags
    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        pass


def build_parser(app_cls) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"{app_cls.title} — {app_cls.description}")
    p.add_argument("--display", default="web", help="web | sundai:INSTANCE | pygame | record:PATH | udp:HOST:PORT | http:URL | null | file.py:Class  (chain with +)")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)), help="web simulator port")
    p.add_argument("--fps", type=int, default=30, help="frame rate (the building caps at 30)")
    p.add_argument("--duration", type=float, default=None, help="stop after N seconds")
    p.add_argument("--frames", type=int, default=None, help="stop after N frames")
    p.add_argument("--demo", action="store_true", help="run the scripted demo timeline (no hardware needed)")
    p.add_argument("--open", action="store_true", help="open the simulator in a browser")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    p.add_argument("--gif", default=None, help="with record: also write an animated GIF here")
    p.add_argument("--stats", action="store_true", help="print loop timing every 5 s")
    p.add_argument("--gentle", action="store_true", help="limit sudden whole-building flashes (photosensitivity-safe mode for the real facade)")
    p.add_argument("--ssl-cert", default=None, help="serve the web simulator over https (phone camera/motion APIs need it); see tools/make_cert.sh")
    p.add_argument("--ssl-key", default=None, help="private key for --ssl-cert (defaults to the cert file)")
    app_cls.add_args(p)
    return p


def run(app: App, args: Optional[argparse.Namespace] = None, display: Optional[Display] = None, bus: InputBus = BUS) -> Context:
    """Run ``app`` until duration/frames elapse or Ctrl-C."""
    if args is None:
        args = build_parser(type(app)).parse_args([])
    if getattr(args, "seed", None) is not None:
        import random

        import numpy as np

        random.seed(args.seed)
        np.random.seed(args.seed)

    fps = max(1, min(30, int(getattr(args, "fps", 30) or 30)))
    if display is None:
        display = make_display(args.display, port=args.port, title=app.title, description=app.description, open_browser=getattr(args, "open", False), fps=fps,
                               ssl_cert=getattr(args, "ssl_cert", None), ssl_key=getattr(args, "ssl_key", None))
    server = getattr(display, "server", None)
    ctx = Context(display=display, bus=bus, args=args, server=server, fps=fps, demo=bool(getattr(args, "demo", False)))

    timeline = app.demo_script() if ctx.demo else None
    canvas = Canvas()
    frame: Frame = display.makeframe()
    app.setup(ctx)

    gentle = bool(getattr(args, "gentle", False))
    prev_px = None
    period = 1.0 / fps
    t0 = time.perf_counter()
    next_frame = t0
    last_t = 0.0
    stat_t, stat_n, stat_work = t0, 0, 0.0
    stop = False

    def _sig(*_):
        nonlocal stop
        stop = True

    try:
        signal.signal(signal.SIGTERM, _sig)
    except Exception:
        pass

    try:
        while not stop:
            now = time.perf_counter()
            t = now - t0
            dt = min(0.1, t - last_t) if ctx.frame_index else period
            last_t = t
            ctx.t = t
            if timeline:
                timeline.tick(t)
            for ev in bus.poll():
                app.on_event(ev, ctx)
            work0 = time.perf_counter()
            app.update(dt, t, canvas, ctx)
            canvas.clip()
            if gentle:  # cap frame-to-frame jumps in mean brightness (no hard strobes)
                if prev_px is not None:
                    jump = float(abs(canvas.px.mean() - prev_px.mean()))
                    if jump > 0.12:
                        k = 0.12 / jump
                        canvas.px[:] = prev_px + (canvas.px - prev_px) * k
                prev_px = canvas.px.copy()
            canvas.to_frame(frame)
            display.send(frame)
            stat_work += time.perf_counter() - work0
            stat_n += 1
            ctx.frame_index += 1
            if getattr(args, "stats", False) and now - stat_t >= 5:
                print(f"[loop] {stat_n / (now - stat_t):.1f} fps, {1000 * stat_work / max(1, stat_n):.2f} ms/frame of work", flush=True)
                stat_t, stat_n, stat_work = now, 0, 0.0
            if getattr(args, "duration", None) is not None and t >= args.duration:
                break
            if getattr(args, "frames", None) is not None and ctx.frame_index >= args.frames:
                break
            next_frame += period
            sleep_for = next_frame - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:  # we fell behind; resync instead of racing to catch up
                next_frame = time.perf_counter()
    except KeyboardInterrupt:
        pass
    finally:
        app.teardown(ctx)
        try:
            display.send(Frame())  # leave the building dark
            for d in [display] + list(getattr(display, "displays", []) or []):
                if hasattr(d, "flush"):
                    d.flush(3.0)
        except Exception:
            pass
        rec = _find_recorder(display)
        if rec is not None:
            path = rec.save()
            print(f"[record] {len(rec.frames)} frames -> {path}", flush=True)
            if getattr(args, "gif", None):
                rec.save_gif(args.gif)
                print(f"[record] gif -> {args.gif}", flush=True)
    return ctx


def _find_recorder(display) -> Optional[RecordingDisplay]:
    if isinstance(display, RecordingDisplay):
        return display
    for d in getattr(display, "displays", []) or []:
        if isinstance(d, RecordingDisplay):
            return d
    return None


def main(app_cls, argv: Optional[List[str]] = None) -> Context:
    for stream in (sys.stdout, sys.stderr):  # titles and notes contain em dashes/arrows; cp1252 consoles raise
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = build_parser(app_cls)
    args = parser.parse_args(argv)
    app = app_cls()
    print(f"== {app.title} ==\n{app.description}\n", flush=True)
    return run(app, args)
