"""Generative worlds for the 17x9 tower. Each world is a function
``render(t, dt, state, rng) -> Canvas`` with its own persistent ``state``
dict, plus cinematic transitions between worlds.

Worlds: ocean, forest, aurora, hyperspace, sunrise, storm, snow, lava, city
Transitions: warp, iris, elevator, dissolve, blinds, slide, flash
"""

from __future__ import annotations

import math
import random

import numpy as np

from common.canvas import CC, COLS, RR, ROWS, Canvas, ValueNoise, clamp, hsv, lerp, lerp_rgb

NOISE = ValueNoise(21)
NOISE2 = ValueNoise(22)

# --------------------------------------------------------------------------- worlds

def ocean(t, dt, st, rng):
    cv = Canvas()
    cv.vgradient((0.02, 0.15, 0.30), (0.0, 0.03, 0.10))
    # rolling swells: sine bands travelling upward, foam sparkle on the crests
    for k, (freq, speed, amp) in enumerate(((0.55, 1.4, 0.35), (0.9, 2.1, 0.22), (1.6, 3.0, 0.12))):
        w = 0.5 + 0.5 * np.sin(RR * freq + t * speed + 0.7 * np.sin(CC * 0.8 + k))
        cv.mask((w ** 3).astype(np.float32), (0.1, 0.55, 0.9), amp, "add")
    crest = np.clip((NOISE.field(t, 0.4, 0.8, 2) - 0.62) * 6, 0, 1)
    cv.mask(crest.astype(np.float32), (0.85, 0.95, 1.0), 0.8, "add")
    return cv


def forest(t, dt, st, rng):
    cv = Canvas()
    canopy = NOISE.field(t, 0.35, 0.12, 3)
    cv.mask(canopy.astype(np.float32), (0.05, 0.45, 0.12), 0.9, "add")
    cv.vgradient((0.0, 0.08, 0.02), (0.05, 0.03, 0.0), 0.6)
    # light shafts drifting slowly
    shaft = np.exp(-((CC - (4 + 3 * math.sin(t * 0.15))) ** 2) / 1.5) * (1 - RR / ROWS)
    cv.mask(shaft.astype(np.float32), (0.7, 0.8, 0.4), 0.25, "add")
    # fireflies
    ff = st.setdefault("ff", [])
    if rng.random() < 0.25:
        ff.append([rng.uniform(4, 16), rng.uniform(0, 8), t, rng.uniform(1.5, 3.5)])
    keep = []
    for f in ff:
        age = t - f[2]
        if age < f[3]:
            keep.append(f)
            k = math.sin(age / f[3] * math.pi) ** 2
            cv.add_px(int(f[0] + 0.6 * math.sin(age * 3)), int(f[1] + 0.6 * math.cos(age * 2)), (1.0, 0.95, 0.4), k)
    st["ff"] = keep[-40:]
    return cv


def aurora(t, dt, st, rng):
    cv = Canvas()
    cv.vgradient((0.02, 0.02, 0.08), (0.0, 0.0, 0.03))
    # curtains: vertical ribbons whose x wobbles with noise, colour green->violet with height
    for k in range(3):
        x = 4 + 3.2 * np.sin(t * (0.25 + 0.1 * k) + k * 2.1 + 0.6 * np.sin(RR * 0.5 + t * 0.4 + k))
        d = np.exp(-((CC - x) ** 2) / (2 * (0.9 + 0.3 * k) ** 2))
        h = 0.78 - 0.42 * (RR / ROWS) - 0.04 * k   # violet at the top -> green at the base
        col = np.stack([np.array(hsv(hh, 0.85, 1.0)) for hh in h[:, 0]], axis=0)  # per row colour
        cv.px += (d * (0.35 + 0.35 * NOISE.sample(RR * 0.3 + k, CC * 0.3, t * 0.5)))[..., None] * col[:, None, :]
    return cv


def hyperspace(t, dt, st, rng):
    cv = Canvas()
    stars = st.setdefault("stars", [])
    speed = st.get("speed", 1.0)
    for _ in range(2):
        if rng.random() < 0.9 * speed:
            ang = rng.uniform(0, 2 * math.pi)
            stars.append([8.0, 4.0, math.cos(ang) * 0.6, math.sin(ang) * 0.6, t])
    keep = []
    for s in stars:
        s[0] += s[2] * dt * 10 * speed
        s[1] += s[3] * dt * 10 * speed
        if -2 < s[0] < ROWS + 2 and -2 < s[1] < COLS + 2:
            keep.append(s)
            age = t - s[4]
            k = min(1.0, 0.2 + age * 2.5)
            cv.line(s[0] - s[2] * 2.5 * speed, s[1] - s[3] * 2.5 * speed, s[0], s[1], (0.8, 0.85, 1.0), k, width=0.4, mode="max")
    st["stars"] = keep[-120:]
    cv.blob(8, 4, 1.2, (0.4, 0.5, 1.0), 0.25 * speed)
    return cv


