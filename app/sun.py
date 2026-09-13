"""Sun times for the building, because sunset is what closes the door.

Open-Meteo (free, no key) gives sunrise and sunset for today and tomorrow in the building's
own local time, plus the UTC offset. Keeping the offset means we never need a timezone
database on the host: local now is just UTC now plus the offset.

Cached to disk and held in memory. A request never waits on this: `refresh()` runs on a
background task and every reader falls back to the cache and then to a bundled sample, so
the gate keeps working with no internet at all.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

from .config import settings


def cache_path() -> Path:
    """Beside the data, not in the repo: two instances with different coordinates must not
    overwrite each other's table, and the tests must not read a stale one."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / "sun_cache.json"

# Late-September Cambridge, so an offline host is at most a few minutes wrong.
SAMPLE: Dict[str, object] = {
    "sunrise": ["2026-09-13T06:22", "2026-09-14T06:23"],
    "sunset": ["2026-09-13T19:02", "2026-09-14T19:00"],
    "utc_offset_seconds": -14400,
    "fetched": 0.0,
    "source": "sample",
}

URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
       "&daily=sunrise,sunset&timezone={tz}&forecast_days=2")

_lock = threading.Lock()
_state: Optional[Dict[str, object]] = None

# The transition window around sunrise and sunset, matching the facade's dawn/dusk phases.
WINDOW = timedelta(minutes=15)


def _parse(s: object) -> Optional[datetime]:
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def fetch(timeout: float = 6.0) -> Optional[Dict[str, object]]:
    """Ask Open-Meteo. Returns None on any failure; callers fall back to the cache."""
    if settings.offline:
        return None
    url = URL.format(lat=settings.lat, lon=settings.lon, tz=settings.tz.replace("/", "%2F"))
    req = urllib.request.Request(url, headers={"user-agent": "greendream-llm/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        daily = data["daily"]
        out: Dict[str, object] = {
            "sunrise": list(daily["sunrise"]),
            "sunset": list(daily["sunset"]),
            "utc_offset_seconds": int(data.get("utc_offset_seconds", 0)),
            "fetched": time.time(),
            "source": "open-meteo",
        }
    except Exception as e:
        print(f"[sun] fetch failed ({type(e).__name__}: {e})", flush=True)
        return None
    try:
        cache_path().write_text(json.dumps(out), encoding="utf-8")
    except OSError:
        pass
    return out


def cached() -> Dict[str, object]:
    try:
        data = json.loads(cache_path().read_text(encoding="utf-8"))
        if data.get("sunrise") and data.get("sunset"):
            data["source"] = "cache"
            return data
    except (OSError, ValueError):
        pass
    return dict(SAMPLE)


def refresh() -> Dict[str, object]:
    """Fetch and adopt, or fall back. Safe to call from a background task."""
    global _state
    data = fetch() or cached()
    with _lock:
        _state = data
    return data


def times() -> Dict[str, object]:
    """The current sun table. Refreshes lazily if it is a day old, never blocking a request
    for more than one fetch timeout."""
    global _state
    with _lock:
        state = _state
    if state is None:
        return refresh()
    if float(state.get("fetched") or 0) < time.time() - 21600 and state.get("source") != "open-meteo":
        return refresh()
    return state


def local_now(state: Optional[Dict[str, object]] = None) -> datetime:
    """Now, in the building's local wall clock, as a naive datetime (matching Open-Meteo)."""
    state = state or times()
    offset = int(state.get("utc_offset_seconds") or 0)
    return (datetime.now(timezone.utc) + timedelta(seconds=offset)).replace(tzinfo=None)


def _same_time_today(when: datetime, now: datetime) -> datetime:
    """Move a stale sunrise/sunset onto today, keeping its time of day.

    A table from another date (the bundled sample, or a cache written weeks ago) is still
    roughly right about *when* the sun sets. Without this, a stale table reads as permanent
    night and the gate never opens.
    """
    return now.replace(hour=when.hour, minute=when.minute, second=0, microsecond=0)


def _today_pair(state: Dict[str, object], now: datetime):
    """Today's sunrise and sunset, plus the next sunrise after `now`."""
    rises = [d for d in (_parse(s) for s in state.get("sunrise", [])) if d]
    sets = [d for d in (_parse(s) for s in state.get("sunset", [])) if d]
    if not rises or not sets:
        return None, None, None

    rise = next((d for d in rises if d.date() == now.date()), _same_time_today(rises[0], now))
    dusk = next((d for d in sets if d.date() == now.date()), _same_time_today(sets[0], now))
    next_rise = next((d for d in rises if d > now), None) or (
        rise if rise > now else rise + timedelta(days=1))
    return rise, dusk, next_rise


def snapshot(now: Optional[datetime] = None) -> Dict[str, object]:
    """Everything the gate and /api/state need, computed once.

    phase: dawn and dusk are 30-minute windows centred on sunrise and sunset, matching the
    facade's own choreography, so intake closes as the building starts falling asleep.
    """
    state = times()
    now = now or local_now(state)
    rise, dusk, next_rise = _today_pair(state, now)

    if rise is None or dusk is None:
        return {"phase": "day", "now": now.isoformat(timespec="seconds"), "sunrise": None,
                "sunset": None, "closes_at": None, "reopens_at": None,
                "source": str(state.get("source", "sample"))}

    if rise - WINDOW / 2 <= now < rise + WINDOW / 2:
        phase = "dawn"
    elif dusk - WINDOW / 2 <= now < dusk + WINDOW / 2:
        phase = "dusk"
    elif rise + WINDOW / 2 <= now < dusk - WINDOW / 2:
        phase = "day"
    else:
        phase = "night"

    closes = dusk - WINDOW / 2
    return {
        "phase": phase,
        "now": now.isoformat(timespec="seconds"),
        "sunrise": rise.isoformat(timespec="seconds"),
        "sunset": dusk.isoformat(timespec="seconds"),
        "closes_at": closes.isoformat(timespec="seconds") if now < closes else None,
        "reopens_at": (next_rise - WINDOW / 2).isoformat(timespec="seconds") if next_rise else None,
        "source": str(state.get("source", "sample")),
    }
