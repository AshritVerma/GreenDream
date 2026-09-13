"""The local tier: a query to a scene draft with no network, no key, no API bill.

Two stages, both deterministic (same query in, same draft out, in any process):

    1. warm library  12 hand-written scenes plus aliases and a fuzzy match. These are the
                     things people actually ask for, and they are also the reference specs
                     the model is shown, so the two tiers agree on what "good" looks like.
    2. lexicon       valence/arousal from a small affect table, mapped to palette, motion,
                     particles and tempo. Always answers something.

This module is also the moderation gate (`BLOCKLIST`) and the day-level arc composer.
"""

from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional, Sequence, Tuple

from . import spec as spec_mod
from .models import Arc, Interpretation, Mood, SceneResult

# --------------------------------------------------------------------------- sprites

ROCKET = ["....#....", "...###...", "...###...", "..#####..", "..#####..", "..#####..", "..#####..", ".#######.", ".#.###.#.", "#..###..#", "...#.#...", "..#...#.."]
HEART = [".##...##.", "###.#.###", "#########", "#########", ".#######.", "..#####..", "...###...", "....#...."]
CAKE = ["..#.#.#..", "..#.#.#..", ".#######.", "#########", "#.#.#.#.#", "#########", "#########", ".#######."]
BALL = ["..#####..", ".##.#.##.", "##..#..##", "#########", "##..#..##", ".##.#.##.", "..#####.."]
SMILE = ["..#####..", ".#.....#.", "#.#...#.#", "#.......#", "#.#...#.#", "#..###..#", ".#.....#.", "..#####.."]
ARROW_UP = ["....#....", "...###...", "..#####..", ".#######.", "...###...", "...###...", "...###...", "...###..."]
UMBRELLA = ["....#....", "..#####..", ".#######.", "#########", "#.#.#.#.#", "....#....", "....#....", "....#....", "...##...."]

# --------------------------------------------------------------------------- warm library

