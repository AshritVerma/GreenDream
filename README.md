# greendream-llm

The language half of GreenDream, as its own service. A website collects up to five short
phrases; this API reads them together and returns what each one means and how the Green
Building would show it. **It renders no pixels** — it stops at a validated scene draft, which
is the handoff point to the facade runtime.

Independent of the GreenDream repo on purpose: nothing here imports it, nothing here edits it,
and it can be deployed, restarted, and rate-limited without touching the thing driving 153
windows. `FEATURES.md` has the switch semantics and the open questions.

## Run it

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env            # optional; fill in ANTHROPIC_API_KEY to enable the model
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8100
```

Interactive docs at http://localhost:8100/docs. Tests: `.\.venv\Scripts\python.exe -m pytest -q`
(26 tests, no network, no key required).

With no key it still answers every request — see the local tier below.

## The five endpoints

| Route | Purpose |
|---|---|
| `POST /api/ingest` | the only write: 1-5 phrases in, drafts out. `423` when the gate is shut |
| `GET /api/state` | what the frontend polls: phase, whether it may submit, when it reopens, live view URL |
| `GET /api/queue?since=` | what the pixel side reads: accepted submissions, oldest first, with a cursor |
| `POST /api/admin/switch` | the off switches: `{"llm": "on"\|"off", "gate": "auto"\|"open"\|"closed"}` |
| `GET /api/health` | liveness, plus whether the model tier is actually available |

`GET /api/library` also lists the 12 warm-library phrases and their aliases, which is useful
when writing frontend copy or picking demo phrases.

## Submitting five phrases

```bash
curl -s localhost:8100/api/ingest -H 'content-type: application/json' -d '{
  "phrases": ["a thunderstorm", "my heart is racing", "a rocket launch", "snow day", "i miss my dog"],
  "source": "web"
}'
```

The response, abbreviated:

```json
{
  "id": "9f1c2b7a4e01",
  "seq": 1789412345678,
  "tier": "claude-haiku-4-5",
  "latency_ms": 2140,
  "channel": "web",
  "priority": "dream",
  "gate": {"mode": "auto", "phase": "day", "accepting": true, "reason": "open"},
  "results": [
    {
      "index": 0,
      "phrase": "a thunderstorm",
      "ok": true,
      "tier": "claude-haiku-4-5",
      "interpretation": {
        "title": "thunderstorm", "theme": "weather",
        "keywords": ["rain", "lightning", "cloud"],
        "word": null, "mood": {"valence": -0.3, "arousal": 0.8},
        "recognizability": 0.9, "notes": "sheeting rain with lightning behind it"
      },
      "spec_draft": {
        "schema_version": "spec-v1", "ok": true, "title": "thunderstorm",
        "duration_s": 12, "world": "storm",
        "palette": {"base": "#0d1220", "accent": "#8fa6d9", "glow": "#f4f7ff"},
        "motion": {"kind": "shake", "speed": 0.6, "amount": 0.25},
        "particles": {"kind": "rain", "density": 0.9, "direction": "down"},
        "tempo_bpm": 70, "flash": {"kind": "lightning", "rate": 0.7},
        "sprite": null, "word": null, "mood": {"valence": -0.3, "arousal": 0.8}
      }
    }
  ],
  "arc": {
    "title": "DUNK!", "logline": "5 things said today: thunderstorm, racing heart, ...",
    "order": [0, 2, 1, 4, 3], "through_line": "a night of weather, opening on thunderstorm",
    "palette": {"base": "#1a0508", "accent": "#ff3b4e", "glow": "#ffd6d9"}
  }
}
```

`interpretation` is what the phrase means; `spec_draft` is how to show it, in the same
vocabulary GreenDream's renderer already speaks (`scene.SCHEMA`). Keeping both means the
pixel side can be built from either without another round trip to the model.

## Two tiers, one shape

1. **Claude** — one tool-use call for the whole batch, so the five phrases are read together
   and the `arc` is worth something. System prompt is cached; timeout 8 s.
2. **Local** — a warm library of 12 hand-written scenes with aliases and a fuzzy match, then
   an affect lexicon that maps valence and arousal onto palette, motion, particles and tempo.
   No network, no key, deterministic.

The local tier answers when the switch is off, when there is no key, when the API fails or
times out, or when its answer cannot be parsed. Only `tier` in the response changes.

```bash
# force the local tier at runtime
curl -s localhost:8100/api/admin/switch -H 'content-type: application/json' \
     -H 'x-admin-token: ...' -d '{"llm": "off"}'
```

## Sunset closes the door

With `GD_GATE=auto`, intake is open from dawn until the dusk window opens and then closed
until tomorrow's dawn, on real sun times for the building. Closed is not an error — it is a
`423` saying the building is dreaming, with `reopens_at` and a `live_view_url` for anyone who
cannot get to the plaza. Poll `GET /api/state` and swap the form for the live view before
anyone sees the 423. `GD_GATE=closed` is the kill switch; `GD_GATE=open` holds it open.

## Environment

Copy `.env.example` to `.env`. Everything has a working default except the API key and the
tokens. `.env` is gitignored; **never commit a key.**

| var | default | effect |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | enables the model tier; absent means local only |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | model for the batched call |
| `GD_USE_LLM` | `1` | `0` forces the local tier even with a key |
| `GD_GATE` | `auto` | `auto` / `open` / `closed` |
| `GD_INGEST_TOKEN` | — | required in `X-Ingest-Token` when set |
| `GD_ADMIN_TOKEN` | — | required in `X-Admin-Token`; unset disables the switch route |
| `GD_LIVE_VIEW_URL` | olive-koala viewer | shown when intake is closed |
| `GD_CORS_ORIGINS` | `*` | comma-separated origins |
| `GD_LAT` / `GD_LON` / `GD_TZ` | Green Building, `America/New_York` | sun times |
| `GD_RATE_SECONDS` / `GD_RATE_PER_HOUR` | `20` / `20` | per-IP limits |
| `GD_MAX_PHRASES` / `GD_MAX_PHRASE_CHARS` | `5` / `120` | request caps |
| `GD_DATA_DIR` | `./data` | JSONL log and phrase cache |
| `GD_OFFLINE` | `0` | `1` blocks every outbound request, sun times included |

## Handing off to pixels

`GET /api/queue?since=<cursor>` is the pull path: hold the returned `cursor` and pass it back.
`tools/push_to_greendream.py` is the push path, written but not wired — it reads the queue and
posts `{"type": "text", ...}` to a running GreenDream's `/input`, which is vocabulary that
instance already understands. When the renderer learns to accept a finished draft, it should
send `spec_draft` instead so the model is not asked the same question twice.

```bash
python tools/push_to_greendream.py --api http://localhost:8100 --target http://localhost:8000 --once
```
