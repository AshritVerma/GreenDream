"""Scene spec v1 — the small vocabulary an LLM fills in, and the performer
that renders any valid spec on the 17x9 tower.

The point: the model never emits pixels. It emits a handful of fields whose
every combination is legible by construction. See SCHEMA below; validate()
coerces anything into a safe spec, so a half-broken model answer still plays.
"""

from __future__ import annotations

import math
import random
import re
from typing import Any, Dict, List, Optional

import numpy as np

from common.canvas import (CC, COLS, RR, ROWS, Canvas, Marquee, blit_mask, clamp,
                           hex_rgb, lerp, lerp_rgb)

from worlds import WORLDS

WORLD_NAMES = list(WORLDS) + ["none"]
MOTIONS = ["rise", "fall", "sweep", "pulse", "shake", "spiral", "breathe", "still"]
PARTICLES = ["rain", "snow", "sparks", "stars", "bubbles", "confetti", "none"]
FLASHES = ["lightning", "burst", "none"]
SPRITE_ANIMS = ["rise", "fall", "bounce", "pulse", "hold"]
MAX_BEATS = 4
BEAT_FLOOR = 0.3      # no beat may sit darker than this: from the street a near-black tower reads as broken
BEAT_RAMP_S = 0.8     # how long a beat takes to fade its brightness in from the previous one