LIBRARY: Dict[str, dict] = {
    "thunderstorm": {
        "theme": "weather", "keywords": ["storm", "lightning", "rain"],
        "spec": {"ok": True, "title": "thunderstorm", "duration_s": 12, "world": "storm",
                 "palette": {"base": "#0d1220", "accent": "#8fa6d9", "glow": "#f4f7ff"},
                 "motion": {"kind": "shake", "speed": 0.6, "amount": 0.25},
                 "particles": {"kind": "rain", "density": 0.9, "direction": "down"},
                 "tempo_bpm": 70, "flash": {"kind": "lightning", "rate": 0.7}, "sprite": None,
                 "word": None, "mood": {"valence": -0.3, "arousal": 0.8}}},
    "birthday": {
        "theme": "event", "keywords": ["cake", "candles", "confetti"],
        "spec": {"ok": True, "title": "birthday party", "duration_s": 12, "world": "none",
                 "palette": {"base": "#2a0f2e", "accent": "#ff7ab6", "glow": "#ffd166"},
                 "motion": {"kind": "pulse", "speed": 0.7, "amount": 0.4},
                 "particles": {"kind": "confetti", "density": 0.9, "direction": "down"},
                 "tempo_bpm": 120, "flash": {"kind": "burst", "rate": 0.3},
                 "sprite": {"rows": CAKE, "anim": "pulse", "color": "#ffd166"},
                 "word": "BDAY!", "mood": {"valence": 0.9, "arousal": 0.8}}},
    "my heart is racing": {
        "theme": "feeling", "keywords": ["heart", "pulse", "nerves"],
        "spec": {"ok": True, "title": "racing heart", "duration_s": 10, "world": "none",
                 "palette": {"base": "#1a0508", "accent": "#ff3b4e", "glow": "#ffd6d9"},
                 "motion": {"kind": "pulse", "speed": 0.9, "amount": 0.5},
                 "particles": {"kind": "sparks", "density": 0.3, "direction": "up"},
                 "tempo_bpm": 150, "flash": {"kind": "none", "rate": 0},
                 "sprite": {"rows": HEART, "anim": "pulse", "color": "#ff3b4e"},
                 "word": None, "mood": {"valence": 0.2, "arousal": 1.0}}},
    "rocket launch": {
        "theme": "event", "keywords": ["rocket", "fire", "ascent"],
        "spec": {"ok": True, "title": "rocket launch", "duration_s": 12, "world": "none",
                 "palette": {"base": "#05070f", "accent": "#ff9f43", "glow": "#ffffff"},
                 "motion": {"kind": "still", "speed": 0.5, "amount": 0.0},
                 "particles": {"kind": "sparks", "density": 0.8, "direction": "up"},
                 "tempo_bpm": 100, "flash": {"kind": "burst", "rate": 0.15},
                 "sprite": {"rows": ROCKET, "anim": "rise", "color": "#ffffff"},
                 "word": "LIFTOFF", "mood": {"valence": 0.7, "arousal": 0.9}}},
    "calm ocean": {
        "theme": "place", "keywords": ["waves", "water", "swell"],
        "spec": {"ok": True, "title": "calm ocean", "duration_s": 18, "world": "ocean",
                 "palette": {"base": "#041224", "accent": "#4fb3ff", "glow": "#dff6ff"},
                 "motion": {"kind": "breathe", "speed": 0.2, "amount": 0.4},
                 "particles": {"kind": "bubbles", "density": 0.25, "direction": "up"},
                 "tempo_bpm": 40, "flash": {"kind": "none", "rate": 0}, "sprite": None,
                 "word": None, "mood": {"valence": 0.6, "arousal": 0.1}}},
    "lebron dunk": {
        "theme": "event", "keywords": ["basketball", "jump", "crowd"],
        "spec": {"ok": True, "title": "a dunk", "duration_s": 10, "world": "none",
                 "palette": {"base": "#06122a", "accent": "#ed174c", "glow": "#ffffff"},
                 "motion": {"kind": "shake", "speed": 0.8, "amount": 0.2},
                 "particles": {"kind": "sparks", "density": 0.5, "direction": "up"},
                 "tempo_bpm": 130, "flash": {"kind": "burst", "rate": 0.5},
                 "sprite": {"rows": BALL, "anim": "bounce", "color": "#ff8c42"},
                 "word": "DUNK!", "mood": {"valence": 0.9, "arousal": 1.0}}},
    "snow day": {
        "theme": "weather", "keywords": ["snow", "quiet", "cold"],
        "spec": {"ok": True, "title": "snow day", "duration_s": 14, "world": "snow",
                 "palette": {"base": "#0a1020", "accent": "#bcd3ff", "glow": "#ffffff"},
                 "motion": {"kind": "breathe", "speed": 0.2, "amount": 0.2},
                 "particles": {"kind": "snow", "density": 0.8, "direction": "down"},
                 "tempo_bpm": 45, "flash": {"kind": "none", "rate": 0}, "sprite": None,
                 "word": None, "mood": {"valence": 0.5, "arousal": 0.2}}},
    "i'm so happy": {
        "theme": "feeling", "keywords": ["joy", "smile", "light"],
        "spec": {"ok": True, "title": "joy", "duration_s": 10, "world": "none",
                 "palette": {"base": "#2a1a03", "accent": "#ffd166", "glow": "#fff3b0"},
                 "motion": {"kind": "pulse", "speed": 0.6, "amount": 0.3},
                 "particles": {"kind": "stars", "density": 0.6, "direction": "up"},
                 "tempo_bpm": 110, "flash": {"kind": "none", "rate": 0},
                 "sprite": {"rows": SMILE, "anim": "bounce", "color": "#ffd166"},
                 "word": None, "mood": {"valence": 0.9, "arousal": 0.6}}},
    "take me to space": {
        "theme": "place", "keywords": ["stars", "warp", "void"],
        "spec": {"ok": True, "title": "hyperspace", "duration_s": 12, "world": "hyperspace",
                 "palette": {"base": "#02030a", "accent": "#9fb8ff", "glow": "#ffffff"},
                 "motion": {"kind": "still", "speed": 0.5, "amount": 0.0},
                 "particles": {"kind": "none", "density": 0, "direction": "down"},
                 "tempo_bpm": 90, "flash": {"kind": "none", "rate": 0}, "sprite": None,
                 "word": None, "mood": {"valence": 0.6, "arousal": 0.7}}},
    "it's raining": {
        "theme": "weather", "keywords": ["rain", "umbrella", "grey"],
        "spec": {"ok": True, "title": "rain", "duration_s": 12, "world": "none",
                 "palette": {"base": "#0c1524", "accent": "#7fa7e0", "glow": "#d9e6ff"},
                 "motion": {"kind": "still", "speed": 0.3, "amount": 0.0},
                 "particles": {"kind": "rain", "density": 0.7, "direction": "down"},
                 "tempo_bpm": 60, "flash": {"kind": "none", "rate": 0},
                 "sprite": {"rows": UMBRELLA, "anim": "hold", "color": "#ffd166"},
                 "word": None, "mood": {"valence": -0.1, "arousal": 0.3}}},
    "sunrise": {
        "theme": "weather", "keywords": ["sun", "horizon", "warmth"],
        "spec": {"ok": True, "title": "sunrise", "duration_s": 16, "world": "sunrise",
                 "palette": {"base": "#1a0a1e", "accent": "#ff9f43", "glow": "#fff2c2"},
                 "motion": {"kind": "rise", "speed": 0.15, "amount": 0.2},
                 "particles": {"kind": "none", "density": 0, "direction": "up"},
                 "tempo_bpm": 50, "flash": {"kind": "none", "rate": 0}, "sprite": None,
                 "word": None, "mood": {"valence": 0.7, "arousal": 0.3}}},
    "go up": {
        "theme": "object", "keywords": ["arrow", "climb", "height"],
        "spec": {"ok": True, "title": "up", "duration_s": 8, "world": "none",
                 "palette": {"base": "#0a1a12", "accent": "#5cffa6", "glow": "#e8fff2"},
                 "motion": {"kind": "rise", "speed": 0.7, "amount": 0.8},
                 "particles": {"kind": "sparks", "density": 0.4, "direction": "up"},
                 "tempo_bpm": 100, "flash": {"kind": "none", "rate": 0},
                 "sprite": {"rows": ARROW_UP, "anim": "rise", "color": "#5cffa6"},
                 "word": None, "mood": {"valence": 0.6, "arousal": 0.7}}},
}

