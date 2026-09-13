"""Affect from language: text -> (valence, arousal, emotion, gesture, reply word).

Uses the Anthropic Messages API when ANTHROPIC_API_KEY is set (plain
``requests``/urllib, no SDK). Otherwise a small lexicon does a decent job
offline so the demo is deterministic and never blocks. Either way the result
is the same dict, computed on a worker thread and delivered as an
``{"type": "affect", ...}`` event on the InputBus.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.request
from typing import Dict, Optional

from common.inputs import BUS, InputBus

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

GESTURES = ["nod", "shake", "bounce", "spread", "shrink", "shiver", "wave", "sway", "still"]
EMOTIONS = ["joy", "calm", "curious", "surprise", "sad", "lonely", "tired", "angry", "fear", "love", "neutral"]

SYSTEM = """You are the emotional core of a 21-story building whose 153 windows are lights.
People talk to you; you cannot speak in sentences, only in light and ONE short word.
Given what a person said, respond with strict JSON only:
{"valence": -1..1, "arousal": 0..1, "emotion": one of %s,
 "gesture": one of %s, "word": a reply of 1-6 uppercase letters (A-Z, may include ! or ?), "why": short phrase}
Be warm, playful and a little theatrical. Match the speaker's energy.""" % (EMOTIONS, GESTURES)

# --- offline lexicon fallback ------------------------------------------------
LEX = {
    "happy": (0.8, 0.6, "joy"), "joy": (0.9, 0.7, "joy"), "love": (0.9, 0.5, "love"), "great": (0.7, 0.6, "joy"), "amazing": (0.9, 0.9, "surprise"),
    "wow": (0.7, 0.9, "surprise"), "awesome": (0.8, 0.8, "joy"), "beautiful": (0.8, 0.4, "love"), "thanks": (0.6, 0.4, "joy"), "thank": (0.6, 0.4, "joy"),
    "excited": (0.8, 0.95, "joy"), "party": (0.8, 0.95, "joy"), "dance": (0.7, 0.9, "joy"), "fun": (0.7, 0.7, "joy"), "yay": (0.9, 0.9, "joy"),
    "calm": (0.4, 0.15, "calm"), "peace": (0.5, 0.1, "calm"), "quiet": (0.2, 0.1, "calm"), "relax": (0.5, 0.1, "calm"), "sleep": (0.1, 0.05, "tired"),
    "tired": (-0.3, 0.15, "tired"), "exhausted": (-0.5, 0.1, "tired"), "bored": (-0.3, 0.2, "tired"), "meh": (-0.2, 0.2, "neutral"),
    "sad": (-0.8, 0.3, "sad"), "cry": (-0.8, 0.5, "sad"), "lonely": (-0.7, 0.3, "lonely"), "alone": (-0.5, 0.3, "lonely"), "miss": (-0.5, 0.3, "lonely"),
    "angry": (-0.8, 0.9, "angry"), "hate": (-0.9, 0.8, "angry"), "furious": (-0.9, 1.0, "angry"), "ugh": (-0.5, 0.5, "angry"), "annoyed": (-0.5, 0.6, "angry"),
    "scared": (-0.7, 0.8, "fear"), "afraid": (-0.7, 0.7, "fear"), "nervous": (-0.4, 0.7, "fear"), "worried": (-0.5, 0.6, "fear"),
    "curious": (0.4, 0.6, "curious"), "why": (0.1, 0.5, "curious"), "how": (0.1, 0.5, "curious"), "what": (0.1, 0.5, "curious"), "wonder": (0.4, 0.5, "curious"),
    "hello": (0.5, 0.5, "joy"), "hi": (0.5, 0.5, "joy"), "hey": (0.5, 0.6, "joy"), "goodbye": (-0.2, 0.3, "sad"), "bye": (-0.1, 0.3, "sad"),
    "no": (-0.4, 0.5, "angry"), "yes": (0.5, 0.5, "joy"), "stop": (-0.5, 0.7, "angry"), "help": (-0.4, 0.8, "fear"), "wake": (0.3, 0.8, "surprise"),
    "mit": (0.6, 0.6, "joy"), "tetris": (0.7, 0.7, "joy"), "beautiful": (0.8, 0.4, "love"), "cold": (-0.3, 0.3, "sad"), "warm": (0.5, 0.3, "love"),
}
REPLY = {"joy": ["YAY!", "HELLO", "HI!", "LOVE", "WOO!"], "love": ["LOVE", "AWW", "HUG"], "calm": ["AHH", "OK", "PEACE"], "curious": ["HMM?", "OH?", "WHY?"],
         "surprise": ["WOW!", "OH!", "WHOA"], "sad": ["AWW", "OH NO", "HUG?"], "lonely": ["STAY?", "HI", "HERE"], "tired": ["ZZZ", "YAWN", "SHH"],
         "angry": ["GRR", "NO!", "HEY!"], "fear": ["EEK", "HIDE", "OH NO"], "neutral": ["HMM", "OK", "HI"]}
