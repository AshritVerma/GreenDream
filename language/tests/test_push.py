"""The push tool, driven against fakes.

The thing worth testing here is not that it can POST. It is the cursor: a row this walks past
is a prompt somebody typed that the building will never show, and the queue is the only copy.
So every test below is really asking the same question — after this went wrong, is the row
still going to be sent?
"""

from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("push_tool", ROOT / "tools" / "push_to_greendream.py")
push = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(push)


def row(seq: int, query: str, *, ok: bool = True, review: str = "auto",
        channel: str = "pedestal", priority: str = "live") -> Dict[str, Any]:
    return {
        "id": f"id{seq}", "seq": seq, "channel": channel, "tier": "library",
        "latency_ms": 4, "priority": priority, "review": review,
        "result": {"query": query, "ok": ok,
                   "spec_draft": {"title": query, "world": "storm", "word": None}},
    }


class Runner:
    """A GreenDream that accepts, refuses or breaks, and remembers what it was told."""

    def __init__(self, refuse_at=(), code: int = 401, explode_at=()) -> None:
        self.sent: List[Dict[str, Any]] = []
        self.tries = 0
        self.refuse_at, self.code, self.explode_at = set(refuse_at), code, set(explode_at)

    def post(self, url: str, body: Dict[str, Any], timeout: float = 6.0, token=None) -> int:
        n, self.tries = self.tries, self.tries + 1
        if n in self.explode_at:
            raise OSError("connection refused")
        if n in self.refuse_at:
            raise urllib.error.HTTPError(url, self.code, "no", {},  # type: ignore[arg-type]
                                         _Body(json.dumps({"error": "refused"})))
        self.sent.append(body)
        return 200


class _Body:
    """Enough of a file for HTTPError to hold and for us to read the detail out of."""

    def __init__(self, text: str) -> None:
        self._text = text.encode()

    def read(self) -> bytes:
        return self._text

    def close(self) -> None:
        pass


@pytest.fixture
def wired(monkeypatch):
    """Patch the tool's two IO calls; hand back a helper that drains one page."""
    state: Dict[str, Any] = {}

    def go(rows: List[Dict[str, Any]], runner: Runner, *, cursor: int = 0, page_cursor=None, **kw):
        def get_json(url, timeout=6.0, token=None):
            since = int(url.split("since=")[1].split("&")[0])
            visible = [r for r in rows if r["seq"] > since]
            return {"cursor": page_cursor if page_cursor is not None
                    else max([r["seq"] for r in visible], default=since),
                    "count": len(visible), "submissions": visible}

        monkeypatch.setattr(push, "get_json", get_json)
        monkeypatch.setattr(push, "post_json", runner.post)
        monkeypatch.setattr(push.time, "sleep", lambda _s: None)
        return push.drain("http://api", "http://runner", cursor, verbose=False, **kw)

    state["go"] = go
    return go


def test_a_clean_page_sends_everything_and_advances(wired):
    r = Runner()
    cursor, ok = wired([row(10, "a storm"), row(20, "a rocket")], r)
    assert ok is True
    assert [e["text"] for e in r.sent] == ["a storm", "a rocket"]
    assert cursor == 20


def test_the_event_carries_the_draft_not_the_query(wired):
    r = Runner()
    wired([row(10, "a storm")], r)
    ev = r.sent[0]
    assert ev["type"] == "spec" and ev["origin"] == "ingest"
    assert ev["spec"]["title"] == "a storm"      # the interpretation already paid for
    assert ev["tier"] == "library" and ev["latency_ms"] == 4
    assert ev["source"] == "pedestal" and ev["priority"] == "live"


def test_a_refused_row_leaves_the_cursor_before_it(wired):
    """The regression: a 401 used to advance the cursor past the whole page."""
    r = Runner(refuse_at={1})
    cursor, ok = wired([row(10, "a storm"), row(20, "a rocket"), row(30, "fireflies")], r)
    assert ok is False
    assert [e["text"] for e in r.sent] == ["a storm"]
    assert cursor == 10, "the rocket must still be waiting, not skipped"


def test_fixing_the_token_sends_the_rows_that_were_refused(wired):
    rows = [row(10, "a storm"), row(20, "a rocket"), row(30, "fireflies")]
    locked = Runner(refuse_at={1})
    cursor, ok = wired(rows, locked)
    assert ok is False

    opened = Runner()
    cursor, ok = wired(rows, opened, cursor=cursor)
    assert ok is True
    assert [e["text"] for e in opened.sent] == ["a rocket", "fireflies"]
    assert cursor == 30


def test_nothing_is_sent_twice_across_two_clean_drains(wired):
    rows = [row(10, "a storm"), row(20, "a rocket")]
    r = Runner()
    cursor, _ = wired(rows, r)
    cursor, _ = wired(rows, r, cursor=cursor)
    assert [e["text"] for e in r.sent] == ["a storm", "a rocket"]


def test_a_dead_runner_stops_rather_than_burning_the_page(wired):
    r = Runner(explode_at={1})
    cursor, ok = wired([row(10, "a storm"), row(20, "a rocket")], r)
    assert ok is False and cursor == 10


def test_a_row_the_runner_rejects_on_its_own_merits_is_stepped_over(wired):
    """A 400 is this row's problem; retrying it forever would wedge the queue."""
    r = Runner(refuse_at={1}, code=400)
    cursor, ok = wired([row(10, "a storm"), row(20, "bad"), row(30, "fireflies")], r)
    assert ok is True
    assert [e["text"] for e in r.sent] == ["a storm", "fireflies"]
    assert cursor == 30


def test_a_refusal_never_leaves_here(wired):
    r = Runner()
    cursor, ok = wired([row(10, "a storm"), row(20, "blocked", ok=False), row(30, "fireflies")], r)
    assert [e["text"] for e in r.sent] == ["a storm", "fireflies"]
    assert cursor == 30 and ok is True


def test_a_rejected_row_never_leaves_here(wired):
    r = Runner()
    wired([row(10, "a storm"), row(20, "vetoed", review="rejected")], r)
    assert [e["text"] for e in r.sent] == ["a storm"]


def test_approved_only_skips_what_no_one_has_looked_at(wired):
    rows = [row(10, "onsite"), row(20, "waiting", review="pending"), row(30, "blessed", review="approved")]
    r = Runner()
    cursor, ok = wired(rows, r, approved_only=True)
    assert [e["text"] for e in r.sent] == ["onsite", "blessed"]
    assert cursor == 30, "a pending row is skipped for now, not retried forever"


def test_a_queue_that_cannot_be_read_changes_nothing(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("no service")

    monkeypatch.setattr(push, "get_json", boom)
    cursor, ok = push.drain("http://api", "http://runner", 77, verbose=False)
    assert (cursor, ok) == (77, False)


def test_the_cursor_steps_over_rows_the_queue_filtered_out(wired):
    """The queue hides refusals but its cursor counts them, so a clean page may jump ahead."""
    r = Runner()
    cursor, ok = wired([row(10, "a storm")], r, page_cursor=99)
    assert ok is True and cursor == 99
