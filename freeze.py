"""The kill switch's route in when there is no browser: a sentinel file, and a signal.

`freeze` is an ordinary event on the bus, so the control panel and `POST /input` already
reach it. Neither of those is much use at 9pm on a plaza with a tunnel that has gone
sideways, so this module adds two paths that need no page, no port and no token:

    touch FREEZE       # the facade holds on the next frame
    rm FREEZE          # it comes back
    kill -USR1 <pid>   # toggle, where the platform has SIGUSR1 (not Windows)

The file is the one to teach an operator, because it is the only route that survives every
other thing being broken — it works over ssh, from a phone with a shell on it, from a line
in somebody else's script, and from the machine's own console with the network down. A file
left in place also outlives a restart, which is what you want: a crash-restart during an
incident comes back frozen rather than coming back showing the thing you froze it for.

Nothing here touches the canvas or blocks; it is one `os.path.exists` every 250 ms on a
thread that pushes events, per the frame-loop rule in CLAUDE.md.
"""

from __future__ import annotations

import os
import threading

from common.inputs import BUS, InputBus

FREEZE_FILE = os.environ.get("GREENDREAM_FREEZE_FILE", "FREEZE")
POLL_S = 0.25

# Set from a signal handler, so it must be a bare assignment and nothing else: a handler
# that took the bus's lock could deadlock against a poll() on the main thread, and a kill
# switch that can hang is not a kill switch. The watcher thread does the actual push.
_toggle_pending = False


def _on_signal(*_) -> None:
    global _toggle_pending
    _toggle_pending = True


def install_signal_toggle() -> str:
    """Make SIGUSR1 toggle the freeze. Returns the signal name, or "" where there is none.

    Must be called from the main thread (``App.setup`` is). Windows has no SIGUSR1, and a
    missing one is not a problem worth reporting — the file route is the documented one.
    """
    try:
        import signal

        sig = getattr(signal, "SIGUSR1", None)
        if sig is None:
            return ""
        signal.signal(sig, _on_signal)
        return "SIGUSR1"
    except (AttributeError, OSError, ValueError):
        return ""


class FreezeWatcher(threading.Thread):
    """Watch the sentinel file and push a ``freeze`` event when it appears or disappears.

    Edge-triggered on the file's existence, starting from "absent", so a file that is
    already there when the process starts fires a freeze on the first poll.
    """

    def __init__(self, bus: InputBus = BUS, path: str = FREEZE_FILE, poll_s: float = POLL_S):
        super().__init__(name="freeze-watch", daemon=True)
        self.bus = bus
        self.path = path
        self.poll_s = poll_s
        self.state = False
        self._stop = threading.Event()

    def present(self) -> bool:
        if not self.path:
            return False
        try:
            return os.path.exists(self.path)
        except OSError:
            return False

    def poll_once(self) -> bool:
        """One check of both routes. True if an event was pushed."""
        global _toggle_pending
        if _toggle_pending:
            _toggle_pending = False
            self.bus.push({"type": "freeze", "toggle": True, "source": "signal"})
            return True
        now = self.present()
        if now != self.state:
            self.state = now
            self.bus.push({"type": "freeze", "on": now, "source": "file"})
            return True
        return False

    def run(self) -> None:
        while not self._stop.wait(self.poll_s):
            try:
                self.poll_once()
            except Exception as e:  # a watcher that dies silently is worse than a noisy one
                print(f"[freeze] watch failed: {e}", flush=True)

    def stop(self) -> None:
        self._stop.set()
