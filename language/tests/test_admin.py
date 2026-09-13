"""The operator's review page, and the endpoint behind it.

A person on a plaza with twenty minutes before dusk has to be able to see what is waiting,
judge it, and say yes or no. These tests cover the two halves of that: the endpoint carries
enough of each reading to judge it, and the page is a shell that reads nothing without the
admin token.

    cd language && python -m pytest -q tests/test_admin.py
"""

from __future__ import annotations

import re

from app.config import settings

ADMIN = {"x-admin-token": "test-admin"}


def _post(client, query, source="web"):
    r = client.post("/api/ingest", json={"query": query, "source": source})
    assert r.status_code == 200, r.text
    return r.json()


def _row(client, rid, state="pending"):
    body = client.get(f"/api/admin/review?state={state}&limit=500", headers=ADMIN).json()
    return next((x for x in body["rows"] if x["id"] == rid), None)


# --------------------------------------------------------------------------- the endpoint

def test_a_row_carries_enough_to_judge_it(client):
    posted = _post(client, "a thunderstorm")
    row = _row(client, posted["id"])
    assert row is not None

    # what they said, and what the building would become
    assert row["query"] == "a thunderstorm"
    assert row["title"] and row["world"] == "storm" and row["duration_s"]
    assert row["palette"].get("accent", "").startswith("#")
    assert row["keywords"], "the keywords are how you tell a good reading from a lucky one"
    assert 0.0 <= row["recognizability"] <= 1.0

    # ...and how much of it was actually understood
    assert row["match"] and row["coverage"] == 1.0 and row["unused_words"] == []
    assert row["channel"] == "web" and row["priority"] == "dream" and row["review"] == "pending"


def test_a_partial_reading_says_so_on_the_row(client):
    # The case an operator has to look twice at: a canned scene unlocked by one word.
    posted = _post(client, "lebron dunk as 76er")
    row = _row(client, posted["id"])
    assert row["unused_words"] == ["76er"] and row["coverage"] < 1.0


def test_a_refusal_shows_as_a_refusal_rather_than_as_a_scene(client):
    posted = _post(client, "kill everyone")
    row = _row(client, posted["id"])
    assert row["ok"] is False and row["review"] == "pending"


def test_the_original_pending_key_still_works(client):
    # Kept on purpose: anything already built against this endpoint must not have to change.
    posted = _post(client, "a lone heron")
    body = client.get("/api/admin/review", headers=ADMIN).json()
    assert body["state"] == "pending"
    assert body["pending"] == body["rows"]
    assert posted["id"] in [r["id"] for r in body["pending"]]


def test_decided_rows_are_visible_after_the_decision(client):
    posted = _post(client, "a quiet tuesday")
    assert _row(client, posted["id"], "decided") is None

    client.post("/api/admin/review", json={"id": posted["id"], "decision": "approved"}, headers=ADMIN)
    assert _row(client, posted["id"], "pending") is None, "it leaves the queue"
    decided = _row(client, posted["id"], "decided")
    assert decided is not None and decided["review"] == "approved"
    assert _row(client, posted["id"], "approved") is not None
    assert _row(client, posted["id"], "rejected") is None


def test_a_decision_can_be_taken_back_from_the_page(client):
    posted = _post(client, "a refused gull")
    client.post("/api/admin/review", json={"id": posted["id"], "decision": "rejected"}, headers=ADMIN)
    assert _row(client, posted["id"], "rejected") is not None

    client.post("/api/admin/review", json={"id": posted["id"], "decision": "pending"}, headers=ADMIN)
    assert _row(client, posted["id"], "pending") is not None, "back in the queue"


def test_onsite_rows_are_not_in_anybody_queue(client):
    # Nobody has to approve a prompt that was typed at the building.
    posted = _post(client, "sunrise", source="pedestal")
    assert _row(client, posted["id"], "pending") is None
    assert _row(client, posted["id"], "decided") is None
    assert _row(client, posted["id"], "all") is not None


def test_the_counts_are_there_so_the_page_can_say_how_much_is_left(client):
    _post(client, "a spare pigeon")
    body = client.get("/api/admin/review", headers=ADMIN).json()
    assert body["counts"].get("pending", 0) >= 1


def test_an_unknown_state_is_rejected(client):
    assert client.get("/api/admin/review?state=maybe", headers=ADMIN).status_code == 422


def test_every_state_still_needs_the_token(client):
    for state in ("pending", "approved", "rejected", "decided", "all"):
        assert client.get(f"/api/admin/review?state={state}").status_code == 401, state


# --------------------------------------------------------------------------- the page

def test_the_page_is_served_and_holds_no_data(client):
    r = client.get("/admin")
    assert r.status_code == 200
    page = r.text
    assert "Review" in page and "admin token" in page
    assert "/api/admin/review" in page and "x-admin-token" in page
    # It is a shell: the data arrives over the token-gated API, so a page fetched without one
    # cannot contain a query.
    _post(client, "a secret starling")
    assert "starling" not in client.get("/admin").text


