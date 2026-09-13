"""What has to stay true: the gate closes at sunset, the local tier always answers, and
nothing the model says is trusted without clamping."""

from __future__ import annotations

from datetime import datetime

import pytest

from app import fallback, llm, ratelimit, spec, store, sun
from app.config import settings

FIVE = ["thunderstorm", "my heart is racing", "a rocket launch", "snow day", "i miss my dog"]

NIGHT = datetime(2026, 9, 13, 22, 30)
NOON = datetime(2026, 9, 13, 12, 0)


@pytest.fixture
def at_night(monkeypatch):
    """Freeze the building's local clock well after sunset."""
    monkeypatch.setattr(sun, "local_now", lambda state=None: NIGHT)


# --------------------------------------------------------------------------- gate

def test_state_reports_open_and_the_live_view(client):
    body = client.get("/api/state").json()
    assert body["accepting"] is True
    assert body["gate_mode"] == "open"
    assert body["live_view_url"] == "https://example.test/live"
    assert body["max_phrases"] == 5


def test_sunset_closes_intake_with_a_dreaming_body(client, at_night):
    settings.set_gate("auto")

    state = client.get("/api/state").json()
    assert state["phase"] == "night"
    assert state["accepting"] is False
    assert state["reason"] == "sunset"
    assert state["reopens_at"], "the frontend needs to say when it may ask again"

    r = client.post("/api/ingest", json={"phrases": FIVE})
    assert r.status_code == 423
    body = r.json()
    assert body["state"] == "dreaming"
    assert "dreaming" in body["message"]
    assert body["live_view_url"] == "https://example.test/live"
    assert body["reopens_at"]


def test_daytime_stays_open_on_auto(client, monkeypatch):
    monkeypatch.setattr(sun, "local_now", lambda state=None: NOON)
    settings.set_gate("auto")
    assert client.get("/api/state").json()["accepting"] is True


def test_kill_switch_closes_regardless_of_the_sky(client, monkeypatch):
    monkeypatch.setattr(sun, "local_now", lambda state=None: NOON)
    settings.set_gate("closed")
    r = client.post("/api/ingest", json={"phrases": ["sunrise"]})
    assert r.status_code == 423
    assert r.json()["state"] == "off"


# --------------------------------------------------------------------------- local tier

def test_five_phrases_answered_offline(client):
    r = client.post("/api/ingest", json={"phrases": FIVE, "source": "web"})
    assert r.status_code == 200
    body = r.json()

    assert body["tier"] == "local"
    assert body["priority"] == "dream", "web submissions are dream material, not live"
    assert len(body["results"]) == 5

    for i, result in enumerate(body["results"]):
        assert result["index"] == i
        assert result["tier"] in ("library", "lexicon")
        draft = result["spec_draft"]
        assert draft["schema_version"] == spec.SCHEMA_VERSION
        assert draft["world"] in spec.WORLD_NAMES
        assert draft["motion"]["kind"] in spec.MOTIONS
        assert draft["particles"]["kind"] in spec.PARTICLES
        assert 6 <= draft["duration_s"] <= 20
        assert result["interpretation"]["keywords"] is not None

    arc = body["arc"]
    assert sorted(arc["order"]) == [0, 1, 2, 3, 4]
    assert arc["title"] and len(arc["title"]) <= 7
    assert arc["logline"]


def test_local_tier_is_deterministic():
    first = fallback.local_result(0, "the T is late again")
    second = fallback.local_result(0, "the T is late again")
    assert first.spec_draft == second.spec_draft


def test_library_hit_beats_the_lexicon():
    result = fallback.local_result(0, "a huge THUNDERSTORM!!")
    assert result.tier == "library"
    assert result.spec_draft["world"] == "storm"
    assert result.spec_draft["flash"]["kind"] == "lightning"


def test_blocked_phrase_never_leaves_a_scene(client):
    r = client.post("/api/ingest", json={"phrases": ["i want to kill someone", "sunrise"]})
    assert r.status_code == 200
    blocked, fine = r.json()["results"]
    assert blocked["tier"] == "blocked" and blocked["ok"] is False
    assert blocked["spec_draft"]["title"] == "shrug"
    assert blocked["spec_draft"]["word"] == "HMM?"
    assert fine["ok"] is True


def test_empty_submission_is_rejected(client):
    assert client.post("/api/ingest", json={"phrases": ["   ", ""]}).status_code == 422
    assert client.post("/api/ingest", json={"phrases": []}).status_code == 422


def test_more_than_five_phrases_is_rejected(client):
    assert client.post("/api/ingest", json={"phrases": ["a"] * 6}).status_code == 422


