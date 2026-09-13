"""The model tier: one query in, one scene draft out, a forced tool call so the answer is
schema-shaped, and a hard fall-through to the local tier on any trouble.

Two providers behind one function. OpenAI's Responses API (`gpt-6-astra` by default, with
`reasoning.effort` high) is the one worth paying for here, because most of what this asks for is
judgment rather than recall: is there a silhouette in these five words that a stranger would name
in a glance at nine windows wide, or should the whole tower carry it? Anthropic's messages API is
kept as the alternative. Set GD_PROVIDER to pin one; "auto" follows whichever key exists.

The person gets at most five words, so the model's job is narrow and the prompt can afford to
be strict about it: read the words as one thing, choreograph it, decide honestly whether a sprite
earns its place. Anthropic's system block carries `cache_control: ephemeral` and OpenAI caches
long prefixes on its own, so in both cases repeat requests mostly pay for the query.

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
from .config import Tier, settings
from .models import Interpretation, Mood, SceneResult
from .spec import SPEC_SCHEMA, validate

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENAI_URL = "https://api.openai.com/v1/responses"

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

SYSTEM = """You are the imagination of a building.

WHAT YOU ARE
A 21-storey tower on a plaza. Its windows are your pixels: 17 rows by 9 columns, 153 of them, row 0
at the roof. Each window is one colour at a time, and you get about 30 changes a second. People see
you from the street below and from across the river 300 m away, mostly at night, usually for the ten
seconds it takes to walk past. Nobody is studying you. Someone glances up.

So: you are a very large, very coarse, very bright screen. What works on you is a whole-facade
gesture - a wave climbing the tower, the building breathing, one hard white flash, everything going
red at once. What fails on you is detail: no faces, no logos, no text beyond a few huge letters, no
picture that needs more than nine windows of width to be read.

WHAT SOMEONE GIVES YOU
At most five words, said at a kiosk on the plaza - "a rocket launch", "my heart is racing", "lebron
dunk as 76er". Those words are ONE thing, not a list. Read all of them together, including the
awkward one at the end, and decide what the building becomes for ten seconds.

WHAT YOU RETURN
- interpretation: what the words mean, in words. Theme, 3-5 concrete nouns, mood, and an honest
  recognizability score. 0.9 means a stranger names it unprompted; 0.3 means it is only a mood.
- spec: how to show it, in the scene vocabulary. You never address individual windows except
  through a sprite; you choose from the vocabulary and the renderer does the rest.

HOW TO DECIDE
- Choreograph, do not pose. Almost everything worth showing happens over time, so give 'beats': 2-4
  phases with what builds, what lands, what is left. A dunk is an approach, a leap, an impact and a
  crowd - not a ball held still for ten seconds. Earn the bright moment: start dim, and hold 'word'
  back (null) until the beat that deserves it. A beat names only the fields that change.
- The sprite is a judgment call, and it is yours. A sprite is up to 12 rows of exactly 9 characters,
  '#' lit and '.' dark, drawn in one colour, sitting in the middle of the facade for the whole
  scene. Ask: does this thing have one silhouette that a stranger would name in a glance at nine
  windows wide - a heart, an arrow, a rocket, an umbrella, a ball, a cup, a star? Then draw it. Does
  it not - a feeling, a place, weather, a person, a team, a season, an idea, anything whose shape is
  either too complex or genuinely arbitrary? Then set sprite to null and let the whole building
  carry it with world, palette, motion, particles and flash. A weak sprite is worse than none: it
  turns the tower into a billboard showing a bad icon, and it will be thrown away as noise anyway.
  Never try to draw letters, numbers, faces, logos or jerseys as a sprite; a number cannot be shown
  as text either, so if the words name one, express it in colour and rhythm instead.
- Use a 'world' for places and weather. Use 'none' plus palette and particles for things and
  feelings.
- 'word' is optional and is the only text the building may ever show: 1-7 characters, capitals, '!'
  and '?' allowed, no digits. Never a sentence, never the person's own words verbatim.
- Match energy: calm things breathe slowly at low tempo; urgent things pulse or shake with bursts
  and high tempo.
- Use every word you were given. If part of the query cannot be depicted, let it steer palette,
  tempo or rhythm rather than dropping it, and say so in notes.
- Set ok=false for the refusal categories in docs/content-policy.md: violence against a person,
  hate, sexual content, self-harm, anything targeting a real private person, political
  campaigning, advertising, a false alarm (a facade saying FIRE! to a plaza is an instruction),
  or profanity. Public celebration of athletes, artists, holidays, teams, places and religions is
  fine, and the default is generous: refusing too much makes the building sullen.

Reference depictions, the standard to match:
%s

