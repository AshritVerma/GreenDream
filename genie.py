"""Text -> scene spec, three tiers: warm library (instant, offline), Claude
(open vocabulary, ~1 s, tool-use so the answer is schema-shaped), lexicon
(affect-only fallback). Always answers; never blocks the frame loop.

Env: ANTHROPIC_API_KEY, optional ANTHROPIC_MODEL (default claude-haiku-4-5).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from typing import Optional

from common.inputs import BUS, InputBus

from library import LIBRARY, lookup
from scene import SCHEMA, SHRUG, validate

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

SYSTEM = """You are the imagination of a 21-storey building whose 153 windows (17 rows x 9 columns) are lights.
People on the plaza say anything - a thing, a place, a feeling, an event - and you turn it into a short light performance by filling a scene spec.
Rules:
- Pick the ONE most recognisable depiction. Bold and simple beats detailed: the tower is 9 windows wide and seen from 300 m away.
- Use a 'world' when the request is a place/weather; use 'none' + palette + particles + sprite for things and feelings.
- A sprite is optional: up to 12 rows of exactly 9 characters, '#' lit and '.' dark, a bold silhouette (heart, arrow, rocket, cup, tree, star, face). Skip it if the thing has no simple silhouette.
- 'word' is optional: a 1-7 character reply in capitals (a name, a cheer, an echo). Never write a sentence.
- Match energy: calm things breathe slowly with low tempo; exciting things pulse/shake with bursts and high tempo.
- Set ok=false (and nothing else) for hate, harassment, sexual content, or anything targeting a real private person. Public celebration of athletes, artists, holidays, teams is fine.
Answer only by calling the tool."""

FEW_SHOT = [("thunderstorm", LIBRARY["thunderstorm"]), ("rocket launch", LIBRARY["rocket launch"]), ("my heart is racing", LIBRARY["my heart is racing"]), ("birthday", LIBRARY["birthday"])]


def claude_spec(text: str, timeout: float = 6.0) -> Optional[dict]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    messages = []
    for q, spec in FEW_SHOT:  # few-shot as prior tool calls
        messages.append({"role": "user", "content": q})
        messages.append({"role": "assistant", "content": [{"type": "tool_use", "id": f"ex_{len(messages)}", "name": "perform", "input": spec}]})
        messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"ex_{len(messages) - 1}", "content": "performed"}]})
    messages.append({"role": "user", "content": text[:200]})
    body = {
        "model": MODEL, "max_tokens": 600,
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "tools": [{"name": "perform", "description": "Perform a scene on the building", "input_schema": SCHEMA}],
        "tool_choice": {"type": "tool", "name": "perform"},
        "messages": messages,
    }
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        for part in data.get("content", []):
            if part.get("type") == "tool_use":
                return part.get("input")
    except Exception as e:
        print(f"[genie] API failed ({e})", flush=True)
    return None


def lexicon_spec(text: str) -> dict:
    """Affect-only fallback: colour + motion from valence/arousal, word = first word."""
    from sensors.llm import lexicon_affect  # shipped with the repo

    a = lexicon_affect(text)
    v, ar = a["valence"], a["arousal"]
    warm = v > 0
    base = "#2a1a03" if warm else "#0c1524"
    accent = "#ffd166" if warm else "#7fa7e0"
    word = re.sub(r"[^A-Z]", "", text.upper().split()[0] if text.split() else "")[:7] or None
    return {"ok": True, "title": a["emotion"], "duration_s": 9, "world": "none",
            "palette": {"base": base, "accent": accent, "glow": "#ffffff"},
            "motion": {"kind": "pulse" if ar > 0.6 else "breathe", "speed": ar, "amount": 0.3 + 0.4 * ar},
            "particles": {"kind": "stars" if warm else "rain", "density": 0.3 + 0.5 * ar, "direction": "up" if warm else "down"},
            "tempo_bpm": 50 + 100 * ar, "flash": {"kind": "burst" if ar > 0.8 else "none", "rate": 0.3},
            "sprite": None, "word": word, "mood": {"valence": v, "arousal": ar}}


BLOCKLIST = re.compile(r"\b(kill|nazi|rape|slur)\b", re.I)  # extend before the show; the model also screens


def request_async(text: str, bus: InputBus = BUS, offline: bool = False, source: str = "web") -> None:
    """Push {"type": "spec", "text", "spec", "tier", "latency_ms", "source"} when ready.

    ``source`` rides along so the caller can attribute the answer to the channel that
    asked for it; two overlapping prompts would otherwise be told apart by arrival order.
    """

    def go():
        t0 = time.time()
        tier, raw = "library", None
        if BLOCKLIST.search(text):
            raw, tier = SHRUG, "blocked"
        else:
            raw = lookup(text)
            if raw is None and not offline:
                got = claude_spec(text)
                if got is not None:
                    raw, tier = got, MODEL
            if raw is None:
                raw, tier = lexicon_spec(text), "lexicon"
        spec = validate(raw)
        bus.push({"type": "spec", "text": text, "spec": spec, "tier": tier, "source": source,
                  "latency_ms": int((time.time() - t0) * 1000)})

    threading.Thread(target=go, daemon=True).start()
