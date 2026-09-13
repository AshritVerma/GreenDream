"""Append-only JSONL of everything accepted, plus a small query cache.

One file per local day, `data/YYYY-MM-DD.jsonl`, one line per submission. This is both the
audit log (what was said, what we made of it, which tier answered), the queue the pixel side
reads with `GET /api/queue?since=`, and the day of scenes tonight's arc is composed from.

`seq` is epoch milliseconds and increases within a process, so `since=<seq>` is a cursor a
consumer can hold across restarts without any coordination.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import settings
from .fallback import normalize

_lock = threading.Lock()
_last_seq = 0

CACHE_LIMIT = 500


def _dir() -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir


def next_seq() -> int:
    """Monotonic within the process, epoch-ms based across restarts."""
    global _last_seq
    with _lock:
        seq = max(int(time.time() * 1000), _last_seq + 1)
        _last_seq = seq
        return seq


def append(record: Dict[str, Any], day: Optional[str] = None) -> None:
    path = _dir() / f"{day or date.today().isoformat()}.jsonl"
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _read_day(day: str) -> List[Dict[str, Any]]:
    path = _dir() / f"{day}.jsonl"
    out: List[Dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue  # a torn write should not break the queue
    except OSError:
        pass
    return out


def recent(since: int = 0, limit: int = 50, days: int = 2) -> List[Dict[str, Any]]:
    """Submissions with seq > since, oldest first, looking back `days` local days."""
    today = date.today()
    rows: List[Dict[str, Any]] = []
    for back in range(days - 1, -1, -1):
        rows.extend(_read_day((today - timedelta(days=back)).isoformat()))
    rows = [r for r in rows if int(r.get("seq", 0)) > since]
    rows.sort(key=lambda r: int(r.get("seq", 0)))
    return rows[-limit:] if limit else rows


def today(limit: int = 0) -> List[Dict[str, Any]]:
    """Everything said today, oldest first: the material tonight's dream is made from."""
    rows = _read_day(date.today().isoformat())
    rows.sort(key=lambda r: int(r.get("seq", 0)))
    return rows[-limit:] if limit else rows


# --------------------------------------------------------------------------- query cache

def _cache_path() -> Path:
    return _dir() / "phrase_cache.json"


def _load_cache() -> Dict[str, Any]:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def cache_key(query: str) -> str:
    """Punctuation- and case-insensitive, so "a Rocket Launch!" hits "a rocket launch"."""
    return normalize(query)


def cache_get(key: str) -> Optional[Dict[str, Any]]:
    return _load_cache().get(key)


def cache_put(key: str, payload: Dict[str, Any]) -> None:
    """Store a model answer so an identical batch costs nothing the second time."""
    with _lock:
        cache = _load_cache()
        cache[key] = payload
        if len(cache) > CACHE_LIMIT:
            for stale in list(cache)[: len(cache) - CACHE_LIMIT]:
                cache.pop(stale, None)
        try:
            _cache_path().write_text(json.dumps(cache, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
