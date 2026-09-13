"""The local tier: a query to a scene draft with no network, no key, no API bill.

Two stages, both deterministic (same query in, same draft out, in any process):

    1. warm library  hand-written scenes plus aliases and an indexed matcher. These are the
                     things people actually ask for, and they are also the reference specs
                     the model is shown, so the two tiers agree on what "good" looks like.
    2. lexicon       valence/arousal from a small affect table, mapped to palette, motion,
                     particles and tempo. Always answers something.

This module is also the moderation gate (`BLOCKLIST`) and the day-level arc composer.

`LIBRARY`, `BEATS` and `ALIASES` are mirrored, entry for entry, by GreenDream's `library.py`
(`tests/test_alignment.py` pins the two together when both repos are checked out side by
side). Change a scene here and there, or the preview and the performance stop matching.
"""

from __future__ import annotations

import difflib
import random
import re
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from . import spec as spec_mod
from .models import Arc, Interpretation, Mood, SceneResult

# --------------------------------------------------------------------------- sprites (9 wide)

ROCKET = ["....#....", "...###...", "...###...", "..#####..", "..#####..", "..#####..", "..#####..", ".#######.", ".#.###.#.", "#..###..#", "...#.#...", "..#...#.."]
HEART = [".##...##.", "###.#.###", "#########", "#########", ".#######.", "..#####..", "...###...", "....#...."]
CAKE = ["..#.#.#..", "..#.#.#..", ".#######.", "#########", "#.#.#.#.#", "#########", "#########", ".#######."]
BALL = ["..#####..", ".##.#.##.", "##..#..##", "#########", "##..#..##", ".##.#.##.", "..#####.."]
SMILE = ["..#####..", ".#.....#.", "#.#...#.#", "#.......#", "#.#...#.#", "#..###..#", ".#.....#.", "..#####.."]
ARROW_UP = ["....#....", "...###...", "..#####..", ".#######.", "...###...", "...###...", "...###...", "...###..."]
UMBRELLA = ["....#....", "..#####..", ".#######.", "#########", "#.#.#.#.#", "....#....", "....#....", "....#....", "...##...."]
MOON = ["..#####..", ".###.....", "###......", "###......", "###......", ".###.....", "..#####.."]
TREE = ["....#....", "...###...", "..#####..", "...###...", "..#####..", ".#######.", "#########", "....#....", "...###..."]
CUP = ["..#.#.#..", "...#.#.#.", ".........", ".######..", ".######.#", ".######.#", ".######..", "..####..."]
CAP = ["....#....", "..#####..", "#########", "..#####..", "...###.#.", "...###.#.", "...###.#.", "........#"]
STAR = ["....#....", "....#....", "...###...", "#########", ".#######.", "..#####..", ".###.###.", ".#.....#."]
RING = ["....#....", "...###...", "..#.#.#..", "...###...", "..##.##..", ".##...##.", ".##...##.", "..##.##..", "...###..."]


def _spec(title: str, *, duration_s: float = 12, world: str = "none", base: str = "#101a2e", accent: str = "#7cc4ff",
          glow: str = "#ffffff", motion=("still", 0.5, 0.0), particles=("none", 0.0, "down"), tempo_bpm: float = 70,
          flash=("none", 0.0), sprite=None, word: Optional[str] = None, mood=(0.2, 0.5)) -> dict:
    """One scene, written positionally so the mirror on the renderer side is verifiable."""
    return {"ok": True, "title": title, "duration_s": duration_s, "world": world,
            "palette": {"base": base, "accent": accent, "glow": glow},
            "motion": {"kind": motion[0], "speed": motion[1], "amount": motion[2]},
            "particles": {"kind": particles[0], "density": particles[1], "direction": particles[2]},
            "tempo_bpm": tempo_bpm, "flash": {"kind": flash[0], "rate": flash[1]},
            "sprite": {"rows": sprite[0], "anim": sprite[1], "color": sprite[2]} if sprite else None,
            "word": word, "mood": {"valence": mood[0], "arousal": mood[1]}}


def _e(theme: str, keywords: List[str], spec: dict) -> dict:
    return {"theme": theme, "keywords": keywords, "spec": spec}


# --------------------------------------------------------------------------- warm library

