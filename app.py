"""GREENDREAM — by day the building becomes what people tell it; at night it dreams the day back.

Phases (from real sunrise/sunset for MIT, or an accelerated clock for demos):
  DAWN   the building wakes: light floods up from the base, a stretch, two blinks, GOOD MORNING
  DAY    awake: prompts (Say It engine) are performed live; between them it breathes, looks
         around and has short daydreams of what it was told earlier
  DUSK   falling asleep: eyelids close from the top, breathing slows, colours cool, a last yawn
  NIGHT  dreaming: the day's prompts are composed into a dream script (Claude or the offline
         composer) and played in cycles — descent, dream, surfacing, deep sleep — each cycle a
         new dream; late prompts are absorbed as sleep-talk and woven into the next dream
Everything is logged to a journal (prompts + dream scripts) served at /journal.

Across all four phases sits FREEZE, the operator's kill switch: one flag that replaces the
whole render with a standby field on the next frame, whatever the building was doing. See
``_render_frozen`` and ``_set_freeze``.
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from collections import deque
from datetime import datetime

import numpy as np

from common.canvas import COLS, RR, ROWS, Canvas, Marquee, breath, clamp, hex_rgb, lerp, lerp_rgb
from common.engine import App, Context
from common.inputs import Timeline
from sensors.weather import WeatherSensor

from dream import DreamPlayer, compose_async
from freeze import FREEZE_FILE, FreezeWatcher, install_signal_toggle
from genie import clip_words, request_async
from pages import JOURNAL_PAGE, SAY_PAGE
from scene import Performance, validate
from worlds import mix

HOLD = 5.0
QUEUE_MAX = 5
ONSITE = ("pedestal", "onsite", "qr", "plaza", "speech")   # channels whose prompts perform live by default

# Standby, the frozen facade. Amber because it is nobody's scene palette and it is the
# colour every other held machine in the world uses; dim because calm; flat because a
# 153-window grid is never uniform by accident. Numbers in _render_frozen's docstring.
FREEZE_RGB = (1.0, 0.58, 0.16)
FREEZE_LEVEL = 0.10        # the floor of the swell
FREEZE_SWELL = 0.05        # ...and how far above it the breath goes
FREEZE_BREATH_S = 9.0      # slower than the night's 8 s breath, so the two do not read alike
THAW_S = 1.2               # coming back is a fade; going in is not (see _set_freeze)


def _hour_of(iso: str, default: float) -> float:
    try:
        d = datetime.fromisoformat(iso)
        return d.hour + d.minute / 60.0
    except Exception:
        return default


def _shown(spec: dict) -> dict:
    """What the building actually made of a prompt, for the journal and /api/journal.

    `word` is the only text the facade ever displays, so a log that omits it cannot answer
    the one question an operator gets asked: what did it say?
    """
    return {"title": spec["title"], "ok": spec["ok"], "world": spec["world"], "word": spec["word"]}


class GreenDream(App):
    name = "greendream"
    title = "GreenDream — by day it becomes what you say; at night it dreams the day back"
    description = "Prompts → scenes while awake; at sunset it falls asleep and dreams an arc stitched from everything it was told."

    @classmethod
    def add_args(cls, parser):
        parser.add_argument("--offline", action="store_true", help="never call the API (library/lexicon + offline dream composer)")
        parser.add_argument("--time-scale", type=float, default=1.0, help="clock speed (720 = a day in 2 minutes)")
        parser.add_argument("--start-hour", type=float, default=None, help="start the clock at this hour")
        parser.add_argument("--journal", default="journal", help="folder for the day log and dream scripts")
        parser.add_argument("--freeze-file", default=None, metavar="PATH",
                            help="sentinel file for the kill switch: create it to freeze the facade, delete it to resume "
                                 "(default FREEZE, or $GREENDREAM_FREEZE_FILE; empty string disables)")

    # ------------------------------------------------------------------ setup
    def setup(self, ctx: Context) -> None:
        self.rng = random.Random(21)
        self.offline = bool(getattr(ctx.args, "offline", False))
        now = datetime.now()
        sh = getattr(ctx.args, "start_hour", None)
        self.hour0 = float(sh) if sh is not None else now.hour + now.minute / 60.0
        self.scale = float(getattr(ctx.args, "time_scale", 1.0))
        self.t_ref = 0.0
        self.sunrise, self.sunset = 6.4, 19.0
        self.override = "auto"
        self.phase = "DAY"
        self.phase_t0 = 0.0
        self.hour = self.hour0
        # day
        self.day: list = []                  # today's prompts: {when, text, spec, channel}
        self.queue: deque = deque(maxlen=QUEUE_MAX)
        self.current: Performance | None = None
        self.prev_canvas: Canvas | None = None
        self.trans_t0 = -10.0
        self.trans_kind = "dissolve"
        self.pending = 0
        self.think_t0 = 0.0
        self.energy = 0.0
        self.last_request_t = -100.0
        self.daydream: Performance | None = None
        self.gaze = [8.0, 4.0]
        self.gaze_goal = [8.0, 4.0]
        self.wander_t = 0.0
        # night
        self.dream: DreamPlayer | None = None
        self.dream_script: dict | None = None
        self.dream_cycle = 0
        self.dream_stage = "descent"       # descent | dream | surfacing | deep
        self.stage_t0 = 0.0
        self.dream_pending = False
        self.dreams_tonight: list = []
        self.dream_material: list = []        # the snapshot of self.day the current script indexes into
        self.mumble: tuple | None = None      # (t, accent) sleep-talk acknowledgement
        self.marquee: Marquee | None = None
        # freeze — orthogonal to all of the above, and deliberately not part of the phase machine
        self.frozen = False
        self.freeze_t0 = 0.0
        self.thaw_t0 = -1e6
        self.freeze_source = "-"
        self.journal_dir = getattr(ctx.args, "journal", "journal")
        os.makedirs(self.journal_dir, exist_ok=True)
        self.last_tier = "-"
        self.sensor = WeatherSensor(ctx.bus, offline=self.offline)
        self.sensor.start()
        fpath = getattr(ctx.args, "freeze_file", None)
        self.watcher = FreezeWatcher(ctx.bus, path=FREEZE_FILE if fpath is None else fpath)
        self.watcher.start()
        sig = install_signal_toggle()
        if self.watcher.path:
            print(f"[freeze] kill switch: touch {self.watcher.path}"
                  f"{f', or kill -{sig} {os.getpid()}' if sig else ''}", flush=True)
        # pages
        ctx.add_page("/say", SAY_PAGE)
        ctx.add_page("/journal", JOURNAL_PAGE)
        if ctx.server:
            ctx.server.add_json("/api/journal", lambda m, b: self.journal_json())
        url = (ctx.server.lan_url + "/say") if ctx.server else "/say"
        ctx.set_controls([
            # First in the panel on purpose: the one control you reach for when something is
            # wrong on the facade in front of people. It takes effect on the next frame.
            {"type": "toggle", "label": "FREEZE — hold the facade", "value": False, "event": {"type": "freeze"}, "key": "on"},
            {"type": "note", "text": "Type anything (or open /say on a phone). Phase follows real sunrise/sunset; override it below for demos."},
            {"type": "speech", "label": "Say it"},
            {"type": "link", "label": "Phone input page", "href": "/say", "text": url},
            {"type": "link", "label": "Dream journal", "href": "/journal", "text": "prompts + tonight's dreams"},
            {"type": "select", "label": "Phase", "options": ["auto", "dawn", "day", "dusk", "night"], "value": "auto", "event": {"type": "phase"}, "key": "name"},
            {"type": "slider", "label": "Clock speed (x)", "min": 1, "max": 1440, "value": int(self.scale), "event": {"type": "time_scale"}, "key": "x"},
            {"type": "slider", "label": "Hour of day", "min": 0, "max": 24, "step": 0.25, "value": round(self.hour, 2), "event": {"type": "set_hour"}, "key": "hour"},
        ] + [{"type": "button", "label": k, "event": {"type": "text", "text": k}} for k in ("thunderstorm", "birthday", "rocket launch", "lebron dunk", "calm ocean", "my heart is racing")]
          + [{"type": "button", "label": "🌙 dream now", "event": {"type": "phase", "name": "night"}}, {"type": "button", "label": "⏭ skip", "event": {"type": "skip"}}])

    # ------------------------------------------------------------------ input
    def on_event(self, ev: dict, ctx: Context) -> None:
        t = ev.get("type")
        if t == "weather":
            self.sunrise = _hour_of(ev.get("sunrise", ""), 6.4)
            self.sunset = _hour_of(ev.get("sunset", ""), 19.0)
        elif t == "text" and ev.get("text", "").strip():
            self.pending += 1
            self.think_t0 = ctx.t
            self.last_request_t = ctx.t
            self.energy = min(1.0, self.energy + 0.25)
            ev_text = ev["text"].strip()
            request_async(ev_text, ctx.bus, offline=self.offline, source=ev.get("source", "web"))
        elif t == "spec":
            # A finished scene, from our own genie thread or pushed in by the language service.
            # Either way it is re-validated here: this is the last gate before the windows.
            spec = validate(ev.get("spec"))
            if ev.get("origin") == "genie":
                self.pending = max(0, self.pending - 1)
            channel = str(ev.get("source", "web"))[:32]
            # "live" performs now (default; every on-site channel is live); "dream" is material for tonight only
            priority = ev.get("priority") if ev.get("priority") in ("live", "dream") else "live"
            self.last_tier = str(ev.get("tier", "external"))[:40]
            entry = {"when": f"{int(self.hour):02d}:{int((self.hour % 1) * 60):02d}", "text": clip_words(ev.get("text") or spec["title"]),
                     "spec": spec, "channel": channel, "priority": priority, "tier": self.last_tier,
                     "latency_ms": int(ev.get("latency_ms") or 0), "ts": time.time()}
            self.day.append(entry)
            self._journal_append(entry)
            if self.frozen:
                # Written down, never performed. The words are the material of the piece and
                # one JSONL line keeps them, so this still reaches tonight's dream; what is
                # deliberately dropped is the performance debt, because unfreezing into a
                # backlog is the opposite of what the operator pressed the switch for.
                pass
            elif self.phase in ("DAY", "DAWN") and priority == "live":
                self.queue.append(spec)
            else:  # asleep, or dream material only: acknowledge faintly, weave into the next dream
                self.mumble = (ctx.t, spec["palette"]["accent"])
        elif t == "dream_script":
            self.dream_script = ev["script"]
            self.dream_pending = False
            self.dreams_tonight.append({"cycle": ev.get("cycle"), "tier": ev.get("tier"), "script": ev["script"]})
            self._journal_dream(ev)
        elif t == "phase":
            self.override = ev.get("name", "auto")
        elif t == "time_scale":
            self.hour0 = (self.hour0 + (ctx.t - self.t_ref) * self.scale / 3600.0) % 24.0
            self.t_ref = ctx.t
            self.scale = float(ev.get("x", 1))
        elif t == "set_hour":
            self.hour0 = float(ev.get("hour", 12)) % 24
            self.t_ref = ctx.t
        elif t == "skip":
            if self.current:
                self.current.done = True
            if self.dream and self.dream.cur:
                self.dream.cur.done = True
        elif t == "freeze":
            on = (not self.frozen) if ev.get("toggle") else bool(ev.get("on", True))
            self._set_freeze(on, ctx.t, str(ev.get("source", "web"))[:32])
            if ctx.server:
                ctx.server.frozen = self.frozen   # so /healthz answers honestly straight away

    # ----------------------------------------------------------------- freeze
    def _set_freeze(self, on: bool, t: float, source: str = "web") -> None:
        """Hold the facade, or let it go. Idempotent, and safe from any phase.

        Freezing drops everything in flight rather than pausing it. Two reasons: whatever was
        on the windows when the switch went is by hypothesis the thing that was wrong, so
        resuming it would put the problem straight back up; and a paused `Performance` or
        `DreamPlayer` would come back mid-gesture, which reads as a glitch rather than as a
        decision. The phase machine underneath is untouched — it keeps its clock, keeps
        entering phases, and whatever it has arrived at is what the building resumes into.
        """
        if on == self.frozen:
            return
        self.frozen = on
        self.freeze_source = source
        if on:
            self.freeze_t0 = t
            self.queue.clear()
            self.current = None
            self.daydream = None
            self.prev_canvas = None
            self.trans_t0 = -1e6
            self.marquee = None
            self.mumble = None
            self.dream = None
        else:
            self.thaw_t0 = t
            # Start the night clean: descent will use a script that arrived during the freeze
            # if one did, and otherwise ask for a fresh one.
            self.dream_stage, self.stage_t0 = "descent", t
        print(f"[freeze] {'ON — facade held' if on else 'off — resuming'} (via {source})", flush=True)

    def _render_frozen(self, t: float) -> Canvas:
        """Standby: all 153 windows at one identical dim amber level, swelling very slowly.

        Not black. A dark tower reads as a fault, and a fault on this building in front of an
        audience is the failure mode the switch exists to avoid — the point is to say "somebody
        is in charge of this", not "it broke". Not a scene either: every window the same value
        is something no world, particle field or sprite ever produces, so flatness is the most
        legible statement a facade can make that it is being held on purpose. At 300 m the read
        is an evenly lit amber tower, which is exactly what a held machine looks like.

        The swell (0.10 → 0.15 of full amber over 9 s) is the one moving part, and it is there
        so the field cannot be mistaken for a frozen frame or a dead sender. 9 s rather than the
        night's 8 s, and warm rather than the night's indigo, so an operator on the plaza can
        tell standby from deep sleep at a glance. Mean brightness lands near 0.09 — the same
        band as the building's own resting states, which is what makes it read as calm rather
        than as a signal — and it moves by ~0.0004 per frame, two orders of magnitude inside
        --gentle's limiter.
        """
        cv = Canvas()
        b = 0.5 + 0.5 * math.sin((t - self.freeze_t0) * 2 * math.pi / FREEZE_BREATH_S)
        cv.px[:] = np.array(FREEZE_RGB, dtype=np.float32) * (FREEZE_LEVEL + FREEZE_SWELL * b)
        return cv

    # ---------------------------------------------------------------- journal
    def _journal_append(self, entry: dict) -> None:
        try:
            with open(os.path.join(self.journal_dir, datetime.now().strftime("%Y-%m-%d") + ".jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({k: v for k, v in entry.items() if k != "spec"} | _shown(entry["spec"])) + "\n")
        except Exception as e:
            print(f"[journal] write failed: {e}", flush=True)

    def _journal_dream(self, ev: dict) -> None:
        try:
            with open(os.path.join(self.journal_dir, datetime.now().strftime("%Y-%m-%d") + ".dreams.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"cycle": ev.get("cycle"), "tier": ev.get("tier"), "script": ev["script"], "ts": time.time()}) + "\n")
        except Exception as e:
            print(f"[journal] write failed: {e}", flush=True)

    def journal_json(self) -> dict:
        return {"phase": self.phase, "hour": round(self.hour, 2), "sunrise": self.sunrise, "sunset": self.sunset,
                "prompts": [{"when": d["when"], "text": d["text"], "channel": d["channel"],
                             "priority": d.get("priority", "live"), "tier": d.get("tier", "-")} | _shown(d["spec"]) for d in self.day],
                "dreams": [{"cycle": d["cycle"], "tier": d["tier"], "title": d["script"]["title"], "logline": d["script"]["logline"],
                            "scenes": [dict(s, act=a["name"]) for a in d["script"]["acts"] for s in a["scenes"]]} for d in self.dreams_tonight],
                "now": (self.dream.current["note"] if (self.dream and self.dream.current) else (self.current.spec["title"] if self.current else "")) }

    # -------------------------------------------------------------------- clock
    def _auto_phase(self, h: float) -> tuple:
        w = max(0.5, 10.0 * self.scale / 3600.0)  # transition window in hours (≥ 10 s real time)
        if self.sunrise - w / 2 <= h < self.sunrise + w / 2:
            return "DAWN", (h - (self.sunrise - w / 2)) / w
        if self.sunset - w / 2 <= h < self.sunset + w / 2:
            return "DUSK", (h - (self.sunset - w / 2)) / w
        if self.sunrise + w / 2 <= h < self.sunset - w / 2:
            return "DAY", 0.0
        return "NIGHT", 0.0

    # ------------------------------------------------------------------ update
    def update(self, dt: float, t: float, cv: Canvas, ctx: Context) -> None:
        self.hour = (self.hour0 + (t - self.t_ref) * self.scale / 3600.0) % 24.0
        if self.override == "auto":
            phase, prog = self._auto_phase(self.hour)
        else:
            phase = self.override.upper()
            prog = clamp((t - self.phase_t0) / 12.0)
        if phase != self.phase:
            self._enter(phase, t)
        self.energy = max(0.0, self.energy - dt / 40.0)
        if self.frozen:
            # The one early return in the frame loop. The clock and the phase machine above
            # have already run, so the building knows what time it is and which phase it is
            # in; it is simply not showing it. A marquee queued by an _enter() that fired
            # during the freeze is dropped rather than saved up for the thaw.
            self.marquee = None
            cv.px[:] = self._render_frozen(t).px
            cv.clip()
            if ctx.frame_index % 6 == 0:
                self._publish(ctx, "FROZEN")
            return
        if phase == "DAY":
            out = self._render_day(t, dt)
        elif phase == "DAWN":
            out = self._render_dawn(t, dt, prog)
        elif phase == "DUSK":
            out = self._render_dusk(t, dt, prog)
        else:
            out = self._render_night(t, dt)
        if self.pending:  # thinking shimmer (any phase)
            band = np.exp(-(((RR - (ROWS - ((t - self.think_t0) * 14) % (ROWS + 4) + 2)) ** 2) / 2.0)).astype(np.float32)
            out.mask(band, (1.0, 1.0, 1.0), 0.35, "add")
        if self.marquee:
            self.marquee.update(dt)
            self.marquee.draw(out, 0.9)
            if self.marquee.done:
                self.marquee = None
        k = (t - self.thaw_t0) / THAW_S
        if k < 1.0:   # coming out of a freeze: fade up from standby into whatever is running now
            out.px = out.px * max(0.0, k) + self._render_frozen(t).px * (1.0 - max(0.0, k))
        cv.px[:] = out.px
        cv.clip()
        if ctx.frame_index % 6 == 0:
            self._publish(ctx)

    def _publish(self, ctx: Context, phase_override: str = "") -> None:
        """The status panel and /healthz. Called from both the frozen and the live path."""
        if ctx.server:
            ctx.server.frozen = self.frozen
        ctx.set_status(phase=phase_override or (self.phase + (f" · {self.dream_stage}" if self.phase == "NIGHT" else "")),
                       clock=f"{int(self.hour):02d}:{int((self.hour % 1) * 60):02d}",
                       prompts_today=len(self.day),
                       now=("held (%s)" % self.freeze_source) if self.frozen else (self.dream.current["note"][:40] if (self.dream and self.dream.current) else (self.current.spec["title"] if self.current else "idle")),
                       dreams=len(self.dreams_tonight), thinking=self.pending, energy=round(self.energy, 2), last=self.last_tier)

    def _enter(self, phase: str, t: float) -> None:
        self.phase, self.phase_t0 = phase, t
        if phase == "DAWN":
            self.marquee = None
            self.dream = None
            self.dream_script = None
        elif phase == "DAY":
            self.marquee = Marquee("GOOD MORNING", (1.0, 0.85, 0.5), speed=7.0) if self.hour < 12 else None
            self.dreams_tonight = []
            self.dream_cycle = 0
        elif phase == "DUSK":
            self.queue.clear()
            self.current = None
            self.daydream = None
            self.marquee = Marquee("GOOD NIGHT", (0.6, 0.6, 1.0), speed=6.0)
        elif phase == "NIGHT":
            self.dream_stage, self.stage_t0 = "descent", t
            self.dream = None
            self.dream_script = None
            self.dream_pending = False

    # -------------------------------------------------------------------- day
    def _idle_awake(self, t: float, dt: float) -> Canvas:
        cv = Canvas()
        b = breath(t, 4.5 - 1.5 * self.energy)
        depth = RR / (ROWS - 1)
        lit = 1.0 / (1.0 + np.exp(-(depth - (1.0 - (0.25 + 0.75 * b))) * 7.0))
        rgb = lerp_rgb((1.0, 0.55, 0.15), (1.0, 0.9, 0.7), self.energy * 0.6)
        cv.mask((0.05 + 0.25 * lit).astype(np.float32), rgb, 1.0, "add")
        # looking around: a brighter patch wanders (the building is awake and curious)
        self.wander_t -= dt
        if self.wander_t <= 0:
            self.wander_t = self.rng.uniform(1.5, 4.0)
            self.gaze_goal = [self.rng.uniform(2, 14), self.rng.uniform(1, 7)]
        self.gaze[0] += (self.gaze_goal[0] - self.gaze[0]) * 0.06
        self.gaze[1] += (self.gaze_goal[1] - self.gaze[1]) * 0.06
        cv.blob(self.gaze[0], self.gaze[1], 1.4, (1.0, 0.9, 0.7), 0.35, "add")
        return cv

    def _start(self, spec: dict, t: float, dt: float) -> None:
        self.prev_canvas = self.current.render(t, dt) if self.current else self._idle_awake(t, dt)
        self.trans_t0 = t
        self.trans_kind = self.rng.choice(["dissolve", "iris", "elevator", "blinds"])
        self.current = Performance(spec, t, seed=self.rng.randrange(1 << 30))
        self.daydream = None

    def _render_day(self, t: float, dt: float) -> Canvas:
        if self.queue and (self.current is None or self.current.done or (t - self.current.t0) > HOLD):
            self._start(self.queue.popleft(), t, dt)
        if self.current and self.current.done:
            self.prev_canvas = self.current.render(t, dt)
            self.trans_t0, self.trans_kind = t, "dissolve"
            self.current = None
        if self.current is not None:
            out = self.current.render(t, dt)
        else:
            out = self._idle_awake(t, dt)
            # daydream: a short faint replay of something it was told
            memories = [d for d in self.day if d["spec"]["ok"]]
            if memories and self.daydream is None and t - self.last_request_t > 25 and self.rng.random() < dt * 0.04:
                spec = dict(self.rng.choice(memories)["spec"], duration_s=6, word=None, beats=[])
                self.daydream = Performance(spec, t, seed=self.rng.randrange(1 << 30))
            if self.daydream:
                d = self.daydream.render(t, dt)
                k = 0.4 * math.sin(clamp((t - self.daydream.t0) / 6.0) * math.pi)
                out.px = out.px * (1 - k) + d.px * k
                if self.daydream.done:
                    self.daydream = None
        p = (t - self.trans_t0) / 0.9
        if self.prev_canvas is not None and p < 1.0:
            out = mix(self.prev_canvas, out, self.trans_kind, p, self.rng)
        return out

    # ------------------------------------------------------------------- dawn
    def _render_dawn(self, t: float, dt: float, prog: float) -> Canvas:
        """Light floods up from the base (sunlight climbing the tower), a stretch, two blinks."""
        cv = Canvas()
        depth = 1.0 - RR / (ROWS - 1)               # 0 bottom .. 1 top
        fill = clamp(prog / 0.6)                     # first 60 %: the light climbs
        lit = 1.0 / (1.0 + np.exp(-(fill * 1.2 - depth) * 8.0))
        rgb = lerp_rgb((0.35, 0.25, 0.6), (1.0, 0.7, 0.35), fill)
        cv.mask((0.06 + 0.5 * lit).astype(np.float32), rgb, 1.0, "add")
        if prog > 0.6:                                # stretch: expand from the centre, then two blinks
            a = (prog - 0.6) / 0.4
            stretch = np.exp(-(((RR - 8) / (2 + 14 * a)) ** 2 + ((RR * 0 + (np.arange(COLS)[None, :]) - 4) / (1.5 + 6 * a)) ** 2))
            cv.mask(stretch.astype(np.float32), (1.0, 0.85, 0.6), 0.5 * math.sin(a * math.pi), "add")
            blink = 1.0
            for centre in (0.55, 0.8):
                blink *= 1 - 0.85 * math.exp(-((a - centre) ** 2) / (2 * 0.03 ** 2))
            cv.px *= blink
        cv.px *= (0.9 + 0.1 * math.sin(t * 2))
        return cv

    # ------------------------------------------------------------------- dusk
    def _render_dusk(self, t: float, dt: float, prog: float) -> Canvas:
        """Eyelids close from the top; breathing slows; colours cool; a last yawn."""
        cv = self._idle_awake(t, dt)
        cool = lerp_rgb((1.0, 0.75, 0.45), (0.3, 0.3, 0.8), prog)
        cv.px *= np.array(cool, dtype=np.float32)[None, None, :] / max(1e-3, max(cool))
        lid = clamp(prog * 1.15)                      # rows above the lid go dark
        lid_row = lid * (ROWS + 2) - 1
        mask = 1.0 / (1.0 + np.exp(-(RR - lid_row) * 3.0))
        cv.px *= mask[..., None]
        if 0.25 < prog < 0.55:                        # yawn: a slow bright wave up and back
            y = (prog - 0.25) / 0.3
            r = ROWS - 1 - (ROWS - 1) * math.sin(y * math.pi)
            cv.px += (np.exp(-((RR - r) ** 2) / 3.0) * 0.35)[..., None] * np.array((0.8, 0.7, 1.0), dtype=np.float32)
        cv.px *= (0.6 + 0.4 * (1 - prog))
        return cv

    # ------------------------------------------------------------------ night
    def _render_night(self, t: float, dt: float) -> Canvas:
        stage = self.dream_stage
        e = t - self.stage_t0
        cv = Canvas()
        # deep-sleep base: very dim indigo breathing (8 s)
        b = 0.5 + 0.5 * math.sin(t * 2 * math.pi / 8.0)
        cv.vgradient((0.03, 0.03, 0.12), (0.06, 0.05, 0.18), 0.6 + 0.4 * b)   # asleep, but visibly breathing
        if stage == "descent":
            if not self.dream_pending and self.dream_script is None:
                self.dream_cycle += 1
                self.dream_pending = True
                # a snapshot: the composer thread reads it while sleep-talk keeps appending to self.day,
                # and the script's source ids must index into exactly this list. Refusals do not dream.
                self.dream_material = [d for d in self.day if d["spec"].get("ok", True)]
                compose_async(self.dream_material, self.dream_cycle, offline=self.offline, seed=self.rng.randrange(1000))
            if self.dream_script is not None and e > 6.0:
                self.dream = DreamPlayer(self.dream_script, self.dream_material, t, self.rng.randrange(1 << 30))
                self.dream_script = None
                self.dream_stage, self.stage_t0 = "dream", t
            # REM onset: faint flickers of colour
            if self.rng.random() < dt * 1.5:
                cv.blob(self.rng.uniform(2, 14), self.rng.uniform(1, 7), 1.0, (0.5, 0.4, 0.9), 0.25, "add")
        elif stage == "dream":
            if self.dream is None or self.dream.done:
                self.dream = None
                self.dream_stage, self.stage_t0 = "surfacing", t
            else:
                d = self.dream.render(t, dt, depth=0.4)
                cv.px = np.maximum(cv.px, d.px)
        elif stage == "surfacing":
            k = 1 - clamp(e / 10.0)
            cv.px *= (0.6 + 0.4 * k)
            if e > 10.0:
                self.dream_stage, self.stage_t0 = "deep", t
        elif stage == "deep":
            if e > 25.0:
                self.dream_stage, self.stage_t0 = "descent", t
        # sleep-talk: a faint coloured mumble when someone speaks to the sleeping building
        if self.mumble and t - self.mumble[0] < 3.0:
            k = 0.25 * math.sin(clamp((t - self.mumble[0]) / 3.0) * math.pi)
            cv.blob(9.0, 4.0, 2.5, hex_rgb(self.mumble[1]), k, "add")
        return cv

    # --------------------------------------------------------------- teardown
    def teardown(self, ctx: Context) -> None:
        self.watcher.stop()

    # ------------------------------------------------------------------- demo
    def demo_script(self):
        """A whole day in ~3.5 minutes: dawn, eight prompts, dusk, a full dream, dawn again."""
        ev = [(0.0, {"type": "set_hour", "hour": 6.0}), (0.0, {"type": "time_scale", "x": 600})]   # 1 s = 10 min
        for i, s in enumerate(("sunrise", "rocket launch", "lebron dunk", "it's raining", "my heart is racing", "birthday", "calm ocean", "thunderstorm")):
            ev.append((10.0 + 8.0 * i, {"type": "text", "text": s}))
        ev += [(84.0, {"type": "phase", "name": "night"}),            # hold the night so one full dream plays
               (120.0, {"type": "text", "text": "snow day"}),         # sleep-talk: said to the sleeping building
               (196.0, {"type": "phase", "name": "dawn"}), (208.0, {"type": "phase", "name": "day"})]
        return Timeline(ev)
