"""Drain the ingest queue into a running GreenDream instance.

The push half of the handoff to pixels. It does not touch the GreenDream repo, it only
speaks its existing HTTP vocabulary: `POST /input` becomes an event on its InputBus.

    python tools/push_to_greendream.py --api http://localhost:8100 --target http://localhost:8000

What it sends is a `spec` event carrying the finished `spec_draft`, not the raw query. That
matters for three reasons: the model is not asked the same question twice (the answer was
already paid for here), the interpretation the operator previewed is the one that plays, and
the tier and latency travel with it so the journal can say who answered.

GreenDream re-validates every spec it receives, so this is a suggestion rather than a command;
the `priority` field decides whether it performs now or is only material for tonight's dream.

Set GREENDREAM_INPUT_TOKEN to the runner's operator token: a `spec` event changes what the
building shows, so the runner requires the token for it. Blocked or rejected rows never leave
here - the queue filters them, and this checks again, because a filter on one side of an HTTP
call is not a guarantee on the other.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

UA = "greendream-llm-push/0.2"


def get_json(url: str, timeout: float = 6.0, token: Optional[str] = None) -> Dict[str, Any]:
    headers = {"user-agent": UA}
    if token:
        headers["x-ingest-token"] = token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, body: Dict[str, Any], timeout: float = 6.0, token: Optional[str] = None) -> int:
    headers = {"content-type": "application/json", "user-agent": UA}
    if token:
        headers["x-input-token"] = token
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def event_for(sub: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One queue row to one GreenDream `spec` event, or None if it should not be sent."""
    result = sub.get("result") or {}
    draft = result.get("spec_draft")
    if not result.get("ok") or not isinstance(draft, dict):
        return None
    if sub.get("review") == "rejected":
        return None
    return {
        "type": "spec",
        "spec": draft,
        "text": result.get("query", ""),
        "tier": sub.get("tier", "ingest"),
        "latency_ms": int(sub.get("latency_ms") or 0),
        "source": sub.get("channel", "web"),
        "priority": sub.get("priority", "dream"),
        "origin": "ingest",
    }


def drain(api: str, target: str, cursor: int, *, api_token: Optional[str] = None,
          input_token: Optional[str] = None, limit: int = 50, gap: float = 0.2,
          approved_only: bool = False, verbose: bool = True) -> Tuple[int, bool]:
    """Send one page of the queue. Returns (new cursor, whether the page went through).

    The cursor only ever advances past rows this actually dealt with. A row the runner
    refused leaves the cursor where it was, so fixing the token and running again sends it
    rather than skipping it: a page dropped here is a prompt somebody typed that the building
    never showed, and there is no second copy of it anywhere.
    """
    try:
        page = get_json(f"{api}/api/queue?since={cursor}&limit={limit}", token=api_token)
    except Exception as e:
        print(f"[push] queue read failed: {e}", flush=True)
        return cursor, False

    done = cursor        # how far we have genuinely got
    subs: List[Dict[str, Any]] = page.get("submissions", [])
    for sub in subs:
        seq = int(sub.get("seq") or 0)
        if approved_only and sub.get("review") == "pending":
            done = max(done, seq)   # an operator has not looked at this one yet
            continue
        ev = event_for(sub)
        if ev is None:
            done = max(done, seq)
            continue
        try:
            post_json(f"{target}/input", ev, token=input_token)
            done = max(done, seq)
            if verbose:
                print(f"[push] {ev['text']!r} ({ev['tier']}, {ev['priority']}) -> {target}", flush=True)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()[:200]
            except Exception:
                pass
            print(f"[push] refused: HTTP {e.code} {detail}", flush=True)
            if e.code in (401, 403):
                print("[push] the runner wants its operator token: set GREENDREAM_INPUT_TOKEN.\n"
                      f"[push] stopping at cursor {done}; nothing after it has been sent.", flush=True)
                return done, False
            done = max(done, seq)   # a 4xx this row's own fault: skip it, keep going
        except Exception as e:
            print(f"[push] send failed: {e}", flush=True)
            return done, False      # the runner may be down; do not burn the rest of the page
        time.sleep(gap)   # let the tower finish one scene before the next arrives

    # Nothing was refused, so it is safe to take the service's cursor, which also steps over
    # the rows the queue filtered out before we ever saw them.
    return max(done, int(page.get("cursor", cursor))), True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://localhost:8100", help="this ingest service")
    ap.add_argument("--target", default="http://localhost:8000", help="a running GreenDream")
    ap.add_argument("--since", type=int, default=0, help="queue cursor to start from")
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--approved-only", action="store_true",
                    help="skip rows no operator has approved yet")
    ap.add_argument("--input-token", default=os.environ.get("GREENDREAM_INPUT_TOKEN", ""),
                    help="the runner's operator token (a spec event needs it)")
    ap.add_argument("--api-token", default=os.environ.get("GD_INGEST_TOKEN", ""),
                    help="this service's token, if it is set")
    args = ap.parse_args()

    cursor = args.since
    while True:
        cursor, ok = drain(args.api, args.target, cursor,
                           api_token=args.api_token or None, input_token=args.input_token or None,
                           approved_only=args.approved_only)
        if args.once:
            print(f"[push] cursor now {cursor}", flush=True)
            raise SystemExit(0 if ok else 1)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
