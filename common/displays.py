"""Display back-ends that all speak the repo's ``Display.send(Frame)`` contract.

    web                 browser simulator at http://localhost:PORT (default)
    pygame              the original DummyDisplay window from the Tetris repo
    record:PATH.json    save every frame (used to build demo.html previews)
    sundai:INSTANCE     the hack's hosted simulator at sundai.willsarg.com/INSTANCE
    udp:HOST:PORT       JSON frames over UDP
    http:URL            JSON frames POSTed to a URL
    null                discard (tests / benchmarks)
    path/to/file.py:ClassName   or   package.module:ClassName
                        any Display subclass, e.g. the real Green Building
                        driver handed out at the hack. Constructed with no args.

Chain several with ``+``: ``--display web+record:out.json``.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import socket
import sys
import time
from typing import List, Optional

import numpy as np

from utilities.display import Color, Display, Frame

from .canvas import COLS, ROWS


def frame_to_hex(frame: Frame) -> str:
    arr = frame.asarray()
    out = []
    for r in range(ROWS):
        row = arr[r]
        for c in range(COLS):
            col = row[c]
            out.append(f"{col.r:02x}{col.g:02x}{col.b:02x}")
    return "".join(out)


def frame_to_list(frame: Frame) -> List[List[int]]:
    arr = frame.asarray()
    return [[int(arr[r, c].r), int(arr[r, c].g), int(arr[r, c].b)] for r in range(ROWS) for c in range(COLS)]


def frame_to_uint8(frame: Frame) -> np.ndarray:
    arr = frame.asarray()
    out = np.zeros((ROWS, COLS, 3), dtype=np.uint8)
    for r in range(ROWS):
        for c in range(COLS):
            col = arr[r, c]
            out[r, c] = (col.r, col.g, col.b)
    return out


class NullDisplay(Display):
    def __init__(self):
        self.count = 0

    def makeframe(self):
        return Frame()

    def send(self, frame):
        self.count += 1


class WebSimDisplay(Display):
    """Browser simulator: streams frames to http://localhost:PORT over SSE."""

    def __init__(self, port: int = 8000, title: str = "Green Building", description: str = "", open_browser: bool = False, server=None, ssl_cert=None, ssl_key=None):
        from .webserver import ControlServer

        self.server = server or ControlServer(port=port, title=title, description=description, ssl_cert=ssl_cert, ssl_key=ssl_key)
        self.server.start()
        print(f"[web] simulator at {self.server.url}   (LAN: {self.server.lan_url})", flush=True)
        if open_browser:
            try:
                import webbrowser

                webbrowser.open(self.server.url)
            except Exception:
                pass

    def makeframe(self):
        return Frame()

    def send(self, frame):
        self.server.push_frame_hex(frame_to_hex(frame))


class PygameDisplay(Display):
    """The repo's original window (utilities/dummy.py), kept as an option."""

    def __init__(self, scalar: int = 40):
        from utilities.dummy import DummyDisplay

        self._inner = DummyDisplay(scalar=scalar)

    def makeframe(self):
        return Frame()

    def send(self, frame):
        import pygame

        for ev in pygame.event.get():  # keep the window responsive
            if ev.type == pygame.QUIT:
                raise KeyboardInterrupt
        self._inner.send(frame)


class RecordingDisplay(Display):
    """Collects frames in memory; ``save()`` writes JSON (and optionally a GIF)."""

    def __init__(self, path: str = "recording.json", fps: int = 30, max_frames: int = 20000):
        self.path = path
        self.fps = fps
        self.max_frames = max_frames
        self.frames: List[str] = []

    def makeframe(self):
        return Frame()

    def send(self, frame):
        if len(self.frames) < self.max_frames:
            self.frames.append(frame_to_hex(frame))

    def save(self, path: Optional[str] = None, every: int = 1) -> str:
        path = path or self.path
        data = {"rows": ROWS, "cols": COLS, "fps": self.fps / every, "frames": self.frames[::every]}
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def save_gif(self, path: str, every: int = 2, scale: int = 14) -> str:
        """Render frames to an animated GIF (needs Pillow)."""
        from PIL import Image

        imgs = []
        for hx in self.frames[::every]:
            imgs.append(render_hex_image(hx, scale))
        if imgs:
            imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=int(1000 * every / self.fps), loop=0)
        return path

    def save_strip(self, path: str, n: int = 12, scale: int = 10) -> str:
        """A contact sheet of n evenly spaced frames (quick visual check)."""
        from PIL import Image

        if not self.frames:
            return path
        idx = np.linspace(0, len(self.frames) - 1, n).astype(int)
        tiles = [render_hex_image(self.frames[i], scale) for i in idx]
        w, h = tiles[0].size
        sheet = Image.new("RGB", (w * n + 4 * (n - 1), h), (20, 20, 24))
        for k, t in enumerate(tiles):
            sheet.paste(t, (k * (w + 4), 0))
        sheet.save(path)
        return path


