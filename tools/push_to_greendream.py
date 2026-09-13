"""Drain the ingest queue into a running GreenDream instance.

The push half of the handoff to pixels, written but deliberately not wired: it does not
touch the GreenDream repo, it only speaks its existing HTTP vocabulary. GreenDream's
ControlServer turns `POST /input` bodies into events on its InputBus, and a `text` event is
what its own prompt engine already listens for.

    python tools/push_to_greendream.py --api http://localhost:8100 --target http://localhost:8000

Once the renderer learns to accept a finished draft, this sends `spec` events instead of
`text` and the model stops being asked the same question twice.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from typing import Any, Dict, List


def get_json(url: str, timeout: float = 6.0) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"user-agent": "greendream-llm-push/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, body: Dict[str, Any], timeout: float = 6.0) -> int:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json", "user-agent": "greendream-llm-push/0.1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://localhost:8100", help="this ingest service")
    ap.add_argument("--target", default="http://localhost:8000", help="a running GreenDream")
    ap.add_argument("--since", type=int, default=0, help="queue cursor to start from")
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    cursor = args.since
    while True:
        try:
            page = get_json(f"{args.api}/api/queue?since={cursor}&limit=50")
        except Exception as e:
            print(f"[push] queue read failed: {e}", flush=True)
            page = {"submissions": [], "cursor": cursor}

        subs: List[Dict[str, Any]] = page.get("submissions", [])
        for sub in subs:
            result = sub.get("result") or {}
            if not result.get("ok"):
                continue
            body = {"type": "text", "text": result["query"], "source": sub.get("channel", "web")}
            try:
                post_json(f"{args.target}/input", body)
                print(f"[push] {result['query']!r} -> {args.target}", flush=True)
            except Exception as e:
                print(f"[push] send failed: {e}", flush=True)
            time.sleep(0.2)  # let the tower finish one scene before the next arrives
        cursor = int(page.get("cursor", cursor))

        if args.once:
            print(f"[push] cursor now {cursor}", flush=True)
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
