"""Turn five words, or any scene spec, into a clip a browser can play.

A separate process from the runner on purpose. It holds no phase, drives no
display and pushes nothing onto the InputBus, so it can face the public while the
machine driving the building stays unreachable.

    python render.py                                    # preview page on :8110, interpreting locally
    python render.py --offline                          # never call the API
    python render.py --ingest http://localhost:8100     # interpret through the language service

    POST /digest {"text": "..."}   -> {spec, seed, t0, rec, tier}
    POST /render {"spec": {...}}   -> {rec}

``/render`` is the piece nothing else can do: only this repo has ``scene.py``,
``worlds.py`` and ``common/canvas.py``, so the ingest service's ``spec_draft`` has
to come here to become pixels.

``/digest`` interprets a phrase without any side effect, which is what a preview
needs - posting to the ingest service's ``/api/ingest`` would enqueue every idle sketch.

With ``--ingest URL`` the interpretation comes from that service's ``/api/preview``
instead of this repo's own tiers, and only the pixels are made here. That is the
mode to run in front of people: what the preview shows is then the same reading of
the words that the building will perform, rather than a second opinion about them.
Any failure over there falls through to the local tiers, so the page never stalls.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.request
import zlib
from collections import OrderedDict, deque
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Deque, Dict, Optional, Tuple

from common.canvas import COLS, ROWS, Canvas
from common.webserver import facade_js
from genie import BLOCKLIST, MODEL, claude_spec, clip_words, lexicon_spec
from library import LIBRARY, lookup, normalize
from scene import SHRUG, Performance, validate

_HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_PORT = 8110   # 8000 is the runner's simulator, 8100 is the LLM ingest service

RENDER_FPS = 30   # Particles.update spawns per call, so density is tied to this rate
DECIMATE = 2      # ...but playing back every other frame costs half the bytes and looks the same

DAILY_MODEL_CALLS = int(os.environ.get("GREENDREAM_DAILY_MODEL_CALLS", "400"))
IP_PER_MINUTE = int(os.environ.get("GREENDREAM_IP_PER_MINUTE", "12"))

INGEST_URL = os.environ.get("GREENDREAM_INGEST_URL", "").strip().rstrip("/")
INGEST_TOKEN = os.environ.get("GD_INGEST_TOKEN", "").strip()
INGEST_TIMEOUT = float(os.environ.get("GREENDREAM_INGEST_TIMEOUT", "6"))


# ---------------------------------------------------------------------------- render

def canvas_hex(cv: Canvas) -> str:
    """The same bytes as ``frame_to_hex(cv.to_frame(frame))``, about fifty times faster.

    ``to_uint8()`` is exactly what ``to_frame`` feeds into ``Color``, and the array is
    already row-major r,g,b, so the hex is identical rather than merely close. A test
    pins the two together so this cannot quietly drift from the display path.
    """
    return cv.to_uint8().tobytes().hex()


def render_spec(spec: dict, seed: int = 0, t0: float = 0.0, fps: int = RENDER_FPS, every: int = DECIMATE) -> dict:
    """Play a spec offline into a ``{rows, cols, fps, frames}`` recording.

    Generated at ``fps`` and then thinned by ``every``. The generated rate has to
    stay at the building's 30, because ``Particles.update`` spawns per call rather
    than per second: rendering at 15 would give half the rain. Every frame is still
    rendered, since the performance carries particle state forward; only the kept
    ones are converted.
    """
    perf = Performance(spec, t0, seed=seed)
    dt = 1.0 / fps
    frames = []
    for i in range(max(1, int(round(spec["duration_s"] * fps)))):
        cv = perf.render(t0 + i * dt, dt)
        if i % every == 0:
            frames.append(canvas_hex(cv))
    return {"rows": ROWS, "cols": COLS, "fps": fps / every, "frames": frames}


def seed_for(text: str) -> int:
    """A phrase always previews identically, without keeping any state to do it."""
    return zlib.crc32(normalize(clip_words(text)).encode()) & 0x3FFFFFFF


# ---------------------------------------------------------------------------- digest

def ingest_digest(text: str, url: str, timeout: float = INGEST_TIMEOUT) -> Optional[Tuple[dict, str]]:
    """Ask the language service what these words mean. None on any trouble.

    ``/api/preview`` is the right endpoint for a sketch: same validation, same gate and
    same moderation as a submission, but nothing is written to the day's log and nothing
    enters tonight's arc. Its ``spec_draft`` still goes through ``validate`` here, because
    a spec from another process is input like any other.
    """
    body = json.dumps({"query": text, "source": "preview"}).encode()
    headers = {"Content-Type": "application/json"}
    if INGEST_TOKEN:
        headers["X-Ingest-Token"] = INGEST_TOKEN
    req = urllib.request.Request(f"{url}/api/preview", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:200]
        except Exception:
            pass
        print(f"[render] ingest HTTP {e.code}: {detail}", flush=True)
        return None
    except Exception as e:
        print(f"[render] ingest unreachable ({type(e).__name__}: {e}); interpreting locally", flush=True)
        return None
    result = data.get("result") if isinstance(data, dict) else None
    draft = result.get("spec_draft") if isinstance(result, dict) else None
    if not isinstance(draft, dict):
        return None
    tier = str(data.get("tier") or result.get("tier") or "ingest")
    return validate(draft), tier


def digest(text: str, offline: bool = False, budget: Optional["Budget"] = None,
           ingest_url: str = "") -> Tuple[dict, str]:
    """Text -> validated spec, by the same tiers the building uses.

    ``BLOCKLIST`` is checked here because neither ``lookup`` nor ``lexicon_spec``
    does, and this is the one path where a phrase becomes pixels without the model
    ever having had the chance to refuse it.

    With ``ingest_url`` the language service does the interpreting, so the preview and
    the performance read the words the same way. It is tried before the local library:
    the point of the mode is that the answer comes from over there.
    """
    text = clip_words(text)
    if not text:
        return validate(SHRUG), "empty"
    if BLOCKLIST.search(text):
        return validate(SHRUG), "blocked"
    if ingest_url:
        got = ingest_digest(text, ingest_url)
        if got is not None:
            return got
    raw = lookup(text)
    if raw is not None:
        return validate(raw), "library"
    if not offline and (budget is None or budget.take_model_call()):
        got = claude_spec(text)
        if got is not None:
            return validate(got), MODEL
    return validate(lexicon_spec(text)), "lexicon"


class SpecCache:
    """One digest per distinct phrase, keyed the way the library already matches.

    Lexicon answers are deliberately not cached: they mean the model was skipped
    or unreachable, and caching one would make a temporary outage permanent. The
    test is on the tier name rather than a list, because in ``--ingest`` mode the
    tier is whatever the service called itself.
    """

    NEVER = ("lexicon", "ingest")

    def __init__(self, cap: int = 2048):
        self.cap = cap
        self._d: "OrderedDict[str, Tuple[dict, str]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, text: str) -> Optional[Tuple[dict, str]]:
        k = normalize(clip_words(text))
        with self._lock:
            hit = self._d.get(k)
            if hit is not None:
                self._d.move_to_end(k)
            return hit

    def put(self, text: str, spec: dict, tier: str) -> None:
        if any(tier.startswith(n) for n in self.NEVER):
            return
        k = normalize(clip_words(text))
        with self._lock:
            self._d[k] = (spec, tier)
            self._d.move_to_end(k)
            while len(self._d) > self.cap:
                self._d.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._d)


class Budget:
    """A ceiling for an endpoint nobody has to authenticate against.

    Two limits: a per-IP burst, and a daily number of model calls. Only a cache
    miss that actually reaches the model counts, so repeated phrases are free.
    Running out degrades to ``lexicon_spec`` rather than failing the request.
    """

    def __init__(self, daily_model_calls: int = DAILY_MODEL_CALLS, per_ip_per_min: int = IP_PER_MINUTE):
        self.daily = daily_model_calls
        self.per_ip = per_ip_per_min
        self._day = date.today()
        self._used = 0
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def allow_ip(self, ip: str) -> bool:
        now = time.time()
        with self._lock:
            q = self._hits.setdefault(ip, deque())
            while q and now - q[0] > 60.0:
                q.popleft()
            if len(self._hits) > 4096:  # a busy day should not become a slow leak
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            if len(q) >= self.per_ip:
                return False
            q.append(now)
            return True

    def take_model_call(self) -> bool:
        with self._lock:
            today = date.today()
            if today != self._day:
                self._day, self._used = today, 0
            if self._used >= self.daily:
                return False
            self._used += 1
            return True

    def state(self) -> dict:
        with self._lock:
            return {"model_calls_used": self._used, "model_calls_daily": self.daily,
                    "ip_per_minute": self.per_ip}


# ---------------------------------------------------------------------------- service

def preview_html() -> str:
    with open(os.path.join(_HERE, "web", "preview.html"), "r", encoding="utf-8") as f:
        return f.read()


class Service:
    """The digest endpoint plus the page that talks to it. No bus, no display.

    Rendering a novel phrase costs a few seconds of CPU - a storm runs at roughly
    15 ms a frame and a 12 s scene is 360 of them - so finished clips are kept too,
    and the library is pre-rendered at startup.
    """

    def __init__(self, offline: bool = False, cache: Optional[SpecCache] = None,
                 budget: Optional[Budget] = None, clip_cap: int = 48, ingest_url: str = INGEST_URL):
        self.offline = offline
        self.ingest_url = (ingest_url or "").rstrip("/")
        self.cache = cache if cache is not None else SpecCache()
        self.budget = budget if budget is not None else Budget()
        self.clip_cap = clip_cap
        self._clips: "OrderedDict[str, dict]" = OrderedDict()
        self._clip_lock = threading.Lock()

    def _clip(self, key: str, spec: dict, seed: int) -> Tuple[dict, bool]:
        with self._clip_lock:
            hit = self._clips.get(key)
            if hit is not None:
                self._clips.move_to_end(key)
                return hit, True
        rec = render_spec(spec, seed=seed, t0=0.0)
        with self._clip_lock:
            self._clips[key] = rec
            self._clips.move_to_end(key)
            while len(self._clips) > self.clip_cap:
                self._clips.popitem(last=False)
        return rec, False

    def preview(self, text: str) -> dict:
        started = time.time()
        text = clip_words(text)
        hit = self.cache.get(text)
        if hit is not None:
            spec, tier = hit
        else:
            spec, tier = digest(text, offline=self.offline, budget=self.budget, ingest_url=self.ingest_url)
            self.cache.put(text, spec, tier)
        seed = seed_for(text)
        rec, from_clips = self._clip(normalize(text), spec, seed)
        return {"ok": True, "text": text, "tier": tier, "cached": from_clips,
                "title": spec["title"], "spec": spec, "seed": seed, "t0": 0.0,
                "rec": rec, "ms": int((time.time() - started) * 1000)}

    def render(self, raw_spec: dict, seed: int = 0, t0: float = 0.0) -> dict:
        """Render a spec that came from somewhere else, e.g. an ingest ``spec_draft``.

        ``validate`` rebuilds the spec from known fields only, so extra keys such as
        ``schema_version`` are dropped rather than rejected.
        """
        spec = validate(raw_spec)
        return {"ok": True, "title": spec["title"], "spec": spec, "seed": seed, "t0": t0,
                "rec": render_spec(spec, seed=seed, t0=t0)}

    def warm(self, phrases=None) -> int:
        """Pre-render the library so the chips and the common phrases answer instantly.

        Skipped in ``--ingest`` mode: warming there would spend the service's preview
        allowance on phrases nobody asked for, and caching a local answer under a phrase
        would later serve it as though the service had given it.
        """
        if self.ingest_url:
            return 0
        done = 0
        for phrase in (list(LIBRARY) if phrases is None else list(phrases)):
            try:
                self.preview(phrase)
                done += 1
            except Exception:
                pass
        return done


def serve(port: int = DEFAULT_PORT, host: str = "0.0.0.0", offline: bool = False, warm: bool = True,
          ingest_url: str = INGEST_URL) -> ThreadingHTTPServer:
    service = Service(offline=offline, ingest_url=ingest_url)
    page = preview_html()
    js = facade_js()
    if warm:
        threading.Thread(target=service.warm, name="warm-library", daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def handle_one_request(self):
            # A client that walks away mid-request is normal, not an incident. Without this,
            # every closed keep-alive connection prints a traceback, and the one message that
            # matters ("ingest unreachable") gets lost in it.
            try:
                super().handle_one_request()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                self.close_connection = True

        def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _ip(self) -> str:
            fwd = self.headers.get("X-Forwarded-For", "")
            return fwd.split(",")[0].strip() if fwd else self.client_address[0]

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                return self._send(200, page.encode())
            if path == "/facade.js":
                return self._send(200, js.encode(), "application/javascript")
            if path == "/healthz":
                return self._json(200, {"ok": True, "offline": service.offline,
                                        "interpreter": service.ingest_url or "local",
                                        "cached_phrases": len(service.cache),
                                        "cached_clips": len(service._clips),
                                        **service.budget.state()})
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path not in ("/digest", "/render"):
                return self._send(404, b"not found", "text/plain")
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n).decode() or "{}") if n else {}
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}
            # both endpoints render, which is seconds of CPU, so both are rate limited
            if not service.budget.allow_ip(self._ip()):
                return self._json(429, {"ok": False, "error": "too many sketches in a minute — give it a moment"})
            try:
                if path == "/render":
                    if not isinstance(data.get("spec"), dict):
                        return self._json(400, {"ok": False, "error": "send a scene spec as 'spec'"})
                    return self._json(200, service.render(data["spec"], int(data.get("seed", 0)),
                                                          float(data.get("t0", 0.0))))
                text = data.get("text", "")
                if not str(text).strip():
                    return self._json(400, {"ok": False, "error": "say something first"})
                return self._json(200, service.preview(str(text)))
            except Exception as e:  # pragma: no cover
                return self._json(500, {"ok": False, "error": str(e)})

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            pass   # already handled above; nothing here is worth a traceback on stderr

    httpd = Server((host, port), Handler)
    where = f"interpreting via {service.ingest_url}" if service.ingest_url else "interpreting locally"
    print(f"[render] digest + preview on http://localhost:{port}  ({where}"
          f"{', offline' if offline else ''})", flush=True)
    return httpd


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="GreenDream digest + preview service")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--offline", action="store_true", help="never call the API (library + lexicon only)")
    p.add_argument("--no-warm", action="store_true", help="skip pre-rendering the library at startup")
    p.add_argument("--ingest", default=INGEST_URL, metavar="URL",
                   help="interpret through the language service instead of this repo's tiers, "
                        "e.g. http://localhost:8100 (so the preview and the building agree)")
    args = p.parse_args(argv)
    httpd = serve(port=args.port, host=args.host, offline=args.offline, warm=not args.no_warm,
                  ingest_url=args.ingest)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