GESTURE_FOR = {"joy": "bounce", "love": "spread", "calm": "sway", "curious": "nod", "surprise": "spread", "sad": "shrink", "lonely": "shrink",
               "tired": "still", "angry": "shake", "fear": "shiver", "neutral": "nod"}


def lexicon_affect(text: str) -> Dict:
    words = re.findall(r"[a-z']+", text.lower())
    vals, ars, emos = [], [], {}
    for w in words:
        w2 = w.rstrip("s")
        hit = LEX.get(w) or LEX.get(w2)
        if hit:
            v, a, e = hit
            vals.append(v)
            ars.append(a)
            emos[e] = emos.get(e, 0) + 1
    excl = text.count("!")
    caps = sum(1 for ch in text if ch.isupper()) / max(1, len(text))
    valence = sum(vals) / len(vals) if vals else 0.05
    arousal = (sum(ars) / len(ars) if ars else 0.35) + 0.12 * min(excl, 3) + 0.3 * (caps > 0.5)
    arousal = max(0.0, min(1.0, arousal))
    if "not" in words or "n't" in text.lower():
        valence *= -0.6
    emotion = max(emos, key=emos.get) if emos else ("curious" if "?" in text else "neutral")
    import random

    rng = random.Random(hash(text) & 0xFFFF)
    return {"valence": round(valence, 2), "arousal": round(arousal, 2), "emotion": emotion, "gesture": GESTURE_FOR.get(emotion, "nod"),
            "word": rng.choice(REPLY.get(emotion, REPLY["neutral"])), "why": "lexicon", "backend": "lexicon"}


def claude_affect(text: str, timeout: float = 12.0) -> Optional[Dict]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    body = json.dumps({"model": MODEL, "max_tokens": 200, "system": SYSTEM, "messages": [{"role": "user", "content": text}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        txt = "".join(part.get("text", "") for part in data.get("content", []))
        m = re.search(r"\{.*\}", txt, re.S)
        out = json.loads(m.group(0)) if m else None
        if not out:
            return None
        out["valence"] = max(-1.0, min(1.0, float(out.get("valence", 0))))
        out["arousal"] = max(0.0, min(1.0, float(out.get("arousal", 0.5))))
        out["emotion"] = out.get("emotion") if out.get("emotion") in EMOTIONS else "neutral"
        out["gesture"] = out.get("gesture") if out.get("gesture") in GESTURES else GESTURE_FOR[out["emotion"]]
        out["word"] = re.sub(r"[^A-Z!?' ]", "", str(out.get("word", "")).upper())[:7] or "HMM"
        out["backend"] = MODEL
        return out
    except Exception as e:
        print(f"[llm] API failed ({e}); using lexicon", flush=True)
        return None


def affect_async(text: str, bus: InputBus = BUS, force_lexicon: bool = False) -> None:
    """Compute affect off-thread and push {"type": "affect", "text": ..., **result}."""

    def go():
        res = None if force_lexicon else claude_affect(text)
        if res is None:
            res = lexicon_affect(text)
        ev = {"type": "affect", "text": text}
        ev.update(res)
        bus.push(ev)

    threading.Thread(target=go, daemon=True).start()
