"""Per-client rate limit: a minimum gap between submissions and an hourly cap.

Bounds both abuse and the API bill, since one submission is one model call. In-process and
therefore per-instance; a second instance behind a load balancer would need shared state,
which is not worth it for one building.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from .config import settings

_lock = threading.Lock()
_hits: Dict[str, Deque[float]] = {}
HOUR = 3600.0


def check(client: str, now: float = 0.0, seconds: Optional[float] = None,
          per_hour: Optional[int] = None) -> Tuple[bool, int]:
    """(allowed, retry_after_seconds). Records the hit when allowed.

    `seconds` and `per_hour` override the configured limits, so a cheap preview can be allowed to
    run far more often than a submission that costs real money and a slot on the building.
    """
    now = now or time.time()
    gap = settings.rate_seconds if seconds is None else seconds
    cap = settings.rate_per_hour if per_hour is None else per_hour
    if gap <= 0 and cap <= 0:
        return True, 0

    with _lock:
        q = _hits.setdefault(client, deque())
        while q and q[0] < now - HOUR:
            q.popleft()
        if q and gap > 0 and now - q[-1] < gap:
            return False, max(1, int(gap - (now - q[-1]) + 0.999))
        if cap > 0 and len(q) >= cap:
            return False, max(1, int(HOUR - (now - q[0]) + 0.999))
        q.append(now)
        if len(_hits) > 5000:  # keep the table from growing without bound
            for key in [k for k, v in _hits.items() if not v or v[-1] < now - HOUR]:
                _hits.pop(key, None)
        return True, 0


def reset() -> None:
    with _lock:
        _hits.clear()
