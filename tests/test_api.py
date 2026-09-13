"""What has to stay true: one query is one thing to show, the gate closes at sunset, the local
tier always answers, and nothing the model says is trusted without clamping."""

from __future__ import annotations

from datetime import datetime

import pytest

from app import fallback, llm, ratelimit, spec, store, sun
from app.config import settings

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
    assert body["max_words"] == 5


def test_sunset_closes_intake_with_a_dreaming_body(client, at_night):
    settings.set_gate("auto")

    state = client.get("/api/state").json()
    assert state["phase"] == "night"
    assert state["accepting"] is False
    assert state["reason"] == "sunset"
    assert state["reopens_at"], "the frontend needs to say when it may ask again"

    r = client.post("/api/ingest", json={"query": "a thunderstorm"})
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
    r = client.post("/api/ingest", json={"query": "sunrise"})
    assert r.status_code == 423
    assert r.json()["state"] == "off"


# --------------------------------------------------------------------------- one query in

def test_one_query_becomes_one_scene(client):
    r = client.post("/api/ingest", json={"query": "a thunderstorm over the river", "source": "web"})
    assert r.status_code == 200
    body = r.json()

    assert body["tier"] == "library"
    assert body["priority"] == "dream", "web queries are dream material, not live"

    result = body["result"]
    assert result["query"] == "a thunderstorm over the river"
    assert result["words"] == ["a", "thunderstorm", "over", "the", "river"]
    assert result["tier"] == "library"

    draft = result["spec_draft"]
    assert draft["schema_version"] == spec.SCHEMA_VERSION
    assert draft["world"] == "storm"
    assert draft["motion"]["kind"] in spec.MOTIONS
    assert draft["particles"]["kind"] in spec.PARTICLES
    assert 6 <= draft["duration_s"] <= 20
    assert result["interpretation"]["keywords"]


def test_six_words_is_rejected(client):
    r = client.post("/api/ingest", json={"query": "one two three four five six"})
    assert r.status_code == 422
    assert "at most 5 words" in str(r.json()["detail"])


def test_five_words_is_accepted(client):
    assert client.post("/api/ingest", json={"query": "one two three four five"}).status_code == 200


def test_empty_query_is_rejected(client):
    assert client.post("/api/ingest", json={"query": "   "}).status_code == 422
    assert client.post("/api/ingest", json={}).status_code == 422


def test_whitespace_and_control_characters_are_normalised(client):
    body = client.post("/api/ingest", json={"query": "  a\t\trocket   launch\n "}).json()
    assert body["result"]["query"] == "a rocket launch"
    assert body["result"]["words"] == ["a", "rocket", "launch"]


def test_local_tier_is_deterministic():
    first = fallback.local_result("the T is late")
    second = fallback.local_result("the T is late")
    assert first.spec_draft == second.spec_draft


def test_library_hit_beats_the_lexicon():
    result = fallback.local_result("a huge THUNDERSTORM!!")
    assert result.tier == "library"
    assert result.spec_draft["world"] == "storm"
    assert result.spec_draft["flash"]["kind"] == "lightning"


def test_unknown_words_still_get_a_mood(client):
    body = client.post("/api/ingest", json={"query": "finals week again"}).json()
    result = body["result"]
    assert result["tier"] == "lexicon"
    assert result["ok"] is True
    assert result["interpretation"]["recognizability"] <= 0.4, "a mood is not a depiction"
    assert result["coverage"] == 0.0
    assert "finals" in result["unused_words"], "the lexicon depicts nothing, and says so"


# --------------------------------------------------------------------------- honesty

def test_digits_survive_normalisation():
    assert fallback.normalize("lebron dunk as 76er") == "lebron dunk as 76er"
    assert "76er" in fallback.local_result("lebron dunk as 76er").unused_words


