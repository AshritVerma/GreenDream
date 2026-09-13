"""The API. One query of up to five words in, one validated scene draft out.

    POST /api/ingest         the only write. 423 with a "dreaming" body when the gate is shut.
    GET  /api/state          what the frontend polls: phase, whether it may submit, live view.
    GET  /api/queue?since=   what the pixel side reads: accepted scenes, oldest first.
    GET  /api/arc            the day's scenes read as one story, to seed tonight's dream.
    POST /api/admin/switch   the off switches: the Claude tier and the intake gate.
    GET  /api/health         liveness.

No pixels are rendered here. The service stops at a validated draft.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from . import fallback, gate, llm, ratelimit, store, sun
from .demo import DEMO_PAGE
from .config import settings
from .models import (ArcResponse, GateInfo, IngestRequest, IngestResponse, SceneResult,
                     StateResponse, SwitchRequest)

SUN_REFRESH_S = 1800.0

# Previews are cheap and are meant to be tried repeatedly while someone plays with their wording,
# so they get their own far looser allowance.
PREVIEW_SECONDS = 2.0
PREVIEW_PER_HOUR = 120


async def _sun_loop() -> None:
    """Keep the sun table warm off the request path."""
    while True:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(sun.refresh)
        await asyncio.sleep(SUN_REFRESH_S)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_sun_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="GreenDream LLM ingest",
    version="0.1.0",
    summary="Phrases from the web become validated scene drafts for the Green Building.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type", "x-ingest-token", "x-admin-token"],
)


# --------------------------------------------------------------------------- helpers

def require_ingest_token(x_ingest_token: Optional[str] = Header(None)) -> None:
    """Shared secret for the frontend. Unset means open, which is fine locally."""
    if settings.ingest_token and x_ingest_token != settings.ingest_token:
        raise HTTPException(status_code=401, detail="invalid or missing X-Ingest-Token")


def require_admin_token(x_admin_token: Optional[str] = Header(None)) -> None:
    if not settings.admin_token:
        raise HTTPException(status_code=403, detail="admin route disabled: set GD_ADMIN_TOKEN")
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="invalid or missing X-Admin-Token")


def client_id(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def priority_for(source: str) -> str:
    """Presence is the price of immediacy: on-site prompts perform live, remote ones dream."""
    return "live" if source in ("pedestal", "onsite", "qr", "plaza") else "dream"


# --------------------------------------------------------------------------- routes

@app.get("/")
def index() -> Dict[str, Any]:
    g = gate.state()
    return {
        "service": "greendream-llm",
        "accepting": g["accepting"],
        "phase": g["phase"],
        "endpoints": ["POST /api/ingest", "POST /api/preview", "GET /api/state", "GET /api/queue", "GET /api/arc",
                      "POST /api/admin/switch", "GET /api/health"],
        "demo": "/demo",
        "docs": "/docs",
    }


@app.get("/demo", response_class=HTMLResponse, include_in_schema=False)
def demo() -> str:
    """A bench for trying the API by hand. Not the product frontend."""
    return DEMO_PAGE


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "llm_available": settings.llm_available, "gate": settings.gate}


@app.get("/api/state", response_model=StateResponse)
def state() -> StateResponse:
    g = gate.state()
    return StateResponse(
        phase=str(g["phase"]), accepting=bool(g["accepting"]), reason=str(g["reason"]),
        gate_mode=str(g["mode"]), message=str(g["message"]), now=str(g["now"]),
        sunrise=g["sunrise"], sunset=g["sunset"], closes_at=g["closes_at"], reopens_at=g["reopens_at"],
        sun_source=str(g["sun_source"]),
        llm_enabled=settings.llm_available,
        tier=settings.model if settings.llm_available else "local",
        provider=settings.provider if settings.llm_available else "",
        live_view_url=settings.live_view_url,
        max_words=settings.max_words, max_chars=settings.max_chars,
    )


@app.post("/api/ingest", response_model=IngestResponse, dependencies=[Depends(require_ingest_token)])
def ingest(req: IngestRequest, request: Request):
    g = gate.state()
    if not g["accepting"]:
        return JSONResponse(status_code=423, content=gate.closed_payload(g))

    allowed, retry_after = ratelimit.check(client_id(request))
    if not allowed:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={"state": "too_many", "message": "one at a time; the tower is listening to someone else.",
                     "retry_after_s": retry_after},
        )

    key = store.cache_key(req.query)
    cached = store.cache_get(key)
    if cached:
        result = SceneResult(**cached["result"])
        tier, latency_ms = f"{cached['tier']}-cached", 0
    else:
        result, tier, latency_ms = llm.ingest(req.query)
        if tier not in ("library", "lexicon", "blocked"):
            store.cache_put(key, {"result": result.model_dump(), "tier": tier})

    priority = priority_for(req.source)
    payload = IngestResponse(
        id=uuid.uuid4().hex[:12], seq=store.next_seq(), received_at=str(g["now"]),
        tier=tier, latency_ms=latency_ms, channel=req.source, priority=priority,
        gate=GateInfo(mode=str(g["mode"]), phase=str(g["phase"]), accepting=True, reason=str(g["reason"])),
        result=result,
    )

    record = payload.model_dump()
    record["session_id"] = req.session_id
    # Remote queries are dream material and stay flagged for review; the composer can skip
    # anything unapproved without us losing it.
    record["review"] = "pending" if priority == "dream" else "auto"
    store.append(record)
    return payload


@app.post("/api/preview", response_model=IngestResponse)
def preview(req: IngestRequest, request: Request):
    """What these words might look like, cheaply, before anyone commits to them.

    Same validation, same gate, same moderation as a submission, and deliberately less than a
    submission in every other way: the fast model, a short timeout, nothing written to the day's
    log, nothing in tonight's arc, and a separate cache so a preview can never be promoted into
    the real answer. A preview is a guess about the building, not a claim on it.
    """
    if not settings.preview_enabled:
        raise HTTPException(status_code=404, detail="previews are switched off")

    g = gate.state()
    if not g["accepting"]:
        return JSONResponse(status_code=423, content=gate.closed_payload(g))

    allowed, retry_after = ratelimit.check(f"preview:{client_id(request)}", per_hour=PREVIEW_PER_HOUR,
                                           seconds=PREVIEW_SECONDS)
    if not allowed:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={"state": "too_many", "message": "give it a moment to think.",
                     "retry_after_s": retry_after},
        )

    key = store.cache_key(req.query, "preview")
    cached = store.cache_get(key)
    if cached:
        result, tier, latency_ms = SceneResult(**cached["result"]), f"{cached['tier']}-cached", 0
    else:
        result, tier, latency_ms = llm.ingest(req.query, kind="preview")
        if tier not in ("library", "lexicon", "blocked"):
            store.cache_put(key, {"result": result.model_dump(), "tier": tier})

    return IngestResponse(
        id=uuid.uuid4().hex[:12], seq=0, received_at=str(g["now"]),
        tier=tier, latency_ms=latency_ms, channel=req.source, priority="preview", preview=True,
        gate=GateInfo(mode=str(g["mode"]), phase=str(g["phase"]), accepting=True, reason=str(g["reason"])),
        result=result,
    )


@app.get("/api/queue")
def queue(since: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    """Accepted scenes for the pixel side. Hold `cursor` and pass it back as `since`."""
    rows: List[Dict[str, Any]] = store.recent(since=since, limit=limit)
    cursor = max([int(r.get("seq", 0)) for r in rows], default=since)
    return {"cursor": cursor, "count": len(rows), "submissions": rows}


@app.get("/api/arc", response_model=ArcResponse)
def arc(limit: int = Query(40, ge=1, le=200)) -> ArcResponse:
    """Everything said today, read as one story. This is what seeds tonight's dream.

    A single query is one scene; the arc only exists at the scale of a day, so it lives here
    rather than in the ingest response.
    """
    scenes: List[SceneResult] = []
    for row in store.today(limit=limit):
        try:
            scenes.append(SceneResult(**row["result"]))
        except (KeyError, TypeError, ValueError):
            continue  # an older or torn line should not break the arc
    live = [s for s in scenes if s.ok]
    return ArcResponse(count=len(live), scenes=[s.query for s in live],
                       arc=fallback.compose_arc(scenes))


@app.post("/api/admin/switch", dependencies=[Depends(require_admin_token)])
def switch(req: SwitchRequest) -> Dict[str, Any]:
    """Flip the Claude tier and the intake gate at runtime. No restart, no redeploy."""
    if req.llm is None and req.gate is None:
        raise HTTPException(status_code=400, detail="send llm and/or gate")
    if req.llm is not None:
        settings.set_llm(req.llm == "on")
    if req.gate is not None:
        settings.set_gate(req.gate)
    g = gate.state()
    return {"llm_enabled": settings.llm_enabled, "llm_available": settings.llm_available,
            "gate_mode": settings.gate, "accepting": g["accepting"], "phase": g["phase"],
            "message": g["message"]}


@app.get("/api/library")
def library() -> Dict[str, Any]:
    """The warm library: what the local tier can depict without a key, and the model's standard."""
    return {"count": len(fallback.LIBRARY),
            "phrases": {k: {"theme": v["theme"], "title": v["spec"]["title"]} for k, v in fallback.LIBRARY.items()},
            "aliases": fallback.ALIASES}