# The JSON schema handed to the model as a tool definition (also documents v1).
SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean", "description": "false if the request is hateful, sexual, targets a person, or is nonsense you cannot depict"},
        "title": {"type": "string", "description": "2-4 word summary of what will be shown"},
        "duration_s": {"type": "number", "minimum": 6, "maximum": 20},
        "world": {"type": "string", "enum": WORLD_NAMES, "description": "background scene; 'none' = flat palette gradient"},
        "palette": {"type": "object", "properties": {"base": {"type": "string"}, "accent": {"type": "string"}, "glow": {"type": "string"}}, "description": "hex colours: base (dark background), accent (particles/motion), glow (flashes/sprite)"},
        "motion": {"type": "object", "properties": {"kind": {"type": "string", "enum": MOTIONS}, "speed": {"type": "number"}, "amount": {"type": "number"}}},
        "particles": {"type": "object", "properties": {"kind": {"type": "string", "enum": PARTICLES}, "density": {"type": "number"}, "direction": {"type": "string", "enum": ["down", "up"]}}},
        "tempo_bpm": {"type": "number", "minimum": 30, "maximum": 200, "description": "drives pulse/breathe/bounce"},
        "flash": {"type": "object", "properties": {"kind": {"type": "string", "enum": FLASHES}, "rate": {"type": "number"}}},
        "sprite": {"type": ["object", "null"], "properties": {"rows": {"type": "array", "items": {"type": "string"}, "description": "up to 12 strings of exactly 9 chars, '#' lit '.' dark; bold simple silhouettes only"}, "anim": {"type": "string", "enum": SPRITE_ANIMS}, "color": {"type": "string"}}},
        "word": {"type": ["string", "null"], "description": "optional reply shown as a vertical marquee; 1-7 chars, A-Z ! ? only"},
        "mood": {"type": "object", "properties": {"valence": {"type": "number"}, "arousal": {"type": "number"}}},
        "beats": {"type": "array", "maxItems": MAX_BEATS, "description":
                  "2-4 phases in time, so the scene is an event rather than a held picture: what builds, what lands, what is left. "
                  "Omit only for scenes that genuinely just sit there. A beat overrides the fields it names and inherits the rest.",
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


def _hex(v, default: str) -> str:
    return v if isinstance(v, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}", v) else default


def _num(x, lo, hi, dflt):
    try:
        return float(min(hi, max(lo, float(x))))
    except Exception:
        return dflt


def clean_word(v: Any) -> Optional[str]:
    """A displayable word or None. The only text the facade may ever show."""
    if not isinstance(v, str):
        return None
    w = re.sub(r"\s+", " ", re.sub(r"[^A-Z!? ]", "", v.upper())).strip()[:7].strip()
    return w or None


def _motion(raw: Any, base: Dict[str, Any]) -> Dict[str, Any]:
    d = raw if isinstance(raw, dict) else {}
    return {"kind": d.get("kind") if d.get("kind") in MOTIONS else base["kind"],
            "speed": _num(d.get("speed"), 0, 1, base["speed"]), "amount": _num(d.get("amount"), 0, 1, base["amount"])}


def _particles(raw: Any, base: Dict[str, Any]) -> Dict[str, Any]:
    d = raw if isinstance(raw, dict) else {}
    return {"kind": d.get("kind") if d.get("kind") in PARTICLES else base["kind"],
            "density": _num(d.get("density"), 0, 1, base["density"]),
            "direction": d.get("direction") if d.get("direction") in ("down", "up") else base["direction"]}


def _flash(raw: Any, base: Dict[str, Any]) -> Dict[str, Any]:
    d = raw if isinstance(raw, dict) else {}
    return {"kind": d.get("kind") if d.get("kind") in FLASHES else base["kind"], "rate": _num(d.get("rate"), 0, 1, base["rate"])}


def _beats(raw: Any, base: Dict[str, Any]) -> List[dict]:
    """Put the scene in time. A beat names only what changes and inherits the rest.

    Fewer than two usable beats is not a timeline, so it degrades to nothing. Beats are sorted,
    clamped into 0..1, nudged apart so two never land on one instant, and floored at BEAT_FLOOR
    so no phase of any scene leaves the tower looking switched off.
    """
    if not isinstance(raw, list):
        return []
    out = []
    for b in raw[:MAX_BEATS]:
        if not isinstance(b, dict):
            continue
        out.append({"at": _num(b.get("at"), 0, 1, 0.0),
                    "label": re.sub(r"\s+", " ", str(b.get("label", "") or ""))[:24].strip(),
                    "motion": _motion(b.get("motion"), base["motion"]),
                    "particles": _particles(b.get("particles"), base["particles"]),
                    "flash": _flash(b.get("flash"), base["flash"]),
                    "brightness": max(BEAT_FLOOR, _num(b.get("brightness"), 0, 1, 1.0)),
                    "word": clean_word(b.get("word")) if "word" in b else base["word"]})
    if len(out) < 2:
        return []
    out.sort(key=lambda b: b["at"])
    out[0]["at"] = 0.0
    for i in range(1, len(out)):
        out[i]["at"] = round(min(1.0, max(out[i]["at"], out[i - 1]["at"] + 0.05)), 3)
    return out


def validate(raw: Any) -> Dict[str, Any]:
    """Coerce anything into a safe, complete spec (never raises).

    Rebuilds from known fields only, so foreign keys (``schema_version``, ``_echo``...) are
    dropped rather than trusted. Idempotent: validate(validate(x)) == validate(x).
    """
    d = raw if isinstance(raw, dict) else {}
    pal = d.get("palette") if isinstance(d.get("palette"), dict) else {}
    sp = d.get("sprite") if isinstance(d.get("sprite"), dict) else None
    md = d.get("mood") if isinstance(d.get("mood"), dict) else {}

    spec = {
        "ok": bool(d.get("ok", True)),
        "title": str(d.get("title", "?"))[:40],
        "duration_s": _num(d.get("duration_s"), 6, 20, 12),
        "world": d.get("world") if d.get("world") in WORLD_NAMES else "none",
        "palette": {"base": _hex(pal.get("base"), "#101a2e"), "accent": _hex(pal.get("accent"), "#7cc4ff"), "glow": _hex(pal.get("glow"), "#ffffff")},
        "motion": _motion(d.get("motion"), {"kind": "breathe", "speed": 0.5, "amount": 0.5}),
        "particles": _particles(d.get("particles"), {"kind": "none", "density": 0.5, "direction": "down"}),
        "tempo_bpm": _num(d.get("tempo_bpm"), 30, 200, 70),
        "flash": _flash(d.get("flash"), {"kind": "none", "rate": 0.3}),
        "sprite": None,
        "word": clean_word(d.get("word")),
        "mood": {"valence": _num(md.get("valence"), -1, 1, 0.2), "arousal": _num(md.get("arousal"), 0, 1, 0.5)},
    }
    spec["beats"] = _beats(d.get("beats"), spec)
    if sp and isinstance(sp.get("rows"), list):
        rows = [re.sub(r"[^#.]", ".", str(r))[:COLS].ljust(COLS, ".") for r in sp["rows"][:12] if isinstance(r, str)]
        rows = [r for r in rows if len(r) == COLS]
        lit = sum(r.count("#") for r in rows)
        # legible: not a speck, not a slab (a slab has every row identical or nearly full)
        if rows and 6 <= lit <= int(0.8 * COLS * len(rows)) and len(set(rows)) >= 2:
            spec["sprite"] = {"rows": rows, "anim": sp.get("anim") if sp.get("anim") in SPRITE_ANIMS else "hold", "color": _hex(sp.get("color"), spec["palette"]["glow"])}
    if not spec["ok"]:
        return dict(SHRUG)
    return spec


# What plays when the building will not or cannot depict a phrase: a grey shake and "HMM?".
# ``ok`` is False so a consumer (the dream composer, the journal) can tell a refusal from a scene;
# validate() returns it unchanged, so it is a fixed point.
SHRUG: Dict[str, Any] = {
    "ok": False, "title": "shrug", "duration_s": 6.0, "world": "none",
    "palette": {"base": "#141821", "accent": "#5a6478", "glow": "#9aa4b8"},
    "motion": {"kind": "shake", "speed": 0.3, "amount": 0.3}, "particles": {"kind": "none", "density": 0.0, "direction": "down"},
    "tempo_bpm": 50.0, "flash": {"kind": "none", "rate": 0.0}, "sprite": None, "word": "HMM?", "mood": {"valence": 0.0, "arousal": 0.2},
    "beats": [],
}


# ---------------------------------------------------------------------------- particles

class Particles:
    def __init__(self, kind: str, density: float, direction: str, accent, glow, rng: random.Random):
        self.kind, self.density, self.dir = kind, density, direction
        self.accent, self.glow, self.rng = accent, glow, rng
        self.p: List[list] = []  # [r, c, vr, vc, life, hue]

    def update(self, dt: float, t: float, cv: Canvas) -> None:
        k = self.kind
        if k == "none":
            return
        rng = self.rng
        spawn = {"rain": 4.0, "snow": 1.6, "sparks": 2.5, "stars": 0.8, "bubbles": 1.2, "confetti": 2.2}[k] * self.density
        n_new = int(spawn) + (1 if rng.random() < spawn - int(spawn) else 0)
        up = self.dir == "up"
        for _ in range(n_new):
            c = rng.uniform(0, COLS - 1)
            if k == "rain":
                self.p.append([ROWS if up else -1.0, c, (-1 if up else 1) * rng.uniform(14, 22), 0.0, 3.0, 0])
            elif k == "snow":
                self.p.append([ROWS if up else -1.0, c, (-1 if up else 1) * rng.uniform(1.5, 3.0), 0.0, 12.0, rng.random()])
            elif k == "sparks":
                self.p.append([ROWS - 0.5 if up else rng.uniform(6, 10), c, -rng.uniform(4, 10) if up else rng.uniform(-6, 6), rng.uniform(-3, 3), rng.uniform(0.4, 1.0), 0])
            elif k == "stars":
                self.p.append([rng.uniform(0, ROWS - 1), c, 0.0, 0.0, rng.uniform(0.6, 1.6), 0])
            elif k == "bubbles":
                self.p.append([ROWS - 0.5, c, -rng.uniform(1.5, 3.5), 0.0, 8.0, rng.random()])
            elif k == "confetti":
                self.p.append([-1.0, c, rng.uniform(2.5, 5.0), rng.uniform(-1, 1), 8.0, rng.random()])
        keep = []
        for q in self.p:
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[4] -= dt
            if k == "snow" or k == "bubbles":
                q[1] += 0.5 * math.sin(t * 1.5 + q[5] * 6) * dt
            if k == "sparks":
                q[2] += 12 * dt  # gravity
            if q[4] <= 0 or q[0] < -2 or q[0] > ROWS + 1:
                continue
            keep.append(q)
            if k == "rain":
                cv.line(q[0] - 1.0, q[1], q[0], q[1], self.accent, 0.7, width=0.3, mode="max")
            elif k == "snow":
                cv.blob(q[0], q[1], 0.42, self.glow, 0.85, "max")
            elif k == "sparks":
                cv.blob(q[0], q[1], 0.4, lerp_rgb(self.glow, self.accent, 1 - q[4]), min(1.0, q[4] * 1.5), "max")
            elif k == "stars":
                cv.blob(q[0], q[1], 0.35, self.glow, math.sin(clamp(q[4] / 1.6) * math.pi), "max")
            elif k == "bubbles":
                cv.ring(q[0], q[1], 0.7, self.accent, 0.5, thickness=0.35)
            elif k == "confetti":
                from common.canvas import hsv

                cv.blob(q[0], q[1], 0.38, hsv(q[5], 0.9, 1.0), 0.9, "max")
        self.p = keep[-160:]


# ---------------------------------------------------------------------------- motion warps

def warp(px: np.ndarray, kind: str, t: float, phase: float, speed: float, amount: float) -> np.ndarray:
    """Whole-body motion applied to the composed frame (cheap nearest-neighbour resampling)."""
    if kind == "still" or amount <= 0:
        return px
    s = 0.3 + 1.7 * speed
    if kind in ("rise", "fall"):  # the whole picture scrolls, like the tower is an elevator
        shift = int((t * s * 4.0 * amount) % ROWS)
        return np.roll(px, -shift if kind == "rise" else shift, axis=0)
    dx = dy = 0.0
    scale = 1.0
    if kind == "sweep":
        dx = 3.0 * amount * math.sin(t * s * 2.0)
    elif kind == "pulse":
        scale = 1.0 + 0.35 * amount * math.exp(-6 * phase)
    elif kind == "shake":
        dx = 1.2 * amount * math.sin(t * 40 * s)
        dy = 0.5 * amount * math.sin(t * 31 * s + 1)
    elif kind == "spiral":
        dx = 2.5 * amount * math.sin(t * s * 2.5)
        dy = 1.5 * amount * math.cos(t * s * 2.5)
    elif kind == "breathe":
        scale = 1.0 + 0.25 * amount * (0.5 + 0.5 * math.sin(t * s * 1.2))
    rr = (RR - 8.0 - dy) / scale + 8.0
    cc = (CC - 4.0 - dx) / scale + 4.0
    ri = np.round(rr).astype(int)
    ci = np.round(cc).astype(int)
    inside = (ri >= 0) & (ri < ROWS) & (ci >= 0) & (ci < COLS)
    out = np.zeros_like(px)
    out[inside] = px[np.clip(ri, 0, ROWS - 1)[inside], np.clip(ci, 0, COLS - 1)[inside]]
    return out


# ---------------------------------------------------------------------------- performer

class Performance:
    """One spec being played: layers world → particles → sprite → flash → word, then motion.

    If the spec carries ``beats``, the active beat overrides motion, particles, flash,
    brightness and the word for its stretch of the scene, so a dunk is an approach, a leap
    and an impact rather than a ball with a wobble. Without beats the base fields hold.
    """

    def __init__(self, spec: Dict[str, Any], t0: float, seed: int = 0):
        self.spec = spec
        self.t0 = t0
        self.rng = random.Random(seed)
        pal = spec["palette"]
        self.base, self.accent, self.glow = hex_rgb(pal["base"]), hex_rgb(pal["accent"]), hex_rgb(pal["glow"])
        self.world_state: Dict = {}
        self.particles = Particles(spec["particles"]["kind"], spec["particles"]["density"], spec["particles"]["direction"], self.accent, self.glow, self.rng)
        self.marquee = Marquee(spec["word"], self.glow, speed=8.0) if spec["word"] else None
        self.word_shown: Optional[str] = spec["word"]
        # the picture lands first; with a sprite, the word comes at the end so they don't fight for 9 columns
        self.word_delay = 1.2 if not spec["sprite"] else max(2.5, spec["duration_s"] - 6.5)
        self.beats: List[dict] = list(spec.get("beats") or [])
        self.bright = self.beats[0]["brightness"] if self.beats else 1.0
        self.flash_t = -10.0
        self.bolt_c = 4.0
        self.done = False
        sp = spec["sprite"]
        self.sprite = None
        if sp:
            self.sprite = np.array([[1.0 if ch == "#" else 0.0 for ch in row] for row in sp["rows"]], dtype=np.float32)
            self.sprite_rgb = hex_rgb(sp["color"])
            self.sprite_anim = sp["anim"]

    @property
    def elapsed(self):
        return self._t - self.t0

    def _elapsed(self, t: float) -> float:
        """The time the scene is *showing*. Subclasses may stutter or loop it."""
        return t - self.t0

    def beat_at(self, p: float) -> Optional[dict]:
        """The beat in force at progress ``p`` (0..1), or None when the spec has no beats."""
        live = None
        for b in self.beats:
            if b["at"] <= p:
                live = b
        return live

    def render(self, t: float, dt: float) -> Canvas:
        self._t = t
        sp = self.spec
        e = self._elapsed(t)
        dur = sp["duration_s"]
        period = 60.0 / sp["tempo_bpm"]
        phase = (e % period) / period
        # --- the beat in force decides motion / particles / flash / word for this stretch
        live = self.beat_at(clamp(e / dur)) if self.beats else None
        motion = live["motion"] if live else sp["motion"]
        flash = live["flash"] if live else sp["flash"]
        if live:
            pk = live["particles"]
            self.particles.kind, self.particles.density, self.particles.dir = pk["kind"], pk["density"], pk["direction"]
            target = live["brightness"]
            self.bright += (target - self.bright) * clamp(dt / BEAT_RAMP_S * 2.5)
            if live["word"] != self.word_shown:
                self.word_shown = live["word"]
                self.marquee = Marquee(live["word"], self.glow, speed=8.0) if live["word"] else None
            show_word = self.marquee is not None
        else:
            show_word = self.marquee is not None and e > self.word_delay
        cv = Canvas()
        # --- world / base
        if sp["world"] != "none":
            cv = WORLDS[sp["world"]](t, dt, self.world_state, self.rng)
            cv.px *= np.array([0.7, 0.7, 0.7], dtype=np.float32) + 0.3 * np.array(self.accent, dtype=np.float32)  # tint toward the accent
        else:
            cv.vgradient(lerp_rgb(self.base, self.accent, 0.25), self.base)
            # a slow living texture so 'none' never reads as a dead fill
            cv.px *= (0.85 + 0.15 * np.sin(e * 1.5 + RR / 4.0)).astype(np.float32)[..., None]
        # --- particles
        self.particles.update(dt, t, cv)
        # --- sprite
        if self.sprite is not None:
            h = self.sprite.shape[0]
            anim = self.sprite_anim
            centre = (ROWS - h) // 2
            if anim == "rise":
                r = int(round(lerp(ROWS, -h, clamp(e / max(dur - 1.0, 1.0)))))
            elif anim == "fall":
                r = int(round(lerp(-h, ROWS, clamp(e / max(dur - 1.0, 1.0)))))
            elif anim == "bounce":
                r = int(round(centre + 3.5 * abs(math.sin(e * math.pi / period))))
            else:
                r = centre
            k = 1.0
            if anim == "pulse":
                k = 0.55 + 0.45 * math.exp(-5 * phase)
            if show_word:
                k *= 0.3  # step back while the word scrolls
            blit_mask(cv, self.sprite, r, 0, self.sprite_rgb, k, "max")
            if anim == "rise":  # exhaust under a rising sprite
                cv.blob(r + h + 0.5, 4.0, 1.3, self.accent, 0.8 * (0.6 + 0.4 * math.sin(e * 25)), "add")
        # --- flash
        fk, fr = flash["kind"], flash["rate"]
        if fk != "none":
            if e < 0.25 or (self.rng.random() < dt * (0.15 + 1.2 * fr) and t - self.flash_t > 1.5 and e < dur - 1):
                if t - self.flash_t > 1.5:
                    self.flash_t = t
                    self.bolt_c = self.rng.uniform(1, 7)
            age = t - self.flash_t
            if age < 0.3:
                k = 1 - age / 0.3
                if fk == "lightning":
                    cv.px += 0.45 * k * (0.5 + 0.5 * math.sin(t * 80))
                    for r in range(0, ROWS - 1, 2):
                        cv.line(r, self.bolt_c + math.sin(r * 1.7) * 0.8, r + 2, self.bolt_c + math.sin((r + 2) * 1.7) * 0.8, self.glow, k, width=0.35, mode="max")
                else:  # burst
                    cv.px += 0.35 * k
                    cv.ring(8.0, 4.0, 0.5 + age * 26.0, self.glow, k, thickness=0.9)
        # --- motion
        cv.px = warp(cv.px, motion["kind"], e, phase, motion["speed"], motion["amount"])
        # --- beat brightness (the earned bright moment; floored by validate so it never reads as off)
        if live:
            cv.px *= self.bright
        # --- word (after a short delay so the picture lands first, or when the beat says so)
        if show_word and self.marquee:
            self.marquee.update(dt)
            cv.px *= 0.65
            self.marquee.draw(cv, 1.0)
            if self.marquee.done:
                self.marquee = None
        cv.clip()
        if e >= dur:
            self.done = True
        return cv
