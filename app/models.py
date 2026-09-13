"""Request and response shapes. These are the contract the frontend builds against.

One submission is one thing to show: a query of at most five words, in, and one scene draft
out. Five words is the whole budget for the idea, not five separate ideas.

`spec_draft` is deliberately a plain dict: `spec.validate()` already guarantees its shape,
and keeping it unmodelled here means the scene vocabulary can grow on the renderer side
without a second schema to keep in sync.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from .config import settings


class Mood(BaseModel):
    valence: float = Field(0.0, ge=-1, le=1)
    arousal: float = Field(0.5, ge=0, le=1)


class Interpretation(BaseModel):
    """What the query means, before anyone decides how to draw it."""

    title: str = Field("", max_length=60, description="2-4 words: what would be shown")
    theme: str = Field("", max_length=40, description="one-word family: weather, feeling, place, object, event")
    keywords: List[str] = Field(default_factory=list, description="3-5 concrete nouns to draw from")
    word: Optional[str] = Field(None, description="the only text the facade may show: 1-7 chars of A-Z ! ?")
    mood: Mood = Field(default_factory=Mood)
    recognizability: float = Field(0.5, ge=0, le=1, description="would a stranger 300 m away recognise it")
    notes: str = Field("", max_length=280)


class SceneResult(BaseModel):
    """One query, one thing the building would become.

    `match`, `unused_words` and `coverage` exist so the answer cannot quietly pretend it
    understood more than it did. A canned scene unlocked by one word out of four says so.
    """

    query: str
    words: List[str] = Field(default_factory=list)
    ok: bool = True
    tier: str = Field(..., description="the model id, 'library', 'lexicon', or 'blocked'")
    match: str = Field("", description="how it was reached: model | exact | alias | fuzzy | lexicon | blocked")
    unused_words: List[str] = Field(default_factory=list, description="words it could not depict")
    coverage: float = Field(1.0, ge=0, le=1, description="fraction of the content words it could use")
    interpretation: Interpretation
    spec_draft: Dict[str, Any]


class GateInfo(BaseModel):
    mode: str
    phase: str
    accepting: bool
    reason: str


class IngestRequest(BaseModel):
    query: str = Field(..., description="the one thing to show, in at most five words")
    source: str = Field("web", max_length=32)
    session_id: Optional[str] = Field(None, max_length=64)

    @field_validator("query")
    @classmethod
    def _clean(cls, v: str) -> str:
        text = re.sub(r"[\x00-\x1f\x7f]", " ", str(v))
        text = re.sub(r"\s+", " ", text).strip()[: settings.max_chars]
        if not text:
            raise ValueError("say something")
        words = text.split(" ")
        if len(words) > settings.max_words:
            raise ValueError(f"at most {settings.max_words} words; got {len(words)}")
        return text

    @field_validator("source")
    @classmethod
    def _slug(cls, v: str) -> str:
        return re.sub(r"[^a-z0-9_-]", "", v.lower()) or "web"


class IngestResponse(BaseModel):
    id: str
    seq: int
    received_at: str
    tier: str = Field(..., description="the tier that answered")
    latency_ms: int
    channel: str = Field("web", description="where the query came from")
    priority: str = Field("dream", description="'dream' = remote, dream material only; 'live' = on-site")
    gate: GateInfo
    result: SceneResult


class Arc(BaseModel):
    """A day of queries read as one story, shaped to seed a dream script.

    Not part of a submission: it is composed over everything said today, which is the only
    scale at which an arc means anything.
    """

    title: str = Field("DREAM", description="<=7 chars, A-Z ! ? only")
    logline: str = Field("", max_length=280)
    order: List[int] = Field(default_factory=list, description="indices into `scenes`, in performance order")
    through_line: str = Field("", max_length=140)
    palette: Dict[str, str] = Field(default_factory=dict)


class ArcResponse(BaseModel):
    count: int
    scenes: List[str] = Field(default_factory=list, description="the queries, in the order they were said")
    arc: Arc


class StateResponse(BaseModel):
    """Polled by the frontend so it can show the dreaming state instead of hitting a 423."""

    phase: str
    accepting: bool
    reason: str
    gate_mode: str
    message: str
    now: str
    sunrise: Optional[str] = None
    sunset: Optional[str] = None
    closes_at: Optional[str] = None
    reopens_at: Optional[str] = None
    sun_source: str = "sample"
    llm_enabled: bool = False
    tier: str = "local"
    live_view_url: str = ""
    max_words: int = 5
    max_chars: int = 60


class SwitchRequest(BaseModel):
    llm: Optional[str] = Field(None, description="'on' | 'off'")
    gate: Optional[str] = Field(None, description="'auto' | 'open' | 'closed'")

    @field_validator("llm")
    @classmethod
    def _llm(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip().lower()
        if v not in ("on", "off"):
            raise ValueError("llm must be 'on' or 'off'")
        return v

    @field_validator("gate")
    @classmethod
    def _gate(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip().lower()
        if v not in ("auto", "open", "closed"):
            raise ValueError("gate must be 'auto', 'open', or 'closed'")
        return v