LIBRARY: Dict[str, dict] = {
    # weather and sky
    "thunderstorm": _e("weather", ["storm", "lightning", "rain"], _spec("thunderstorm", world="storm", base="#0d1220", accent="#8fa6d9", glow="#f4f7ff",
                       motion=("shake", 0.6, 0.25), particles=("rain", 0.9, "down"), tempo_bpm=70, flash=("lightning", 0.7), mood=(-0.3, 0.8))),
    "it's raining": _e("weather", ["rain", "umbrella", "grey"], _spec("rain", base="#0c1524", accent="#7fa7e0", glow="#d9e6ff",
                       motion=("still", 0.3, 0.0), particles=("rain", 0.7, "down"), tempo_bpm=60, sprite=(UMBRELLA, "hold", "#ffd166"), mood=(-0.1, 0.3))),
    "snow day": _e("weather", ["snow", "quiet", "cold"], _spec("snow day", duration_s=14, world="snow", base="#0a1020", accent="#bcd3ff",
                   motion=("breathe", 0.2, 0.2), particles=("snow", 0.8, "down"), tempo_bpm=45, mood=(0.5, 0.2))),
    "sunrise": _e("weather", ["sun", "horizon", "warmth"], _spec("sunrise", duration_s=16, world="sunrise", base="#1a0a1e", accent="#ff9f43", glow="#fff2c2",
                  motion=("rise", 0.15, 0.2), tempo_bpm=50, mood=(0.7, 0.3))),
    "sunset": _e("weather", ["dusk", "evening", "horizon", "orange"], _spec("sunset", duration_s=16, world="sunrise", base="#1a0a1e", accent="#ff6b6b", glow="#ffc48a",
                 motion=("fall", 0.12, 0.2), tempo_bpm=45, mood=(0.5, 0.2))),
    "full moon": _e("object", ["moon", "night", "sky", "glow"], _spec("full moon", duration_s=16, base="#060814", accent="#9fb4ff", glow="#fff7d6",
                    motion=("breathe", 0.15, 0.15), particles=("stars", 0.3, "up"), tempo_bpm=40, sprite=(MOON, "hold", "#fff7d6"), mood=(0.4, 0.15))),
    "northern lights": _e("place", ["aurora", "sky", "green", "ribbons"], _spec("northern lights", duration_s=18, world="aurora", base="#04101a", accent="#5cffa6", glow="#d8fff0",
                          motion=("sweep", 0.3, 0.4), particles=("stars", 0.2, "up"), tempo_bpm=40, mood=(0.7, 0.3))),
    # places
    "calm ocean": _e("place", ["waves", "water", "swell"], _spec("calm ocean", duration_s=18, world="ocean", base="#041224", accent="#4fb3ff", glow="#dff6ff",
                     motion=("breathe", 0.2, 0.4), particles=("bubbles", 0.25, "up"), tempo_bpm=40, mood=(0.6, 0.1))),
    "take me to space": _e("place", ["stars", "warp", "void"], _spec("hyperspace", world="hyperspace", base="#02030a", accent="#9fb8ff",
                           motion=("still", 0.5, 0.0), tempo_bpm=90, mood=(0.6, 0.7))),
    "charles river": _e("place", ["river", "water", "sailboats", "cambridge"], _spec("the charles", duration_s=18, world="ocean", base="#041a24", accent="#4fd1c5", glow="#e0fffb",
                        motion=("breathe", 0.2, 0.3), particles=("bubbles", 0.15, "up"), tempo_bpm=40, mood=(0.6, 0.15))),
    "volcano": _e("place", ["lava", "eruption", "fire", "ash"], _spec("volcano", duration_s=14, world="lava", base="#1a0500", accent="#ff5a1f", glow="#ffd28a",
                  motion=("shake", 0.5, 0.25), particles=("sparks", 0.8, "up"), tempo_bpm=80, flash=("burst", 0.4), mood=(-0.1, 0.9))),
    "the forest": _e("place", ["trees", "green", "leaves", "woods"], _spec("the forest", duration_s=18, world="forest", base="#06140a", accent="#5cffa6", glow="#e8fff2",
                     motion=("breathe", 0.2, 0.3), particles=("stars", 0.2, "up"), tempo_bpm=40, mood=(0.6, 0.15))),
    "city lights": _e("place", ["city", "skyline", "windows", "night"], _spec("city lights", duration_s=14, world="city", base="#0a0a14", accent="#ffd166",
                      motion=("sweep", 0.3, 0.3), tempo_bpm=70, mood=(0.5, 0.5))),
    # events
    "birthday": _e("event", ["cake", "candles", "confetti"], _spec("birthday party", base="#2a0f2e", accent="#ff7ab6", glow="#ffd166",
                   motion=("pulse", 0.7, 0.4), particles=("confetti", 0.9, "down"), tempo_bpm=120, flash=("burst", 0.3),
                   sprite=(CAKE, "pulse", "#ffd166"), word="BDAY!", mood=(0.9, 0.8))),
    "rocket launch": _e("event", ["rocket", "fire", "ascent"], _spec("rocket launch", base="#05070f", accent="#ff9f43",
                        motion=("still", 0.5, 0.0), particles=("sparks", 0.8, "up"), tempo_bpm=100, flash=("burst", 0.15),
                        sprite=(ROCKET, "rise", "#ffffff"), word="LIFTOFF", mood=(0.7, 0.9))),
    "lebron dunk": _e("event", ["basketball", "jump", "crowd"], _spec("a dunk", duration_s=10, base="#06122a", accent="#ed174c",
                      motion=("shake", 0.8, 0.2), particles=("sparks", 0.5, "up"), tempo_bpm=130, flash=("burst", 0.5),
                      sprite=(BALL, "bounce", "#ff8c42"), word="DUNK!", mood=(0.9, 1.0))),
    "fireworks": _e("event", ["burst", "sparks", "boom", "night"], _spec("fireworks", base="#050512", accent="#ff5ea8",
                    motion=("pulse", 0.6, 0.3), particles=("sparks", 0.9, "up"), tempo_bpm=90, flash=("burst", 0.6), word="BOOM!", mood=(0.9, 0.9))),
    "merry christmas": _e("event", ["christmas", "tree", "snow", "lights"], _spec("christmas", duration_s=14, world="snow", base="#0a1a12", accent="#ff3b4e", glow="#ffd166",
                          motion=("breathe", 0.3, 0.2), particles=("snow", 0.6, "down"), tempo_bpm=60, sprite=(TREE, "pulse", "#5cffa6"), word="MERRY!", mood=(0.9, 0.5))),
    "graduation": _e("event", ["cap", "diploma", "confetti", "cheer"], _spec("graduation", base="#1a0f2e", accent="#ffd166",
                     motion=("rise", 0.5, 0.5), particles=("confetti", 0.8, "down"), tempo_bpm=110, flash=("burst", 0.3),
                     sprite=(CAP, "rise", "#ffd166"), word="GRAD!", mood=(0.9, 0.8))),
    "go sox": _e("event", ["baseball", "fenway"], _spec("red sox", duration_s=10, base="#1f0510", accent="#bd3039",
                 motion=("pulse", 0.7, 0.4), particles=("sparks", 0.5, "up"), tempo_bpm=120, flash=("burst", 0.3), word="GO SOX!", mood=(0.9, 0.9))),
    "go celtics": _e("event", ["basketball", "garden", "green"], _spec("celtics", duration_s=10, base="#06180d", accent="#2bd66b",
                     motion=("pulse", 0.7, 0.4), particles=("sparks", 0.5, "up"), tempo_bpm=120, flash=("burst", 0.3), word="CELTICS", mood=(0.9, 0.9))),
    "go bruins": _e("event", ["hockey", "ice", "gold"], _spec("bruins", duration_s=10, base="#0a0a0a", accent="#ffb81c",
                    motion=("shake", 0.6, 0.2), particles=("snow", 0.3, "down"), tempo_bpm=110, flash=("burst", 0.3), word="BRUINS", mood=(0.9, 0.9))),
    "she said yes": _e("event", ["ring", "proposal", "sparkle"], _spec("she said yes", base="#1a0f2e", accent="#ffd6f0",
                       motion=("pulse", 0.6, 0.4), particles=("confetti", 0.7, "down"), tempo_bpm=110, flash=("burst", 0.4),
                       sprite=(RING, "pulse", "#ffffff"), word="YES!", mood=(1.0, 0.9))),
    "i got the job": _e("event", ["hired", "cheer", "sparks"], _spec("hired", duration_s=10, base="#2a1a03", accent="#ffd166",
                        motion=("pulse", 0.7, 0.4), particles=("confetti", 0.8, "down"), tempo_bpm=120, flash=("burst", 0.3), word="HIRED!", mood=(0.95, 0.85))),
    "welcome home": _e("event", ["home", "door", "warm", "return"], _spec("welcome home", base="#2a1a03", accent="#ffb454", glow="#fff3b0",
                       motion=("rise", 0.3, 0.3), particles=("stars", 0.3, "up"), tempo_bpm=70, word="HOME", mood=(0.9, 0.4))),
    # feelings
    "my heart is racing": _e("feeling", ["heart", "pulse", "nerves"], _spec("racing heart", duration_s=10, base="#1a0508", accent="#ff3b4e", glow="#ffd6d9",
                             motion=("pulse", 0.9, 0.5), particles=("sparks", 0.3, "up"), tempo_bpm=150, sprite=(HEART, "pulse", "#ff3b4e"), mood=(0.2, 1.0))),
    "i'm so happy": _e("feeling", ["joy", "smile", "light"], _spec("joy", duration_s=10, base="#2a1a03", accent="#ffd166", glow="#fff3b0",
                       motion=("pulse", 0.6, 0.3), particles=("stars", 0.6, "up"), tempo_bpm=110, sprite=(SMILE, "bounce", "#ffd166"), mood=(0.9, 0.6))),
    "i love you": _e("feeling", ["heart", "warmth", "pink"], _spec("love", base="#2a0a14", accent="#ff5e8a", glow="#ffd6e0",
                     motion=("pulse", 0.5, 0.4), particles=("stars", 0.4, "up"), tempo_bpm=80, sprite=(HEART, "pulse", "#ff5e8a"), word="LOVE", mood=(0.95, 0.6))),
    "good night": _e("feeling", ["sleep", "quiet", "stars"], _spec("good night", duration_s=14, base="#05061a", accent="#5a5aa8", glow="#c9c9ff",
                     motion=("breathe", 0.15, 0.3), particles=("stars", 0.3, "up"), tempo_bpm=35, word="NIGHT", mood=(0.4, 0.1))),
    "good luck": _e("feeling", ["luck", "wish", "hope"], _spec("good luck", duration_s=10, base="#0a1a12", accent="#ffd166",
                    motion=("rise", 0.4, 0.3), particles=("stars", 0.6, "up"), tempo_bpm=80, sprite=(STAR, "pulse", "#ffd166"), word="LUCK!", mood=(0.8, 0.6))),
    # objects
    "go up": _e("object", ["arrow", "climb", "height"], _spec("up", duration_s=8, base="#0a1a12", accent="#5cffa6", glow="#e8fff2",
                motion=("rise", 0.7, 0.8), particles=("sparks", 0.4, "up"), tempo_bpm=100, sprite=(ARROW_UP, "rise", "#5cffa6"), mood=(0.6, 0.7))),
    "coffee": _e("object", ["cup", "steam", "morning"], _spec("coffee", duration_s=10, base="#1a0f05", accent="#c47a3a", glow="#fff3d6",
                 motion=("breathe", 0.3, 0.2), particles=("bubbles", 0.3, "up"), tempo_bpm=60, sprite=(CUP, "hold", "#e8c39e"), mood=(0.6, 0.5))),
    "a tree": _e("object", ["leaves", "green", "grow"], _spec("a tree", base="#06140a", accent="#5cffa6", glow="#e8fff2",
                 motion=("breathe", 0.2, 0.2), tempo_bpm=45, sprite=(TREE, "hold", "#5cffa6"), mood=(0.5, 0.2))),
}

