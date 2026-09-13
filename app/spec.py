"""Scene spec v1 — the draft this service produces and the renderer will later consume.

Mirrors GreenDream's `scene.SCHEMA` / `scene.validate()` so a draft produced here drops
into the facade runtime unchanged. Nothing is rendered on this side; `validate()` only
guarantees the draft is safe and complete, so a half-broken model answer is still usable.

Two rules that outlive the schema:
  - no raw user text ever becomes a displayable field; `word` is 1-7 chars of A-Z ! ? only
  - every draft carries `schema_version`, so the renderer can reject drift
"""

from __future__ import annotations

import re
from typing import Any, Dict

SCHEMA_VERSION = "spec-v1"
COLS = 9  # the tower is 9 windows wide; sprite rows are exactly this long

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
        "motion": {"kind": mo.get("kind") if mo.get("kind") in MOTIONS else "breathe",
                   "speed": _num(mo.get("speed"), 0, 1, 0.5), "amount": _num(mo.get("amount"), 0, 1, 0.5)},
        "particles": {"kind": pa.get("kind") if pa.get("kind") in PARTICLES else "none",
                      "density": _num(pa.get("density"), 0, 1, 0.5),
                      "direction": pa.get("direction") if pa.get("direction") in ("down", "up") else "down"},
        "tempo_bpm": _num(d.get("tempo_bpm"), 30, 200, 70),
        "flash": {"kind": fl.get("kind") if fl.get("kind") in FLASHES else "none", "rate": _num(fl.get("rate"), 0, 1, 0.3)},
        "sprite": None,
        "word": clean_word(d.get("word")),
        "mood": {"valence": _num(md.get("valence"), -1, 1, 0.2), "arousal": _num(md.get("arousal"), 0, 1, 0.5)},
    }
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
        "mood": {"valence": 0.0, "arousal": 0.2},
    }