def sunrise(t, dt, st, rng):
    cv = Canvas()
    ph = (math.sin(t * 0.12) + 1) / 2   # 0 = night, 1 = full sunrise
    top = lerp_rgb((0.01, 0.01, 0.08), (0.35, 0.55, 0.95), ph)
    bot = lerp_rgb((0.15, 0.03, 0.02), (1.0, 0.55, 0.2), ph)
    cv.vgradient(top, bot)
    sun_r = 16 - 12 * ph
    cv.blob(sun_r, 4.0, 1.6, (1.0, 0.85, 0.4), 0.9 * ph)
    haze = np.exp(-((RR - sun_r) ** 2) / 12.0)
    cv.mask(haze.astype(np.float32), (1.0, 0.5, 0.2), 0.5 * ph, "add")
    return cv


def storm(t, dt, st, rng):
    cv = Canvas()
    cv.vgradient((0.06, 0.06, 0.09), (0.02, 0.02, 0.04))
    drops = st.setdefault("drops", [])
    for _ in range(3):
        if rng.random() < 0.9:
            drops.append([rng.uniform(-3, 0), rng.uniform(0, 8), rng.uniform(14, 24)])
    keep = []
    for d in drops:
        d[0] += d[2] * dt
        if d[0] < ROWS + 1:
            keep.append(d)
            cv.line(d[0] - 1.2, d[1], d[0], d[1], (0.55, 0.65, 0.85), 0.6, width=0.3, mode="max")
    st["drops"] = keep[-90:]
    if rng.random() < 0.012 or 0 < st.get("flash", 0):
        if st.get("flash", 0) <= 0:
            st["flash"] = 0.28
            st["bolt_c"] = rng.uniform(1, 7)
        st["flash"] -= dt
        k = max(0.0, st["flash"] / 0.28)
        cv.px += 0.6 * k * (0.5 + 0.5 * math.sin(t * 90))
        c = st["bolt_c"]
        for r in range(0, ROWS - 1, 2):
            cv.line(r, c + math.sin(r * 1.7) * 0.8, r + 2, c + math.sin((r + 2) * 1.7) * 0.8, (0.95, 0.95, 1.0), k, width=0.35, mode="max")
    return cv


def snow(t, dt, st, rng):
    cv = Canvas()
    cv.vgradient((0.04, 0.05, 0.10), (0.02, 0.03, 0.06))
    flakes = st.setdefault("flakes", [])
    pile = st.setdefault("pile", np.zeros(COLS))
    if rng.random() < 0.7:
        flakes.append([-1.0, rng.uniform(0, 8), rng.uniform(1.5, 3.5), rng.uniform(0, 6.3)])
    keep = []
    for f in flakes:
        f[0] += f[2] * dt
        f[1] += 0.4 * math.sin(t * 1.3 + f[3]) * dt
        c = int(round(f[1])) % COLS
        if f[0] >= ROWS - 1 - pile[c]:
            pile[c] = min(6, pile[c] + 0.25)
            continue
        keep.append(f)
        cv.blob(f[0], f[1], 0.45, (0.9, 0.95, 1.0), 0.9, "max")
    st["flakes"] = keep[-80:]
    if pile.sum() > 30:
        pile *= 0.999
    for c in range(COLS):
        h = pile[c]
        if h > 0:
            r0 = ROWS - h
            m = np.clip(RR - r0 + 1, 0, 1)[:, c]
            cv.px[:, c] += m[:, None] * np.array((0.8, 0.85, 0.95), dtype=np.float32) * 0.9
    return cv


def lava(t, dt, st, rng):
    cv = Canvas()
    n = NOISE.field(t, 0.25, 0.08, 3)
    heat = np.clip((n - 0.3) * 1.6, 0, 1)
    cv.mask(heat.astype(np.float32), (0.9, 0.15, 0.02), 0.9, "add")
    crack = np.clip((NOISE2.field(t, 0.5, 0.15, 2) - 0.66) * 8, 0, 1)
    cv.mask(crack.astype(np.float32), (1.0, 0.85, 0.3), 1.0, "add")
    cv.px *= (0.85 + 0.15 * math.sin(t * 0.8))
    return cv