# --------------------------------------------------------------------------- choreography
#
# The base fields above describe a scene that holds for its whole duration, which is how a dunk
# ends up as a picture of a ball with a wobble. These beats give each scene a shape in time: what
# builds, what lands, what is left. A beat names only what changes. Additive by design — a
# renderer that ignores `beats` still plays the held version. No beat opens darker than 0.3:
# from the street a near-black tower reads as switched off.

BEATS: Dict[str, List[dict]] = {
    "thunderstorm": [
        {"at": 0.0, "label": "the air goes still", "motion": {"kind": "still", "speed": 0.2, "amount": 0.1}, "particles": {"density": 0.3}, "flash": {"kind": "none", "rate": 0.0}, "brightness": 0.4},
        {"at": 0.35, "label": "the sky opens", "particles": {"density": 0.9}, "flash": {"rate": 0.4}, "brightness": 0.7},
        {"at": 0.6, "label": "the strike", "motion": {"speed": 0.9, "amount": 0.45}, "flash": {"rate": 1.0}, "brightness": 1.0},
        {"at": 0.75, "label": "rain settles in", "motion": {"kind": "breathe", "speed": 0.3, "amount": 0.2}, "particles": {"density": 0.7}, "flash": {"rate": 0.15}, "brightness": 0.55},
    ],
    "birthday": [
        {"at": 0.0, "label": "candles lit", "motion": {"speed": 0.3, "amount": 0.2}, "particles": {"kind": "none", "density": 0.0}, "flash": {"rate": 0.0}, "brightness": 0.5, "word": None},
        {"at": 0.3, "label": "the blow out", "motion": {"speed": 0.9, "amount": 0.5}, "flash": {"rate": 0.7}, "brightness": 1.0},
        {"at": 0.45, "label": "confetti", "particles": {"density": 1.0}, "flash": {"rate": 0.2}, "brightness": 0.85},
        {"at": 0.8, "label": "the room settles", "motion": {"speed": 0.5, "amount": 0.3}, "particles": {"density": 0.5}, "brightness": 0.7},
    ],
    "my heart is racing": [
        {"at": 0.0, "label": "a held breath", "motion": {"kind": "still", "speed": 0.2, "amount": 0.1}, "particles": {"density": 0.0}, "brightness": 0.4},
        {"at": 0.25, "label": "it starts", "motion": {"speed": 0.7, "amount": 0.4}, "brightness": 0.7},
        {"at": 0.5, "label": "flat out", "motion": {"speed": 1.0, "amount": 0.6}, "particles": {"density": 0.4}, "brightness": 1.0},
        {"at": 0.85, "label": "still going", "motion": {"speed": 0.85, "amount": 0.5}, "brightness": 0.8},
    ],
    "rocket launch": [
        {"at": 0.0, "label": "on the pad", "particles": {"density": 0.15}, "flash": {"rate": 0.0}, "brightness": 0.4, "word": None},
        {"at": 0.2, "label": "ignition", "motion": {"kind": "shake", "speed": 0.7, "amount": 0.3}, "particles": {"density": 1.0}, "flash": {"rate": 0.6}, "brightness": 1.0, "word": None},
        {"at": 0.45, "label": "the climb", "motion": {"kind": "rise", "speed": 0.9, "amount": 0.9}, "particles": {"density": 0.8}, "flash": {"rate": 0.1}, "brightness": 0.9},
        {"at": 0.8, "label": "gone", "motion": {"kind": "rise", "speed": 0.4, "amount": 0.3}, "particles": {"density": 0.2}, "brightness": 0.45, "word": None},
    ],
    "calm ocean": [
        {"at": 0.0, "label": "the swell in", "motion": {"speed": 0.15, "amount": 0.3}, "brightness": 0.55},
        {"at": 0.5, "label": "and out", "motion": {"speed": 0.25, "amount": 0.5}, "brightness": 0.8},
    ],
    "lebron dunk": [
        {"at": 0.0, "label": "the approach", "motion": {"kind": "still", "speed": 0.3, "amount": 0.1}, "particles": {"density": 0.0}, "flash": {"rate": 0.0}, "brightness": 0.45, "word": None},
        {"at": 0.3, "label": "the leap", "motion": {"kind": "rise", "speed": 1.0, "amount": 0.9}, "particles": {"density": 0.3}, "flash": {"rate": 0.05}, "brightness": 0.8, "word": None},
        {"at": 0.55, "label": "it lands", "motion": {"kind": "shake", "speed": 1.0, "amount": 0.5}, "particles": {"density": 1.0}, "flash": {"rate": 1.0}, "brightness": 1.0},
        {"at": 0.75, "label": "the crowd", "motion": {"kind": "shake", "speed": 0.5, "amount": 0.25}, "particles": {"density": 0.5}, "flash": {"rate": 0.2}, "brightness": 0.8},
    ],
    "snow day": [
        {"at": 0.0, "label": "first flakes", "particles": {"density": 0.25}, "brightness": 0.5},
        {"at": 0.35, "label": "steady fall", "particles": {"density": 0.8}, "brightness": 0.7},
        {"at": 0.8, "label": "everything muffled", "motion": {"speed": 0.15, "amount": 0.15}, "particles": {"density": 0.6}, "brightness": 0.85},
    ],
    "i'm so happy": [
        {"at": 0.0, "label": "it rises", "motion": {"kind": "rise", "speed": 0.4, "amount": 0.3}, "particles": {"density": 0.2}, "brightness": 0.5},
        {"at": 0.35, "label": "grinning", "motion": {"kind": "pulse", "speed": 0.6, "amount": 0.3}, "particles": {"density": 0.7}, "brightness": 0.9},
        {"at": 0.75, "label": "held there", "motion": {"kind": "breathe", "speed": 0.3, "amount": 0.25}, "brightness": 1.0},
    ],
    "take me to space": [
        {"at": 0.0, "label": "drifting", "brightness": 0.4},
        {"at": 0.3, "label": "the jump", "motion": {"kind": "rise", "speed": 1.0, "amount": 1.0}, "flash": {"kind": "burst", "rate": 0.5}, "brightness": 1.0},
        {"at": 0.6, "label": "streaking", "motion": {"kind": "sweep", "speed": 1.0, "amount": 0.8}, "brightness": 0.8},
        {"at": 0.9, "label": "out there", "motion": {"kind": "still", "speed": 0.2, "amount": 0.0}, "brightness": 0.45},
    ],
    "it's raining": [
        {"at": 0.0, "label": "it starts", "particles": {"density": 0.35}, "brightness": 0.45},
        {"at": 0.4, "label": "steady now", "particles": {"density": 0.8}, "brightness": 0.6},
    ],
    "sunrise": [
        {"at": 0.0, "label": "before light", "motion": {"speed": 0.1, "amount": 0.05}, "brightness": 0.3},
        {"at": 0.3, "label": "the first edge", "motion": {"speed": 0.15, "amount": 0.2}, "brightness": 0.5},
        {"at": 0.65, "label": "full light", "motion": {"speed": 0.1, "amount": 0.15}, "brightness": 1.0},
    ],
    "sunset": [
        {"at": 0.0, "label": "full light", "brightness": 1.0},
        {"at": 0.4, "label": "the last edge", "motion": {"speed": 0.15, "amount": 0.25}, "brightness": 0.65},
        {"at": 0.8, "label": "afterglow", "motion": {"kind": "breathe", "speed": 0.1, "amount": 0.1}, "brightness": 0.4},
    ],
    "go up": [
        {"at": 0.0, "label": "the crouch", "motion": {"kind": "still", "speed": 0.2, "amount": 0.1}, "particles": {"density": 0.1}, "brightness": 0.5},
        {"at": 0.25, "label": "the push", "motion": {"speed": 1.0, "amount": 1.0}, "particles": {"density": 0.6}, "brightness": 1.0},
        {"at": 0.7, "label": "above it", "motion": {"speed": 0.3, "amount": 0.3}, "particles": {"density": 0.2}, "brightness": 0.7},
    ],
    "fireworks": [
        {"at": 0.0, "label": "the launch", "motion": {"kind": "still", "speed": 0.3, "amount": 0.0}, "particles": {"density": 0.3}, "flash": {"rate": 0.0}, "brightness": 0.4, "word": None},
        {"at": 0.25, "label": "the burst", "particles": {"density": 1.0}, "flash": {"rate": 1.0}, "brightness": 1.0},
        {"at": 0.5, "label": "falling embers", "motion": {"kind": "breathe", "speed": 0.3, "amount": 0.2}, "particles": {"density": 0.6, "direction": "down"}, "flash": {"rate": 0.1}, "brightness": 0.7, "word": None},
        {"at": 0.75, "label": "one more", "particles": {"density": 1.0, "direction": "up"}, "flash": {"rate": 0.9}, "brightness": 1.0},
    ],
    "graduation": [
        {"at": 0.0, "label": "the walk up", "motion": {"kind": "still", "speed": 0.3, "amount": 0.0}, "particles": {"density": 0.0}, "flash": {"rate": 0.0}, "brightness": 0.5, "word": None},
        {"at": 0.35, "label": "caps in the air", "motion": {"kind": "rise", "speed": 1.0, "amount": 0.9}, "particles": {"density": 1.0}, "flash": {"rate": 0.6}, "brightness": 1.0},
        {"at": 0.7, "label": "the cheer", "motion": {"kind": "pulse", "speed": 0.6, "amount": 0.3}, "particles": {"density": 0.5}, "flash": {"rate": 0.2}, "brightness": 0.85},
    ],
    "volcano": [
        {"at": 0.0, "label": "the rumble", "motion": {"speed": 0.3, "amount": 0.1}, "particles": {"density": 0.2}, "flash": {"rate": 0.0}, "brightness": 0.5},
        {"at": 0.35, "label": "eruption", "motion": {"speed": 0.9, "amount": 0.5}, "particles": {"density": 1.0}, "flash": {"rate": 0.8}, "brightness": 1.0},
        {"at": 0.7, "label": "ash falls", "motion": {"kind": "breathe", "speed": 0.3, "amount": 0.2}, "particles": {"density": 0.5, "direction": "down"}, "flash": {"rate": 0.1}, "brightness": 0.6},
    ],
    "she said yes": [
        {"at": 0.0, "label": "the question", "motion": {"kind": "still", "speed": 0.3, "amount": 0.0}, "particles": {"density": 0.0}, "flash": {"rate": 0.0}, "brightness": 0.5, "word": None},
        {"at": 0.4, "label": "yes", "motion": {"kind": "pulse", "speed": 0.9, "amount": 0.5}, "particles": {"density": 1.0}, "flash": {"rate": 0.8}, "brightness": 1.0},
        {"at": 0.75, "label": "still spinning", "motion": {"speed": 0.5, "amount": 0.3}, "particles": {"density": 0.5}, "flash": {"rate": 0.2}, "brightness": 0.85},
    ],
    "i got the job": [
        {"at": 0.0, "label": "the call", "motion": {"kind": "still", "speed": 0.3, "amount": 0.0}, "particles": {"density": 0.0}, "flash": {"rate": 0.0}, "brightness": 0.5, "word": None},
        {"at": 0.3, "label": "yes!", "motion": {"speed": 1.0, "amount": 0.5}, "particles": {"density": 1.0}, "flash": {"rate": 0.7}, "brightness": 1.0},
        {"at": 0.75, "label": "still grinning", "motion": {"speed": 0.5, "amount": 0.3}, "particles": {"density": 0.5}, "brightness": 0.85},
    ],
}


