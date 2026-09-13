"""Settings from the environment, plus the two runtime switches the admin route flips.

Two independent controls, both readable at /api/state:

    llm_enabled   the model tier. Off (or no API key) => the local fallback answers.
    gate          "auto" closes intake at sunset, "open" keeps it open, "closed" is the
                  kill switch.

Two tokens, both unset by default (which is right on a laptop and wrong behind a tunnel):
GD_INGEST_TOKEN guards both writing and previewing, GD_ADMIN_TOKEN guards the switches and
the review queue.

`settings` is a process-wide singleton; `settings.refresh()` re-reads the environment
(the tests use it after monkeypatching os.environ).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import List, NamedTuple, Optional

ROOT = Path(__file__).resolve().parent.parent
GATE_MODES = ("auto", "open", "closed")
PROVIDERS = ("openai", "anthropic")
EFFORTS = ("low", "medium", "high", "xhigh", "max")  # astra's reasoning.effort ladder

# Two jobs, two price points. A preview is what someone sees while they are still deciding, so it
# must be fast and nearly free; a submission is going on the side of a building, so it gets the
# good model at high effort. Anthropic's Haiku has no effort dial at all, which is exactly why it
# suits the preview slot.
DEFAULT_SUBMIT = {"openai": "gpt-6-astra", "anthropic": "claude-sonnet-5"}
DEFAULT_PREVIEW = {"openai": "gpt-5.6-luna", "anthropic": "claude-haiku-4-5"}


class Tier(NamedTuple):
    """Everything one call needs to know about which brain to use."""

    kind: str
    provider: str
    model: str
    effort: str
    api_key: str


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
        # Two providers, one contract. "auto" picks whichever key is present, preferring OpenAI,
        # because the judgment this asks for (is there an iconic shape here or not?) is the part
        # worth paying a flagship for.
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        provider = os.environ.get("GD_PROVIDER", "auto").strip().lower()
        if provider not in PROVIDERS:
            provider = "openai" if openai_key or not anthropic_key else "anthropic"
        self.provider: str = provider
        self.api_key: str = openai_key if provider == "openai" else anthropic_key
        self.model: str = (os.environ.get("GD_MODEL")
                           or os.environ.get("ANTHROPIC_MODEL")
                           or DEFAULT_SUBMIT[provider]).strip()
        effort = os.environ.get("GD_REASONING_EFFORT", "high").strip().lower()
        self.reasoning_effort: str = effort if effort in EFFORTS else "high"
        self.preview_model: str = (os.environ.get("GD_PREVIEW_MODEL")
                                   or DEFAULT_PREVIEW[provider]).strip()
        preview_effort = os.environ.get("GD_PREVIEW_EFFORT", "low").strip().lower()
        self.preview_effort: str = preview_effort if preview_effort in EFFORTS else "low"
        self.preview_enabled: bool = _bool("GD_PREVIEW", True)
        self.llm_timeout: float = _float("GD_LLM_TIMEOUT", 8.0)
        self.preview_timeout: float = _float("GD_PREVIEW_TIMEOUT", 4.0)
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
        # A preview is cheap and is meant to be tried repeatedly while someone plays with their
        # wording, so it gets its own far looser allowance - but still an allowance, because it
        # is a model call.
        self.preview_rate_seconds: float = _float("GD_PREVIEW_RATE_SECONDS", 2.0)
        self.preview_per_hour: int = _int("GD_PREVIEW_PER_HOUR", 120)
        # Rate limits key on the client IP, which is only knowable behind a proxy we trust to
        # set X-Forwarded-For. Off by default: otherwise anyone can forge a fresh identity per
        # request with one header and the limit is decoration.
        self.trust_proxy: bool = _bool("GD_TRUST_PROXY", False)
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
        """True when a model call would actually be attempted."""
        return bool(self.llm_enabled and self.api_key and not self.offline)

    def tier(self, kind: str = "submit") -> Tier:
        """The brain for this job. Same provider and key either way; different model and effort."""
        preview = kind == "preview"
        return Tier(kind="preview" if preview else "submit", provider=self.provider,
                    model=self.preview_model if preview else self.model,
                    effort=self.preview_effort if preview else self.reasoning_effort,
                    api_key=self.api_key)

    def timeout(self, kind: str = "submit") -> float:
        """A preview nobody waits for is worse than no preview."""
        return self.preview_timeout if kind == "preview" else self.llm_timeout


load_dotenv()
settings = Settings()