def city(t, dt, st, rng):
    cv = Canvas()
    cv.vgradient((0.02, 0.02, 0.06), (0.03, 0.02, 0.02))
    lights = st.setdefault("lights", np.zeros((ROWS, COLS), dtype=np.float32))
    if rng.random() < 0.6:
        lights[rng.randint(4, 16), rng.randint(0, 8)] = rng.uniform(0.3, 1.0)
    lights *= 0.985
    warm = (lights > 0.4).astype(np.float32) * lights
    cool = (lights <= 0.4).astype(np.float32) * lights
    cv.mask(warm, (1.0, 0.75, 0.4), 1.0, "add")
    cv.mask(cool, (0.5, 0.7, 1.0), 1.0, "add")
    # a plane crossing the sky
    x = (t * 1.5) % (COLS + 6) - 3
    cv.add_px(1, int(x), (1.0, 0.3, 0.3), 0.5 + 0.5 * math.sin(t * 8))
    return cv


WORLDS = {"ocean": ocean, "forest": forest, "aurora": aurora, "hyperspace": hyperspace, "sunrise": sunrise, "storm": storm, "snow": snow, "lava": lava, "city": city}
WORLD_NAMES = list(WORLDS.keys())

# --------------------------------------------------------------------- transitions

def mix(a: Canvas, b: Canvas, kind: str, p: float, rng) -> Canvas:
    """Blend from world a to world b, p in [0,1]."""
    p = clamp(p)
    out = Canvas()
    if kind == "dissolve":
        thr = st_threshold(rng)
        m = (thr < p).astype(np.float32)
        out.px = a.px * (1 - m[..., None]) + b.px * m[..., None]
    elif kind == "iris":
        d = np.sqrt(((RR - 8) / 8.5) ** 2 + ((CC - 4) / 4.5) ** 2)
        m = np.clip((p * 1.4 - d) / 0.25 + 0.5, 0, 1).astype(np.float32)
        out.px = a.px * (1 - m[..., None]) + b.px * m[..., None]
        ring = np.exp(-((d - p * 1.4) ** 2) / 0.02).astype(np.float32)
        out.mask(ring, (1, 1, 1), 0.6 * math.sin(p * math.pi), "add")
    elif kind == "elevator":
        # the new world rises from below, as if the building were moving floors
        shift = int(round((1 - p) * ROWS))
        out.px = np.concatenate([a.px[shift:], b.px[: shift]], axis=0) if shift > 0 else b.px.copy()
        edge = ROWS - shift
        if 0 <= edge < ROWS:
            out.px[edge] = np.maximum(out.px[edge], 0.7)
    elif kind == "blinds":
        m = np.clip((p * (ROWS + 4) - RR) / 3.0, 0, 1).astype(np.float32)
        out.px = a.px * (1 - m[..., None]) + b.px * m[..., None]
    elif kind == "slide":
        shift = int(round((1 - p) * COLS))
        out.px = np.concatenate([a.px[:, shift:], b.px[:, :shift]], axis=1) if shift > 0 else b.px.copy()
    elif kind == "warp":
        # accelerate into white streaks, then decelerate out into the new world
        if p < 0.5:
            q = p / 0.5
            out.px = a.px * (1 - q)
            streak = np.exp(-((CC - 4) ** 2) / (0.3 + 4 * q)) * np.clip((q * 2 - (RR / ROWS)) * 2, 0, 1)
            out.mask(streak.astype(np.float32), (0.8, 0.9, 1.0), q, "add")
            out.px += q ** 3
        else:
            q = (p - 0.5) / 0.5
            out.px = b.px * q + (1 - q) ** 2
    else:  # flash
        k = math.sin(p * math.pi)
        out.px = (a.px if p < 0.5 else b.px) + k
    out.clip()
    return out


_THR = None


def st_threshold(rng):
    global _THR
    if _THR is None:
        _THR = np.random.default_rng(3).random((ROWS, COLS)).astype(np.float32)
    return _THR


TRANSITIONS = ["warp", "iris", "elevator", "dissolve", "blinds", "slide", "flash"]
DURATION = {"warp": 2.6, "iris": 1.8, "elevator": 2.2, "dissolve": 1.8, "blinds": 1.6, "slide": 1.4, "flash": 0.9}
