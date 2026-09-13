"""The Claude tier: one call per batch of five phrases, tool-use so the answer is
schema-shaped, and a hard fall-through to the local tier on any trouble.

Why one call and not five: five phrases cost one round trip, one cached system prompt, and
the model gets to see them together, which is what makes the `arc` worth anything. The
system block carries `cache_control: ephemeral`, so repeat batches only pay for the phrases.

Trust boundary: the model's answer is a suggestion. Every spec goes through
`spec.validate()`, every field is clamped, and anything missing is filled from the local
tier rather than dropped.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import fallback
from .config import settings
from .models import Arc, Interpretation, Mood, PhraseResult
from .spec import SPEC_SCHEMA, clean_word, hex_or, validate

API_URL = "https://api.anthropic.com/v1/messages"

INTERPRETATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "2-4 words: what would be shown"},
        "theme": {"type": "string", "enum": ["weather", "feeling", "place", "object", "event", "person", "abstract"]},
        "keywords": {"type": "array", "items": {"type": "string"}, "description": "3-5 concrete nouns worth drawing"},
        "word": {"type": ["string", "null"], "description": "1-7 chars of A-Z ! ? or null; the only text the facade may show"},
        "mood": {"type": "object", "properties": {"valence": {"type": "number"}, "arousal": {"type": "number"}}},
        "recognizability": {"type": "number", "description": "0-1: would a stranger 300 m away recognise this depiction"},
        "notes": {"type": "string", "description": "one short line on the depiction choice"},
    },
    "required": ["title", "theme", "keywords", "mood", "recognizability"],
}

ARC_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "the night's name, 1-7 chars, A-Z ! ? only"},
        "logline": {"type": "string", "description": "one sentence: the story these five phrases tell together"},
        "order": {"type": "array", "items": {"type": "integer"}, "description": "phrase indices in performance order, quiet open, loud middle, quiet close"},
        "through_line": {"type": "string", "description": "the thread connecting them"},
        "palette": {"type": "object", "properties": {"base": {"type": "string"}, "accent": {"type": "string"}, "glow": {"type": "string"}}},
    },
    "required": ["title", "logline", "order", "through_line"],
}

INGEST_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "description": "one entry per phrase, in the order given",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "the phrase's index as given"},
                    "ok": {"type": "boolean"},
                    "interpretation": INTERPRETATION_SCHEMA,
                    "spec": SPEC_SCHEMA,
                },
                "required": ["index", "ok", "interpretation", "spec"],
            },
        },
        "arc": ARC_SCHEMA,
    },
    "required": ["results", "arc"],
}

SYSTEM = """You are the imagination of a 21-storey building whose 153 windows (17 rows x 9 columns) are lights.
People send it short phrases - a thing, a place, a feeling, an event. You read a batch of them at once and, for each one, decide what the tower should become.

For every phrase return two things:
- interpretation: what the phrase means, in words. Theme, 3-5 concrete nouns, mood, and an honest recognizability score.
- spec: how to show it, filling the scene vocabulary. You never draw pixels; you choose from the vocabulary and the renderer does the rest.

Then return one arc for the whole batch: the five phrases read as a single night, ordered quiet-loud-quiet, with a name of at most 7 capital letters.

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


