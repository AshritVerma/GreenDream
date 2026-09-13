"""Tiny stdlib HTTP server: browser simulator, SSE frame stream, input POSTs,
and extra app pages (phone controllers etc.). No third-party dependencies.

Endpoints
---------
GET  /            the simulator page (facade renderer + control panel)
GET  /stream      Server-Sent Events: ``frame`` (hex), ``controls``, ``status``, ``meta``
GET  /frame       latest frame as JSON {"rows":17,"cols":9,"hex":"..."}
POST /input       any JSON object -> pushed onto the InputBus (adds "source")
GET  /<extra>     pages registered with ``add_page(path, html)``
GET  /api/<name>  JSON handlers registered with ``add_json(path, fn)``

Operator surface
----------------
``/input`` is how the simulator page, the phone page and the language service talk to the
app, so it stays open for ``{"type": "text"}`` (rate limited per client: one prompt every
GREENDREAM_TEXT_GAP_S seconds, default 10). Every other event type - phase overrides, the
clock, ``spec`` and ``dream_script`` pushes - changes what the building does without asking
anyone, so when GREENDREAM_INPUT_TOKEN is set those require the token in an ``X-Input-Token``
header or a ``?key=`` query parameter. Open ``/?key=TOKEN`` to use the control panel.
Unset (the default) means open, which is fine on a laptop and not fine behind a tunnel.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

from .inputs import BUS, InputBus

_HERE = os.path.dirname(os.path.abspath(__file__))


def _read(name: str) -> str:
    with open(os.path.join(_HERE, "web", name), "r", encoding="utf-8") as f:
        return f.read()


def facade_js() -> str:
    return _read("facade.js")


def lan_ip() -> str:
    """Best-effort LAN IP so phones can reach the server."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ControlServer:
    """HTTP + SSE server shared by the web simulator display and phone pages."""

    def __init__(self, port: int = 8000, host: str = "0.0.0.0", bus: InputBus = BUS, title: str = "Green Building", description: str = "", ssl_cert: str | None = None, ssl_key: str | None = None):
        self.port = port
        self.host = host
        self.ssl_cert = ssl_cert
        self.ssl_key = ssl_key
        self.bus = bus
        self.title = title
        self.description = description
        self.pages: Dict[str, str] = {}
        self.json_handlers: Dict[str, Callable[[str, dict], dict]] = {}
        self.controls: List[dict] = []
        self.status: Dict = {}
        self.latest_hex: str = "000000" * 153
        self._clients: List[queue.Queue] = []
        self._lock = threading.Lock()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._sim_html: Optional[str] = None
        self.input_token: str = os.environ.get("GREENDREAM_INPUT_TOKEN", "").strip()
        self.text_gap_s: float = float(os.environ.get("GREENDREAM_TEXT_GAP_S", "10") or 0)
        self._last_text: Dict[str, float] = {}

    # -- input policy -----------------------------------------------------
    def allow_text(self, client: str, now: Optional[float] = None) -> bool:
        """One prompt per client per ``text_gap_s``; records the hit when allowed."""
        if self.text_gap_s <= 0:
            return True
        now = time.time() if now is None else now
        with self._lock:
            last = self._last_text.get(client, -1e9)
            if now - last < self.text_gap_s:
                return False
            self._last_text[client] = now
            if len(self._last_text) > 4096:
                for k in [k for k, v in self._last_text.items() if now - v > self.text_gap_s]:
                    del self._last_text[k]
            return True

    def authorized(self, token: Optional[str]) -> bool:
        """True when no token is configured, or the presented one matches."""
        return not self.input_token or (token or "") == self.input_token

    # -- registration -----------------------------------------------------
    def add_page(self, path: str, html: str) -> None:
        self.pages[path if path.startswith("/") else "/" + path] = html

    def add_json(self, path: str, fn: Callable[[str, dict], dict]) -> None:
        self.json_handlers[path if path.startswith("/") else "/" + path] = fn

    def set_controls(self, controls: List[dict]) -> None:
        self.controls = list(controls)
        self._broadcast("controls", json.dumps(self.controls))

    def set_status(self, **status) -> None:
        self.status = status
        self._broadcast("status", json.dumps(status))

    def set_meta(self, title: str | None = None, description: str | None = None) -> None:
        if title:
            self.title = title
        if description is not None:
            self.description = description
        self._sim_html = None
        self._broadcast("meta", json.dumps({"title": self.title, "description": self.description}))

    # -- frames -----------------------------------------------------------
    def push_frame_hex(self, hexstr: str) -> None:
        self.latest_hex = hexstr
        self._broadcast("frame", hexstr)

    def _broadcast(self, event: str, data: str) -> None:
        msg = f"event: {event}\ndata: {data}\n\n".encode()
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(msg)
            except queue.Full:
                try:  # drop the oldest frame for slow clients
                    q.get_nowait()
                    q.put_nowait(msg)
                except Exception:
                    pass

    # -- lifecycle --------------------------------------------------------
    def sim_html(self) -> str:
        if self._sim_html is None:
            html = _read("sim.html")
            html = html.replace("/*FACADE_JS*/", facade_js())
            html = html.replace("__TITLE__", _esc(self.title)).replace("__DESC__", _esc(self.description))
            self._sim_html = html
        return self._sim_html

    def start(self) -> "ControlServer":
        if self._server:
            return self
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # quiet
                pass

            def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _client(self) -> str:
                fwd = self.headers.get("X-Forwarded-For", "")
                return fwd.split(",")[0].strip() if fwd else self.client_address[0]

            def _token(self) -> str:
                hdr = self.headers.get("X-Input-Token")
                if hdr:
                    return hdr.strip()
                qs = parse_qs(urlsplit(self.path).query)
                return (qs.get("key") or [""])[0]

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Input-Token")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path == "/" or path == "/index.html":
                    return self._send(200, server.sim_html().encode())
                if path == "/facade.js":
                    return self._send(200, facade_js().encode(), "application/javascript")
                if path == "/frame":
                    return self._send(200, json.dumps({"rows": 17, "cols": 9, "hex": server.latest_hex}).encode(), "application/json")
                if path == "/healthz":
                    # The input policy, so an operator can tell from outside whether the building
                    # is actually locked down. Whether a token is set, never what it is.
                    return self._send(200, json.dumps({"ok": True, "locked": bool(server.input_token),
                                                       "text_gap_s": server.text_gap_s,
                                                       "clients": len(server._clients)}).encode(), "application/json")
                if path == "/stream":
                    return self._stream()
                if path in server.pages:
                    return self._send(200, server.pages[path].encode())
                if path in server.json_handlers:
                    try:
                        out = server.json_handlers[path]("GET", {})
                    except Exception as e:  # pragma: no cover
                        out = {"error": str(e)}
                    return self._send(200, json.dumps(out).encode(), "application/json")
                return self._send(404, b"not found", "text/plain")

            def do_POST(self):
                path = self.path.split("?", 1)[0]
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b"{}"
                try:
                    data = json.loads(raw.decode() or "{}")
                except Exception:
                    data = {}
                if path == "/input":
                    if not isinstance(data, dict) or not data.get("type"):
                        return self._send(400, b'{"ok":false,"error":"send a JSON object with a type"}', "application/json")
                    if data.get("type") == "text":
                        if not server.allow_text(self._client()):
                            return self._send(429, json.dumps({"ok": False, "error": f"one prompt every {int(server.text_gap_s)} s - give it a moment"}).encode(), "application/json")
                    elif not server.authorized(self._token()):
                        return self._send(401, b'{"ok":false,"error":"this event needs the operator token"}', "application/json")
                    data.setdefault("source", "web")
                    server.bus.push(data)
                    return self._send(200, b'{"ok":true}', "application/json")
                if path in server.json_handlers:
                    try:
                        out = server.json_handlers[path]("POST", data if isinstance(data, dict) else {})
                    except Exception as e:  # pragma: no cover
                        out = {"error": str(e)}
                    return self._send(200, json.dumps(out).encode(), "application/json")
                return self._send(404, b"not found", "text/plain")

            def _stream(self):
                q: queue.Queue = queue.Queue(maxsize=8)
                with server._lock:
                    server._clients.append(q)
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    # initial state
                    self.wfile.write(f"event: meta\ndata: {json.dumps({'title': server.title, 'description': server.description})}\n\n".encode())
                    self.wfile.write(f"event: controls\ndata: {json.dumps(server.controls)}\n\n".encode())
                    if server.status:
                        self.wfile.write(f"event: status\ndata: {json.dumps(server.status)}\n\n".encode())
                    self.wfile.write(f"event: frame\ndata: {server.latest_hex}\n\n".encode())
                    self.wfile.flush()
                    while True:
                        try:
                            msg = q.get(timeout=15)
                        except queue.Empty:
                            msg = b": keepalive\n\n"
                        self.wfile.write(msg)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    with server._lock:
                        if q in server._clients:
                            server._clients.remove(q)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        if self.ssl_cert:
            import ssl

            sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            sctx.load_cert_chain(self.ssl_cert, self.ssl_key or self.ssl_cert)
            self._server.socket = sctx.wrap_socket(self._server.socket, server_side=True)
        self._thread = threading.Thread(target=self._server.serve_forever, name="control-server", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def scheme(self) -> str:
        return "https" if self.ssl_cert else "http"

    @property
    def url(self) -> str:
        return f"{self.scheme}://localhost:{self.port}"

    @property
    def lan_url(self) -> str:
        return f"{self.scheme}://{lan_ip()}:{self.port}"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def qr_data_uri(text: str) -> str | None:
    """PNG data URI of a QR code for ``text`` if the optional ``qrcode`` package is installed."""
    try:
        import base64
        import io

        import qrcode  # type: ignore

        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None
