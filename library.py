"""Reference specs: ground truth for what the model should produce, the
few-shot examples in its prompt, and the offline "warm library" that answers
instantly (and keeps the show running with no internet)."""

from __future__ import annotations

import difflib
import re
from typing import Dict, Optional

ROCKET = ["....#....", "...###...", "...###...", "..#####..", "..#####..", "..#####..", "..#####..", ".#######.", ".#.###.#.", "#..###..#", "...#.#...", "..#...#.."]
HEART = [".##...##.", "###.#.###", "#########", "#########", ".#######.", "..#####..", "...###...", "....#...."]
CAKE = ["..#.#.#..", "..#.#.#..", ".#######.", "#########", "#.#.#.#.#", "#########", "#########", ".#######."]
BALL = ["..#####..", ".##.#.##.", "##..#..##", "#########", "##..#..##", ".##.#.##.", "..#####.."]
SMILE = ["..#####..", ".#.....#.", "#.#...#.#", "#.......#", "#.#...#.#", "#..###..#", ".#.....#.", "..#####.."]
ARROW_UP = ["....#....", "...###...", "..#####..", ".#######.", "...###...", "...###...", "...###...", "...###..."]
UMBRELLA = ["....#....", "..#####..", ".#######.", "#########", "#.#.#.#.#", "....#....", "....#....", "....#....", "...##...."]

LIBRARY: Dict[str, dict] = {
    "thunderstorm": {"ok": True, "title": "thunderstorm", "duration_s": 12, "world": "storm",
                     "palette": {"base": "#0d1220", "accent": "#8fa6d9", "glow": "#f4f7ff"},
                     "motion": {"kind": "shake", "speed": 0.6, "amount": 0.25}, "particles": {"kind": "rain", "density": 0.9, "direction": "down"},
                     "tempo_bpm": 70, "flash": {"kind": "lightning", "rate": 0.7}, "sprite": None, "word": None, "mood": {"valence": -0.3, "arousal": 0.8}},
    "birthday": {"ok": True, "title": "birthday party", "duration_s": 12, "world": "none",
                 "palette": {"base": "#2a0f2e", "accent": "#ff7ab6", "glow": "#ffd166"},
                 "motion": {"kind": "pulse", "speed": 0.7, "amount": 0.4}, "particles": {"kind": "confetti", "density": 0.9, "direction": "down"},
                 "tempo_bpm": 120, "flash": {"kind": "burst", "rate": 0.3}, "sprite": {"rows": CAKE, "anim": "pulse", "color": "#ffd166"}, "word": "BDAY!", "mood": {"valence": 0.9, "arousal": 0.8}},
    "my heart is racing": {"ok": True, "title": "racing heart", "duration_s": 10, "world": "none",
                           "palette": {"base": "#1a0508", "accent": "#ff3b4e", "glow": "#ffd6d9"},
                           "motion": {"kind": "pulse", "speed": 0.9, "amount": 0.5}, "particles": {"kind": "sparks", "density": 0.3, "direction": "up"},
                           "tempo_bpm": 150, "flash": {"kind": "none", "rate": 0}, "sprite": {"rows": HEART, "anim": "pulse", "color": "#ff3b4e"}, "word": None, "mood": {"valence": 0.2, "arousal": 1.0}},
    "rocket launch": {"ok": True, "title": "rocket launch", "duration_s": 12, "world": "none",
                      "palette": {"base": "#05070f", "accent": "#ff9f43", "glow": "#ffffff"},
                      "motion": {"kind": "still", "speed": 0.5, "amount": 0.0}, "particles": {"kind": "sparks", "density": 0.8, "direction": "up"},
                      "tempo_bpm": 100, "flash": {"kind": "burst", "rate": 0.15}, "sprite": {"rows": ROCKET, "anim": "rise", "color": "#ffffff"}, "word": "LIFTOFF", "mood": {"valence": 0.7, "arousal": 0.9}},
    "calm ocean": {"ok": True, "title": "calm ocean", "duration_s": 18, "world": "ocean",
                   "palette": {"base": "#041224", "accent": "#4fb3ff", "glow": "#dff6ff"},
                   "motion": {"kind": "breathe", "speed": 0.2, "amount": 0.4}, "particles": {"kind": "bubbles", "density": 0.25, "direction": "up"},
                   "tempo_bpm": 40, "flash": {"kind": "none", "rate": 0}, "sprite": None, "word": None, "mood": {"valence": 0.6, "arousal": 0.1}},
    "lebron dunk": {"ok": True, "title": "LeBron dunk", "duration_s": 10, "world": "none",
                    "palette": {"base": "#06122a", "accent": "#ed174c", "glow": "#ffffff"},
                    "motion": {"kind": "shake", "speed": 0.8, "amount": 0.2}, "particles": {"kind": "sparks", "density": 0.5, "direction": "up"},
                    "tempo_bpm": 130, "flash": {"kind": "burst", "rate": 0.5}, "sprite": {"rows": BALL, "anim": "bounce", "color": "#ff8c42"}, "word": "DUNK!", "mood": {"valence": 0.9, "arousal": 1.0}},
    "snow day": {"ok": True, "title": "snow day", "duration_s": 14, "world": "snow",
                 "palette": {"base": "#0a1020", "accent": "#bcd3ff", "glow": "#ffffff"},
                 "motion": {"kind": "breathe", "speed": 0.2, "amount": 0.2}, "particles": {"kind": "snow", "density": 0.8, "direction": "down"},
                 "tempo_bpm": 45, "flash": {"kind": "none", "rate": 0}, "sprite": None, "word": None, "mood": {"valence": 0.5, "arousal": 0.2}},
    "i'm so happy": {"ok": True, "title": "joy", "duration_s": 10, "world": "none",
                     "palette": {"base": "#2a1a03", "accent": "#ffd166", "glow": "#fff3b0"},
                     "motion": {"kind": "pulse", "speed": 0.6, "amount": 0.3}, "particles": {"kind": "stars", "density": 0.6, "direction": "up"},
                     "tempo_bpm": 110, "flash": {"kind": "none", "rate": 0}, "sprite": {"rows": SMILE, "anim": "bounce", "color": "#ffd166"}, "word": None, "mood": {"valence": 0.9, "arousal": 0.6}},
    "take me to space": {"ok": True, "title": "hyperspace", "duration_s": 12, "world": "hyperspace",
                         "palette": {"base": "#02030a", "accent": "#9fb8ff", "glow": "#ffffff"},
                         "motion": {"kind": "still", "speed": 0.5, "amount": 0.0}, "particles": {"kind": "none", "density": 0, "direction": "down"},
                         "tempo_bpm": 90, "flash": {"kind": "none", "rate": 0}, "sprite": None, "word": None, "mood": {"valence": 0.6, "arousal": 0.7}},
    "it's raining": {"ok": True, "title": "rain", "duration_s": 12, "world": "none",
                     "palette": {"base": "#0c1524", "accent": "#7fa7e0", "glow": "#d9e6ff"},
                     "motion": {"kind": "still", "speed": 0.3, "amount": 0.0}, "particles": {"kind": "rain", "density": 0.7, "direction": "down"},
                     "tempo_bpm": 60, "flash": {"kind": "none", "rate": 0}, "sprite": {"rows": UMBRELLA, "anim": "hold", "color": "#ffd166"}, "word": None, "mood": {"valence": -0.1, "arousal": 0.3}},
    "sunrise": {"ok": True, "title": "sunrise", "duration_s": 16, "world": "sunrise",
                "palette": {"base": "#1a0a1e", "accent": "#ff9f43", "glow": "#fff2c2"},
                "motion": {"kind": "rise", "speed": 0.15, "amount": 0.2}, "particles": {"kind": "none", "density": 0, "direction": "up"},
                "tempo_bpm": 50, "flash": {"kind": "none", "rate": 0}, "sprite": None, "word": None, "mood": {"valence": 0.7, "arousal": 0.3}},
    "go up": {"ok": True, "title": "up", "duration_s": 8, "world": "none",
              "palette": {"base": "#0a1a12", "accent": "#5cffa6", "glow": "#e8fff2"},
              "motion": {"kind": "rise", "speed": 0.7, "amount": 0.8}, "particles": {"kind": "sparks", "density": 0.4, "direction": "up"},
              "tempo_bpm": 100, "flash": {"kind": "none", "rate": 0}, "sprite": {"rows": ARROW_UP, "anim": "rise", "color": "#5cffa6"}, "word": None, "mood": {"valence": 0.6, "arousal": 0.7}},
}

