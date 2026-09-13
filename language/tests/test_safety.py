"""What the building will not say, and who gets to decide.

The tower is a public object with nobody standing next to it. These tests cover the three
places that judgement lives: the moderation gate, the scrub on the way in, and the review
queue an operator works through before the sun goes down.

    python -m pytest -q tests/test_safety.py
"""

from __future__ import annotations

import re

import pytest

from app import fallback, store
from app.config import settings

ADMIN = {"x-admin-token": "test-admin"}


# --------------------------------------------------------------------------- moderation

@pytest.mark.parametrize("phrase", [
    "kill everyone",
    "i want to kill someone",
    "shoot the police",
    "nazi rally",
    "a genocide",
    "rape",
    "i want to die",
    "kill myself",
    "self harm",
    "vote for trump",
    "vote against them",
    "buy bitcoin now",
    "check www.example.com",
    "text me 555 0100",
    "she is a whore",
    "fuck this",
])
def test_the_categories_we_refuse(phrase):
    assert fallback.is_blocked(phrase), f"{phrase!r} should not reach the building"


@pytest.mark.parametrize("phrase", [
    "thunderstorm",
    "kill the lights",              # a lighting cue, not a threat
    "a killer bassline",
    "my heart is racing",
    "lebron dunk",
    "sunset over boston",
    "go celtics",
    "class of 2027",
    "i miss my dog",
    "the charles river",
    "shooting stars",               # 'shoot' with no target
])
def test_the_things_we_happily_show(phrase):
    assert not fallback.is_blocked(phrase), f"{phrase!r} is innocent and was refused"


def test_a_refusal_is_a_shrug_and_never_a_scene():
    result = fallback.local_result("kill everyone")
    assert result.ok is False and result.tier == "blocked"
    assert result.spec_draft["title"] == "shrug" and result.spec_draft["word"] == "HMM?"
    assert result.spec_draft["ok"] is False


def test_moderation_beats_the_library():
    # "fuck this storm" contains a library word; the refusal still wins.
    assert fallback.local_result("fuck this storm").tier == "blocked"


# --------------------------------------------------------------------------- pii

@pytest.mark.parametrize("raw, gone", [
    ("email me at bob@example.com", "bob@example.com"),
    ("see https://example.com/x", "https://example.com/x"),
    ("call 617 555 0100", "555"),
    ("@someones_handle", "@someones_handle"),
])
def test_contact_details_are_scrubbed(raw, gone):
    assert gone not in fallback.scrub_pii(raw)


def test_the_scrub_leaves_ordinary_words_alone():
    for phrase in ("thunderstorm", "lebron dunk as 76er", "class of 2027", "i'm so happy"):
        assert fallback.scrub_pii(phrase) == phrase


def test_a_phone_number_is_scrubbed_before_the_word_count(client):
    # It would be a confusing way to say no: the words only go over the limit before scrubbing.
    body = client.post("/api/ingest", json={"query": "call me 617 555 0100"})
    assert body.status_code == 200
    assert "555" not in body.json()["result"]["query"]


def test_nothing_of_the_query_reaches_the_facade_verbatim():
    # `word` is the only text the building shows, and it is never the person's own words.
    for phrase in ("hello there stranger", "bob@example.com", "<script>alert(1)</script>"):
        draft = fallback.local_result(phrase).spec_draft
        word = draft["word"]
        assert word is None or (len(word) <= 7 and word == word.upper())


def test_the_bench_escapes_everything_it_renders(client):
    """The facade cannot show text, so the operator's bench is the only place injection lands.

    `GET /api/arc` deliberately still returns the queries (the dream composer writes notes from
    them, and they are already scrubbed and moderated), so the fix belongs at the render site.
    """
    page = client.get("/demo").text
    assert "const esc =" in page, "the bench needs one escaping helper"

    # Any `${...}` that mentions a field a person or a model controls must also call esc().
    tainted = ("r.query", "it.notes", "it.title", "it.theme", "it.keywords", "a.arc.logline",
               "a.arc.title", "a.arc.through_line", "a.scenes", "body.message", "out.detail",
               "b.label", "b.word", "d.word", "d.world", "r.tier", "r.match")
    bad = [m for m in re.findall(r"\$\{[^{}]*\}", page)
           if any(f in m for f in tainted) and "esc(" not in m]
    assert not bad, f"these interpolations reach innerHTML unescaped: {bad}"


def test_a_script_tag_survives_as_inert_text(client):
    body = client.post("/api/ingest", json={"query": "<script>alert(1)</script>"})
    # It is not rejected - it is just words that depict nothing, and the facade shows none of it.
    assert body.status_code == 200
    assert body.json()["result"]["spec_draft"]["word"] in (None, "SCRIPT", "ALERT"), "letters only"


# --------------------------------------------------------------------------- the queue

def test_a_refusal_is_not_handed_to_the_pixel_side(client):
    start = client.get("/api/queue").json()["cursor"]
    client.post("/api/ingest", json={"query": "kill everyone"})
    ok = client.post("/api/ingest", json={"query": "sunrise"}).json()

    page = client.get(f"/api/queue?since={start}").json()
    queries = [r["result"]["query"] for r in page["submissions"]]
    assert "kill everyone" not in queries, "the queue drives 153 windows"
    assert "sunrise" in queries
    assert page["cursor"] >= ok["seq"], "the cursor still moves past what it filtered"


