"""The warm library: reference scenes that answer instantly and offline, and the
few-shots the model is shown so both tiers agree on what "good" looks like.

This file is mirrored, entry for entry, by the language service's ``app/fallback.py``
(a test over there pins the two together). Change a scene here and there, or preview
and performance stop matching.

Vocabulary:
    ENTRIES   key -> {theme, keywords, spec}   the scenes, in the renderer's spec-v1 shape
    BEATS     key -> [beat, ...]               choreography: what builds, what lands, what is left
    ALIASES   phrase -> key                    the other ways people say the same thing
    LIBRARY   key -> spec                      what the renderer and the model few-shots read
    match()   text -> (key, how, words)        the matcher; lookup() wraps it for the runner
"""

from __future__ import annotations

import difflib
import random
import re
from datetime import date
from typing import Dict, List, Optional, Tuple

# ----------------------------------------------------------------------------- sprites (9 wide)

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
    return {"ok": True, "title": title, "duration_s": duration_s, "world": world,
            "palette": {"base": base, "accent": accent, "glow": glow},
            "motion": {"kind": motion[0], "speed": motion[1], "amount": motion[2]},
            "particles": {"kind": particles[0], "density": particles[1], "direction": particles[2]},
            "tempo_bpm": tempo_bpm, "flash": {"kind": flash[0], "rate": flash[1]},
            "sprite": {"rows": sprite[0], "anim": sprite[1], "color": sprite[2]} if sprite else None,
            "word": word, "mood": {"valence": mood[0], "arousal": mood[1]}}


def _e(theme: str, keywords: List[str], spec: dict) -> dict:
    return {"theme": theme, "keywords": keywords, "spec": spec}


# ----------------------------------------------------------------------------- the scenes

