"""The dream engine: the day's prompts -> a dream script -> dream scenes.

A DreamScript is an arc of acts (opening, rising, turn, climax, resolution,
coda). Each act holds scenes that reuse the day's specs with DREAM OPS applied:
slow, recolor, merge (two sprites cross-fade), echo (a sprite repeats in a
column), fragment (a sprite dissolves into sparks), invert (rise<->fall),
storm-of (particles become tiny copies of the sprite), loop.

Two composers produce the same script shape:
  compose_offline(day)   deterministic, always available
  compose_claude(day)    Claude tool-use; falls back to offline on any failure

Rendering: DreamPlayer wraps Performance with a dream filter (indigo shift,
desaturation, slow breathing modulation, REM flutters) and the ops.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import threading
import urllib.request
from typing import Any, Dict, List, Optional

import numpy as np

from common.canvas import COLS, ROWS, Canvas, Marquee, blit_mask, clamp, hex_rgb, lerp
from common.inputs import BUS, InputBus

from scene import Performance, validate
from worlds import mix

DREAM_OPS = ["slow", "recolor", "merge", "echo", "fragment", "invert", "storm-of", "loop", "none"]
ACTS = ["opening", "rising", "turn", "climax", "resolution", "coda"]

DREAM_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "a 1-2 word dream title, uppercase, <= 7 letters, e.g. 'STORM', 'ASCENT'"},
        "logline": {"type": "string", "description": "one sentence: what this dream is about, written like a dream diary"},
        "acts": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string", "enum": ACTS},
            "scenes": {"type": "array", "items": {"type": "object", "properties": {
                "sources": {"type": "array", "items": {"type": "integer"}, "description": "ids of the day's prompts this scene reuses (1 or 2)"},
                "op": {"type": "string", "enum": DREAM_OPS},
                "duration_s": {"type": "number", "minimum": 6, "maximum": 25},
                "transition": {"type": "string", "enum": ["dissolve", "iris", "elevator", "blinds", "slide", "flash", "warp"]},
                "note": {"type": "string", "description": "what happens in the dream here (for the journal)"},
            }, "required": ["sources", "op", "duration_s", "transition"]}},
        }, "required": ["name", "scenes"]}},
    },
    "required": ["title", "logline", "acts"],
}

DREAM_SYSTEM = """You are the dreaming mind of a 21-storey building whose 153 windows are lights.
All day, people told the building what they wanted to see (a list of prompts with the time of day and a mood).
Tonight it dreams: write a dream that connects those prompts into one arc — opening, rising, turn, climax,
resolution, coda — the way dreams do: things recur, merge, grow, dissolve, and the last image echoes the first.
Rules: reuse the day's prompts by id (1 or 2 per scene). Prefer the ones that recurred or were vivid.
Each prompt names the channel it arrived on. Prompts said at the building (pedestal, plaza, qr, speech) were
witnessed in person: open and close the dream with them. Remote prompts (web, phone, sms) fill the middle.
Dream ops: slow (gentle), recolor (dream palette), merge (two prompts become one thing), echo (it repeats),
fragment (it dissolves into sparks), invert (it falls instead of rises), storm-of (it rains tiny copies), loop.
Keep 6-10 scenes, total 2-4 minutes. Title: one word, uppercase, at most 7 letters. Be poetic but concrete.
Answer only by calling the tool."""

ONSITE = ("pedestal", "onsite", "qr", "plaza", "speech")


# ---------------------------------------------------------------------------- composers

def compose_offline(day: List[dict], seed: int = 0, cycle: int = 1) -> Dict[str, Any]:
    """A deterministic arc: first thing → energetic middle → contrasting turn → merge climax → calm → echo.

    Presence is the price of immediacy: if anything was said at the building itself, the dream
    opens with the first of those and closes on the last; remote prompts fill the middle.
    """
    rng = random.Random(seed + cycle)
    n = len(day)
    if n == 0:
        return {"title": "QUIET", "logline": "Nobody spoke to the building today; it dreams of the sky.", "acts": [
            {"name": "opening", "scenes": [{"sources": [], "op": "slow", "duration_s": 20, "transition": "dissolve", "note": "an empty sky"}]}]}
    by_arousal = sorted(range(n), key=lambda i: -day[i]["spec"]["mood"]["arousal"])
    by_valence = sorted(range(n), key=lambda i: day[i]["spec"]["mood"]["valence"])
    counts: Dict[str, int] = {}
    for d in day:
        counts[d["spec"]["title"]] = counts.get(d["spec"]["title"], 0) + 1
    popular = sorted(range(n), key=lambda i: -counts[day[i]["spec"]["title"]])
    onsite = [i for i in range(n) if day[i].get("channel") in ONSITE]
    first = onsite[0] if onsite else 0
    last = onsite[-1] if onsite else first
    acts = [
        {"name": "opening", "scenes": [{"sources": [first], "op": "slow", "duration_s": 14, "transition": "dissolve", "note": f"the day begins again with {day[first]['text']}"}]},
        {"name": "rising", "scenes": [{"sources": [i], "op": rng.choice(["echo", "loop", "recolor"]), "duration_s": 10, "transition": "elevator", "note": f"{day[i]['text']} returns"} for i in by_arousal[:2]]},
        {"name": "turn", "scenes": [{"sources": [by_valence[0]], "op": "invert", "duration_s": 12, "transition": "blinds", "note": f"{day[by_valence[0]]['text']}, upside down"}]},
        {"name": "climax", "scenes": [{"sources": popular[:2] if n > 1 else [popular[0]], "op": "merge" if n > 1 else "storm-of", "duration_s": 16, "transition": "warp", "note": "two things become one thing"}]},
        {"name": "resolution", "scenes": [{"sources": [by_arousal[-1]], "op": "slow", "duration_s": 14, "transition": "iris", "note": f"{day[by_arousal[-1]]['text']}, slowly"}]},
        {"name": "coda", "scenes": [{"sources": [last], "op": "fragment", "duration_s": 12, "transition": "dissolve", "note": f"{day[last]['text']} dissolves" if last != first else "the first thing dissolves"}]},
    ]
    title = re.sub(r"[^A-Z]", "", day[popular[0]]["spec"]["title"].upper().split()[0] if day[popular[0]]["spec"]["title"] else "DREAM")[:7] or "DREAM"
    star = day[popular[0]]["text"] if popular[0] != first else (day[by_arousal[0]]["text"] if by_arousal[0] != first else None)
    logline = f"Dream {cycle}: {day[first]['text']} came back" + (f", then {star} took over everything." if star else ", and everything else drifted through it.")
    return {"title": title, "logline": logline, "acts": acts}


def compose_claude(day: List[dict], cycle: int = 1, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not day:
        return None
    model = os.environ.get("ANTHROPIC_MODEL_DREAM", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"))
    listing = "\n".join(f"{i}: [{d.get('when', '?')} via {d.get('channel', 'web')}] \"{d['text']}\" (mood v={d['spec']['mood']['valence']:+.1f} a={d['spec']['mood']['arousal']:.1f}, shown as: {d['spec']['title']})" for i, d in enumerate(day))
    body = {"model": model, "max_tokens": 1500, "system": DREAM_SYSTEM,
            "tools": [{"name": "dream", "description": "Write tonight's dream", "input_schema": DREAM_SCHEMA}], "tool_choice": {"type": "tool", "name": "dream"},
            "messages": [{"role": "user", "content": f"Dream cycle {cycle} of the night. Today's prompts:\n{listing}"}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        for part in data.get("content", []):
            if part.get("type") == "tool_use":
                return part.get("input")
    except Exception as e:
        print(f"[dream] API failed ({e}); composing offline", flush=True)
    return None


def validate_script(raw: Any, n_sources: int) -> Dict[str, Any]:
    d = raw if isinstance(raw, dict) else {}
    title = re.sub(r"[^A-Z]", "", str(d.get("title", "DREAM")).upper())[:7] or "DREAM"
    acts = []
    for a in d.get("acts", []) if isinstance(d.get("acts"), list) else []:
        if not isinstance(a, dict):
            continue
        scenes = []
        for s in a.get("scenes", []) if isinstance(a.get("scenes"), list) else []:
            if not isinstance(s, dict):
                continue
            src = [int(i) for i in s.get("sources", []) if isinstance(i, (int, float)) and 0 <= int(i) < n_sources][:2]
            scenes.append({"sources": src, "op": s.get("op") if s.get("op") in DREAM_OPS else "slow",
                           "duration_s": float(min(25, max(6, float(s.get("duration_s", 12) or 12)))),
                           "transition": s.get("transition") if s.get("transition") in ("dissolve", "iris", "elevator", "blinds", "slide", "flash", "warp") else "dissolve",
                           "note": str(s.get("note", ""))[:140]})
        if scenes:
            acts.append({"name": a.get("name") if a.get("name") in ACTS else "rising", "scenes": scenes})
    if not acts:
        return None
    return {"title": title, "logline": str(d.get("logline", ""))[:240], "acts": acts}


def compose_async(day: List[dict], cycle: int, bus: InputBus = BUS, offline: bool = False, seed: int = 0) -> None:
    def go():
        script = None
        tier = "offline"
        if not offline:
            raw = compose_claude(day, cycle)
            script = validate_script(raw, len(day)) if raw else None
            if script:
                tier = "claude"
        if script is None:
            # the offline composer is trusted, but it goes through the same gate so the two paths cannot drift
            script = validate_script(compose_offline(day, seed, cycle), len(day)) or compose_offline([], seed, cycle)
        bus.push({"type": "dream_script", "script": script, "tier": tier, "cycle": cycle})

    threading.Thread(target=go, daemon=True).start()


# ---------------------------------------------------------------------------- dream rendering

DREAM_BASE = "#0b0a24"
DREAM_ACCENTS = ["#7c6cff", "#4fd1ff", "#ff9fd6", "#9dffb3", "#ffd28a"]
LOOP_S = 3.0   # how often a 'loop' scene restarts itself


def dream_spec(spec: dict, op: str, rng: random.Random, partner: Optional[dict] = None) -> dict:
    """Apply a dream op to a copy of a day spec."""
    s = json.loads(json.dumps(spec))
    s["palette"] = {"base": DREAM_BASE, "accent": rng.choice(DREAM_ACCENTS), "glow": "#e8e4ff"}
    s["word"] = None
    for b in s.get("beats") or []:   # dreams are wordless; the choreography stays
        b["word"] = None
    s["tempo_bpm"] = max(30, s["tempo_bpm"] * 0.6)
    s["motion"] = dict(s["motion"], speed=s["motion"]["speed"] * 0.6)
    if op == "slow":
        s["tempo_bpm"] = max(30, s["tempo_bpm"] * 0.7)
        s["particles"]["density"] *= 0.6
    elif op == "recolor":
        s["palette"]["accent"] = rng.choice(DREAM_ACCENTS)
        if s["sprite"]:
            s["sprite"]["color"] = rng.choice(DREAM_ACCENTS)
    elif op == "echo":
        s["_echo"] = True
    elif op == "fragment":
        s["_fragment"] = True
        s["particles"] = {"kind": "sparks", "density": 0.5, "direction": "up"}
    elif op == "invert":
        if s["sprite"]:
            s["sprite"]["anim"] = {"rise": "fall", "fall": "rise"}.get(s["sprite"]["anim"], "fall")
        s["motion"]["kind"] = {"rise": "fall", "fall": "rise"}.get(s["motion"]["kind"], s["motion"]["kind"])
        s["particles"]["direction"] = "up" if s["particles"]["direction"] == "down" else "down"
    elif op == "storm-of":
        s["_storm_of"] = True
    elif op == "merge" and partner and partner.get("sprite") and s.get("sprite"):
        s["_merge"] = partner["sprite"]
        s["world"] = partner["world"] if s["world"] == "none" else s["world"]
    elif op == "merge" and partner:
        # no two sprites: borrow the partner's world/particles instead
        s["world"] = partner["world"] if partner["world"] != "none" else s["world"]
        s["particles"] = partner["particles"] if partner["particles"]["kind"] != "none" else s["particles"]
    elif op == "loop":
        s["_loop"] = True
    return s


class DreamScene(Performance):
    """A Performance with dream ops rendered on top."""

    def __init__(self, spec: dict, t0: float, seed: int = 0):
        super().__init__(validate(spec), t0, seed)
        self.ops = {k: spec[k] for k in ("_echo", "_fragment", "_storm_of", "_merge", "_loop") if k in spec}
        self.merge_mask = None
        if "_merge" in self.ops:
            m = self.ops["_merge"]
            self.merge_mask = np.array([[1.0 if ch == "#" else 0.0 for ch in row] for row in m["rows"]], dtype=np.float32)
            self.merge_rgb = hex_rgb(m["color"])
        self.frag: list = []

    def _elapsed(self, t: float) -> float:
        # 'loop': the picture keeps restarting its own motion, the stutter dreams have.
        # The scene as a whole still ends on time — render() owns `done` in that case.
        e = t - self.t0
        return e % LOOP_S if "_loop" in self.ops else e

    def render(self, t: float, dt: float) -> Canvas:
        e = t - self.t0
        cv = super().render(t, dt)
        sp = self.spec
        if "_merge" in self.ops and self.sprite is not None and self.merge_mask is not None:
            # cross-fade between the two silhouettes every ~2 s: they become one thing
            k = 0.5 + 0.5 * math.sin(e * math.pi / 2.0)
            h = self.merge_mask.shape[0]
            r = (ROWS - h) // 2
            blit_mask(cv, self.merge_mask, r, 0, self.merge_rgb, k, "max")
            # dim the original in counter-phase (it was drawn at full by the parent)
            cv.px *= (0.6 + 0.4 * (1 - k))
        if "_echo" in self.ops and self.sprite is not None:
            h = self.sprite.shape[0]
            small = self.sprite[::2, ::2] if h > 4 else self.sprite   # a half-size echo
            for j, rr in enumerate((1, ROWS - small.shape[0] - 1)):
                k = 0.35 + 0.3 * math.sin(e * 1.5 + j * 2)
                blit_mask(cv, small, rr, 0 if j == 0 else COLS - small.shape[1], self.sprite_rgb, k, "max")
        if "_fragment" in self.ops and self.sprite is not None:
            # the sprite's own pixels peel off as sparks, more over time
            if self.rng.random() < dt * (2 + 6 * clamp(e / sp["duration_s"])):
                ys, xs = np.nonzero(self.sprite)
                if len(ys):
                    i = self.rng.randrange(len(ys))
                    self.frag.append([float(ys[i] + (ROWS - self.sprite.shape[0]) // 2), float(xs[i]), -self.rng.uniform(2, 6), self.rng.uniform(-2, 2), 1.2])
            keep = []
            for f in self.frag:
                f[0] += f[2] * dt
                f[1] += f[3] * dt
                f[4] -= dt
                if f[4] > 0:
                    keep.append(f)
                    cv.blob(f[0], f[1], 0.4, self.sprite_rgb, f[4], "max")
            self.frag = keep[-80:]
            cv.px *= (1 - 0.7 * clamp(e / sp["duration_s"]))  # the original fades away
        if "_storm_of" in self.ops and self.sprite is not None:
            # tiny copies (3x3 downsample) rain through the tower
            tiny = self.sprite[::4, ::4] if self.sprite.shape[0] >= 8 else self.sprite[::2, ::2]
            for j in range(3):
                r = int((e * (3 + j) + j * 7) % (ROWS + 6)) - 3
                blit_mask(cv, tiny, r, (j * 3) % COLS, self.sprite_rgb, 0.7, "max")
        if "_loop" in self.ops and e >= sp["duration_s"]:
            self.done = True   # the looped clock never reaches duration_s on its own
        return cv


class DreamPlayer:
    """Plays a DreamScript: scenes in order with transitions, under the dream filter."""

    def __init__(self, script: Dict[str, Any], day: List[dict], t0: float, seed: int = 0):
        self.script = script
        self.day = day
        self.rng = random.Random(seed)
        self.items: List[dict] = []
        for act in script["acts"]:
            for sc in act["scenes"]:
                self.items.append(dict(sc, act=act["name"]))
        self.idx = -1
        self.cur: Optional[DreamScene] = None
        self.prev_canvas: Optional[Canvas] = None
        self.trans_t0 = t0
        self.trans_kind = "dissolve"
        self.t0 = t0
        self.title = Marquee(script["title"], (0.75, 0.7, 1.0), speed=5.0)
        self.done = False
        self._advance(t0)

    def _spec_for(self, item: dict) -> dict:
        src = item["sources"]
        if not src:
            base = {"title": "sky", "world": "aurora", "duration_s": item["duration_s"], "motion": {"kind": "breathe"}, "particles": {"kind": "stars", "density": 0.3}, "flash": {"kind": "none"}, "sprite": None, "word": None}
            base = validate(base)
        else:
            base = self.day[src[0]]["spec"]
        partner = self.day[src[1]]["spec"] if len(src) > 1 else None
        s = dream_spec(base, item["op"], self.rng, partner)
        s["duration_s"] = item["duration_s"]
        return s

    def _advance(self, t: float):
        self.idx += 1
        if self.idx >= len(self.items):
            self.done = True
            return
        item = self.items[self.idx]
        if self.cur is not None:
            self.prev_canvas = self.cur.render(t, 1 / 30)
        self.trans_t0 = t
        self.trans_kind = item["transition"]
        self.cur = DreamScene(self._spec_for(item), t, self.rng.randrange(1 << 30))

    @property
    def current(self) -> Optional[dict]:
        return self.items[self.idx] if 0 <= self.idx < len(self.items) else None

    def render(self, t: float, dt: float, depth: float = 1.0) -> Canvas:
        """depth 0..1: how deep the sleep is (dims and slows the dream)."""
        if self.cur is None or self.done:
            return Canvas()
        if self.cur.done:
            self._advance(t)
            if self.done:
                return Canvas()
        out = self.cur.render(t, dt)
        p = (t - self.trans_t0) / 1.6
        if self.prev_canvas is not None and p < 1.0:
            out = mix(self.prev_canvas, out, self.trans_kind, p, self.rng)
        # dream filter: indigo shift + desaturation + breath + REM flutter
        lum = out.px.mean(axis=2, keepdims=True)
        out.px = out.px * 0.7 + lum * np.array([0.35, 0.3, 0.7], dtype=np.float32) * 0.6   # an indigo cast, but the thing stays recognisable
        breath = 0.85 + 0.15 * math.sin(t * 2 * math.pi / 8.0)
        flutter = 1.0 + 0.08 * math.sin(t * 37.0) * (1.0 if self.rng.random() < 0.15 else 0.0)
        out.px *= (0.55 + 0.35 * (1 - depth * 0.5)) * breath * flutter
        if t - self.t0 < 6.0:  # the dream's title climbs once at the start
            self.title.update(dt)
            self.title.draw(out, 0.8)
        out.clip()
        return out
