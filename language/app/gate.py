"""The off switch.

Three ways intake closes, in precedence order:

    gate = "closed"   the kill switch. Closed regardless of the sky.
    gate = "auto"     open from dawn until the dusk window opens; closed once the building
                      starts falling asleep, reopening at tomorrow's dawn.
    gate = "open"     held open for testing or for a night demo.

Closed is not an error. The frontend is expected to poll /api/state, show that the building
is dreaming, and offer the live view instead of the form.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from . import sun
from .config import settings

DREAMING = "the building is dreaming. come back at dawn, or watch tonight's dream."
RESTING = "the building is resting. intake is switched off."
AWAKE = "the building is awake. tell it what you want to see."

OPEN_PHASES = ("dawn", "day")


def state(now: Optional[datetime] = None) -> Dict[str, object]:
    """One dict describing the gate and the sky. Cheap enough to call per request."""
    sky = sun.snapshot(now)
    mode = settings.gate

    if mode == "closed":
        accepting, reason, message = False, "kill-switch", RESTING
    elif mode == "open":
        accepting, reason, message = True, "forced-open", AWAKE
    else:
        accepting = sky["phase"] in OPEN_PHASES
        reason = "open" if accepting else "sunset"
        message = AWAKE if accepting else DREAMING

    return {
        "mode": mode,
        "phase": sky["phase"],
        "accepting": accepting,
        "reason": reason,
        "message": message,
        "now": sky["now"],
        "sunrise": sky["sunrise"],
        "sunset": sky["sunset"],
        "closes_at": sky["closes_at"] if accepting else None,
        "reopens_at": None if accepting else sky["reopens_at"],
        "sun_source": sky["source"],
    }


def closed_payload(gate: Dict[str, object]) -> Dict[str, object]:
    """The body of the 423. Everything the frontend needs to explain itself."""
    return {
        "state": "dreaming" if gate["reason"] == "sunset" else "off",
        "message": gate["message"],
        "phase": gate["phase"],
        "reason": gate["reason"],
        "reopens_at": gate["reopens_at"],
        "sunset": gate["sunset"],
        "now": gate["now"],
        "live_view_url": settings.live_view_url,
    }