ENTRIES: Dict[str, dict] = {
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

# ----------------------------------------------------------------------------- choreography
#
# A beat names only what changes and inherits the rest. No beat opens darker than 0.3: from the
# street a near-black tower reads as switched off, and the first beat is what a passer-by sees.

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

# ----------------------------------------------------------------------------- aliases

ALIASES: Dict[str, str] = {
    "storm": "thunderstorm", "lightning": "thunderstorm", "thunder": "thunderstorm", "thunderstorms": "thunderstorm",
    "rain": "it's raining", "rainy": "it's raining", "raining": "it's raining", "umbrella": "it's raining",
    "pouring": "it's raining", "drizzle": "it's raining",
    "snow": "snow day", "winter": "snow day", "snowing": "snow day", "blizzard": "snow day", "snowstorm": "snow day",
    "sun": "sunrise", "morning": "sunrise", "dawn": "sunrise", "good morning": "sunrise",
    "dusk": "sunset", "evening": "sunset", "golden hour": "sunset", "sundown": "sunset",
    "moon": "full moon", "moonlight": "full moon", "the moon": "full moon", "moonrise": "full moon",
    "aurora": "northern lights", "aurora borealis": "northern lights",
    "ocean": "calm ocean", "sea": "calm ocean", "waves": "calm ocean", "beach": "calm ocean", "the ocean": "calm ocean",
    "space": "take me to space", "stars": "take me to space", "warp": "take me to space", "outer space": "take me to space", "galaxy": "take me to space",
    "milky way": "take me to space",
    "charles": "charles river", "river": "charles river", "the charles": "charles river", "sailboats": "charles river",
    "esplanade": "charles river", "the esplanade": "charles river",
    "lava": "volcano", "eruption": "volcano", "erupting": "volcano",
    "forest": "the forest", "woods": "the forest", "trees": "the forest", "jungle": "the forest",
    "city": "city lights", "skyline": "city lights", "downtown": "city lights", "the city": "city lights",
    "boston": "city lights",
    "happy birthday": "birthday", "party": "birthday", "cake": "birthday", "bday": "birthday",
    "rocket": "rocket launch", "launch": "rocket launch", "liftoff": "rocket launch", "blast off": "rocket launch", "spaceship": "rocket launch",
    "dunk": "lebron dunk", "lebron": "lebron dunk", "basketball": "lebron dunk", "sixers": "lebron dunk", "slam dunk": "lebron dunk",
    "firework": "fireworks", "boom": "fireworks", "fourth of july": "fireworks", "july fourth": "fireworks",
    "new years": "fireworks", "new year": "fireworks", "happy new year": "fireworks",
    "christmas": "merry christmas", "xmas": "merry christmas", "santa": "merry christmas", "happy holidays": "merry christmas",
    "graduated": "graduation", "graduate": "graduation", "commencement": "graduation", "diploma": "graduation", "graduation day": "graduation",
    "congrats": "graduation", "congratulations": "graduation",
    "sox": "go sox", "red sox": "go sox", "fenway": "go sox", "baseball": "go sox",
    "celtics": "go celtics", "celts": "go celtics",
    "bruins": "go bruins", "hockey": "go bruins",
    "proposal": "she said yes", "engaged": "she said yes", "wedding": "she said yes", "married": "she said yes", "he said yes": "she said yes",
    "marry me": "she said yes", "will you marry me": "she said yes",
    "hired": "i got the job", "new job": "i got the job", "promotion": "i got the job", "got the job": "i got the job",
    "home": "welcome home", "coming home": "welcome home", "homecoming": "welcome home",
    "heart": "my heart is racing", "heartbeat": "my heart is racing", "nervous": "my heart is racing", "racing heart": "my heart is racing",
    "happy": "i'm so happy", "joy": "i'm so happy", "so happy": "i'm so happy",
    "love": "i love you", "valentine": "i love you", "valentines": "i love you", "love you": "i love you",
    "goodnight": "good night", "sleep": "good night", "sleepy": "good night", "bedtime": "good night", "sweet dreams": "good night",
    "luck": "good luck", "lucky": "good luck", "wish me luck": "good luck",
    "fingers crossed": "good luck", "break a leg": "good luck",
    "up": "go up", "higher": "go up",
    "espresso": "coffee", "latte": "coffee", "tea": "coffee", "caffeine": "coffee",
    "dunkin": "coffee", "dunkies": "coffee", "dunkin donuts": "coffee",
    "tree": "a tree",
}

# "surprise me" is not a scene, it is a request for any scene. Seeded by the date: a different
# answer each day, the same answer all day, which is what both caches here assume anyway.
SURPRISE: Tuple[str, ...] = ("surprise me", "surprise", "anything", "random", "show me something", "dealers choice", "dealer's choice", "whatever", "you pick")

LIBRARY: Dict[str, dict] = {k: v["spec"] for k, v in ENTRIES.items()}

STOPWORDS = {"the", "a", "an", "and", "or", "but", "is", "am", "are", "was", "were", "be", "to", "of", "in", "on", "at", "for",
             "with", "my", "me", "i", "you", "it", "its", "it's", "i'm", "im", "this", "that", "so", "very", "just", "we", "as", "by",
             "from", "into", "over", "under", "than", "then", "too", "his", "her", "their", "our", "please", "show", "make", "go", "some",
             "day", "full", "got", "she", "said", "take", "one"}
NEGATORS = {"not", "no", "never", "dont", "don't", "cant", "can't", "isnt", "isn't", "without", "nothing", "aint", "ain't"}
# emotion words that should lose to a concrete noun in the same phrase ("i love the rain" is about rain)
WEAK = {"happy", "love", "joy", "luck", "lucky", "home"}
# Colours never enter the derived index. Every scene has a palette, so a colour is the least
# discriminating word in the vocabulary, and whichever entry happens to list one wins by
# accident of authorship: "red" reached *red sox*, so "a red balloon" and "red leaves" both put
# GO SOX! on the facade and "a gold medal" got BRUINS. An alias may still name one on purpose.
COLOURS = {"red", "orange", "yellow", "green", "blue", "purple", "pink", "gold", "golden",
           "silver", "grey", "gray", "white", "black", "brown", "teal", "crimson", "scarlet"}


def library_spec(key: str) -> dict:
    """A scene with its choreography attached, ready for validate()."""
    return {**ENTRIES[key]["spec"], "beats": BEATS.get(key, [])}


def normalize(text: str) -> str:
    """Lower-case words; digits and apostrophes kept ("76er" is a jersey, not noise)."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]", " ", str(text or "").lower())).strip()


def _build_index() -> Tuple[List[Tuple[List[str], str]], Dict[str, str], set]:
    """Phrases (longest first), a word -> key index, and the words the index had to give up on.

    The index is built from aliases, key words, keywords and titles. A derived word that could
    point at more than one scene is dropped; an alias always wins.

    The dropped ones are kept, because "cannot place this word" and "have never heard this word"
    are different facts and the typo pass needs to tell them apart. See ``match``.
    """
    phrases = [(k.split(" "), k) for k in ENTRIES] + [(a.split(" "), k) for a, k in ALIASES.items() if " " in a]
    phrases.sort(key=lambda p: -len(p[0]))
    derived: Dict[str, set] = {}
    for key, entry in ENTRIES.items():
        words = set(key.split(" ")) | set(entry["keywords"]) | set(normalize(entry["spec"]["title"]).split(" "))
        for w in words:
            if len(w) >= 3 and w not in STOPWORDS and w not in COLOURS:
                derived.setdefault(w, set()).add(key)
    index = {w: next(iter(ks)) for w, ks in derived.items() if len(ks) == 1}
    index.update({a: k for a, k in ALIASES.items() if " " not in a})
    ambiguous = {w for w, ks in derived.items() if len(ks) > 1} - set(index)
    return phrases, index, ambiguous


PHRASES, INDEX, AMBIGUOUS = _build_index()
_INDEX_WORDS = sorted(INDEX)
_PHRASE_LIST = list(ENTRIES) + list(ALIASES)

# A typo pass is a guess, so it only runs on words long enough for the guess to be worth making.
# Below six letters it is not: one wrong letter in a five-letter word scores exactly 0.8, the
# cutoff, so every short English word has a neighbour in the index. "late" became *coffee*
# (latte), "tired" became *i got the job* (hired), "shana tova" became *merry christmas*
# (santa). At six the same test catches the misspellings that matter — firewroks, chirstmas,
# brithday, graduaton — and stops inventing scenes out of ordinary words.
MIN_TYPO_LEN = 6


def _negated(toks: List[str], i: int) -> bool:
    return any(toks[j] in NEGATORS for j in range(max(0, i - 2), i))


def match(text: str, cutoff: float = 0.72) -> Optional[Tuple[str, str, List[str]]]:
    """text -> (key, how, words that did the matching), or None.

    Order: exact key/alias, then the longest alias phrase on word boundaries, then single
    words (aliases, key words, keywords, title words), then a typo-tolerant pass per word,
    then a fuzzy pass over the whole phrase. Negated words never match ("not happy" is not
    joy). ``how`` is one of exact | alias | keyword | fuzzy | surprise.

    The typo pass skips anything in ``AMBIGUOUS``. "night" belongs to four scenes, so the
    index drops it on purpose — and correcting it to "light" and landing on *joy* is worse
    than the honest miss the drop was for. A word we know and cannot place stays unplaced.
    """
    q = normalize(text)
    if not q:
        return None
    toks = q.split(" ")
    if q in SURPRISE:
        return random.Random(date.today().isoformat()).choice(list(ENTRIES)), "surprise", toks
    if q in ENTRIES:
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
        if len(w) >= MIN_TYPO_LEN and w not in AMBIGUOUS and not _negated(toks, i):
            m = difflib.get_close_matches(w, _INDEX_WORDS, n=1, cutoff=0.8)
            if m:
                return INDEX[m[0]], "fuzzy", [w]
    if len(q) >= 4:
        m = difflib.get_close_matches(q, _PHRASE_LIST, n=1, cutoff=cutoff)
        if m:
            return (m[0] if m[0] in ENTRIES else ALIASES[m[0]]), "fuzzy", toks
    return None


def lookup(text: str, cutoff: float = 0.72) -> Optional[dict]:
    """Instant answers for the runner: the matched scene (with beats), or None."""
    hit = match(text, cutoff)
    return library_spec(hit[0]) if hit else None