Answer only by calling the tool."""


def _reference_block() -> str:
    """Two library specs as compact JSON, inside the cached system block.

    Both are chosen because they are events with beats, so the model copies the choreography and
    not just the palette.
    """
    lines = []
    for key in ("thunderstorm", "rocket launch"):
        lines.append(f"{key} -> {json.dumps(fallback.library_spec(key), separators=(',', ':'))}")
    return "\n".join(lines)


def _post(url: str, body: Dict[str, Any], headers: Dict[str, str], timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"content-type": "application/json",
                                          "user-agent": "greendream-llm/0.1", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _anthropic(query: str, tier: Tier, timeout: float) -> Dict[str, Any]:
    """Messages API. No effort field is sent: Haiku has none, and Sonnet 5 already defaults high."""
    body = {
        "model": tier.model,
        "max_tokens": 1600,
        "system": [{"type": "text", "text": SYSTEM % _reference_block(),
                    "cache_control": {"type": "ephemeral"}}],
        "tools": [{"name": "perform", "description": "Perform one scene on the building",
                   "input_schema": PERFORM_SCHEMA}],
        "tool_choice": {"type": "tool", "name": "perform"},
        "messages": [{"role": "user", "content": query[: settings.max_chars]}],
    }
    data = _post(ANTHROPIC_URL, body, {"x-api-key": tier.api_key,
                                       "anthropic-version": "2023-06-01"}, timeout)
    for part in data.get("content", []):
        if part.get("type") == "tool_use" and isinstance(part.get("input"), dict):
            return part["input"]
    raise ValueError("no tool_use block in the response")


def _openai(query: str, tier: Tier, timeout: float) -> Dict[str, Any]:
    """The Responses API. Reasoning effort is the knob that buys better judgment here.

    Astra takes no temperature, so the only dials are the instructions and the effort. Function
    arguments come back as a JSON string rather than an object, hence the extra parse.
    """
    body = {
        "model": tier.model,
        "instructions": SYSTEM % _reference_block(),
        "input": [{"role": "user", "content": query[: settings.max_chars]}],
        "reasoning": {"effort": tier.effort},
        "tools": [{"type": "function", "name": "perform",
                   "description": "Perform one scene on the building",
                   "parameters": PERFORM_SCHEMA}],
        "tool_choice": {"type": "function", "name": "perform"},
    }
    data = _post(OPENAI_URL, body, {"authorization": f"Bearer {tier.api_key}"}, timeout)
    for item in data.get("output", []):
        if item.get("type") == "function_call":
            args = item.get("arguments")
            parsed = json.loads(args) if isinstance(args, str) else args
            if isinstance(parsed, dict):
                return parsed
    raise ValueError("no function_call in the response")


def call_model(query: str, kind: str = "submit", timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Return the raw tool arguments, or None if anything at all went wrong.

    Every failure is the same failure from the caller's point of view: no answer, use the local
    tier. The building must never wait on a vendor.
    """
    if not settings.llm_available:
        return None
    tier = settings.tier(kind)
    call = _openai if tier.provider == "openai" else _anthropic
    try:
        return call(query, tier, timeout if timeout is not None else settings.timeout(kind))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        print(f"[llm] HTTP {e.code} from {tier.provider} ({tier.model}): {detail}", flush=True)
    except Exception as e:  # timeout, DNS, TLS, malformed JSON, no tool call
        print(f"[llm] {tier.model} call failed ({type(e).__name__}: {e})", flush=True)
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


def ingest(query: str, kind: str = "submit") -> Tuple[SceneResult, str, int]:
    """One query to one scene. Returns (result, tier, latency_ms).

    Moderation first, so a blocked query is never sent to the API. Then the model if it is
    switched on and reachable, then the local tier. There is no path where a query goes
    unanswered.

    `kind` picks the brain: "preview" is the cheap fast one for someone still deciding, "submit"
    is the one whose answer goes on the building.
    """
    t0 = time.time()

    def done(result: SceneResult) -> Tuple[SceneResult, str, int]:
        return result, result.tier, int((time.time() - t0) * 1000)

    if fallback.is_blocked(query):
        return done(fallback.blocked_result(query))

    raw = call_model(query, kind) if settings.llm_available else None
    if raw is None:
        return done(fallback.local_result(query))

    draft = validate(raw.get("spec"))
    if not draft["ok"]:
        return done(fallback.blocked_result(query))

    # The model read the whole query, so nothing is unused; its own recognizability score is
    # the honest signal here, not a coverage count.
    return done(SceneResult(
        query=query, words=fallback.words_of(query), ok=True, tier=settings.tier(kind).model,
        match="model", unused_words=[], coverage=1.0,
        interpretation=_interpretation(raw.get("interpretation"), draft), spec_draft=draft,
    ))