def test_partial_match_is_not_reported_as_a_full_one():
    partial = fallback.local_result("lebron dunk as 76er")
    full = fallback.local_result("lebron dunk")

    assert partial.spec_draft["title"] == full.spec_draft["title"], "same canned scene"
    assert partial.match == "alias" and full.match == "exact"
    assert partial.unused_words == ["76er"]
    assert partial.coverage < 1.0 and full.coverage == 1.0
    assert partial.interpretation.recognizability < full.interpretation.recognizability, \
        "one word out of three is not a 90% match"
    assert "76er" in partial.interpretation.notes


def test_stopwords_do_not_count_as_ignored():
    assert fallback.local_result("a dunk").unused_words == []
    assert fallback.local_result("take me to space").unused_words == []


def test_unused_words_still_colour_the_energy():
    plain = fallback.local_result("my heart is racing")
    tired = fallback.local_result("my exhausted heart is racing")

    assert tired.unused_words == ["exhausted"]
    assert tired.spec_draft["tempo_bpm"] < plain.spec_draft["tempo_bpm"], \
        "it cannot draw exhaustion, but it can slow down"
    assert "energy" in tired.interpretation.notes


def test_a_second_library_word_is_named_not_silently_dropped():
    result = fallback.local_result("storm dunk 76er")
    assert result.spec_draft["world"] == "storm", "the first match wins"
    assert "dunk" in result.unused_words
    assert "lebron dunk" in result.interpretation.notes, "say what it chose not to show"


def test_the_model_tier_claims_full_coverage(with_stub_llm):
    result, _, _ = llm.ingest("the green line")
    assert result.match == "model" and result.unused_words == [] and result.coverage == 1.0


# --------------------------------------------------------------------------- beats

def test_a_scene_is_an_event_in_time():
    beats = fallback.local_result("lebron dunk").spec_draft["beats"]
    labels = [b["label"] for b in beats]

    assert labels == ["the approach", "the leap", "it lands", "the crowd"]
    assert [b["at"] for b in beats] == sorted(b["at"] for b in beats)
    assert beats[0]["brightness"] < beats[2]["brightness"] == 1.0, "the impact is the bright moment"
    assert beats[0]["word"] is None and beats[2]["word"] == "DUNK!", "the word waits for the landing"


def test_beats_are_additive_so_the_current_renderer_still_works():
    draft = fallback.local_result("lebron dunk").spec_draft
    assert draft["schema_version"] == spec.SCHEMA_VERSION, "not a version bump"
    for key in spec.SPEC_SCHEMA["required"]:
        assert key in draft, "the held version is still fully described"
    assert "beats" not in spec.SPEC_SCHEMA["required"]
    assert fallback.local_result("finals week").spec_draft["beats"], "even a mood arrives and subsides"


def test_a_beat_inherits_what_it_does_not_name():
    draft = spec.validate({
        "motion": {"kind": "sweep", "speed": 0.4, "amount": 0.9},
        "particles": {"kind": "snow", "density": 0.6, "direction": "down"},
        "word": "HELLO",
        "beats": [{"at": 0, "brightness": 0.2}, {"at": 0.5, "motion": {"speed": 1.0}}],
    })
    first, second = draft["beats"]
    assert first["motion"] == draft["motion"], "named nothing, so it is the scene"
    assert second["motion"] == {"kind": "sweep", "speed": 1.0, "amount": 0.9}, "only speed changed"
    assert second["particles"]["kind"] == "snow"
    assert first["word"] == "HELLO", "absent word inherits"
    assert spec.validate({"word": "HI", "beats": [{"at": 0, "word": None}, {"at": 0.5}]})["beats"][0]["word"] is None, \
        "an explicit null is a deliberate silence"


@pytest.mark.parametrize("raw, why", [
    ("nonsense", "not a list"),
    ([], "empty"),
    ([{"at": 0}], "one phase is not a timeline"),
    (["x", 3], "no usable entries"),
])
def test_unusable_beats_degrade_to_a_held_scene(raw, why):
    assert spec.validate({"beats": raw})["beats"] == [], why