def test_the_page_asks_for_the_token_before_anything_else(client):
    page = client.get("/admin").text
    assert "gatecover" in page, "the token prompt covers the page until it is satisfied"
    assert "sessionStorage" in page, "and it is kept for that tab only"
    assert "401" in page, "a refused token puts the prompt back"
    # The overlay is hidden by adding `hide` to it, and an id beats a class, so without this
    # rule the prompt never dismisses and the page is unusable with the right token in it.
    assert "#gatecover.hide" in page


def test_nothing_on_the_page_is_small_print(client):
    # It is read outdoors, at night, by somebody who is also watching a building.
    page = client.get("/admin").text
    sizes = [int(m) for m in re.findall(r"font-size:\s*(\d+)px", page)]
    assert sizes and min(sizes) >= 15, f"smallest type on the page is {min(sizes)}px"


def test_the_page_escapes_everything_it_renders(client):
    """Same rule as the bench: a query is somebody else's text, and this page is the only
    place it reaches innerHTML."""
    page = client.get("/admin").text
    assert "const esc =" in page, "one escaping helper"

    tainted = ("r.query", "r.title", "r.world", "r.word", "r.theme", "r.notes", "r.tier",
               "r.match", "r.channel", "r.id", "r.review", "r.priority", "r.received_at",
               "r.unused_words", "r.keywords", "r.beats", "out.detail", "out.gate_mode")
    # `esc(x)` and `list.map(esc)` both count as escaped; nothing else does.
    bad = [m for m in re.findall(r"\$\{[^{}]*\}", page)
           if any(f in m for f in tainted) and "esc(" not in m and ".map(esc)" not in m]
    assert not bad, f"these interpolations reach innerHTML unescaped: {bad}"


def test_the_page_offers_the_switches_and_points_at_the_other_kill_switch(client):
    page = client.get("/admin").text
    assert "/api/admin/switch" in page and "intake gate" in page and "model tier" in page
    # Two different switches and an operator must not confuse them: the gate stops words
    # coming in, freezing the runner stops the building showing anything.
    assert "FREEZE" in page


def test_the_index_advertises_the_page(client):
    assert client.get("/").json()["admin"] == "/admin"


# --------------------------------------------------------------------------- tokens

def test_a_token_can_come_from_a_file_rather_than_a_command_line(monkeypatch, tmp_path):
    from app.config import read_secret

    path = tmp_path / "admin.token"
    path.write_text("from-a-file\n", encoding="utf-8")
    monkeypatch.delenv("GD_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("GD_ADMIN_TOKEN_FILE", str(path))
    assert read_secret("GD_ADMIN_TOKEN") == "from-a-file", "trailing newline stripped"

    settings.refresh()
    assert settings.admin_token == "from-a-file"

    monkeypatch.setenv("GD_ADMIN_TOKEN", "from-the-environment")
    settings.refresh()
    assert settings.admin_token == "from-the-environment", "what works today keeps working"


def test_an_unreadable_token_file_says_so(monkeypatch, tmp_path, capsys):
    from app.config import read_secret

    monkeypatch.delenv("GD_INGEST_TOKEN", raising=False)
    monkeypatch.setenv("GD_INGEST_TOKEN_FILE", str(tmp_path / "missing"))
    assert read_secret("GD_INGEST_TOKEN") == ""
    assert "unreadable" in capsys.readouterr().out


def test_the_review_page_works_with_a_file_held_token(client, monkeypatch, tmp_path):
    path = tmp_path / "admin.token"
    path.write_text("file-held", encoding="utf-8")
    monkeypatch.delenv("GD_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("GD_ADMIN_TOKEN_FILE", str(path))
    settings.refresh()

    assert client.get("/api/admin/review", headers=ADMIN).status_code == 401
    assert client.get("/api/admin/review", headers={"x-admin-token": "file-held"}).status_code == 200


def test_the_pusher_prefers_a_file_over_a_flag(monkeypatch, tmp_path):
    import sys

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "tools"))
    from push_to_greendream import resolve_token

    path = tmp_path / "input.token"
    path.write_text("op-secret\n", encoding="utf-8")
    monkeypatch.delenv("GREENDREAM_INPUT_TOKEN_FILE", raising=False)

    assert resolve_token("", str(path), "GREENDREAM_INPUT_TOKEN") == "op-secret"
    monkeypatch.setenv("GREENDREAM_INPUT_TOKEN_FILE", str(path))
    assert resolve_token("", "", "GREENDREAM_INPUT_TOKEN") == "op-secret"
    assert resolve_token("on-the-command-line", "", "GREENDREAM_INPUT_TOKEN") == "on-the-command-line", \
        "the flag still wins, so a running deployment does not change under anyone"
    assert resolve_token("", str(tmp_path / "nope"), "GD_MISSING") == ""
