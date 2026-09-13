"""Simulator-only helpers for sundai.willsarg.com (never needed on the real building).

    python -m common.sundai clip INSTANCE recording.json [fps]   upload a loop that plays with no laptop
    python -m common.sundai clear INSTANCE                       remove it
    python -m common.sundai status INSTANCE
"""

from __future__ import annotations

import http.client
import json
import sys
from typing import List

BASE = "sundai.willsarg.com"
UA = {"User-Agent": "greenhack/1"}


def _req(method: str, path: str, body=None, ctype: str | None = None):
    c = http.client.HTTPSConnection(BASE, timeout=15)
    h = dict(UA)
    if ctype:
        h["Content-Type"] = ctype
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data


def hex_to_bytes(hx: str) -> bytes:
    return bytes.fromhex(hx)


def upload_clip(instance: str, hex_frames: List[str], fps: int = 15) -> bool:
    """Frames as the runtime's hex strings (153*6 chars), 1..900 of them, fps 1..30."""
    hex_frames = hex_frames[:900]
    fps = max(1, min(30, int(fps)))
    buf = bytearray((0x43, fps, len(hex_frames) & 0xFF, len(hex_frames) >> 8))
    for hx in hex_frames:
        buf += hex_to_bytes(hx)
    st, data = _req("POST", f"/api/i/{instance}/clip", bytes(buf), "application/octet-stream")
    print(f"[sundai] clip {len(hex_frames)} frames @ {fps} fps -> HTTP {st} {data[:120].decode(errors='replace')}")
    return st < 400


def clear_clip(instance: str) -> bool:
    st, _ = _req("DELETE", f"/api/i/{instance}/clip")
    return st < 400


def status(instance: str) -> dict:
    st, data = _req("GET", f"/api/i/{instance}/")
    return json.loads(data) if st == 200 else {"error": st}


if __name__ == "__main__":
    cmd, inst = sys.argv[1], sys.argv[2]
    if cmd == "clip":
        rec = json.load(open(sys.argv[3]))
        fps = int(sys.argv[4]) if len(sys.argv) > 4 else int(rec.get("fps", 15))
        frames = rec["frames"]
        step = max(1, round(rec.get("fps", 30) / fps))
        upload_clip(inst, frames[::step][:900], fps)
    elif cmd == "clear":
        print("cleared" if clear_clip(inst) else "failed")
    else:
        print(json.dumps(status(inst), indent=1))