def library_spec(key: str) -> dict:
    """A library entry's spec with its choreography attached."""
    return {**LIBRARY[key]["spec"], "beats": BEATS.get(key, [])}


ALIASES: Dict[str, str] = {
    "storm": "thunderstorm", "lightning": "thunderstorm", "thunder": "thunderstorm", "thunderstorms": "thunderstorm",
    "rain": "it's raining", "rainy": "it's raining", "raining": "it's raining", "umbrella": "it's raining",
    "snow": "snow day", "winter": "snow day", "snowing": "snow day", "blizzard": "snow day",
    "sun": "sunrise", "morning": "sunrise", "dawn": "sunrise", "good morning": "sunrise",
    "dusk": "sunset", "evening": "sunset", "golden hour": "sunset",
    "moon": "full moon", "moonlight": "full moon", "the moon": "full moon",
    "aurora": "northern lights", "aurora borealis": "northern lights",
    "ocean": "calm ocean", "sea": "calm ocean", "waves": "calm ocean", "beach": "calm ocean", "the ocean": "calm ocean",
    "space": "take me to space", "stars": "take me to space", "warp": "take me to space", "outer space": "take me to space", "galaxy": "take me to space",
    "charles": "charles river", "river": "charles river", "the charles": "charles river", "sailboats": "charles river",
    "lava": "volcano", "eruption": "volcano", "erupting": "volcano",
    "forest": "the forest", "woods": "the forest", "trees": "the forest", "jungle": "the forest",
    "city": "city lights", "skyline": "city lights", "downtown": "city lights", "the city": "city lights",
    "happy birthday": "birthday", "party": "birthday", "cake": "birthday", "bday": "birthday",
    "rocket": "rocket launch", "launch": "rocket launch", "liftoff": "rocket launch", "blast off": "rocket launch", "spaceship": "rocket launch",
    "dunk": "lebron dunk", "lebron": "lebron dunk", "basketball": "lebron dunk", "sixers": "lebron dunk", "slam dunk": "lebron dunk",
    "firework": "fireworks", "boom": "fireworks", "fourth of july": "fireworks", "july fourth": "fireworks", "new years": "fireworks",
    "christmas": "merry christmas", "xmas": "merry christmas", "santa": "merry christmas", "happy holidays": "merry christmas",
    "graduated": "graduation", "graduate": "graduation", "commencement": "graduation", "diploma": "graduation", "graduation day": "graduation",
    "sox": "go sox", "red sox": "go sox", "fenway": "go sox", "baseball": "go sox",
    "celtics": "go celtics", "celts": "go celtics",
    "bruins": "go bruins", "hockey": "go bruins",
    "proposal": "she said yes", "engaged": "she said yes", "wedding": "she said yes", "married": "she said yes", "he said yes": "she said yes",
    "hired": "i got the job", "new job": "i got the job", "promotion": "i got the job", "got the job": "i got the job",
    "home": "welcome home", "coming home": "welcome home", "homecoming": "welcome home",
    "heart": "my heart is racing", "heartbeat": "my heart is racing", "nervous": "my heart is racing", "racing heart": "my heart is racing",
    "happy": "i'm so happy", "joy": "i'm so happy", "so happy": "i'm so happy",
    "love": "i love you", "valentine": "i love you", "valentines": "i love you", "love you": "i love you",
    "goodnight": "good night", "sleep": "good night", "sleepy": "good night", "bedtime": "good night", "sweet dreams": "good night",
    "luck": "good luck", "lucky": "good luck", "wish me luck": "good luck",
    "up": "go up", "higher": "go up",
    "espresso": "coffee", "latte": "coffee", "tea": "coffee", "caffeine": "coffee",
    "tree": "a tree",
}

