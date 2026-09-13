# GreenDream · the language half

The `language/` directory of the GreenDream repo: the API that reads words. Someone gets up to
five words to say what they want to see; this service turns those words into one scene the Green
Building could show. **It renders no pixels** — it stops at a validated scene draft, which is the
handoff point to the facade runtime one directory up.

Five words is the budget for one idea, not five ideas. "a rocket launch" is one query and one
scene. A day of queries becomes one story at `GET /api/arc`, which is what seeds the night.

Separate from the runtime on purpose, and still separate now that it is versioned with it:
nothing here imports the pixel half, nothing here edits it, they meet only over HTTP, and this
directory can be deployed, restarted and rate-limited without touching the thing driving 153
windows. What one repo buys is that a change to a scene lands on both sides in one commit, and
the alignment test that proves the two agree can no longer be skipped for want of the other half.

The canonical feature list for everything below is `../FEATURES.md`, at the root of the repo.

## Run it

From the repo root, once, for both halves:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r language\requirements.txt
```

Then, from this directory:

```powershell
Copy-Item .env.example .env            # optional; fill in OPENAI_API_KEY to enable the model
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8100
```

**Start it from here, not from the repo root.** The root has a top-level `app.py` (the runner) and
this directory has a top-level `app/` package, so `app.main` only means this service when
`language/` is what is first on `sys.path`. The data directory is resolved from `__file__` rather
than the cwd, so the JSONL log always lands in `language/data` either way.

A bench page for trying it by hand is at http://localhost:8100/demo, interactive API docs at
`/docs`. Tests, from this directory: `..\.venv\Scripts\python.exe -m pytest` (137 tests, no
network, no key needed). The same `app` collision is why this directory has its own `pytest.ini`
with `pythonpath = .`, and why the root suite does not collect these tests — see `HANDOFF.md`
§2.1. `tests/test_alignment.py` imports the pixel half's `library.py` and `scene.py` to prove a
draft made here plays there unchanged; it finds them in the parent directory and fails rather
than skips if they are missing (set `GREENDREAM_PATH` to compare against a checkout elsewhere).

With no key it still answers every request — see the local tier below.

## The endpoints

| Route | Purpose |
|---|---|
| `POST /api/ingest` | the only write: one query in, one scene draft out. `423` when the gate is shut |
| `POST /api/preview` | the same answer from the cheap fast model, not logged and not part of tonight |
| `GET /api/state` | what the frontend polls: phase, whether it may submit, when it reopens, live view URL |
| `GET /api/queue?since=` | what the pixel side reads: accepted scenes, oldest first, with a cursor |
| `GET /api/arc` | the day's scenes read as one story, to seed tonight's dream |
| `POST /api/admin/switch` | the off switches: `{"llm": "on"\|"off", "gate": "auto"\|"open"\|"closed"}` |
| `GET /api/health` | liveness, plus whether the model tier is actually available |

`GET /api/library` lists the 33 warm-library queries and their aliases, which is useful when
writing frontend copy or picking demo phrases.

## One query in

```bash
curl -s localhost:8100/api/ingest -H 'content-type: application/json' \
     -d '{"query": "a rocket launch", "source": "web"}'
```

Six words is a `422`, not a truncation: the constraint is the point, and the frontend should
show a word counter rather than let people write sentences.

The response:

```json
{
  "id": "9f1c2b7a4e01",
  "seq": 1789412345678,
  "received_at": "2026-09-13T14:22:10",
  "tier": "claude-haiku-4-5",
  "latency_ms": 940,
  "channel": "web",
  "priority": "dream",
  "gate": {"mode": "auto", "phase": "day", "accepting": true, "reason": "open"},
  "result": {
    "query": "a rocket launch",
    "words": ["a", "rocket", "launch"],
    "ok": true,
    "tier": "claude-haiku-4-5",
    "match": "model",
    "unused_words": [],
    "coverage": 1.0,
    "interpretation": {
      "title": "rocket launch", "theme": "event",
      "keywords": ["rocket", "fire", "ascent"],
      "word": "LIFTOFF", "mood": {"valence": 0.7, "arousal": 0.9},
      "recognizability": 0.9, "notes": "a bright column climbing out of sparks"
    },
    "spec_draft": {
      "schema_version": "spec-v1", "ok": true, "title": "rocket launch",
      "duration_s": 12, "world": "none",
      "palette": {"base": "#05070f", "accent": "#ff9f43", "glow": "#ffffff"},
      "motion": {"kind": "still", "speed": 0.5, "amount": 0.0},
      "particles": {"kind": "sparks", "density": 0.8, "direction": "up"},
      "tempo_bpm": 100, "flash": {"kind": "burst", "rate": 0.15},
      "sprite": {"rows": ["....#....", "...###...", "..."], "anim": "rise", "color": "#ffffff"},
      "word": "LIFTOFF", "mood": {"valence": 0.7, "arousal": 0.9}
    }
  }
}
```

`interpretation` is what the words mean; `spec_draft` is how to show it, in the same vocabulary
GreenDream's renderer already speaks (`scene.SCHEMA`). Keeping both means the pixel side can be
built from either without another round trip to the model.

`match`, `unused_words` and `coverage` stop the answer from pretending it understood more than it
did — the local tier will happily unlock a canned scene off one recognised word, and these fields
are how the frontend can say so out loud. See `../FEATURES.md`.

## Two tiers, one shape

1. **Claude** — one tool-use call, forced to the `perform` tool whose schema is the scene
   vocabulary. System prompt is cached, so every request after the first pays only for the
   query. Timeout 8 s.
2. **Local** — a warm library of 33 hand-written scenes with aliases and a fuzzy match, then an
   affect lexicon that maps valence and arousal onto palette, motion, particles and tempo.
   No network, no key, deterministic.

The local tier answers when the switch is off, when there is no key, when the API fails or
times out, or when its answer cannot be parsed. Only `tier` in the response changes.

```bash
# force the local tier at runtime
curl -s localhost:8100/api/admin/switch -H 'content-type: application/json' \
     -H 'x-admin-token: ...' -d '{"llm": "off"}'