# --------------------------------------------------------------------------- validator

def test_validator_clamps_hostile_input():
    draft = spec.validate({
        "ok": True, "title": "x" * 200, "duration_s": 9999, "world": "moon",
        "palette": {"base": "not-a-colour", "accent": "#GGGGGG"},
        "motion": {"kind": "teleport", "speed": 42, "amount": -3},
        "particles": {"kind": "frogs", "density": 7, "direction": "sideways"},
        "tempo_bpm": 10000, "flash": {"kind": "strobe", "rate": 9},
        "sprite": {"rows": ["###", "###", "###"], "anim": "wiggle", "color": "puce"},
        "word": "please show my full sentence here",
        "mood": {"valence": 12, "arousal": -5},
    })
    assert len(draft["title"]) <= 40
    assert draft["duration_s"] == 20
    assert draft["world"] == "none"
    assert draft["palette"]["base"] == "#101a2e"
    assert draft["motion"]["kind"] == "breathe" and draft["motion"]["speed"] <= 1
    assert draft["particles"]["kind"] == "none" and draft["particles"]["direction"] == "down"
    assert draft["tempo_bpm"] == 200
    assert draft["flash"]["kind"] == "none"
    assert draft["sprite"] is None, "identical rows are a slab, not a silhouette"
    assert draft["word"] == "PLEASE", "a sentence is cut to a word, with no trailing space"
    assert -1 <= draft["mood"]["valence"] <= 1 and 0 <= draft["mood"]["arousal"] <= 1


def test_validator_keeps_a_real_sprite():
    draft = spec.validate({"ok": True, "title": "heart", "sprite": {"rows": fallback.HEART, "anim": "pulse"},
                           "world": "none", "motion": {}, "particles": {}, "flash": {}, "word": None})
    assert draft["sprite"] is not None
    assert all(len(row) == spec.COLS for row in draft["sprite"]["rows"])


def test_not_ok_becomes_a_shrug():
    draft = spec.validate({"ok": False, "title": "something awful"})
    assert draft["title"] == "shrug" and draft["ok"] is False


def test_garbage_is_still_a_usable_draft():
    for junk in (None, [], "text", 7, {"sprite": "nope"}):
        draft = spec.validate(junk)
        assert draft["schema_version"] == spec.SCHEMA_VERSION
        assert draft["world"] in spec.WORLD_NAMES


# --------------------------------------------------------------------------- claude tier

def _stub_tool_input():
    """A plausible model answer: one skipped phrase, one out-of-range spec, a loose arc."""
    return {
        "results": [
            {"index": 0, "ok": True,
             "interpretation": {"title": "green line", "theme": "place", "keywords": ["tram", "rails"],
                                "mood": {"valence": -0.2, "arousal": 0.4}, "recognizability": 0.4,
                                "notes": "a slow bright line"},
             "spec": {"ok": True, "title": "green line", "duration_s": 500, "world": "city",
                      "palette": {"base": "#0a1a12", "accent": "#5cffa6", "glow": "#ffffff"},
                      "motion": {"kind": "sweep", "speed": 0.4, "amount": 0.3},
                      "particles": {"kind": "none", "density": 0, "direction": "down"},
                      "tempo_bpm": 60, "flash": {"kind": "none", "rate": 0}, "sprite": None,
                      "word": "late again, sorry", "mood": {"valence": -0.2, "arousal": 0.4}}},
            {"index": 2, "ok": False,
             "interpretation": {"title": "no", "theme": "abstract", "keywords": [],
                                "mood": {"valence": 0, "arousal": 0}, "recognizability": 0},
             "spec": {"ok": False}},
        ],
        "arc": {"title": "the whole city at once", "logline": "three things", "order": [2, 99],
                "through_line": "a night in transit", "palette": {"base": "#000000"}},
    }


@pytest.fixture
def with_stub_llm(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "test-key")
    monkeypatch.setattr(settings, "offline", False)
    settings.set_llm(True)
    monkeypatch.setattr(llm, "call_claude", lambda phrases, timeout=None: _stub_tool_input())


