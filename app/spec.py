"""Scene spec v1 — the draft this service produces and the renderer will later consume.

Mirrors GreenDream's `scene.SCHEMA` / `scene.validate()` so a draft produced here drops
into the facade runtime unchanged. Nothing is rendered on this side; `validate()` only
guarantees the draft is safe and complete, so a half-broken model answer is still usable.

Two rules that outlive the schema:
  - no raw user text ever becomes a displayable field; `word` is 1-7 chars of A-Z ! ? only
  - every draft carries `schema_version`, so the renderer can reject drift

`beats` is an additive extension, deliberately not in `required` and not a version bump: the
base fields still describe the whole scene on their own, so GreenDream's current renderer keeps
working and simply plays a held picture. A renderer that does read `beats` gets the same scene as
an event in time — what builds, what lands, what is left.
"""

from __future__ import annotations

import re
from typing import Any, Dict

SCHEMA_VERSION = "spec-v1"
COLS = 9  # the tower is 9 windows wide; sprite rows are exactly this long
ROWS = 17  # and 17 tall, 153 windows in all
MAX_BEATS = 4

WORLDS = ["ocean", "forest", "aurora", "hyperspace", "sunrise", "storm", "snow", "lava", "city"]
WORLD_NAMES = WORLDS + ["none"]
MOTIONS = ["rise", "fall", "sweep", "pulse", "shake", "spiral", "breathe", "still"]
PARTICLES = ["rain", "snow", "sparks", "stars", "bubbles", "confetti", "none"]
FLASHES = ["lightning", "burst", "none"]
SPRITE_ANIMS = ["rise", "fall", "bounce", "pulse", "hold"]

SPEC_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean", "description": "false if the phrase is hateful, sexual, targets a private person, or cannot be depicted"},
        "title": {"type": "string", "description": "2-4 word summary of what would be shown"},
        "duration_s": {"type": "number", "minimum": 6, "maximum": 20},
        "world": {"type": "string", "enum": WORLD_NAMES, "description": "background scene; 'none' = flat palette gradient"},
        "palette": {"type": "object", "properties": {"base": {"type": "string"}, "accent": {"type": "string"}, "glow": {"type": "string"}},
                    "description": "hex colours: base (dark background), accent (particles/motion), glow (flashes/sprite)"},
        "motion": {"type": "object", "properties": {"kind": {"type": "string", "enum": MOTIONS}, "speed": {"type": "number"}, "amount": {"type": "number"}}},
        "particles": {"type": "object", "properties": {"kind": {"type": "string", "enum": PARTICLES}, "density": {"type": "number"}, "direction": {"type": "string", "enum": ["down", "up"]}}},
        "tempo_bpm": {"type": "number", "minimum": 30, "maximum": 200, "description": "drives pulse/breathe/bounce"},
        "flash": {"type": "object", "properties": {"kind": {"type": "string", "enum": FLASHES}, "rate": {"type": "number"}}},
        "sprite": {"type": ["object", "null"], "properties": {
            "rows": {"type": "array", "items": {"type": "string"}, "description": "up to 12 strings of exactly 9 chars, '#' lit '.' dark; bold simple silhouettes only"},
            "anim": {"type": "string", "enum": SPRITE_ANIMS}, "color": {"type": "string"}}},
        "word": {"type": ["string", "null"], "description": "optional reply shown as a vertical marquee; 1-7 chars, A-Z ! ? only"},
        "mood": {"type": "object", "properties": {"valence": {"type": "number"}, "arousal": {"type": "number"}}},
        "beats": {"type": "array", "maxItems": MAX_BEATS, "description":
                  "2-4 phases in time, so the scene is an event rather than a held picture: what "
                  "builds, what lands, what is left. Omit only for scenes that genuinely just sit "
                  "there. A beat overrides the fields it names and inherits the rest.",
                  "items": {"type": "object", "properties": {
                      "at": {"type": "number", "minimum": 0, "maximum": 1, "description": "start, as a fraction of duration_s"},
                      "label": {"type": "string", "description": "2-3 words: 'the leap', 'impact', 'settling'"},
                      "motion": {"type": "object"}, "particles": {"type": "object"}, "flash": {"type": "object"},
                      "brightness": {"type": "number", "minimum": 0, "maximum": 1},
                      "word": {"type": ["string", "null"], "description": "null to stay silent until the beat that earns the word"},
                  }}},
    },
    "required": ["ok", "title", "world", "motion", "particles", "flash", "sprite", "word"],
}


def hex_or(v: Any, default: str) -> str:
    """A #rrggbb colour or the default. Colours are the one field a typo makes invisible."""
    if isinstance(v, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}", v):
        return v if v.startswith("#") else "#" + v
    return default


def _num(x: Any, lo: float, hi: float, default: float) -> float:
    try:
        return float(min(hi, max(lo, float(x))))
    except (TypeError, ValueError):
        return default


def clean_word(v: Any) -> Any:
    """A displayable word or None. Never returns raw user text."""
    if not isinstance(v, str):
        return None
    w = re.sub(r"\s+", " ", re.sub(r"[^A-Z!? ]", "", v.upper()))[:7].strip()
    return w or None


def _motion(raw: Any, base: Dict[str, Any]) -> Dict[str, Any]:
    d = raw if isinstance(raw, dict) else {}
    return {"kind": d.get("kind") if d.get("kind") in MOTIONS else base["kind"],
            "speed": _num(d.get("speed"), 0, 1, base["speed"]),
            "amount": _num(d.get("amount"), 0, 1, base["amount"])}


