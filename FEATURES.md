# Features

What this service does today, what each switch does, and what is deliberately left open.
It is independent of the GreenDream repo: nothing here imports it, and nothing here edits it.

## What it does

Someone types up to five words. This service reads them as **one thing to show** and returns an
**interpretation** (what it means) and a **spec draft** (how the building would show it). It
renders nothing; the pixel side comes later. A day of those scenes becomes one **arc** at
`GET /api/arc`, which is the seed for that night's dream.

| Feature | State | Where |
|---|---|---|
| One query of up to 5 words, 6 words rejected | done | `app/models.py::IngestRequest` |
| Claude tier: one tool-use call, cached system prompt | done, never run against the real API | `app/llm.py` |
| Local tier: warm library of 12 scenes, then an affect lexicon | done, fully offline | `app/fallback.py` |
| Spec draft validated and clamped on every path | done | `app/spec.py::validate` |
| Day-level arc (quiet open, loud middle, quiet close) | done | `app/fallback.py::compose_arc`, `GET /api/arc` |
| Sunset gate with a "the building is dreaming" 423 | done | `app/sun.py`, `app/gate.py` |
| Manual kill switch and LLM off switch at runtime | done | `POST /api/admin/switch` |
| Blocklist moderation, before any API call | done | `app/fallback.py::BLOCKLIST` |
| Per-IP rate limit (gap + hourly cap) | done | `app/ratelimit.py` |
| JSONL audit log, one file per day | done | `app/store.py` |
| Queue endpoint with a cursor for the pixel side | done | `GET /api/queue?since=` |
| Identical queries served from a disk cache | done | `app/store.py::cache_get` |
| Frontend state endpoint (phase, accepting, live view) | done | `GET /api/state` |
| Bench page: one query box, word counter, the draft, the arc | done | `GET /demo` |
| Push script into a running GreenDream | written, not wired | `tools/push_to_greendream.py` |

## Why five words and not five phrases

Because the building shows one thing at a time, and the hard part is choosing that one thing.
Five words is enough for "a thunderstorm over the river" and not enough for a paragraph, which
keeps the model's job narrow: read the words as a single idea, pick the single most recognisable
depiction. The frontend should show a word counter, since `422` on the sixth word is deliberate
rather than a truncation.

The arc lives at the scale of a day for the same reason. Ordering five unrelated ideas inside
one submission would be arbitrary; ordering everything a city said today is the actual story.

## The three switches

They are independent, and all three are visible at `GET /api/state`.

**1. The LLM switch — "if we don't want to use the API".**

```
GD_USE_LLM=0                                          # at startup
POST /api/admin/switch {"llm": "off"}                 # at runtime
```

Off means the local tier answers everything: warm library first, affect lexicon second. The
response shape is identical, only `tier` changes (`library` / `lexicon` instead of the model
id). The same path is taken automatically when there is no `ANTHROPIC_API_KEY`, when
`GD_OFFLINE=1`, when the API errors, when it times out (8 s), and when its answer cannot be
parsed. The service has no failure mode where a query gets no answer.

**2. The gate — closes at sunset.**

```
GD_GATE=auto     open from dawn until the dusk window opens, then closed until tomorrow's dawn
GD_GATE=open     held open (testing, or a night demo)
GD_GATE=closed   the kill switch
```

`auto` is driven by real sun times for the building's coordinates from Open-Meteo, cached to the
data directory, with a bundled sample as a last resort. Dawn and dusk are 30-minute windows
centred on sunrise and sunset, matching the facade's own choreography, so intake shuts as the
building starts falling asleep. A stale table (the sample, or an old cache) has its times moved
onto today rather than reading as permanent night.

When the gate is shut, `POST /api/ingest` answers **423** rather than an error:

```json
{
  "state": "dreaming",
  "message": "the building is dreaming. come back at dawn, or watch tonight's dream.",
  "phase": "night",
  "reason": "sunset",
  "reopens_at": "2026-09-14T06:08:00",
  "live_view_url": "https://sundai.willsarg.com/olive-koala?view=street",
  "now": "2026-09-13T22:30:00"
}
```

The frontend should poll `GET /api/state` and swap the input for the live view before anyone
sees a 423. `live_view_url` exists precisely for the person who cannot get to the plaza.

**3. The tokens.**

`GD_INGEST_TOKEN` gates `POST /api/ingest` (header `X-Ingest-Token`); empty means open, which is
fine locally and not fine behind a tunnel. `GD_ADMIN_TOKEN` gates the switch route
(`X-Admin-Token`); empty disables that route entirely rather than leaving it open.

## What the model is and is not trusted with

Trusted to choose a depiction. Not trusted with anything that reaches the windows:

- every spec goes through `spec.validate()`, whatever tier produced it: enums checked, numbers
  clamped, colours parsed, sprites measured (a speck or a solid slab is thrown away)
- `word` is the only text the facade may show, and it is 1-7 characters of A-Z, `!`, `?` and
  space. A query comes back as one word or nothing.
- `ok: false` from the model, or a blocklist hit, becomes a shrug scene, and blocklist hits are
  never sent to the API at all
- any failure of the model path returns the local draft; nothing is dropped

## Deliberately open

- **Interpretation and spec both.** We keep both halves until the renderer exists, so the pixel
  side can be built from either. `schema_version: "spec-v1"` is on every draft; when the
  renderer disagrees with it, that is the signal to version rather than guess.
- **Handoff direction.** `GET /api/queue?since=` (pull) is built. `tools/push_to_greendream.py`
  (push, as `text` events into a running instance) is written but not wired. Once the renderer
  accepts a finished draft, the push should send the draft and stop making the model answer the
  same query twice.
- **Review queue.** Remote queries are stored with `review: "pending"` and `priority: "dream"`;
  on-site sources (`pedestal`, `onsite`, `qr`, `plaza`) get `priority: "live"`. Nothing consumes
  those flags yet. That is the asymmetry from the handoff: presence is the price of immediacy,
  participation is free.
- **Live view is a link, not a relay.** `/api/state` hands out a URL. A real relay (proxying the
  runtime's SSE frame stream so the website can draw the facade itself) is a separate job.
- **Rate limits are per instance**, held in memory. Two instances behind a load balancer would
  each allow the full rate; for one building that is not worth solving.
- **The blocklist is small on purpose.** Widen it before a public show, and decide then whether
  remote queries go in unmoderated or through the review flag.
- **Nothing calls the real API yet.** The Claude path is exercised only by a stubbed tool answer
  in the tests. First run with a key: check tier and latency on a handful of queries, and
  confirm the sprite rows come back as exactly 9 characters.
