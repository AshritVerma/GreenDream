"""Affect from language, offline: text -> (valence, arousal, emotion).

A small lexicon that never blocks and is deterministic across processes, so the demo
plays the same way every time. This is the last tier of the prompt engine (``genie``):
when a phrase is not in the warm library and the model is unavailable, its mood still
colours the tower. The language service (``greendream-llm/app/fallback.py``) carries
the same table; keep them aligned.

Negation is read: "not happy" lands on the other side of zero from "happy", and the
emotion flips with it, so the reply word is never the opposite of what was said.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple

LEX: Dict[str, Tuple[float, float, str]] = {
    "happy": (0.8, 0.6, "joy"), "joy": (0.9, 0.7, "joy"), "love": (0.9, 0.5, "love"), "great": (0.7, 0.6, "joy"),
    "amazing": (0.9, 0.9, "surprise"), "wow": (0.7, 0.9, "surprise"), "awesome": (0.8, 0.8, "joy"),
    "beautiful": (0.8, 0.4, "love"), "thanks": (0.6, 0.4, "joy"), "thank": (0.6, 0.4, "joy"),
    "excited": (0.8, 0.95, "joy"), "party": (0.8, 0.95, "joy"), "dance": (0.7, 0.9, "joy"), "fun": (0.7, 0.7, "joy"),
    "yay": (0.9, 0.9, "joy"), "win": (0.8, 0.85, "joy"), "won": (0.8, 0.85, "joy"), "graduate": (0.9, 0.8, "joy"),
    "calm": (0.4, 0.15, "calm"), "peace": (0.5, 0.1, "calm"), "quiet": (0.2, 0.1, "calm"), "relax": (0.5, 0.1, "calm"),
    "sleep": (0.1, 0.05, "tired"), "tired": (-0.3, 0.15, "tired"), "exhausted": (-0.5, 0.1, "tired"),
    "bored": (-0.3, 0.2, "tired"), "meh": (-0.2, 0.2, "neutral"),
    "sad": (-0.8, 0.3, "sad"), "cry": (-0.8, 0.5, "sad"), "lonely": (-0.7, 0.3, "lonely"), "alone": (-0.5, 0.3, "lonely"),
    "miss": (-0.5, 0.3, "lonely"), "angry": (-0.8, 0.9, "angry"), "furious": (-0.9, 1.0, "angry"), "hate": (-0.9, 0.8, "angry"),
    "annoyed": (-0.5, 0.6, "angry"), "ugh": (-0.5, 0.5, "angry"), "scared": (-0.7, 0.8, "fear"), "afraid": (-0.7, 0.7, "fear"),
    "nervous": (-0.4, 0.7, "fear"), "worried": (-0.5, 0.6, "fear"), "stressed": (-0.6, 0.8, "fear"), "anxious": (-0.6, 0.8, "fear"),
    "curious": (0.4, 0.6, "curious"), "wonder": (0.4, 0.5, "curious"), "why": (0.1, 0.5, "curious"),
    "hello": (0.5, 0.5, "joy"), "hi": (0.5, 0.5, "joy"), "hey": (0.5, 0.6, "joy"),
    "goodbye": (-0.2, 0.3, "sad"), "bye": (-0.1, 0.3, "sad"),
    "cold": (-0.3, 0.3, "sad"), "warm": (0.5, 0.3, "love"), "mit": (0.6, 0.6, "joy"), "boston": (0.5, 0.5, "joy"),
    "exam": (-0.5, 0.7, "fear"), "finals": (-0.6, 0.8, "fear"), "coffee": (0.4, 0.7, "joy"),
}

# The reply for a mood. Neutral says nothing: on nine windows "OK" is the least interesting
# two letters available, and a mood the building cannot name should just be a colour.
EMOTION_WORD: Dict[str, str | None] = {"joy": "YAY!", "love": "LOVE", "calm": "AHH", "curious": "HMM?", "surprise": "WOW!",
                                       "sad": "AWW", "lonely": "STAY?", "tired": "ZZZ", "angry": "GRR", "fear": "EEK", "neutral": None}

OPPOSITE = {"joy": "sad", "sad": "calm", "love": "lonely", "lonely": "love", "calm": "fear", "fear": "calm",
            "angry": "calm", "tired": "joy", "surprise": "neutral", "curious": "neutral", "neutral": "neutral"}

NEGATORS = {"not", "no", "never", "dont", "don't", "cant", "can't", "isnt", "isn't", "aint", "ain't", "without", "nothing"}


def lexicon_affect(text: str) -> Dict:
    """Valence/arousal/emotion with no network. Deterministic across processes."""
    words = re.findall(r"[a-z']+", text.lower())
    vals, ars, emos = [], [], {}
    for i, w in enumerate(words):
        hit = LEX.get(w) or LEX.get(w.rstrip("s"))
        if not hit:
            continue
        v, a, e = hit
        if any(words[j] in NEGATORS for j in range(max(0, i - 2), i)):
            v, e = -v * 0.8, OPPOSITE.get(e, "neutral")
        vals.append(v)
        ars.append(a)
        emos[e] = emos.get(e, 0) + 1
    caps = sum(1 for ch in text if ch.isupper()) / max(1, len(text))
    valence = sum(vals) / len(vals) if vals else 0.05
    arousal = (sum(ars) / len(ars) if ars else 0.35) + 0.12 * min(text.count("!"), 3) + 0.3 * (caps > 0.5)
    emotion = max(emos, key=lambda k: emos[k]) if emos else ("curious" if "?" in text else "neutral")
    return {"valence": round(max(-1.0, min(1.0, valence)), 2),
            "arousal": round(max(0.0, min(1.0, arousal)), 2),
            "emotion": emotion, "matched": bool(vals), "backend": "lexicon"}