def _particles(raw: Any, base: Dict[str, Any]) -> Dict[str, Any]:
    d = raw if isinstance(raw, dict) else {}
    return {"kind": d.get("kind") if d.get("kind") in PARTICLES else base["kind"],
            "density": _num(d.get("density"), 0, 1, base["density"]),
            "direction": d.get("direction") if d.get("direction") in ("down", "up") else base["direction"]}


def _flash(raw: Any, base: Dict[str, Any]) -> Dict[str, Any]:
    d = raw if isinstance(raw, dict) else {}
    return {"kind": d.get("kind") if d.get("kind") in FLASHES else base["kind"],
            "rate": _num(d.get("rate"), 0, 1, base["rate"])}


def _beats(raw: Any, base: Dict[str, Any]) -> list:
    """Put the scene in time. Additive: a renderer that ignores this plays the base fields.

    A beat names only what changes and inherits the rest from the scene, so the model can say
    "then it goes white and shakes" without restating the palette. Fewer than two usable beats
    is not a timeline, so it degrades to nothing rather than to a single pointless phase.
    """
    if not isinstance(raw, list):
        return []
    out = []
    for b in raw[:MAX_BEATS]:
        if not isinstance(b, dict):
            continue
        beat = {
            "at": _num(b.get("at"), 0, 1, 0.0),
            "label": re.sub(r"\s+", " ", str(b.get("label", "") or ""))[:24].strip(),
            "motion": _motion(b.get("motion"), base["motion"]),
            "particles": _particles(b.get("particles"), base["particles"]),
            "flash": _flash(b.get("flash"), base["flash"]),
            "brightness": _num(b.get("brightness"), 0, 1, 1.0),
            "word": clean_word(b.get("word")) if "word" in b else base["word"],
        }
        out.append(beat)
    if len(out) < 2:
        return []
    out.sort(key=lambda b: b["at"])
    out[0]["at"] = 0.0
    for i in range(1, len(out)):  # strictly increasing, or two beats land on the same instant
        out[i]["at"] = round(min(1.0, max(out[i]["at"], out[i - 1]["at"] + 0.05)), 3)
    return out


def validate(raw: Any) -> Dict[str, Any]:
    """Coerce anything into a safe, complete spec draft. Never raises."""
    d = raw if isinstance(raw, dict) else {}
    pal = d.get("palette") if isinstance(d.get("palette"), dict) else {}
    mo = d.get("motion") if isinstance(d.get("motion"), dict) else {}
    pa = d.get("particles") if isinstance(d.get("particles"), dict) else {}
    fl = d.get("flash") if isinstance(d.get("flash"), dict) else {}
    sp = d.get("sprite") if isinstance(d.get("sprite"), dict) else None
    md = d.get("mood") if isinstance(d.get("mood"), dict) else {}

    spec: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": bool(d.get("ok", True)),
        "title": str(d.get("title", "?"))[:40],
        "duration_s": _num(d.get("duration_s"), 6, 20, 12),
        "world": d.get("world") if d.get("world") in WORLD_NAMES else "none",
        "palette": {"base": hex_or(pal.get("base"), "#101a2e"), "accent": hex_or(pal.get("accent"), "#7cc4ff"), "glow": hex_or(pal.get("glow"), "#ffffff")},
        "motion": _motion(mo, {"kind": "breathe", "speed": 0.5, "amount": 0.5}),
        "particles": _particles(pa, {"kind": "none", "density": 0.5, "direction": "down"}),
        "tempo_bpm": _num(d.get("tempo_bpm"), 30, 200, 70),
        "flash": _flash(fl, {"kind": "none", "rate": 0.3}),
        "sprite": None,
        "word": clean_word(d.get("word")),
        "mood": {"valence": _num(md.get("valence"), -1, 1, 0.2), "arousal": _num(md.get("arousal"), 0, 1, 0.5)},
    }
    spec["beats"] = _beats(d.get("beats"), spec)
    if sp and isinstance(sp.get("rows"), list):
        rows = [re.sub(r"[^#.]", ".", str(r))[:COLS].ljust(COLS, ".") for r in sp["rows"][:12] if isinstance(r, str)]
        lit = sum(r.count("#") for r in rows)
        # legible at 153 windows: not a speck, not a slab, and it has to have some shape
        if rows and 6 <= lit <= int(0.8 * COLS * len(rows)) and len(set(rows)) >= 2:
            spec["sprite"] = {"rows": rows,
                              "anim": sp.get("anim") if sp.get("anim") in SPRITE_ANIMS else "hold",
                              "color": hex_or(sp.get("color"), spec["palette"]["glow"])}
    if not spec["ok"]:
        return shrug()
    return spec


def shrug() -> Dict[str, Any]:
    """What plays when we will not or cannot depict a phrase: a grey shake and 'HMM?'."""
    return {
        "schema_version": SCHEMA_VERSION, "ok": False, "title": "shrug", "duration_s": 6.0, "world": "none",
        "palette": {"base": "#141821", "accent": "#5a6478", "glow": "#9aa4b8"},
        "motion": {"kind": "shake", "speed": 0.3, "amount": 0.3},
        "particles": {"kind": "none", "density": 0.0, "direction": "down"},
        "tempo_bpm": 50.0, "flash": {"kind": "none", "rate": 0.0}, "sprite": None, "word": "HMM?",
        "mood": {"valence": 0.0, "arousal": 0.2}, "beats": [],
    }
