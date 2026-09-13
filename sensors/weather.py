"""Exteroception: live weather + sun times for the Green Building's location
via Open-Meteo (free, no API key). Cached to weather_cache.json so the demo
still runs offline (falls back to a bundled sample).

    WeatherSensor(bus).start()   -> pushes {"type": "weather", ...} every
    few minutes: temp_c, wind_kmh, gust_kmh, precip_mm, cloud_pct,
    code (WMO weather code), is_day, sunrise, sunset (local ISO), fetched
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from typing import Optional

from common.inputs import BUS, InputBus

LAT, LON = 42.3603, -71.0893  # MIT Green Building (Building 54)
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "weather_cache.json")
SAMPLE = {"temp_c": 14.0, "wind_kmh": 18.0, "gust_kmh": 30.0, "precip_mm": 0.0, "cloud_pct": 40, "code": 2, "is_day": 0,
          "sunrise": "2026-09-13T06:22", "sunset": "2026-09-13T19:02", "fetched": 0, "source": "sample"}

URL = (f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
       "&current=temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation,cloud_cover,weather_code,is_day"
       "&daily=sunrise,sunset&timezone=America%2FNew_York&forecast_days=1")


def fetch(timeout: float = 6.0) -> Optional[dict]:
    try:
        with urllib.request.urlopen(URL, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        cur = d["current"]
        out = {"temp_c": float(cur["temperature_2m"]), "wind_kmh": float(cur["wind_speed_10m"]), "gust_kmh": float(cur.get("wind_gusts_10m", cur["wind_speed_10m"])),
               "precip_mm": float(cur["precipitation"]), "cloud_pct": float(cur["cloud_cover"]), "code": int(cur["weather_code"]), "is_day": int(cur["is_day"]),
               "sunrise": d["daily"]["sunrise"][0], "sunset": d["daily"]["sunset"][0], "fetched": time.time(), "source": "open-meteo"}
        try:
            with open(CACHE, "w") as f:
                json.dump(out, f)
        except Exception:
            pass
        return out
    except Exception as e:
        print(f"[weather] fetch failed: {e}", flush=True)
        return None


def cached() -> dict:
    try:
        with open(CACHE) as f:
            d = json.load(f)
            d["source"] = "cache"
            return d
    except Exception:
        return dict(SAMPLE)


def describe(code: int) -> str:
    if code == 0:
        return "clear"
    if code in (1, 2):
        return "partly cloudy"
    if code == 3:
        return "overcast"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 57:
        return "drizzle"
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or 85 <= code <= 86:
        return "snow"
    if code >= 95:
        return "thunderstorm"
    return "unknown"


class WeatherSensor(threading.Thread):
    def __init__(self, bus: InputBus = BUS, interval: float = 300.0, offline: bool = False):
        super().__init__(name="weather", daemon=True)
        self.bus = bus
        self.interval = interval
        self.offline = offline

    def run(self):
        while True:
            data = None if self.offline else fetch()
            if data is None:
                data = cached()
            ev = {"type": "weather"}
            ev.update(data)
            ev["desc"] = describe(int(data.get("code", 0)))
            self.bus.push(ev)
            time.sleep(self.interval)