```

## A day becomes one story

`GET /api/arc` reads everything said today and orders it: opening on whatever was said first,
the loudest thing next, settling into the calmest at the end. Title, logline, through line and
palette come with it. That is the seed for a dream script, and it is deliberately not part of a
submission — one query is one scene, and an arc only means something at the scale of a day.

## Sunset closes the door

With `GD_GATE=auto`, intake is open from dawn until the dusk window opens and then closed until
tomorrow's dawn, on real sun times for the building. Closed is not an error — it is a `423`
saying the building is dreaming, with `reopens_at` and a `live_view_url` for anyone who cannot
get to the plaza. Poll `GET /api/state` and swap the input for the live view before anyone sees
the 423. `GD_GATE=closed` is the kill switch; `GD_GATE=open` holds it open.

## Environment

Copy `.env.example` to `.env`. Everything has a working default except the API key and the
tokens. `.env` is gitignored; **never commit a key.**

| var | default | effect |
|---|---|---|
| `OPENAI_API_KEY` | — | enables the model tier via the Responses API |
| `ANTHROPIC_API_KEY` | — | enables it via Anthropic instead; with neither key, local only |
| `GD_PROVIDER` | `auto` | `openai` \| `anthropic` \| `auto` (whichever key exists, OpenAI first) |
| `GD_MODEL` | `gpt-6-astra` / `claude-sonnet-5` | the submit model, per provider |
| `GD_REASONING_EFFORT` | `high` | OpenAI only: `low` … `max` |
| `GD_PREVIEW_MODEL` | `gpt-5.6-luna` / `claude-haiku-4-5` | the cheap model behind `/api/preview` |
| `GD_PREVIEW_EFFORT` | `low` | effort for previews |
| `GD_PREVIEW` | `1` | `0` disables `POST /api/preview` |
| `GD_USE_LLM` | `1` | `0` forces the local tier even with a key |
| `GD_GATE` | `auto` | `auto` / `open` / `closed` |
| `GD_MAX_WORDS` / `GD_MAX_CHARS` | `5` / `60` | how much a person may say |
| `GD_INGEST_TOKEN` | — | required in `X-Ingest-Token` when set |
| `GD_ADMIN_TOKEN` | — | required in `X-Admin-Token`; unset disables the switch route |
| `GD_LIVE_VIEW_URL` | olive-koala viewer | shown when intake is closed |
| `GD_CORS_ORIGINS` | `*` | comma-separated origins |
| `GD_LAT` / `GD_LON` / `GD_TZ` | Green Building, `America/New_York` | sun times |
| `GD_RATE_SECONDS` / `GD_RATE_PER_HOUR` | `20` / `20` | per-IP limits |
| `GD_DATA_DIR` | `./data` | JSONL log, query cache, sun cache |
| `GD_OFFLINE` | `0` | `1` blocks every outbound request, sun times included |

## Handing off to pixels

`GET /api/queue?since=<cursor>` is the pull path: hold the returned `cursor` and pass it back.
`tools/push_to_greendream.py` is the push path, and it is wired: it drains the queue and posts
the finished `spec_draft` as a `spec` event to a running runner's `/input`, so the model is not
asked the same question twice. It holds a cursor and only advances past rows it actually dealt
with — `tests/test_push.py` pins that. A `spec` event drives the building, so the runner wants
its operator token in `GREENDREAM_INPUT_TOKEN`.

Run from the repo root (it speaks only HTTP; it imports nothing from either half):

```bash
python language/tools/push_to_greendream.py --api http://localhost:8100 --target http://localhost:8000 --once
python language/tools/smoke.py --api http://localhost:8100 --admin-token ...
```