# "surprise me" is not a scene, it is a request for any scene. Seeded by the date: a different
# answer each day, the same answer all day, which is what the phrase cache assumes anyway.
SURPRISE: Tuple[str, ...] = ("surprise me", "surprise", "anything", "random", "show me something",
                             "dealers choice", "dealer's choice", "whatever", "you pick")


def normalize(text: str) -> str:
    """Lower-case words, digits kept. "76er" is a jersey, not noise."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]", " ", str(text or "").lower())).strip()


STOPWORDS = {"the", "a", "an", "and", "or", "but", "is", "am", "are", "was", "were", "be", "to", "of", "in", "on",
             "at", "for", "with", "my", "me", "i", "you", "it", "its", "it's", "i'm", "im", "this", "that", "so",
             "very", "just", "we", "as", "by", "from", "into", "over", "under", "than", "then", "too", "his", "her",
             "their", "our", "please", "show", "make", "go", "some", "day", "full", "got", "she", "said", "take", "one"}
NEGATORS = {"not", "no", "never", "dont", "don't", "cant", "can't", "isnt", "isn't", "without", "nothing", "aint", "ain't"}
# emotion words that should lose to a concrete noun in the same phrase ("i love the rain" is about rain)
WEAK = {"happy", "love", "joy", "luck", "lucky", "home"}


def _build_index() -> Tuple[List[Tuple[List[str], str]], Dict[str, str]]:
    """Phrases (longest first) and a word -> key index from aliases, key words, keywords and titles.

    A derived word that could point at more than one scene is dropped rather than guessed at;
    an explicit alias always wins over a derived one.
    """
    phrases = [(k.split(" "), k) for k in LIBRARY] + [(a.split(" "), k) for a, k in ALIASES.items() if " " in a]
    phrases.sort(key=lambda p: -len(p[0]))
    derived: Dict[str, set] = {}
    for key, entry in LIBRARY.items():
        words = set(key.split(" ")) | set(entry["keywords"]) | set(normalize(entry["spec"]["title"]).split(" "))
        for w in words:
            if len(w) >= 3 and w not in STOPWORDS:
                derived.setdefault(w, set()).add(key)
    index = {w: next(iter(ks)) for w, ks in derived.items() if len(ks) == 1}
    index.update({a: k for a, k in ALIASES.items() if " " not in a})
    return phrases, index


PHRASES, INDEX = _build_index()
_INDEX_WORDS = sorted(INDEX)
_PHRASE_LIST = list(LIBRARY) + list(ALIASES)


def _negated(toks: List[str], i: int) -> bool:
    return any(toks[j] in NEGATORS for j in range(max(0, i - 2), i))


def match(text: str, cutoff: float = 0.7) -> Optional[Tuple[str, str, List[str]]]:
    """text -> (key, how, the words that did the matching), or None.

    Order: exact key or alias, then the longest alias phrase on word boundaries, then single
    words (aliases first, then key words, keywords and title words), then a typo-tolerant pass
    per word, then a fuzzy pass over the whole phrase. Negated words never match, so "not
    happy" is not joy, and a match is always on a whole word: the old `phrase in text` test
    made "supper" contain "up" and turned it into an arrow.
    """
    q = normalize(text)
    if not q:
        return None
    toks = q.split(" ")
    if q in SURPRISE:
        return random.Random(date.today().isoformat()).choice(list(LIBRARY)), "surprise", toks
    if q in LIBRARY:
        return q, "exact", toks
    if q in ALIASES:
        return ALIASES[q], "alias", toks
    for pt, key in PHRASES:
        n = len(pt)
        for i in range(len(toks) - n + 1):
            if toks[i:i + n] == pt and not _negated(toks, i):
                return key, "alias", list(pt)
    hits = [(w, INDEX[w]) for i, w in enumerate(toks) if w in INDEX and not _negated(toks, i)]
    strong = [h for h in hits if h[0] not in WEAK]
    if strong or hits:
        w, key = (strong or hits)[0]
        return key, ("alias" if w in ALIASES else "keyword"), [w]
    for i, w in enumerate(toks):   # a typo is still the word it obviously meant
        if len(w) >= 4 and not _negated(toks, i):
            m = difflib.get_close_matches(w, _INDEX_WORDS, n=1, cutoff=0.8)
            if m:
                return INDEX[m[0]], "fuzzy", [w]
    if len(q) >= 4:
        m = difflib.get_close_matches(q, _PHRASE_LIST, n=1, cutoff=cutoff)
        if m:
            return (m[0] if m[0] in LIBRARY else ALIASES[m[0]]), "fuzzy", toks
    return None


def lookup(text: str, cutoff: float = 0.7) -> Optional[Tuple[str, dict, str, List[str]]]:
    """The library key, the entry, *how* it matched, and which of the person's words matched.

    The caller needs the last two to be honest about what it understood.
    """
    hit = match(text, cutoff)
    if hit is None:
        return None
    key, kind, matched = hit
    return key, LIBRARY[key], kind, matched


def understood_by(key: str, entry: dict) -> set:
    """Every word a library entry can honestly claim to cover."""
    words = set(key.split(" ")) | set(entry["keywords"]) | set(normalize(entry["spec"]["title"]).split(" "))
    for alias, target in ALIASES.items():
        if target == key:
            words.update(alias.split(" "))
    return words


# --------------------------------------------------------------------------- affect lexicon

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
    "miss": (-0.5, 0.3, "lonely"), "angry": (-0.8, 0.9, "angry"), "furious": (-0.9, 1.0, "angry"),
    "annoyed": (-0.5, 0.6, "angry"), "scared": (-0.7, 0.8, "fear"), "afraid": (-0.7, 0.7, "fear"),
    "nervous": (-0.4, 0.7, "fear"), "worried": (-0.5, 0.6, "fear"), "stressed": (-0.6, 0.8, "fear"),
    "anxious": (-0.6, 0.8, "fear"),
    "curious": (0.4, 0.6, "curious"), "wonder": (0.4, 0.5, "curious"), "why": (0.1, 0.5, "curious"),
    "hello": (0.5, 0.5, "joy"), "hi": (0.5, 0.5, "joy"), "hey": (0.5, 0.6, "joy"),
    "goodbye": (-0.2, 0.3, "sad"), "bye": (-0.1, 0.3, "sad"),
    "cold": (-0.3, 0.3, "sad"), "warm": (0.5, 0.3, "love"), "mit": (0.6, 0.6, "joy"), "boston": (0.5, 0.5, "joy"),
    "exam": (-0.5, 0.7, "fear"), "finals": (-0.6, 0.8, "fear"), "coffee": (0.4, 0.7, "joy"),
}

# The reply for a mood. Neutral says nothing: on nine windows "OK" is the least interesting
# two letters available, and a mood the building cannot name should be a colour, not a sign.
EMOTION_WORD: Dict[str, Optional[str]] = {"joy": "YAY!", "love": "LOVE", "calm": "AHH", "curious": "HMM?",
                                          "surprise": "WOW!", "sad": "AWW", "lonely": "STAY?", "tired": "ZZZ",
                                          "angry": "GRR", "fear": "EEK", "neutral": None}

EMOTION_THEME = {"joy": "feeling", "love": "feeling", "calm": "feeling", "curious": "feeling", "surprise": "event",
                 "sad": "feeling", "lonely": "feeling", "tired": "feeling", "angry": "feeling", "fear": "feeling",
                 "neutral": "feeling"}

# "not happy" should land on the other side of zero, and say the other thing.
OPPOSITE = {"joy": "sad", "sad": "calm", "love": "lonely", "lonely": "love", "calm": "fear", "fear": "calm",
            "angry": "calm", "tired": "joy", "surprise": "neutral", "curious": "neutral", "neutral": "neutral"}


def lexicon_affect(text: str) -> Dict[str, object]:
    """Valence/arousal/emotion with no network. Deterministic across processes."""
    words = re.findall(r"[a-z']+", text.lower())
    vals: List[float] = []
    ars: List[float] = []
    emos: Dict[str, int] = {}
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
            "emotion": emotion,
            "matched": bool(vals)}


def keywords_of(text: str, limit: int = 5) -> List[str]:
    seen: List[str] = []
    for w in re.findall(r"[a-z']{3,}", text.lower()):
        if w not in STOPWORDS and w not in seen:
            seen.append(w)
    return seen[:limit]


# --------------------------------------------------------------------------- moderation

# The building is a public object with no operator standing next to it, so this list is
# deliberately broader than "profanity": the categories are violence against people, hate,
# sexual content, self-harm, political campaigning, advertising, and abuse aimed at a person.
#
# Two rules keep it from eating innocent phrases: every pattern matches on word boundaries,
# and the violent verbs only trip when they have a target ("kill the lights" is a lighting
# cue, "kill everyone" is not). Anything matched is refused locally and never sent to the API.
BLOCKLIST = re.compile(
    # violence with a target, named or indefinite
    r"\b(kill|murder|shoot|stab|bomb|hurt|behead|lynch)\s+(a\s+|the\s+|my\s+|that\s+|those\s+|all\s+)?"
    r"(me|you|him|her|them|us|myself|yourself|someone|somebody|anyone|anybody|everyone|everybody|"
    r"all|people|person|guy|man|woman|jews|muslims|christians|blacks|whites|asians|gays|women|men|"
    r"kids|children|cops|police|teacher|boss|neighbou?r)\b"
    # hate, terror, sexual content
    r"|\b(nazi|nazis|hitler|holocaust|genocide|kkk|klan|terrorist|isis|rape|rapist|pedo|pedophile|incest|"
    r"porn|porno|nude|nudes|naked|sex|blowjob|dick|cock|pussy|tits)\b"
    # self-harm: refuse the scene, and an operator should see these
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

# Contact details and handles: scrubbed on the way in, because the day's log is an archive and
# nobody typing a phone number at a kiosk means to leave it there.
PII_PATTERNS = (
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "someone"),
    (re.compile(r"\bhttps?://\S+|\bwww\.\S+"), "a link"),
    (re.compile(r"(?<!\w)(?:\+?\d[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)"), "a number"),
    (re.compile(r"(?<![\w@])@[A-Za-z0-9_]{2,}"), "someone"),
)


def scrub_pii(text: str) -> str:
    """Replace contact details with a placeholder. Never rejects; the scene still gets made."""
    out = str(text or "")
    for pattern, replacement in PII_PATTERNS:
        out = pattern.sub(replacement, out)
    return re.sub(r"\s+", " ", out).strip()


def is_blocked(text: str) -> bool:
    return bool(BLOCKLIST.search(str(text or "")))


def words_of(query: str) -> List[str]:
    return [w for w in query.split(" ") if w]


def blocked_result(query: str) -> SceneResult:
    return SceneResult(
        query=query, words=words_of(query), ok=False, tier="blocked", match="blocked",
        interpretation=Interpretation(title="not shown", theme="blocked", keywords=[], word="HMM?",
                                     mood=Mood(valence=0.0, arousal=0.2), recognizability=0.0,
                                     notes="blocked by the local content filter"),
        spec_draft=spec_mod.shrug(),
    )


def _nudge(draft: Dict, affect: Dict[str, object], weight: float = 0.35) -> None:
    """Let leftover words at least colour the energy of a library scene.

    The local tier cannot depict "as 76er", but it can hear that the rest of the query is
    loud or flat, and a canned scene that ignores the person's energy entirely feels like
    being talked over.
    """
    ar, v = float(affect["arousal"]), float(affect["valence"])
    draft["tempo_bpm"] = round((1 - weight) * draft["tempo_bpm"] + weight * (50 + 100 * ar), 1)
    draft["motion"]["speed"] = round(min(1.0, (1 - weight) * draft["motion"]["speed"] + weight * ar), 2)
    draft["mood"]["arousal"] = round(min(1.0, (1 - weight) * draft["mood"]["arousal"] + weight * ar), 2)
    draft["mood"]["valence"] = round(max(-1.0, min(1.0, (1 - weight) * draft["mood"]["valence"] + weight * v)), 2)


# --------------------------------------------------------------------------- the local tier

def local_result(query: str) -> SceneResult:
    """One query to one validated draft, offline.

    The honesty rules here matter more than the pixels: the result says how it matched, which
    words it could not use, and a recognizability score discounted by how much of the query it
    actually understood. A single alias hit on a four-word query is not a 90% match.
    """
    if is_blocked(query):
        return blocked_result(query)

    tokens = normalize(query).split(" ") if normalize(query) else []
    content = [w for w in tokens if w not in STOPWORDS]

    hit = lookup(query)
    if hit is not None:
        key, entry, kind, matched = hit
        known = understood_by(key, entry) | set(matched)
        unused = [w for w in content if w not in known]
        coverage = 1.0 - len(unused) / max(1, len(content))

        draft = spec_mod.validate(library_spec(key))
        notes = [f"warm library scene '{key}', matched on {', '.join(repr(w) for w in matched)}"]
        if unused:
            listed = ", ".join(repr(w) for w in unused)
            them = "them" if len(unused) > 1 else "it"
            leftover = lexicon_affect(" ".join(unused))
            if leftover["matched"]:
                _nudge(draft, leftover)
                notes.append(f"took the energy of {listed} but cannot depict {them}")
            else:
                notes.append(f"could not use {listed}")
            others = {ALIASES[w] for w in unused if w in ALIASES and ALIASES[w] != key}
            if others:
                notes.append(f"the building shows one thing at a time, so it did not also show {', '.join(sorted(others))}")

        rec = 0.9 if kind == "exact" else round(max(0.2, 0.35 + 0.55 * coverage), 2)
        interp = Interpretation(
            title=draft["title"], theme=entry["theme"],
            keywords=list(entry["keywords"]) + unused, word=draft["word"],
            mood=Mood(valence=draft["mood"]["valence"], arousal=draft["mood"]["arousal"]),
            recognizability=rec, notes="; ".join(notes),
        )
        return SceneResult(query=query, words=words_of(query), ok=True, tier="library",
                           match=kind, unused_words=unused, coverage=round(coverage, 2),
                           interpretation=interp, spec_draft=draft)

    affect = lexicon_affect(query)
    v = float(affect["valence"])
    ar = float(affect["arousal"])
    emotion = str(affect["emotion"])
    warm = v > 0
    draft = spec_mod.validate({
        "ok": True, "title": emotion, "duration_s": 9 + 4 * (1 - ar), "world": "none",
        "palette": {"base": "#2a1a03" if warm else "#0c1524",
                    "accent": "#ffd166" if warm else "#7fa7e0",
                    "glow": "#fff3b0" if warm else "#d9e6ff"},
        "motion": {"kind": "pulse" if ar > 0.6 else "breathe", "speed": ar, "amount": 0.3 + 0.4 * ar},
        "particles": {"kind": "stars" if warm else "rain", "density": 0.3 + 0.5 * ar,
                      "direction": "up" if warm else "down"},
        "tempo_bpm": 50 + 100 * ar,
        "flash": {"kind": "burst" if ar > 0.8 else "none", "rate": 0.3},
        "sprite": None,
        "word": EMOTION_WORD.get(emotion),
        "mood": {"valence": v, "arousal": ar},
        # Even a mood-only scene should arrive and subside rather than sit at one level, and the
        # word waits for the middle so the facade is not just a sign the whole time.
        "beats": [
            {"at": 0.0, "label": "it arrives", "motion": {"speed": ar * 0.4, "amount": 0.2},
             "particles": {"density": 0.15}, "brightness": 0.4, "word": None},
            {"at": 0.3, "label": emotion, "motion": {"speed": ar, "amount": 0.3 + 0.4 * ar},
             "particles": {"density": 0.3 + 0.5 * ar}, "brightness": 0.75 + 0.25 * ar},
            {"at": 0.8, "label": "and stays" if ar < 0.5 else "and holds", "motion": {"speed": ar * 0.7},
             "particles": {"density": 0.2 + 0.3 * ar}, "brightness": 0.6},
        ],
    })
    # Nothing in the library resembles this, so every content word is unused: the scene is the
    # query's mood and nothing more, and it should say so rather than imply a depiction.
    interp = Interpretation(
        title=emotion, theme=EMOTION_THEME.get(emotion, "feeling"),
        keywords=keywords_of(query), word=draft["word"],
        mood=Mood(valence=v, arousal=ar),
        recognizability=0.3 if affect["matched"] else 0.15,
        notes=("read the mood of " + ", ".join(repr(w) for w in content) + " but has no way to depict it"
               if content else "nothing recognisable in this"),
    )
    return SceneResult(query=query, words=words_of(query), ok=True, tier="lexicon",
                       match="lexicon", unused_words=content, coverage=0.0,
                       interpretation=interp, spec_draft=draft)


# --------------------------------------------------------------------------- the day's arc

def compose_arc(scenes: Sequence[SceneResult]) -> Arc:
    """Read a day of scenes as one story: as-said opening, loudest middle, calmest close.

    A single query has no arc; a day of them does. This is the seed the dream composer wants,
    and `order` indexes into the list it was given, oldest first.
    """
    live = [s for s in scenes if s.ok] or list(scenes)
    if not live:
        return Arc(title="DREAM", logline="nothing was said today.", order=[],
                   through_line="an empty night", palette={})

    def arousal(i: int) -> float:
        return live[i].interpretation.mood.arousal

    order = list(range(len(live)))
    if len(order) >= 3:
        rest = order[1:]
        rest.sort(key=arousal, reverse=True)
        calmest = min(rest, key=arousal)
        rest.remove(calmest)
        order = [0] + rest + [calmest]

    loudest = max(live, key=lambda s: s.interpretation.mood.arousal)
    themes: Dict[str, int] = {}
    for s in live:
        themes[s.interpretation.theme] = themes.get(s.interpretation.theme, 0) + 1
    theme = max(themes, key=lambda k: themes[k]) if themes else "feeling"

    title = spec_mod.clean_word(loudest.interpretation.word or loudest.interpretation.title) or "DREAM"
    titles = [live[i].interpretation.title for i in order]
    logline = f"{len(live)} things said today: " + ", ".join(titles) + "."

    return Arc(
        title=title, logline=logline[:280], order=order,
        through_line=f"a night of {theme}, opening on {titles[0]} and settling into {titles[-1]}"[:140],
        palette=dict(loudest.spec_draft["palette"]),
    )