def test_beats_are_ordered_clamped_and_never_collide():
    beats = spec.validate({"beats": [{"at": 9}, {"at": 0.4}, {"at": 0.4}, {"at": -2}]})["beats"]
    ats = [b["at"] for b in beats]
    assert ats[0] == 0.0, "the first beat opens the scene"
    assert ats == sorted(ats) and len(set(ats)) == len(ats), "two beats cannot land on one instant"
    assert all(0.0 <= a <= 1.0 for a in ats)


def test_at_most_four_beats():
    beats = spec.validate({"beats": [{"at": i / 10} for i in range(9)]})["beats"]
    assert len(beats) == spec.MAX_BEATS == 4


def test_the_shrug_holds_still():
    assert spec.shrug()["beats"] == [], "we are not choreographing a refusal"


def test_blocked_query_never_becomes_a_scene(client):
    body = client.post("/api/ingest", json={"query": "kill everyone"}).json()
    result = body["result"]
    assert result["tier"] == "blocked" and result["ok"] is False
    assert result["spec_draft"]["title"] == "shrug"
    assert result["spec_draft"]["word"] == "HMM?"


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
    """A plausible model answer with an out-of-range duration and a sentence for a word."""
    return {
        "interpretation": {"title": "green line", "theme": "place", "keywords": ["tram", "rails"],
                           "mood": {"valence": -0.2, "arousal": 0.4}, "recognizability": 0.4,
                           "notes": "a slow bright line"},
        "spec": {"ok": True, "title": "green line", "duration_s": 500, "world": "city",
                 "palette": {"base": "#0a1a12", "accent": "#5cffa6", "glow": "#ffffff"},
                 "motion": {"kind": "sweep", "speed": 0.4, "amount": 0.3},
                 "particles": {"kind": "none", "density": 0, "direction": "down"},
                 "tempo_bpm": 60, "flash": {"kind": "none", "rate": 0}, "sprite": None,
                 "word": "late again, sorry", "mood": {"valence": -0.2, "arousal": 0.4}},
    }


@pytest.fixture
def with_stub_llm(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "test-key")
    monkeypatch.setattr(settings, "offline", False)
    settings.set_llm(True)
    monkeypatch.setattr(llm, "call_claude", lambda query, timeout=None: _stub_tool_input())


def test_model_answer_is_clamped(with_stub_llm):
    result, tier, latency = llm.ingest("the green line")
    assert tier == settings.model
    assert result.spec_draft["duration_s"] == 20, "500 s is not a scene"
    assert result.spec_draft["word"] == "LATE AG", "only 7 chars of A-Z ! ? and space reach the facade"
    assert result.interpretation.word == result.spec_draft["word"]
    assert result.interpretation.theme == "place"
    assert latency >= 0


def test_model_refusal_becomes_a_shrug(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "test-key")
    monkeypatch.setattr(settings, "offline", False)
    settings.set_llm(True)
    monkeypatch.setattr(llm, "call_claude", lambda query, timeout=None: {"interpretation": {}, "spec": {"ok": False}})
    result, tier, _ = llm.ingest("something unspeakable")
    assert tier == "blocked" and result.spec_draft["title"] == "shrug"


def test_api_failure_falls_through_to_local(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "test-key")
    monkeypatch.setattr(settings, "offline", False)
    settings.set_llm(True)
    monkeypatch.setattr(llm, "call_claude", lambda query, timeout=None: None)

    result, tier, _ = llm.ingest("a rocket launch")
    assert tier == "library"
    assert result.spec_draft["word"] == "LIFTOFF"


def test_blocked_query_never_reaches_the_api(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "test-key")
    monkeypatch.setattr(settings, "offline", False)
    settings.set_llm(True)

    def explode(*a, **k):
        raise AssertionError("a blocked query must not be sent to the API")

    monkeypatch.setattr(llm, "call_claude", explode)
    result, tier, _ = llm.ingest("i want to kill someone")
    assert tier == "blocked"


