"""Settings from the environment, plus the two runtime switches the admin route flips.

Two independent controls, both readable at /api/state:

    llm_enabled   the Claude tier. Off (or no API key) => the local fallback answers.
    gate          "auto" closes intake at sunset, "open" keeps it open, "closed" is the
                  kill switch.

`settings` is a process-wide singleton; `settings.refresh()` re-reads the environment
(the tests use it after monkeypatching os.environ).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
GATE_MODES = ("auto", "open", "closed")


def load_dotenv(path: Optional[Path] = None) -> None:
    """Minimal .env loader: KEY=value lines, existing environment wins."""
    p = path or (ROOT / ".env")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(float(os.environ[name]))
    except (KeyError, ValueError):
        return default


class Settings:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.refresh()

    def refresh(self) -> None:
        self.api_key: str = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.model: str = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5").strip()
        self.llm_timeout: float = _float("GD_LLM_TIMEOUT", 8.0)
        self.llm_enabled: bool = _bool("GD_USE_LLM", True)
        gate = os.environ.get("GD_GATE", "auto").strip().lower()
        self.gate: str = gate if gate in GATE_MODES else "auto"
        self.ingest_token: str = os.environ.get("GD_INGEST_TOKEN", "").strip()
        self.admin_token: str = os.environ.get("GD_ADMIN_TOKEN", "").strip()
        self.live_view_url: str = os.environ.get(
            "GD_LIVE_VIEW_URL", "https://sundai.willsarg.com/olive-koala?view=street"
        ).strip()
        self.cors_origins: List[str] = [
            o.strip() for o in os.environ.get("GD_CORS_ORIGINS", "*").split(",") if o.strip()
        ] or ["*"]
        self.lat: float = _float("GD_LAT", 42.3603)
        self.lon: float = _float("GD_LON", -71.0893)
        self.tz: str = os.environ.get("GD_TZ", "America/New_York").strip()
        self.rate_seconds: float = _float("GD_RATE_SECONDS", 20.0)
        self.rate_per_hour: int = _int("GD_RATE_PER_HOUR", 20)
        # One submission is one thing to show, said in at most this many words.
        self.max_words: int = _int("GD_MAX_WORDS", 5)
        self.max_chars: int = _int("GD_MAX_CHARS", 60)
        self.data_dir: Path = Path(os.environ.get("GD_DATA_DIR", str(ROOT / "data")))
        self.offline: bool = _bool("GD_OFFLINE", False)  # skip every outbound request

    # --- runtime switches ---------------------------------------------------
    def set_llm(self, on: bool) -> None:
        with self._lock:
            self.llm_enabled = bool(on)

    def set_gate(self, mode: str) -> None:
        if mode not in GATE_MODES:
            raise ValueError(f"gate must be one of {GATE_MODES}")
        with self._lock:
            self.gate = mode

    @property
    def llm_available(self) -> bool:
        """True when a Claude call would actually be attempted."""
        return bool(self.llm_enabled and self.api_key and not self.offline)


load_dotenv()
settings = Settings()
