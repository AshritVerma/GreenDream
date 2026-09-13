"""A tiny thread-safe event bus that every input source pushes into.

Sources: the browser simulator page (mouse / keys / buttons / text), phone
pages, sensor threads (camera, microphone, weather), or scripted demo
timelines. Apps call ``bus.poll()`` once per frame and get a list of dicts,
each with at least a ``"type"`` key.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Dict, List


class InputBus:
    def __init__(self, maxlen: int = 4096):
        self._q: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self.listeners: List[Callable[[dict], None]] = []

    def push(self, event: Dict) -> None:
        if "t" not in event:
            event["t"] = time.time()
        with self._lock:
            self._q.append(event)
        for fn in list(self.listeners):
            try:
                fn(event)
            except Exception:  # listeners must never kill an input thread
                pass

    def poll(self) -> List[Dict]:
        with self._lock:
            items = list(self._q)
            self._q.clear()
        return items

    def clear(self) -> None:
        with self._lock:
            self._q.clear()


# Process-wide default bus. Sensors and the web server push here.
BUS = InputBus()


class Timeline:
    """Scripted events for hardware-free demos: ``[(t_seconds, event_dict), ...]``.

    ``tick(t)`` pushes every event whose time has passed (in order) into the bus.
    Used by each project's ``demo_script()`` so the recorded demo shows the
    behaviour without a camera, microphone or phone.
    """

    def __init__(self, events, bus: InputBus = BUS, loop: float | None = None):
        self.events = sorted(events, key=lambda e: e[0])
        self.bus = bus
        self.loop = loop
        self._i = 0
        self._offset = 0.0

    def tick(self, t: float) -> None:
        tt = t - self._offset
        while self._i < len(self.events) and self.events[self._i][0] <= tt:
            ev = dict(self.events[self._i][1])
            ev.setdefault("source", "timeline")
            self.bus.push(ev)
            self._i += 1
        if self.loop and tt >= self.loop:
            self._offset += self.loop
            self._i = 0
