"""Manual smoke test against a running server: state, five phrases, both switch positions.

    python tools/smoke.py --api http://localhost:8100 --admin-token ...

Prints the tier that answered and one draft per phrase, which is the fastest way to see
whether a real API key is doing anything useful.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

FIVE = ["a thunderstorm over the river", "my heart is racing", "a rocket launch",
        "the first snow day", "i miss my dog"]


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


def show(label: str, out: Dict[str, Any]) -> None:
    body = out["body"]
    print(f"\n--- {label}  [{out['status']}]")
    if "results" not in body:
        print(json.dumps(body, indent=2)[:900])
        return
    print(f"tier={body['tier']}  latency={body['latency_ms']}ms  priority={body['priority']}")
    for r in body["results"]:
        d = r["spec_draft"]
        sprite = "sprite" if d["sprite"] else "-"
        print(f"  [{r['index']}] {r['phrase'][:34]:34s} {r['tier']:18s} "
              f"world={d['world']:10s} motion={d['motion']['kind']:8s} "
              f"particles={d['particles']['kind']:8s} word={str(d['word']):8s} {sprite}")
    arc = body["arc"]
    print(f"  arc {arc['title']!r} order={arc['order']} :: {arc['through_line']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://localhost:8100")
    ap.add_argument("--admin-token", default="")
    ap.add_argument("--ingest-token", default="")
    args = ap.parse_args()

    show("GET /api/state", call(f"{args.api}/api/state"))

    def submit(label: str) -> None:
        show(label, call(f"{args.api}/api/ingest", {"phrases": FIVE, "source": "web"},
                         "x-ingest-token", args.ingest_token))

    if args.admin_token:
        call(f"{args.api}/api/admin/switch", {"llm": "on"}, "x-admin-token", args.admin_token)
        submit("POST /api/ingest  (llm on)")
        call(f"{args.api}/api/admin/switch", {"llm": "off"}, "x-admin-token", args.admin_token)
        submit("POST /api/ingest  (llm off, local fallback)")
        show("gate -> closed", call(f"{args.api}/api/admin/switch", {"gate": "closed"},
                                    "x-admin-token", args.admin_token))
        show("POST /api/ingest  (gate closed)", call(f"{args.api}/api/ingest", {"phrases": ["sunrise"]},
                                                     "x-ingest-token", args.ingest_token))
        call(f"{args.api}/api/admin/switch", {"gate": "auto", "llm": "on"}, "x-admin-token", args.admin_token)
    else:
        submit("POST /api/ingest")

    show("GET /api/queue", call(f"{args.api}/api/queue?limit=3"))


if __name__ == "__main__":
    main()
