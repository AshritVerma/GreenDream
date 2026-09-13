"""The Claude tier: one query in, one scene draft out, tool-use so the answer is
schema-shaped, and a hard fall-through to the local tier on any trouble.

The person gets at most five words, so the model's job is narrow and the prompt can afford to
be strict about it: read the words as one thing, pick the single most recognisable depiction,
fill the vocabulary. The system block carries `cache_control: ephemeral`, so every request
after the first pays only for the query.

Trust boundary: the model's answer is a suggestion. The spec goes through `spec.validate()`,
every field is clamped, and any failure at all returns the local draft instead.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from . import fallback
from .config import settings
from .models import Interpretation, Mood, SceneResult
from .spec import SPEC_SCHEMA, validate

API_URL = "https://api.anthropic.com/v1/messages"

INTERPRETATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "2-4 words: what will be shown"},
        "theme": {"type": "string", "enum": ["weather", "feeling", "place", "object", "event", "person", "abstract"]},
        "keywords": {"type": "array", "items": {"type": "string"}, "description": "3-5 concrete nouns worth drawing"},
        "mood": {"type": "object", "properties": {"valence": {"type": "number"}, "arousal": {"type": "number"}}},
        "recognizability": {"type": "number", "description": "0-1: would a stranger 300 m away recognise this depiction"},
        "notes": {"type": "string", "description": "one short line on the depiction choice"},
    },
    "required": ["title", "theme", "keywords", "mood", "recognizability"],
}

PERFORM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "interpretation": INTERPRETATION_SCHEMA,
        "spec": SPEC_SCHEMA,
    },
    "required": ["interpretation", "spec"],
}

SYSTEM = """You are the imagination of a 21-storey building whose 153 windows (17 rows x 9 columns) are lights.
A person on the plaza gets at most five words to say what they want to see - "a rocket launch", "my heart is racing", "the first snow". Those words are ONE thing, not a list. Read them together and turn them into one short light performance.

Return two things:
- interpretation: what the words mean, in words. Theme, 3-5 concrete nouns, mood, and an honest recognizability score.
- spec: how to show it, filling the scene vocabulary. You never draw pixels; you choose from the vocabulary and the renderer does the rest.

Rules that come from the building itself:
- Pick the ONE most recognisable depiction. Bold and simple beats detailed: nine windows wide, seen from 300 m away.
- Use a 'world' for places and weather; use 'none' plus palette, particles and a sprite for things and feelings.
- A sprite is optional: up to 12 rows of exactly 9 characters, '#' lit and '.' dark, a bold silhouette (heart, arrow, rocket, cup, tree, star, face). Skip it when the thing has no simple silhouette; a speck or a solid slab reads as noise and will be thrown away.
- 'word' is optional and is the only text the building may ever show: 1-7 characters, capitals, '!' and '?' allowed. Never a sentence, never the person's own words verbatim.
- Match energy: calm things breathe slowly at low tempo; urgent things pulse or shake with bursts and high tempo.
- Set ok=false for hate, harassment, sexual content, or anything targeting a real private person. Public celebration of athletes, artists, holidays and teams is fine.
- Be honest in recognizability: 0.9 means a stranger names it unprompted, 0.3 means it is only a mood.

Reference depictions, the standard to match:
%s

Answer only by calling the tool."""


def _reference_block() -> str:
    """Two library specs as compact JSON, inside the cached system block."""
    lines = []
    for key in ("thunderstorm", "rocket launch"):
        entry = fallback.LIBRARY[key]
        lines.append(f"{key} -> {json.dumps(entry['spec'], separators=(',', ':'))}")
    return "\n".join(lines)


def _post(body: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": settings.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "user-agent": "greendream-llm/0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_claude(query: str, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Return the raw tool input, or None if anything at all went wrong."""
    if not settings.llm_available:
        return None
    body = {
        "model": settings.model,
        "max_tokens": 1200,
        "system": [{"type": "text", "text": SYSTEM % _reference_block(),
                    "cache_control": {"type": "ephemeral"}}],
        "tools": [{"name": "perform", "description": "Perform one scene on the building",
                   "input_schema": PERFORM_SCHEMA}],
        "tool_choice": {"type": "tool", "name": "perform"},
        "messages": [{"role": "user", "content": query[: settings.max_chars]}],
    }
    try:
        data = _post(body, timeout if timeout is not None else settings.llm_timeout)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        print(f"[llm] HTTP {e.code} from Anthropic: {detail}", flush=True)
        return None
    except Exception as e:  # timeout, DNS, TLS, malformed JSON
        print(f"[llm] call failed ({type(e).__name__}: {e})", flush=True)
        return None
    for part in data.get("content", []):
        if part.get("type") == "tool_use" and isinstance(part.get("input"), dict):
            return part["input"]
    print("[llm] no tool_use block in the response", flush=True)
    return None


def _interpretation(raw: Any, draft: Dict[str, Any]) -> Interpretation:
    d = raw if isinstance(raw, dict) else {}
    mood = d.get("mood") if isinstance(d.get("mood"), dict) else {}

    def num(x: Any, lo: float, hi: float, default: float) -> float:
        try:
            return min(hi, max(lo, float(x)))
        except (TypeError, ValueError):
            return default

    keywords = [str(k)[:24] for k in d.get("keywords", []) if isinstance(k, (str, int, float))][:5]
    return Interpretation(
        title=str(d.get("title") or draft["title"])[:60],
        theme=str(d.get("theme") or "abstract")[:40],
        keywords=keywords,
        word=draft["word"],  # already cleaned by validate(); the two must agree
        mood=Mood(valence=num(mood.get("valence"), -1, 1, draft["mood"]["valence"]),
                  arousal=num(mood.get("arousal"), 0, 1, draft["mood"]["arousal"])),
        recognizability=num(d.get("recognizability"), 0, 1, 0.5),
        notes=str(d.get("notes") or "")[:280],
    )


def ingest(query: str) -> Tuple[SceneResult, str, int]:
    """One query to one scene. Returns (result, tier, latency_ms).

    Moderation first, so a blocked query is never sent to the API. Then the model if it is
    switched on and reachable, then the local tier. There is no path where a query goes
    unanswered.
    """
    t0 = time.time()

    def done(result: SceneResult) -> Tuple[SceneResult, str, int]:
        return result, result.tier, int((time.time() - t0) * 1000)

    if fallback.is_blocked(query):
        return done(fallback.blocked_result(query))

    raw = call_claude(query) if settings.llm_available else None
    if raw is None:
        return done(fallback.local_result(query))

    draft = validate(raw.get("spec"))
    if not draft["ok"]:
        return done(fallback.blocked_result(query))

    # The model read the whole query, so nothing is unused; its own recognizability score is
    # the honest signal here, not a coverage count.
    return done(SceneResult(
        query=query, words=fallback.words_of(query), ok=True, tier=settings.model,
        match="model", unused_words=[], coverage=1.0,
        interpretation=_interpretation(raw.get("interpretation"), draft), spec_draft=draft,
    ))