def test_model_answer_is_clamped_and_gaps_are_filled(with_stub_llm):
    phrases = ["the green line", "a quiet room", "something unspeakable"]
    results, arc, tier, latency = llm.ingest(phrases)

    assert tier == settings.model
    assert [r.index for r in results] == [0, 1, 2]

    first = results[0]
    assert first.tier == settings.model
    assert first.spec_draft["duration_s"] == 20, "500 s is not a scene"
    assert first.spec_draft["word"] == "LATE AG", "only 7 chars of A-Z ! ? and space reach the facade"
    assert first.interpretation.word == first.spec_draft["word"]

    assert results[1].tier in ("library", "lexicon"), "a phrase the model skipped falls back locally"
    assert results[2].tier == "blocked", "ok=false becomes a shrug"

    assert arc.title == "THE WHO", "an over-long arc title is cut to what the marquee can climb"
    assert arc.order[0] == 2 and sorted(arc.order) == [0, 1, 2], "a bad index is dropped, none are lost"
    assert latency >= 0


def test_api_failure_falls_through_to_local(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "test-key")
    monkeypatch.setattr(settings, "offline", False)
    settings.set_llm(True)
    monkeypatch.setattr(llm, "call_claude", lambda phrases, timeout=None: None)

    results, arc, tier, _ = llm.ingest(FIVE)
    assert tier == "local"
    assert len(results) == 5
    assert all(r.tier in ("library", "lexicon") for r in results)


def test_llm_switch_off_skips_the_api(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "test-key")
    monkeypatch.setattr(settings, "offline", False)
    settings.set_llm(False)

    def explode(*a, **k):
        raise AssertionError("the API must not be called with the switch off")

    monkeypatch.setattr(llm, "call_claude", explode)
    _, _, tier, _ = llm.ingest(["anything at all"])
    assert tier == "local"


def test_identical_batch_is_served_from_cache(client, with_stub_llm):
    phrases = ["a cold morning", "the river froze", "one warm window"]
    first = client.post("/api/ingest", json={"phrases": phrases}).json()
    second = client.post("/api/ingest", json={"phrases": phrases}).json()
    assert first["tier"] == settings.model
    assert second["tier"].endswith("-cached")
    assert second["results"][0]["spec_draft"] == first["results"][0]["spec_draft"]


# --------------------------------------------------------------------------- operations

def test_admin_switch_needs_the_token(client):
    assert client.post("/api/admin/switch", json={"gate": "closed"}).status_code == 401
    assert client.post("/api/admin/switch", json={"gate": "closed"},
                       headers={"x-admin-token": "wrong"}).status_code == 401

    r = client.post("/api/admin/switch", json={"gate": "closed", "llm": "off"},
                    headers={"x-admin-token": "test-admin"})
    assert r.status_code == 200
    assert r.json()["gate_mode"] == "closed" and r.json()["accepting"] is False
    assert r.json()["llm_enabled"] is False


def test_admin_switch_rejects_nonsense(client):
    r = client.post("/api/admin/switch", json={"gate": "maybe"}, headers={"x-admin-token": "test-admin"})
    assert r.status_code == 422


def test_ingest_token_is_enforced_when_set(client, monkeypatch):
    monkeypatch.setattr(settings, "ingest_token", "frontend-secret")
    assert client.post("/api/ingest", json={"phrases": ["sunrise"]}).status_code == 401
    ok = client.post("/api/ingest", json={"phrases": ["sunrise"]},
                     headers={"x-ingest-token": "frontend-secret"})
    assert ok.status_code == 200


def test_rate_limit_trips(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_seconds", 60.0)
    ratelimit.reset()
    assert client.post("/api/ingest", json={"phrases": ["first thing"]}).status_code == 200
    second = client.post("/api/ingest", json={"phrases": ["second thing"]})
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
    assert second.json()["retry_after_s"] > 0


def test_queue_cursor_advances(client):
    start = client.get("/api/queue").json()["cursor"]
    posted = client.post("/api/ingest", json={"phrases": ["a lone pigeon"]}).json()

    page = client.get(f"/api/queue?since={start}").json()
    ids = [row["id"] for row in page["submissions"]]
    assert posted["id"] in ids
    assert page["cursor"] >= posted["seq"]

    assert client.get(f"/api/queue?since={page['cursor']}").json()["count"] == 0


def test_stored_record_keeps_the_review_flag(client):
    posted = client.post("/api/ingest", json={"phrases": ["a lone seagull"], "source": "web"}).json()
    row = next(r for r in store.recent(limit=200) if r["id"] == posted["id"])
    assert row["review"] == "pending", "remote submissions stay flagged for an operator"
    assert row["channel"] == "web" and row["priority"] == "dream"


def test_onsite_source_is_performed_live(client):
    body = client.post("/api/ingest", json={"phrases": ["sunrise"], "source": "pedestal"}).json()
    assert body["priority"] == "live"


def test_health_and_index(client):
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/").json()["service"] == "greendream-llm"
    assert client.get("/api/library").json()["count"] == len(fallback.LIBRARY)