def test_llm_switch_off_skips_the_api(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "test-key")
    monkeypatch.setattr(settings, "offline", False)
    settings.set_llm(False)

    def explode(*a, **k):
        raise AssertionError("the API must not be called with the switch off")

    monkeypatch.setattr(llm, "call_claude", explode)
    _, tier, _ = llm.ingest("anything at all")
    assert tier in ("library", "lexicon")


def test_identical_query_is_served_from_cache(client, with_stub_llm):
    first = client.post("/api/ingest", json={"query": "the green line"}).json()
    second = client.post("/api/ingest", json={"query": "The Green Line!"}).json()
    assert first["tier"] == settings.model
    assert second["tier"].endswith("-cached")
    assert second["result"]["spec_draft"] == first["result"]["spec_draft"]


# --------------------------------------------------------------------------- the day's arc

def test_arc_is_composed_over_the_day(client):
    for query in ["a calm ocean", "lebron dunk", "a thunderstorm", "snow day"]:
        assert client.post("/api/ingest", json={"query": query}).status_code == 200

    body = client.get("/api/arc").json()
    assert body["count"] >= 4
    arc = body["arc"]
    assert arc["title"] and len(arc["title"]) <= 7
    assert arc["logline"] and arc["through_line"]
    assert len(arc["order"]) == body["count"]
    assert sorted(arc["order"]) == list(range(body["count"])), "every scene is placed once"
    assert arc["order"][0] == 0, "the day opens on what was said first"


def test_arc_orders_loud_in_the_middle_and_calm_at_the_end():
    scenes = [fallback.local_result(q) for q in ["a calm ocean", "lebron dunk", "sunrise", "snow day"]]
    arc = fallback.compose_arc(scenes)
    arousal = [scenes[i].interpretation.mood.arousal for i in arc.order]
    assert arc.order[0] == 0, "the night opens on whatever was said first"
    assert arousal[1] == max(arousal[1:]), "the loudest thing lands right after the opening"
    assert arousal[-1] == min(arousal[1:]), "the night settles into the calmest of the rest"


def test_empty_day_has_an_empty_arc(client):
    arc = fallback.compose_arc([])
    assert arc.order == [] and arc.title == "DREAM"


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
    assert client.post("/api/ingest", json={"query": "sunrise"}).status_code == 401
    ok = client.post("/api/ingest", json={"query": "sunrise"},
                     headers={"x-ingest-token": "frontend-secret"})
    assert ok.status_code == 200


def test_rate_limit_trips(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_seconds", 60.0)
    ratelimit.reset()
    assert client.post("/api/ingest", json={"query": "first thing"}).status_code == 200
    second = client.post("/api/ingest", json={"query": "second thing"})
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
    assert second.json()["retry_after_s"] > 0


def test_queue_cursor_advances(client):
    start = client.get("/api/queue").json()["cursor"]
    posted = client.post("/api/ingest", json={"query": "a lone pigeon"}).json()

    page = client.get(f"/api/queue?since={start}").json()
    ids = [row["id"] for row in page["submissions"]]
    assert posted["id"] in ids
    assert page["cursor"] >= posted["seq"]

    assert client.get(f"/api/queue?since={page['cursor']}").json()["count"] == 0


def test_stored_record_keeps_the_review_flag(client):
    posted = client.post("/api/ingest", json={"query": "a lone seagull", "source": "web"}).json()
    row = next(r for r in store.recent(limit=200) if r["id"] == posted["id"])
    assert row["review"] == "pending", "remote queries stay flagged for an operator"
    assert row["channel"] == "web" and row["priority"] == "dream"
    assert row["result"]["query"] == "a lone seagull"


def test_onsite_source_is_performed_live(client):
    body = client.post("/api/ingest", json={"query": "sunrise", "source": "pedestal"}).json()
    assert body["priority"] == "live"


def test_health_and_index(client):
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/").json()["service"] == "greendream-llm"
    assert client.get("/api/library").json()["count"] == len(fallback.LIBRARY)


def test_demo_page_is_served(client):
    r = client.get("/demo")
    assert r.status_code == 200 and "five words" in r.text