ALIASES = {"storm": "thunderstorm", "lightning": "thunderstorm", "thunder": "thunderstorm", "happy birthday": "birthday", "party": "birthday", "cake": "birthday",
           "heart": "my heart is racing", "heartbeat": "my heart is racing", "nervous": "my heart is racing", "rocket": "rocket launch", "launch": "rocket launch", "liftoff": "rocket launch",
           "ocean": "calm ocean", "sea": "calm ocean", "waves": "calm ocean", "beach": "calm ocean", "dunk": "lebron dunk", "lebron": "lebron dunk", "basketball": "lebron dunk", "sixers": "lebron dunk",
           "snow": "snow day", "winter": "snow day", "happy": "i'm so happy", "joy": "i'm so happy", "space": "take me to space", "stars": "take me to space", "warp": "take me to space",
           "rain": "it's raining", "rainy": "it's raining", "sun": "sunrise", "morning": "sunrise", "dawn": "sunrise", "up": "go up", "higher": "go up"}


def normalize(text: str) -> str:
    return re.sub(r"[^a-z' ]", " ", text.lower()).strip()


def lookup(text: str, cutoff: float = 0.72) -> Optional[dict]:
    """Instant answers: exact / alias / fuzzy match against the warm library."""
    q = normalize(text)
    if not q:
        return None
    if q in LIBRARY:
        return LIBRARY[q]
    for w in q.split():
        if w in ALIASES:
            return LIBRARY[ALIASES[w]]
    for phrase, key in ALIASES.items():
        if phrase in q:
            return LIBRARY[key]
    m = difflib.get_close_matches(q, list(LIBRARY) + list(ALIASES), n=1, cutoff=cutoff)
    if m:
        return LIBRARY[m[0]] if m[0] in LIBRARY else LIBRARY[ALIASES[m[0]]]
    return None