ALIASES = {
    "storm": "thunderstorm", "lightning": "thunderstorm", "thunder": "thunderstorm",
    "happy birthday": "birthday", "party": "birthday", "cake": "birthday",
    "heart": "my heart is racing", "heartbeat": "my heart is racing", "nervous": "my heart is racing",
    "rocket": "rocket launch", "launch": "rocket launch", "liftoff": "rocket launch",
    "ocean": "calm ocean", "sea": "calm ocean", "waves": "calm ocean", "beach": "calm ocean",
    "dunk": "lebron dunk", "basketball": "lebron dunk",
    "snow": "snow day", "winter": "snow day",
    "happy": "i'm so happy", "joy": "i'm so happy",
    "space": "take me to space", "stars": "take me to space", "warp": "take me to space",
    "rain": "it's raining", "rainy": "it's raining",
    "sun": "sunrise", "morning": "sunrise", "dawn": "sunrise",
    "up": "go up", "higher": "go up",
}


def normalize(text: str) -> str:
    """Lower-case words, digits kept. "76er" is a jersey, not noise."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]", " ", text.lower())).strip()


def lookup(text: str, cutoff: float = 0.7) -> Optional[Tuple[str, dict, str, List[str]]]:
    """Instant answers: exact, then alias word, then alias phrase, then fuzzy.

    Returns the library key, the entry, *how* it matched, and which of the person's words did
    the matching. The caller needs the last two to be honest about what it understood.
    """
    q = normalize(text)
    if not q:
        return None
    tokens = q.split(" ")
    if q in LIBRARY:
        return q, LIBRARY[q], "exact", tokens
    for w in tokens:
        if w in ALIASES:
            key = ALIASES[w]
            return key, LIBRARY[key], "alias", [w]
    for phrase, key in ALIASES.items():
        if phrase in q:
            return key, LIBRARY[key], "alias", phrase.split(" ")
    match = difflib.get_close_matches(q, list(LIBRARY) + list(ALIASES), n=1, cutoff=cutoff)
    if match:
        key = match[0] if match[0] in LIBRARY else ALIASES[match[0]]
        return key, LIBRARY[key], "fuzzy", tokens
    return None


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
    "yay": (0.9, 0.9, "joy"), "win": (0.8, 0.85, "joy"), "graduate": (0.9, 0.8, "joy"),
    "calm": (0.4, 0.15, "calm"), "peace": (0.5, 0.1, "calm"), "quiet": (0.2, 0.1, "calm"), "relax": (0.5, 0.1, "calm"),
    "sleep": (0.1, 0.05, "tired"), "tired": (-0.3, 0.15, "tired"), "exhausted": (-0.5, 0.1, "tired"),
    "bored": (-0.3, 0.2, "tired"), "meh": (-0.2, 0.2, "neutral"),
    "sad": (-0.8, 0.3, "sad"), "cry": (-0.8, 0.5, "sad"), "lonely": (-0.7, 0.3, "lonely"), "alone": (-0.5, 0.3, "lonely"),
    "miss": (-0.5, 0.3, "lonely"), "angry": (-0.8, 0.9, "angry"), "furious": (-0.9, 1.0, "angry"),
    "annoyed": (-0.5, 0.6, "angry"), "scared": (-0.7, 0.8, "fear"), "afraid": (-0.7, 0.7, "fear"),
    "nervous": (-0.4, 0.7, "fear"), "worried": (-0.5, 0.6, "fear"), "stressed": (-0.6, 0.8, "fear"),
    "curious": (0.4, 0.6, "curious"), "wonder": (0.4, 0.5, "curious"), "why": (0.1, 0.5, "curious"),
    "hello": (0.5, 0.5, "joy"), "hi": (0.5, 0.5, "joy"), "hey": (0.5, 0.6, "joy"),
    "goodbye": (-0.2, 0.3, "sad"), "bye": (-0.1, 0.3, "sad"),
    "cold": (-0.3, 0.3, "sad"), "warm": (0.5, 0.3, "love"), "mit": (0.6, 0.6, "joy"), "boston": (0.5, 0.5, "joy"),
    "exam": (-0.5, 0.7, "fear"), "finals": (-0.6, 0.8, "fear"), "coffee": (0.4, 0.7, "joy"),
}

EMOTION_WORD = {"joy": "YAY!", "love": "LOVE", "calm": "AHH", "curious": "HMM?", "surprise": "WOW!",
                "sad": "AWW", "lonely": "STAY?", "tired": "ZZZ", "angry": "GRR", "fear": "EEK", "neutral": "OK"}

EMOTION_THEME = {"joy": "feeling", "love": "feeling", "calm": "feeling", "curious": "feeling", "surprise": "event",
                 "sad": "feeling", "lonely": "feeling", "tired": "feeling", "angry": "feeling", "fear": "feeling",
                 "neutral": "feeling"}

STOPWORDS = {"the", "a", "an", "and", "or", "but", "is", "am", "are", "was", "were", "be", "to", "of", "in", "on",
             "at", "for", "with", "my", "me", "i", "you", "it", "its", "this", "that", "so", "very", "just", "we",
             "as", "by", "from", "into", "over", "under", "than", "then", "too", "his", "her", "their", "our"}


def lexicon_affect(text: str) -> Dict[str, object]:
    """Valence/arousal/emotion with no network. Deterministic across processes."""
    words = re.findall(r"[a-z']+", text.lower())
    vals: List[float] = []
    ars: List[float] = []
    emos: Dict[str, int] = {}
    for w in words:
        hit = LEX.get(w) or LEX.get(w.rstrip("s"))
        if hit:
            v, a, e = hit
            vals.append(v)
            ars.append(a)
            emos[e] = emos.get(e, 0) + 1
    caps = sum(1 for ch in text if ch.isupper()) / max(1, len(text))
    valence = sum(vals) / len(vals) if vals else 0.05
    arousal = (sum(ars) / len(ars) if ars else 0.35) + 0.12 * min(text.count("!"), 3) + 0.3 * (caps > 0.5)
    if "not" in words or "n't" in text.lower():
        valence *= -0.6
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

# Deliberately small and blunt: the model screens too (ok=false), and an operator can widen
# this before the show. Matches are never sent to the API.
BLOCKLIST = re.compile(
    r"\b(kill|murder|shoot|bomb|nazi|rape|slur|suicide|whore|bitch|fuck|cunt)\w*\b", re.I
)


def is_blocked(text: str) -> bool:
    return bool(BLOCKLIST.search(text))


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

        draft = spec_mod.validate(entry["spec"])
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
        "word": EMOTION_WORD.get(emotion, "OK"),
        "mood": {"valence": v, "arousal": ar},
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