def render_hex_image(hx: str, scale: int = 14):
    """Render one hex frame as a PIL image that looks like the lit facade."""
    from PIL import Image, ImageDraw

    W, H = COLS * scale + scale, ROWS * scale + scale
    img = Image.new("RGB", (W, H), (28, 30, 36))
    d = ImageDraw.Draw(img)
    for r in range(ROWS):
        for c in range(COLS):
            i = (r * COLS + c) * 6
            rgb = (int(hx[i:i + 2], 16), int(hx[i + 2:i + 4], 16), int(hx[i + 4:i + 6], 16))
            x0 = scale // 2 + c * scale + scale * 0.15
            y0 = scale // 2 + r * scale + scale * 0.25
            d.rectangle([x0, y0, x0 + scale * 0.7, y0 + scale * 0.5], fill=rgb if sum(rgb) > 8 else (12, 13, 16))
    return img


class UDPDisplay(Display):
    """JSON frame per datagram: {"rows":17,"cols":9,"pixels":[[r,g,b],...]}.

    Adjust ``encode`` if the organisers' simulator expects a different layout.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 5005):
        self.addr = (host, int(port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def makeframe(self):
        return Frame()

    def encode(self, frame: Frame) -> bytes:
        return json.dumps({"rows": ROWS, "cols": COLS, "pixels": frame_to_list(frame)}).encode()

    def send(self, frame):
        try:
            self.sock.sendto(self.encode(frame), self.addr)
        except OSError:
            pass


class HTTPDisplay(Display):
    """POST each frame as JSON to a URL (fire-and-forget on a thread)."""

    def __init__(self, url: str):
        import threading

        self.url = url
        self._lock = threading.Lock()
        self._busy = False

    def makeframe(self):
        return Frame()

    def send(self, frame):
        import threading
        import urllib.request

        if self._busy:
            return  # skip a frame rather than queue up
        payload = json.dumps({"rows": ROWS, "cols": COLS, "pixels": frame_to_list(frame)}).encode()

        def go():
            try:
                req = urllib.request.Request(self.url, data=payload, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=1).read()
            except Exception:
                pass
            finally:
                self._busy = False

        self._busy = True
        threading.Thread(target=go, daemon=True).start()


class SundaiDisplay(Display):
    """The hack's hosted simulator (sundai.willsarg.com): POST 459 raw RGB bytes per frame
    to /api/i/<instance>/frame. Non-blocking, latest-wins, one keep-alive HTTPS connection,
    exactly like the organisers' gbsim client. Instance names are adjective-animal pairs
    handed out by the site; anyone can watch at https://sundai.willsarg.com/<instance>.
    """

    def __init__(self, instance: str, base_url: str = "https://sundai.willsarg.com/api", timeout: float = 2.0):
        import http.client
        import threading
        from urllib.parse import urlsplit

        if not instance:
            raise ValueError("sundai display needs an instance name: --display sundai:olive-koala (or set SUNDAI_INSTANCE)")
        u = urlsplit(base_url.rstrip("/"))
        self.instance = instance
        self._host, self._https, self._path = u.netloc, u.scheme == "https", f"{u.path}/i/{instance}/frame"
        self._timeout = timeout
        self._http = http.client
        self._conn = None
        self._slot = None
        self._busy = False
        self._cv = threading.Condition()
        self._fails = 0
        self.sent = 0
        threading.Thread(target=self._pump, name="sundai-sender", daemon=True).start()
        print(f"[sundai] streaming to https://sundai.willsarg.com/{instance}  (?view=close|street|river)", flush=True)

    def makeframe(self):
        return Frame()

    @staticmethod
    def pack(frame: Frame) -> bytes:
        arr = frame.asarray()
        buf = bytearray()
        for r in range(ROWS):
            for c in range(COLS):
                col = arr[r, c]
                buf += bytes((col.r, col.g, col.b))
        return bytes(buf)

    def send(self, frame):
        with self._cv:
            self._slot = self.pack(frame)
            self._cv.notify()

    def flush(self, timeout: float = 3.0) -> bool:
        with self._cv:
            return self._cv.wait_for(lambda: self._slot is None and not self._busy, timeout=timeout)

    def _pump(self):
        headers = {"Content-Type": "application/octet-stream", "User-Agent": "greenhack/1"}
        while True:
            with self._cv:
                while self._slot is None:
                    self._cv.wait()
                buf, self._slot = self._slot, None
                self._busy = True
            try:
                if self._conn is None:
                    cls = self._http.HTTPSConnection if self._https else self._http.HTTPConnection
                    self._conn = cls(self._host, timeout=self._timeout)
                self._conn.request("POST", self._path, body=buf, headers=headers)
                resp = self._conn.getresponse()
                resp.read()
                if resp.status >= 400:
                    raise RuntimeError(f"HTTP {resp.status} {resp.reason}")
                self._fails = 0
                self.sent += 1
            except Exception as e:
                self._fails += 1
                if self._fails <= 3 or self._fails % 100 == 0:
                    print(f"[sundai] send failed: {e}", flush=True)
                try:
                    if self._conn:
                        self._conn.close()
                except Exception:
                    pass
                self._conn = None
            finally:
                with self._cv:
                    self._busy = False
                    self._cv.notify_all()


class MultiDisplay(Display):
    def __init__(self, displays: List[Display]):
        self.displays = displays

    def makeframe(self):
        return Frame()

    def send(self, frame):
        for d in self.displays:
            d.send(frame)

    def __getattr__(self, name):  # proxy things like .server / .frames to children
        for d in self.displays:
            if hasattr(d, name):
                return getattr(d, name)
        raise AttributeError(name)


def load_plugin(spec: str) -> Display:
    """``path/to/file.py:ClassName`` or ``package.module:ClassName``."""
    mod_spec, _, cls_name = spec.partition(":")
    if not cls_name:
        raise ValueError("plugin display needs the form module:ClassName")
    if mod_spec.endswith(".py") or os.sep in mod_spec:
        name = os.path.splitext(os.path.basename(mod_spec))[0]
        s = importlib.util.spec_from_file_location(name, mod_spec)
        module = importlib.util.module_from_spec(s)
        sys.modules[name] = module
        s.loader.exec_module(module)
    else:
        module = importlib.import_module(mod_spec)
    cls = getattr(module, cls_name)
    return cls()


def make_display(spec: str = "web", *, port: int = 8000, title: str = "Green Building", description: str = "", open_browser: bool = False, fps: int = 30, server=None, ssl_cert=None, ssl_key=None) -> Display:
    parts = [p for p in spec.split("+") if p]
    displays: List[Display] = []
    for p in parts:
        kind, _, arg = p.partition(":")
        if kind == "web":
            displays.append(WebSimDisplay(port=port, title=title, description=description, open_browser=open_browser, server=server, ssl_cert=ssl_cert, ssl_key=ssl_key))
        elif kind == "pygame":
            displays.append(PygameDisplay())
        elif kind == "record":
            displays.append(RecordingDisplay(arg or "recording.json", fps=fps))
        elif kind == "udp":
            host, _, prt = (arg or "127.0.0.1:5005").rpartition(":")
            displays.append(UDPDisplay(host or "127.0.0.1", int(prt)))
        elif kind == "http":
            displays.append(HTTPDisplay(p[len("http:"):]))
        elif kind == "null":
            displays.append(NullDisplay())
        elif kind == "sundai":
            displays.append(SundaiDisplay(arg or os.environ.get("SUNDAI_INSTANCE", "")))
        else:
            displays.append(load_plugin(p))
    if not displays:
        displays.append(NullDisplay())
    return displays[0] if len(displays) == 1 else MultiDisplay(displays)