def call_claude(phrases: Sequence[str], timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Return the raw tool input, or None if anything at all went wrong."""
    if not settings.llm_available:
        return None
    listing = "\n".join(f"{i}. {p}" for i, p in enumerate(phrases))
    body = {
        "model": settings.model,
        "max_tokens": 3000,
        "system": [{"type": "text", "text": SYSTEM % _reference_block(),
                    "cache_control": {"type": "ephemeral"}}],
        "tools": [{"name": "ingest", "description": "Interpret a batch of phrases and draft a scene for each",
                   "input_schema": INGEST_SCHEMA}],
        "tool_choice": {"type": "tool", "name": "ingest"},
        "messages": [{"role": "user", "content": f"{len(phrases)} phrases:\n{listing}"}],
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


def _arc(raw: Any, results: Sequence[PhraseResult]) -> Arc:
    """Use the model's arc when it is coherent, otherwise compose one locally."""
    local = fallback.compose_arc(results)
    if not isinstance(raw, dict):
        return local
    valid = {r.index for r in results}
    order = [int(i) for i in raw.get("order", []) if isinstance(i, (int, float)) and int(i) in valid]
    seen: List[int] = []
    for i in order:
        if i not in seen:
            seen.append(i)
    for i in sorted(valid):  # anything the model forgot still gets played
        if i not in seen:
            seen.append(i)
    palette = raw.get("palette") if isinstance(raw.get("palette"), dict) else {}
    return Arc(
        title=clean_word(raw.get("title")) or local.title,
        logline=str(raw.get("logline") or local.logline)[:280],
        order=seen or local.order,
        through_line=str(raw.get("through_line") or local.through_line)[:140],
        palette={"base": hex_or(palette.get("base"), local.palette.get("base", "#101a2e")),
                 "accent": hex_or(palette.get("accent"), local.palette.get("accent", "#7cc4ff")),
                 "glow": hex_or(palette.get("glow"), local.palette.get("glow", "#ffffff"))},
    )


def claude_ingest(phrases: Sequence[str]) -> Tuple[List[PhraseResult], Arc, str, bool]:
    """One batched call. Returns (results, arc, tier, used_llm).

    A missing or unparseable tool block sends the whole batch local. Individual phrases the
    model skipped are filled from the local tier, so a partial answer is still worth having.
    """
    raw = call_claude(phrases)
    if raw is None:
        local_results, local_arc = fallback.local_ingest(phrases)
        return local_results, local_arc, "local", False

    by_index: Dict[int, Dict[str, Any]] = {}
    for item in raw.get("results", []) if isinstance(raw.get("results"), list) else []:
        if not isinstance(item, dict):
            continue
        try:
            i = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(phrases) and i not in by_index:
            by_index[i] = item

    if not by_index:
        local_results, local_arc = fallback.local_ingest(phrases)
        return local_results, local_arc, "local", False

    results: List[PhraseResult] = []
    for i, phrase in enumerate(phrases):
        item = by_index.get(i)
        if item is None:
            results.append(fallback.local_result(i, phrase))
            continue
        draft = validate(item.get("spec"))
        ok = bool(item.get("ok", True)) and draft["ok"]
        if not ok:
            results.append(fallback.blocked_result(i, phrase))
            continue
        results.append(PhraseResult(index=i, phrase=phrase, ok=True, tier=settings.model,
                                    interpretation=_interpretation(item.get("interpretation"), draft),
                                    spec_draft=draft))
    return results, _arc(raw.get("arc"), results), settings.model, True


def ingest(phrases: Sequence[str]) -> Tuple[List[PhraseResult], Arc, str, int]:
    """The whole pipeline for one batch: moderation, the chosen tier, timing.

    Blocked phrases never reach the API. If everything is blocked there is nothing to ask
    about, so no call is made at all.
    """
    t0 = time.time()
    flags = [fallback.is_blocked(p) for p in phrases]
    askable = [p for p, blocked in zip(phrases, flags) if not blocked]

    if not askable or not settings.llm_available:
        results, arc = fallback.local_ingest(phrases)
        tier = "blocked" if not askable else "local"
        return results, arc, tier, int((time.time() - t0) * 1000)

    sub_results, sub_arc, tier, used_llm = claude_ingest(askable)

    if len(askable) == len(phrases):
        return sub_results, sub_arc, tier, int((time.time() - t0) * 1000)

    # Re-seat the answers next to the blocked phrases so indices match the request.
    merged: List[PhraseResult] = []
    it = iter(sub_results)
    for i, (phrase, blocked) in enumerate(zip(phrases, flags)):
        if blocked:
            merged.append(fallback.blocked_result(i, phrase))
        else:
            r = next(it)
            merged.append(r.model_copy(update={"index": i}))
    return merged, fallback.compose_arc(merged), tier, int((time.time() - t0) * 1000)
