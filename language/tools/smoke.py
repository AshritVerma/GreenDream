"""Manual smoke test against a running server: state, a handful of queries, both switch
positions, the day's arc.

    python tools/smoke.py --api http://localhost:8100 --admin-token ...

Prints the tier that answered and the draft for each query, which is the fastest way to see
whether a real API key is doing anything useful.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

QUERIES = ["a thunderstorm", "my heart is racing", "a rocket launch",
           "the first snow", "the T is late"]


def call(url: str, body: Optional[Dict[str, Any]] = None, token_header: str = "", token: str = "") -> Dict[str, Any]:
    headers = {"content-type": "application/json", "user-agent": "greendream-llm-smoke/0.1"}
    if token:
        headers[token_header] = token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "body": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": json.loads(e.read().decode("utf-8") or "{}")}


def submit(api: str, query: str, token: str) -> Dict[str, Any]:
    """Send one query, waiting out the rate limit rather than reporting it as a failure."""
    out = call(f"{api}/api/ingest", {"query": query, "source": "web"}, "x-ingest-token", token)
    if out["status"] == 429:
        time.sleep(float(out["body"].get("retry_after_s", 2)) + 0.2)
        out = call(f"{api}/api/ingest", {"query": query, "source": "web"}, "x-ingest-token", token)
    return out


def show_scene(out: Dict[str, Any]) -> None:
    body = out["body"]
    if "result" not in body:
        print(f"  [{out['status']}] {json.dumps(body)[:200]}")
        return
    r, d = body["result"], body["result"]["spec_draft"]
    sprite = "sprite" if d["sprite"] else "-"
    print(f"  {r['query'][:28]:28s} {r['tier']:18s} {body['latency_ms']:>5}ms  "
          f"world={d['world']:10s} motion={d['motion']['kind']:8s} "
          f"particles={d['particles']['kind']:8s} word={str(d['word']):8s} {sprite}  "
          f"rec={r['interpretation']['recognizability']:.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://localhost:8100")
    ap.add_argument("--admin-token", default="")
    ap.add_argument("--ingest-token", default="")
    args = ap.parse_args()

    state = call(f"{args.api}/api/state")
    print("\n--- GET /api/state")
    print(json.dumps(state["body"], indent=2))

    def run(label: str) -> None:
        print(f"\n--- {label}")
        for query in QUERIES:
            show_scene(submit(args.api, query, args.ingest_token))

    if args.admin_token:
        call(f"{args.api}/api/admin/switch", {"llm": "on"}, "x-admin-token", args.admin_token)
        run("POST /api/ingest  (llm on)")
        call(f"{args.api}/api/admin/switch", {"llm": "off"}, "x-admin-token", args.admin_token)
        run("POST /api/ingest  (llm off, local fallback)")

        print("\n--- gate -> closed")
        call(f"{args.api}/api/admin/switch", {"gate": "closed"}, "x-admin-token", args.admin_token)
        shut = submit(args.api, "sunrise", args.ingest_token)
        print(f"  [{shut['status']}] {shut['body'].get('state')}: {shut['body'].get('message')}")
        call(f"{args.api}/api/admin/switch", {"gate": "auto", "llm": "on"}, "x-admin-token", args.admin_token)
    else:
        run("POST /api/ingest")

    arc = call(f"{args.api}/api/arc")["body"]
    print(f"\n--- GET /api/arc  ({arc.get('count', 0)} scenes today)")
    if arc.get("count"):
        print(f"  {arc['arc']['title']}: {arc['arc']['logline']}")
        print(f"  order: {' -> '.join(arc['scenes'][i] for i in arc['arc']['order'])}")


if __name__ == "__main__":
    main()
