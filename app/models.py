"""Request and response shapes. These are the contract the frontend builds against.

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
    """What the phrase means, before anyone decides how to draw it."""

    title: str = Field("", max_length=60, description="2-4 words: what would be shown")
    theme: str = Field("", max_length=40, description="one-word family: weather, feeling, place, object, event")
    keywords: List[str] = Field(default_factory=list, description="3-5 concrete nouns to draw from")
    word: Optional[str] = Field(None, description="the only text the facade may show: 1-7 chars of A-Z ! ?")
    mood: Mood = Field(default_factory=Mood)
    recognizability: float = Field(0.5, ge=0, le=1, description="would a stranger 300 m away recognise it")
    notes: str = Field("", max_length=280)


class PhraseResult(BaseModel):
    index: int
    phrase: str
    ok: bool = True
    tier: str = Field(..., description="the model id, 'library', 'lexicon', or 'blocked'")
    interpretation: Interpretation
    spec_draft: Dict[str, Any]


class Arc(BaseModel):
    """The five phrases read as one story, shaped to seed a dream script later."""

    title: str = Field("DREAM", description="<=7 chars, A-Z ! ? only")
    logline: str = Field("", max_length=280)
    order: List[int] = Field(default_factory=list, description="phrase indices in performance order")
    through_line: str = Field("", max_length=140)
    palette: Dict[str, str] = Field(default_factory=dict)


class GateInfo(BaseModel):
    mode: str
    phase: str
    accepting: bool
    reason: str


class IngestRequest(BaseModel):
    phrases: List[str] = Field(..., min_length=1, max_length=5)
    source: str = Field("web", max_length=32)
    session_id: Optional[str] = Field(None, max_length=64)

    @field_validator("phrases")
    @classmethod
    def _clean(cls, v: List[str]) -> List[str]:
        out: List[str] = []
        for raw in v:
            if not isinstance(raw, str):
                continue
            text = re.sub(r"[\x00-\x1f\x7f]", " ", raw)
            text = re.sub(r"\s+", " ", text).strip()[: settings.max_phrase_chars]
            if text:
                out.append(text)
        if not out:
            raise ValueError("at least one non-empty phrase is required")
        return out

    @field_validator("source")
    @classmethod
    def _slug(cls, v: str) -> str:
        return re.sub(r"[^a-z0-9_-]", "", v.lower()) or "web"


class IngestResponse(BaseModel):
    id: str
    seq: int
    received_at: str
    tier: str = Field(..., description="the tier that answered the batch")
    latency_ms: int
    channel: str = Field("web", description="where the phrases came from")
    priority: str = Field("dream", description="'dream' = remote, dream material only; 'live' = on-site")
    gate: GateInfo
    results: List[PhraseResult]
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
    max_phrases: int = 5
    max_phrase_chars: int = 120


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
