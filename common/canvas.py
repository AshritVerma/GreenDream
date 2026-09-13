"""Float RGB canvas + drawing helpers for the 17x9 Green Building grid.

Everything here is pure numpy. A ``Canvas`` is a (ROWS, COLS, 3) float32 array
with values in [0, 1]; ``to_frame`` converts it into the repo's ``Frame`` of
``Color`` objects right before it is handed to ``Display.send``.

Coordinate convention (same as the Tetris repo): row 0 is the TOP of the
building, row 16 is the bottom; column 0 is the left edge as seen from the
Charles River side.
"""

from __future__ import annotations

import colorsys
import math
from typing import Iterable, Sequence, Tuple

import numpy as np

from utilities.display import Color, Frame

ROWS = Frame.DISPLAY_ROWS  # 17
COLS = Frame.DISPLAY_COLS  # 9

# Row / column index grids for vectorised effects: RR[r, c] == r, CC[r, c] == c
RR, CC = np.meshgrid(np.arange(ROWS, dtype=np.float32), np.arange(COLS, dtype=np.float32), indexing="ij")
# Normalised coordinates in [0, 1]
NR = RR / (ROWS - 1)
NC = CC / (COLS - 1)
# Centred coordinates in roughly [-1, 1] (aspect preserved: rows are the long axis)
CY = (RR - (ROWS - 1) / 2) / ((ROWS - 1) / 2)
CX = (CC - (COLS - 1) / 2) / ((ROWS - 1) / 2) * 1.0

RGB = Tuple[float, float, float]

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_rgb(a: Sequence[float], b: Sequence[float], t: float) -> RGB:
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t))


def hsv(h: float, s: float = 1.0, v: float = 1.0) -> RGB:
    """Hue in [0, 1) (wraps), saturation and value in [0, 1]."""
    return colorsys.hsv_to_rgb(h % 1.0, clamp(s), clamp(v))


def scale(rgb: Sequence[float], k: float) -> RGB:
    return (rgb[0] * k, rgb[1] * k, rgb[2] * k)


def hex_rgb(code: str) -> RGB:
    code = code.lstrip("#")
    return (int(code[0:2], 16) / 255.0, int(code[2:4], 16) / 255.0, int(code[4:6], 16) / 255.0)


def kelvin(temp_k: float) -> RGB:
    """Approximate black-body colour for a temperature in Kelvin (1000-12000)."""
    t = clamp(temp_k, 1000.0, 12000.0) / 100.0
    if t <= 66:
        r = 1.0
        g = clamp((99.4708025861 * math.log(t) - 161.1195681661) / 255.0)
        b = 0.0 if t <= 19 else clamp((138.5177312231 * math.log(t - 10) - 305.0447927307) / 255.0)
    else:
        r = clamp(329.698727446 * ((t - 60) ** -0.1332047592) / 255.0)
        g = clamp(288.1221695283 * ((t - 60) ** -0.0755148492) / 255.0)
        b = 1.0
    return (r, g, b)


# A few named colours used across projects
WHITE = (1.0, 1.0, 1.0)
BLACK = (0.0, 0.0, 0.0)
WARM = (1.0, 0.72, 0.35)
COOL = (0.35, 0.6, 1.0)
EMBER = (1.0, 0.25, 0.05)
MINT = (0.3, 1.0, 0.6)
VIOLET = (0.6, 0.2, 1.0)
GOLD = (1.0, 0.85, 0.2)
SKY = (0.4, 0.75, 1.0)
ROSE = (1.0, 0.35, 0.55)

# ---------------------------------------------------------------------------
# Easing
# ---------------------------------------------------------------------------

