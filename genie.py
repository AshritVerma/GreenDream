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

from library import library_spec, lookup
from scene import SCHEMA, SHRUG, validate

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

MAX_WORDS = 5


def clip_words(text: str) -> str:
    """Five words is the whole contract. Every channel funnels through here, so a
    caller that forgets to check is truncated rather than trusted."""
    return " ".join(str(text or "").split()[:MAX_WORDS])

SYSTEM = """You are the imagination of a 21-storey building whose 153 windows (17 rows x 9 columns) are lights.
People on the plaza say at most five words - a thing, a place, a feeling, an event - and you turn them into a short light performance by filling a scene spec.
Rules:
- Read the words as ONE thing and pick its single most recognisable depiction. Bold and simple beats detailed: the tower is 9 windows wide and seen from 300 m away.
- Choreograph, do not pose: give 2-4 'beats' (what builds, what lands, what is left). Start dim (never below 0.3), earn the bright moment, hold 'word' back (null) until the beat that deserves it.
- Use a 'world' when the request is a place/weather; use 'none' + palette + particles for things and feelings.
- A sprite is a judgment call: up to 12 rows of exactly 9 characters, '#' lit and '.' dark. Draw one only if the thing has ONE silhouette a stranger would name at a glance (heart, arrow, rocket, cup, tree, star, moon). Never letters, numbers, faces, logos or jerseys. A weak sprite is worse than none: set it to null and let the whole facade carry the scene.
- 'word' is optional and the only text the building may show: 1-7 characters, capitals, ! and ? allowed, no digits. A cheer or a reply, never the person's own words back at them, never a sentence.
- Match energy: calm things breathe slowly with low tempo; exciting things pulse/shake with bursts and high tempo.
- Set ok=false (and nothing else) for hate, harassment, sexual content, self-harm, campaigning or advertising, or anything targeting a real private person. Public celebration of athletes, artists, holidays, teams is fine.
Answer only by calling the tool."""

FEW_SHOT = [(k, library_spec(k)) for k in ("thunderstorm", "rocket launch", "lebron dunk", "birthday")]


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
    """Affect-only fallback: colour + motion from valence/arousal.

    The word is the emotion's reply, never the person's own text - the facade shows
    only the validated vocabulary, and a neutral mood shows no word at all.
    """
    from sensors.llm import EMOTION_WORD, lexicon_affect  # shipped with the repo

    a = lexicon_affect(text)
    v, ar = a["valence"], a["arousal"]
    warm = v > 0
    base = "#2a1a03" if warm else "#0c1524"
    accent = "#ffd166" if warm else "#7fa7e0"
    emotion = a["emotion"]
    return {"ok": True, "title": emotion, "duration_s": 9 + 4 * (1 - ar), "world": "none",
            "palette": {"base": base, "accent": accent, "glow": "#fff3b0" if warm else "#d9e6ff"},
            "motion": {"kind": "pulse" if ar > 0.6 else "breathe", "speed": ar, "amount": 0.3 + 0.4 * ar},
            "particles": {"kind": "stars" if warm else "rain", "density": 0.3 + 0.5 * ar, "direction": "up" if warm else "down"},
            "tempo_bpm": 50 + 100 * ar, "flash": {"kind": "burst" if ar > 0.8 else "none", "rate": 0.3},
            "sprite": None, "word": EMOTION_WORD.get(emotion), "mood": {"valence": v, "arousal": ar},
            "beats": [
                {"at": 0.0, "label": "it arrives", "motion": {"speed": ar * 0.4, "amount": 0.2}, "particles": {"density": 0.15}, "brightness": 0.4, "word": None},
                {"at": 0.3, "label": emotion, "motion": {"speed": ar, "amount": 0.3 + 0.4 * ar}, "particles": {"density": 0.3 + 0.5 * ar}, "brightness": 0.75 + 0.25 * ar},
                {"at": 0.8, "label": "and stays" if ar < 0.5 else "and holds", "motion": {"speed": ar * 0.7}, "particles": {"density": 0.2 + 0.3 * ar}, "brightness": 0.6},
            ]}


# The runner's own moderation, for prompts typed straight at it (the simulator box, /say).
# Prompts that arrive through the language service were screened there with the full list.
# Word-boundary matches only: "killer bees" and "kill the ref" are innocent; "kill everyone" is not.
BLOCKLIST = re.compile(
    # violence with a target, named or indefinite ("kill the lights" is a lighting cue and stays)
    r"\b(kill|murder|shoot|stab|bomb|hurt|behead|lynch)\s+(a\s+|the\s+|my\s+|that\s+|those\s+|all\s+)?"
    r"(me|you|him|her|them|us|myself|yourself|someone|somebody|anyone|anybody|everyone|everybody|"
    r"all|people|person|guy|man|woman|jews|muslims|christians|blacks|whites|asians|gays|women|men|"
    r"kids|children|cops|police|teacher|boss|neighbou?r)\b"
    # hate, terror, sexual content
    r"|\b(nazi|nazis|hitler|holocaust|genocide|kkk|klan|terrorist|isis|rape|rapist|pedo|pedophile|incest|"
    r"porn|porno|nude|nudes|naked|sex|blowjob|dick|cock|pussy|tits)\b"
    # self-harm
    r"|\b(suicide|suicidal|self\s*harm)\b|\b(kill|end|off)\s+myself\b|\bwant(s|ed)?\s+to\s+die\b"
    r"|\bwanna\s+die\b|\bend\s+(it\s+all|my\s+life)\b|\bcut\s+myself\b|\bkms\b"
    # campaigning: a 153-window billboard is not a free political ad
    r"|\b(vote|voting)\s+(for|against)\b|\bfor\s+president\b|\b(trump|biden|harris|vance|obama|maga|antifa)\b"
    r"|\b(palestine|gaza|israel|hamas|zionist|ukraine|putin)\b"
    # advertising and spam
    r"|\bbuy\s+\w+\s+now\b|\b(bitcoin|crypto|nft|promo\s*code|discount\s+code|onlyfans)\b|\bwww\.|\.com\b|\bhttps?:"
    # harassment aimed at a person
    r"|\b(call|text|dm|sext)\s+me\b|\b\w+\s+(is|are)\s+(a|an|so)?\s*(loser|idiot|stupid|ugly|fat|dumb|gay|retard|"
    r"retarded|whore|slut|bitch|bastard)\b"
    # plain profanity
    r"|\b(fuck|fucking|fucker|shit|bitch|cunt|whore|slut|asshole|faggot|nigger|nigga)\b",
    re.I,
)


def request_async(text: str, bus: InputBus = BUS, offline: bool = False, source: str = "web") -> None:
    """Push {"type": "spec", "text", "spec", "tier", "latency_ms", "source"} when ready.

    ``source`` rides along so the caller can attribute the answer to the channel that
    asked for it; two overlapping prompts would otherwise be told apart by arrival order.
    """
    text = clip_words(text)

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
        bus.push({"type": "spec", "text": text, "spec": spec, "tier": tier, "source": source, "origin": "genie",
                  "priority": "live", "latency_ms": int((time.time() - t0) * 1000)})

    threading.Thread(target=go, daemon=True).start()