def test_a_refusal_is_kept_in_the_log(client):
    # Filtered from the queue, not erased: "we said no to this" is worth keeping.
    client.post("/api/ingest", json={"query": "kill everyone"})
    page = client.get("/api/queue?include_refused=true").json()
    assert any(r["result"]["query"] == "kill everyone" for r in page["submissions"])


# --------------------------------------------------------------------------- review

def test_remote_submissions_wait_for_a_person(client):
    posted = client.post("/api/ingest", json={"query": "a lone seagull", "source": "web"}).json()
    pending = client.get("/api/admin/review", headers=ADMIN).json()
    assert posted["id"] in [row["id"] for row in pending["pending"]]


def test_onsite_submissions_do_not(client):
    posted = client.post("/api/ingest", json={"query": "sunrise", "source": "pedestal"}).json()
    pending = client.get("/api/admin/review", headers=ADMIN).json()
    assert posted["id"] not in [row["id"] for row in pending["pending"]]


def test_the_review_queue_needs_the_admin_token(client):
    assert client.get("/api/admin/review").status_code == 401
    assert client.post("/api/admin/review", json={"id": "x", "decision": "approved"}).status_code == 401


def test_approving_clears_it_from_the_queue(client):
    posted = client.post("/api/ingest", json={"query": "a quiet morning", "source": "web"}).json()
    r = client.post("/api/admin/review", json={"id": posted["id"], "decision": "approved"}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["review"] == "approved"

    pending = client.get("/api/admin/review", headers=ADMIN).json()
    assert posted["id"] not in [row["id"] for row in pending["pending"]]
    row = next(x for x in store.recent(limit=500) if x["id"] == posted["id"])
    assert row["review"] == "approved", "the decision is applied over the append-only log"


def test_rejecting_pulls_it_out_of_the_queue_and_the_night(client):
    # A phrase no other test says, so the assertion is about this row and not the shared log.
    query = "a rejected pelican"
    posted = client.post("/api/ingest", json={"query": query, "source": "web"}).json()
    assert query in client.get("/api/arc").json()["scenes"], "it starts out as dream material"

    client.post("/api/admin/review", json={"id": posted["id"], "decision": "rejected"}, headers=ADMIN)

    page = client.get("/api/queue").json()
    assert posted["id"] not in [r["id"] for r in page["submissions"]]
    assert query not in client.get("/api/arc").json()["scenes"], "rejected things do not dream"


def test_a_decision_can_be_taken_back(client):
    posted = client.post("/api/ingest", json={"query": "snow day", "source": "web"}).json()
    client.post("/api/admin/review", json={"id": posted["id"], "decision": "rejected"}, headers=ADMIN)
    client.post("/api/admin/review", json={"id": posted["id"], "decision": "approved"}, headers=ADMIN)
    row = next(x for x in store.recent(limit=500) if x["id"] == posted["id"])
    assert row["review"] == "approved", "the latest decision wins"


def test_reviewing_something_that_does_not_exist(client):
    r = client.post("/api/admin/review", json={"id": "nope", "decision": "approved"}, headers=ADMIN)
    assert r.status_code == 404


def test_a_nonsense_decision_is_rejected(client):
    r = client.post("/api/admin/review", json={"id": "x", "decision": "maybe"}, headers=ADMIN)
    assert r.status_code == 422


# --------------------------------------------------------------------------- the way in

def test_a_preview_is_behind_the_same_token_as_a_submission(client, monkeypatch):
    # A preview is a model call, so an open preview endpoint is an open API budget.
    monkeypatch.setattr(settings, "ingest_token", "frontend-secret")
    assert client.post("/api/preview", json={"query": "sunrise"}).status_code == 401
    ok = client.post("/api/preview", json={"query": "sunrise"},
                     headers={"x-ingest-token": "frontend-secret"})
    assert ok.status_code == 200


def test_preview_limits_are_configurable(client, monkeypatch):
    monkeypatch.setattr(settings, "preview_rate_seconds", 600.0)
    assert client.post("/api/preview", json={"query": "sunrise"}).status_code == 200
    assert client.post("/api/preview", json={"query": "snow day"}).status_code == 429


def test_a_forged_forwarded_header_does_not_mint_a_new_identity(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_seconds", 600.0)
    monkeypatch.setattr(settings, "trust_proxy", False)
    assert client.post("/api/ingest", json={"query": "first thing"}).status_code == 200
    again = client.post("/api/ingest", json={"query": "second thing"},
                        headers={"x-forwarded-for": "9.9.9.9"})
    assert again.status_code == 429, "the rate limit would otherwise be one header away from useless"


def test_behind_a_trusted_proxy_the_header_is_believed(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_seconds", 600.0)
    monkeypatch.setattr(settings, "trust_proxy", True)
    a = client.post("/api/ingest", json={"query": "one thing"}, headers={"x-forwarded-for": "1.1.1.1"})
    b = client.post("/api/ingest", json={"query": "other thing"}, headers={"x-forwarded-for": "2.2.2.2"})
    assert a.status_code == 200 and b.status_code == 200, "two people behind one proxy are two people"