def ease_in_out(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in(t: float) -> float:
    t = clamp(t)
    return t ** 3


def pulse(t: float, period: float, sharpness: float = 4.0) -> float:
    """A rounded pulse train in [0, 1] with the given period (seconds)."""
    phase = (t % period) / period
    return math.exp(-sharpness * 6 * phase) if sharpness > 0 else 1.0


def breath(t: float, period: float = 5.0) -> float:
    """Slow inhale/exhale curve in [0, 1] (inhale is a bit faster than exhale)."""
    phase = (t % period) / period
    if phase < 0.42:
        return ease_in_out(phase / 0.42)
    return 1.0 - ease_in_out((phase - 0.42) / 0.58)


def heartbeat(t: float, bpm: float) -> float:
    """Lub-dub envelope in [0, 1] for the given heart rate."""
    period = 60.0 / max(bpm, 1e-3)
    phase = (t % period) / period
    lub = math.exp(-((phase - 0.05) ** 2) / (2 * 0.03 ** 2))
    dub = 0.6 * math.exp(-((phase - 0.30) ** 2) / (2 * 0.04 ** 2))
    return clamp(lub + dub)


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

class Canvas:
    """A float RGB image the size of the building."""

    __slots__ = ("px",)

    def __init__(self, px: np.ndarray | None = None):
        self.px = np.zeros((ROWS, COLS, 3), dtype=np.float32) if px is None else px

    # -- basic ops ---------------------------------------------------------
    def clear(self, rgb: Sequence[float] = BLACK) -> "Canvas":
        self.px[:] = np.asarray(rgb, dtype=np.float32)
        return self

    fill = clear

    def copy(self) -> "Canvas":
        return Canvas(self.px.copy())

    def fade(self, k: float) -> "Canvas":
        """Multiply everything by k (k<1 darkens; used for trails)."""
        self.px *= k
        return self

    def clip(self) -> "Canvas":
        np.clip(self.px, 0.0, 1.0, out=self.px)
        return self

    def gamma(self, g: float = 2.2) -> "Canvas":
        np.power(np.clip(self.px, 0, 1), 1.0 / g if g < 1 else g, out=self.px)
        return self

    def add(self, other: "Canvas", k: float = 1.0) -> "Canvas":
        self.px += other.px * k
        return self

    def blend(self, other: "Canvas", t: float) -> "Canvas":
        t = clamp(t)
        self.px *= (1.0 - t)
        self.px += other.px * t
        return self

    def max_with(self, other: "Canvas") -> "Canvas":
        np.maximum(self.px, other.px, out=self.px)
        return self

    def tint(self, rgb: Sequence[float]) -> "Canvas":
        self.px *= np.asarray(rgb, dtype=np.float32)
        return self

    # -- pixels ------------------------------------------------------------
    def set(self, r: int, c: int, rgb: Sequence[float], k: float = 1.0) -> None:
        if 0 <= r < ROWS and 0 <= c < COLS:
            self.px[r, c] = np.asarray(rgb, dtype=np.float32) * k

    def get(self, r: int, c: int) -> RGB:
        return tuple(float(x) for x in self.px[r, c])

    def add_px(self, r: int, c: int, rgb: Sequence[float], k: float = 1.0) -> None:
        if 0 <= r < ROWS and 0 <= c < COLS:
            self.px[r, c] += np.asarray(rgb, dtype=np.float32) * k

    def mask(self, m: np.ndarray, rgb: Sequence[float], k: float = 1.0, mode: str = "add") -> "Canvas":
        """Paint colour ``rgb`` weighted by a (ROWS, COLS) float mask."""
        col = np.asarray(rgb, dtype=np.float32) * k
        if mode == "add":
            self.px += m[..., None] * col
        elif mode == "max":
            np.maximum(self.px, m[..., None] * col, out=self.px)
        else:  # "set" / lerp toward colour
            mm = np.clip(m, 0, 1)[..., None]
            self.px = self.px * (1 - mm) + col * mm
        return self

    # -- shapes ------------------------------------------------------------
    def blob(self, r: float, c: float, radius: float, rgb: Sequence[float], k: float = 1.0, mode: str = "add") -> "Canvas":
        """Soft gaussian blob centred at (r, c) in cell units."""
        d2 = (RR - r) ** 2 + (CC - c) ** 2
        m = np.exp(-d2 / (2 * max(radius, 1e-3) ** 2)).astype(np.float32)
        return self.mask(m, rgb, k, mode)

    def rect(self, r0: int, c0: int, r1: int, c1: int, rgb: Sequence[float], k: float = 1.0) -> "Canvas":
        """Fill inclusive cell rectangle."""
        r0, r1 = max(0, min(r0, r1)), min(ROWS - 1, max(r0, r1))
        c0, c1 = max(0, min(c0, c1)), min(COLS - 1, max(c0, c1))
        self.px[r0:r1 + 1, c0:c1 + 1] = np.asarray(rgb, dtype=np.float32) * k
        return self

    def line(self, r0: float, c0: float, r1: float, c1: float, rgb: Sequence[float], k: float = 1.0, width: float = 0.6, mode: str = "max") -> "Canvas":
        """Anti-aliased line between two cell-space points."""
        dr, dc = r1 - r0, c1 - c0
        length2 = dr * dr + dc * dc
        if length2 < 1e-6:
            return self.blob(r0, c0, width, rgb, k, mode)
        t = ((RR - r0) * dr + (CC - c0) * dc) / length2
        t = np.clip(t, 0.0, 1.0)
        pr, pc = r0 + t * dr, c0 + t * dc
        d2 = (RR - pr) ** 2 + (CC - pc) ** 2
        m = np.exp(-d2 / (2 * width ** 2)).astype(np.float32)
        return self.mask(m, rgb, k, mode)

    def ring(self, r: float, c: float, radius: float, rgb: Sequence[float], k: float = 1.0, thickness: float = 0.7) -> "Canvas":
        d = np.sqrt((RR - r) ** 2 + (CC - c) ** 2)
        m = np.exp(-((d - radius) ** 2) / (2 * thickness ** 2)).astype(np.float32)
        return self.mask(m, rgb, k, "add")

    def vgradient(self, top: Sequence[float], bottom: Sequence[float], k: float = 1.0) -> "Canvas":
        top = np.asarray(top, dtype=np.float32)
        bottom = np.asarray(bottom, dtype=np.float32)
        self.px += (top[None, None, :] * (1 - NR)[..., None] + bottom[None, None, :] * NR[..., None]) * k
        return self

    def hline(self, r: int, rgb: Sequence[float], k: float = 1.0) -> "Canvas":
        if 0 <= r < ROWS:
            self.px[r, :] = np.asarray(rgb, dtype=np.float32) * k
        return self

    def vline(self, c: int, rgb: Sequence[float], k: float = 1.0) -> "Canvas":
        if 0 <= c < COLS:
            self.px[:, c] = np.asarray(rgb, dtype=np.float32) * k
        return self

    # -- output ------------------------------------------------------------
    def to_uint8(self) -> np.ndarray:
        return (np.clip(self.px, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)

    def to_frame(self, frame: Frame | None = None) -> Frame:
        """Write this canvas into a repo ``Frame`` (creating one if needed)."""
        if frame is None:
            frame = Frame()
        u8 = self.to_uint8()
        arr = frame.asarray()
        for r in range(ROWS):
            row = u8[r]
            for c in range(COLS):
                p = row[c]
                arr[r, c] = Color(int(p[0]), int(p[1]), int(p[2]))
        return frame

    @staticmethod
    def from_frame(frame: Frame) -> "Canvas":
        cv = Canvas()
        arr = frame.asarray()
        for r in range(ROWS):
            for c in range(COLS):
                col = arr[r, c]
                cv.px[r, c] = (col.r / 255.0, col.g / 255.0, col.b / 255.0)
        return cv


# ---------------------------------------------------------------------------
# Noise (cheap value noise, good enough for 153 pixels)
# ---------------------------------------------------------------------------

class ValueNoise:
    """2D/3D value noise with smooth interpolation. Deterministic per seed."""

    def __init__(self, seed: int = 1, size: int = 64):
        rng = np.random.default_rng(seed)
        self.size = size
        self.table = rng.random((size, size, size), dtype=np.float32)

    def sample(self, y: np.ndarray, x: np.ndarray, z: float) -> np.ndarray:
        """Sample noise at float coordinates. Returns values in [0, 1]."""
        s = self.size
        y = np.asarray(y, dtype=np.float32) % s
        x = np.asarray(x, dtype=np.float32) % s
        z = float(z) % s
        y0 = np.floor(y).astype(int)
        x0 = np.floor(x).astype(int)
        z0 = int(math.floor(z))
        fy = y - y0
        fx = x - x0
        fz = z - z0
        fy = fy * fy * (3 - 2 * fy)
        fx = fx * fx * (3 - 2 * fx)
        fz = fz * fz * (3 - 2 * fz)
        y1 = (y0 + 1) % s
        x1 = (x0 + 1) % s
        z1 = (z0 + 1) % s
        t = self.table

        def lerp_np(a, b, f):
            return a + (b - a) * f

        c00 = lerp_np(t[y0, x0, z0], t[y0, x0, z1], fz)
        c01 = lerp_np(t[y0, x1, z0], t[y0, x1, z1], fz)
        c10 = lerp_np(t[y1, x0, z0], t[y1, x0, z1], fz)
        c11 = lerp_np(t[y1, x1, z0], t[y1, x1, z1], fz)
        c0 = lerp_np(c00, c01, fx)
        c1 = lerp_np(c10, c11, fx)
        return lerp_np(c0, c1, fy)

    def field(self, t: float, scale: float = 0.25, speed: float = 0.3, octaves: int = 2, offset: float = 0.0) -> np.ndarray:
        """Fractal noise over the whole grid, in [0, 1]."""
        acc = np.zeros((ROWS, COLS), dtype=np.float32)
        amp, total = 1.0, 0.0
        for o in range(octaves):
            k = scale * (2 ** o)
            acc += amp * self.sample(RR * k + offset, CC * k + offset * 0.7, t * speed * (o + 1) + offset)
            total += amp
            amp *= 0.5
        return acc / total


# ---------------------------------------------------------------------------
# Bitmap fonts (3x5 and 5x7) for the vertical marquee used by several projects
# ---------------------------------------------------------------------------

FONT_3x5 = {
    "A": ["010", "101", "111", "101", "101"],
    "B": ["110", "101", "110", "101", "110"],
    "C": ["011", "100", "100", "100", "011"],
    "D": ["110", "101", "101", "101", "110"],
    "E": ["111", "100", "110", "100", "111"],
    "F": ["111", "100", "110", "100", "100"],
    "G": ["011", "100", "101", "101", "011"],
    "H": ["101", "101", "111", "101", "101"],
    "I": ["111", "010", "010", "010", "111"],
    "J": ["001", "001", "001", "101", "010"],
    "K": ["101", "110", "100", "110", "101"],
    "L": ["100", "100", "100", "100", "111"],
    "M": ["101", "111", "111", "101", "101"],
    "N": ["110", "101", "101", "101", "101"],
    "O": ["010", "101", "101", "101", "010"],
    "P": ["110", "101", "110", "100", "100"],
    "Q": ["010", "101", "101", "110", "011"],
    "R": ["110", "101", "110", "101", "101"],
    "S": ["011", "100", "010", "001", "110"],
    "T": ["111", "010", "010", "010", "010"],
    "U": ["101", "101", "101", "101", "111"],
    "V": ["101", "101", "101", "101", "010"],
    "W": ["101", "101", "111", "111", "101"],
    "X": ["101", "101", "010", "101", "101"],
    "Y": ["101", "101", "010", "010", "010"],
    "Z": ["111", "001", "010", "100", "111"],
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    "!": ["010", "010", "010", "000", "010"],
    "?": ["111", "001", "011", "000", "010"],
    ".": ["000", "000", "000", "000", "010"],
    "-": ["000", "000", "111", "000", "000"],
    "'": ["010", "010", "000", "000", "000"],
    ":": ["000", "010", "000", "010", "000"],
    "<": ["001", "010", "100", "010", "001"],
    ">": ["100", "010", "001", "010", "100"],
    "+": ["000", "010", "111", "010", "000"],
    " ": ["000", "000", "000", "000", "000"],
}

FONT_5x7 = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "10001", "11001", "10101", "10011", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "10001", "01010", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    "?": ["01110", "10001", "00001", "00010", "00100", "00000", "00100"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    ",": ["00000", "00000", "00000", "00000", "01100", "00100", "01000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "'": ["01100", "00100", "01000", "00000", "00000", "00000", "00000"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "<": ["00010", "00100", "01000", "10000", "01000", "00100", "00010"],
    ">": ["01000", "00100", "00010", "00001", "00010", "00100", "01000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "#": ["01010", "01010", "11111", "01010", "11111", "01010", "01010"],
    "*": ["00000", "10101", "01110", "11111", "01110", "10101", "00000"],
    "/": ["00001", "00010", "00100", "01000", "10000", "00000", "00000"],
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "♥": ["01010", "11111", "11111", "11111", "01110", "00100", "00000"],  # heart
}


def glyph(ch: str, font: dict | None = None) -> np.ndarray:
    """Return a (h, w) float mask for a character (unknown chars -> blank)."""
    font = FONT_5x7 if font is None else font
    rows = font.get(ch.upper(), font.get("?"))
    return np.array([[1.0 if x == "1" else 0.0 for x in row] for row in rows], dtype=np.float32)


def text_mask(text: str, font: dict | None = None, gap: int = 1) -> np.ndarray:
    """Vertical stack of glyphs (one character per band) as a (H, w) mask.

    The building is only 9 windows wide, so words are shown top-to-bottom,
    one letter per band, like a vertical marquee/neon sign.
    """
    font = FONT_5x7 if font is None else font
    glyphs = [glyph(ch, font) for ch in text]
    if not glyphs:
        return np.zeros((1, 5), dtype=np.float32)
    w = glyphs[0].shape[1]
    parts = []
    for g in glyphs:
        parts.append(g)
        parts.append(np.zeros((gap, w), dtype=np.float32))
    return np.vstack(parts)


def blit_mask(canvas: Canvas, m: np.ndarray, r: int, c: int, rgb: Sequence[float], k: float = 1.0, mode: str = "max") -> None:
    """Blit a mask with its top-left corner at cell (r, c); clipped to the grid."""
    h, w = m.shape
    r0, c0 = max(0, r), max(0, c)
    r1, c1 = min(ROWS, r + h), min(COLS, c + w)
    if r1 <= r0 or c1 <= c0:
        return
    sub = m[r0 - r:r1 - r, c0 - c:c1 - c]
    col = np.asarray(rgb, dtype=np.float32) * k
    target = canvas.px[r0:r1, c0:c1]
    if mode == "max":
        np.maximum(target, sub[..., None] * col, out=target)
    else:
        target += sub[..., None] * col


class Marquee:
    """Scrolls a word vertically up the building, one letter per band."""

    def __init__(self, text: str, rgb: Sequence[float] = WHITE, speed: float = 6.0, font: dict | None = None, col: int | None = None):
        self.mask = text_mask(text, font)
        self.rgb = rgb
        self.speed = speed  # rows per second
        w = self.mask.shape[1]
        self.col = (COLS - w) // 2 if col is None else col
        self.pos = float(ROWS)  # top row of the text block (starts below the building)
        self.done = False

    def update(self, dt: float) -> None:
        self.pos -= self.speed * dt
        if self.pos + self.mask.shape[0] < 0:
            self.done = True

    def draw(self, canvas: Canvas, k: float = 1.0) -> None:
        blit_mask(canvas, self.mask, int(round(self.pos)), self.col, self.rgb, k)


def downsample(img: np.ndarray, rows: int = ROWS, cols: int = COLS) -> np.ndarray:
    """Area-average an (H, W[, C]) array down to the building grid."""
    h, w = img.shape[:2]
    ys = np.linspace(0, h, rows + 1).astype(int)
    xs = np.linspace(0, w, cols + 1).astype(int)
    out_shape = (rows, cols) + img.shape[2:]
    out = np.zeros(out_shape, dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            block = img[ys[r]:max(ys[r] + 1, ys[r + 1]), xs[c]:max(xs[c] + 1, xs[c + 1])]
            out[r, c] = block.mean(axis=(0, 1)) if block.size else 0
    return out
