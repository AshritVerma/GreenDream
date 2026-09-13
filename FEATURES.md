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
| Honest match reporting: `match`, `unused_words`, `coverage` | done | `app/fallback.py::local_result` |
| `beats`: a scene is an event in time, not a held picture | done | `app/spec.py::_beats`, `app/fallback.py::BEATS` |
| Two providers behind one call; `gpt-6-astra` at high effort by default | done | `app/llm.py::call_model` |
| The sprite / no-sprite decision belongs to the model | done | `app/llm.py::SYSTEM` |
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

## Nothing you type is silently dropped

The local tier works by matching your words against a small library, which means it will often
recognise one word and have no idea about the rest. Left alone, that reads as comprehension it
does not have: "lebron dunk as 76er" unlocks a canned basketball scene off the word `dunk`, and
the jersey is gone.

So every result carries three fields that keep it honest:

- `match` — `exact`, `alias`, `fuzzy`, `lexicon`, `model`, or `blocked`
- `unused_words` — the content words it could not depict, listed for the frontend to show
- `coverage` — the fraction of your content words it actually used

and `recognizability` is discounted by coverage rather than being a flat 0.9 for any library
hit. An exact match still scores 0.9; one word out of three scores 0.72; a mood-only lexicon
answer scores 0.15-0.30. The unused words are also appended to `keywords` (so the model and the
dream composer still see them) and their mood is blended into tempo and motion, so "my exhausted
heart is racing" comes out slower than "my heart is racing" even though the library has no way
to draw exhaustion. When a leftover word names a *different* library scene, the notes say which
scene was passed over, because the building shows one thing at a time.

Digits survive normalisation, so `76er` stays `76er` in the log, the keywords and the model
prompt. It still cannot be *spelled* on the facade: the displayable word is A-Z, `!`, `?` and
space, with no digits, so a number has to become a sprite.

## Scenes happen; they do not sit there

Every field in spec-v1 describes a steady state: a motion kind with a speed, a particle density, a
flash rate, a tempo. Nothing in it can say "and then". A dunk written that way is a picture of a
basketball with a wobble applied for ten seconds — the leap and the impact, which are the entire
event, have nowhere to live. The sprite ends up carrying the meaning alone, which on a 9 x 17
facade means the building is reduced to showing its logo.

So a draft can carry `beats`: two to four phases with a position in the scene, a label, and
overrides for motion, particles, flash, brightness and `word`. A beat names only what changes and
inherits the rest. The dunk becomes:

| at | beat | what the building does |
|---|---|---|
| 0.0 | the approach | still, dim, no text |
| 0.3 | the leap | a band rising fast, sparks starting |
| 0.55 | it lands | hard shake, full flash, `DUNK!` appears |
| 0.75 | the crowd | shake easing, sparks falling, still bright |

Two properties make this safe to add before the renderer exists:

- **Additive.** `beats` is not in `required` and `schema_version` stays `spec-v1`. The base fields
  still describe the whole scene, so GreenDream's current renderer plays the held version and
  never sees the new key. Reading the beats is opt-in work on the pixel side.
- **Degrading.** Fewer than two usable beats validates to `[]` rather than to one pointless phase,
  and beats are sorted, clamped into 0-1, and nudged apart so two can never land on one instant.

The demo page plays a rough 9 x 17 animation of a draft so choreography can be judged by eye. It
is a sketch for reading drafts, not a second renderer, and it is deliberately not shared with
GreenDream.

## Whether to draw a shape at all is a judgment, so the model makes it

A sprite is up to 12 rows of 9 characters that sits in the middle of the facade for the whole
scene. On a 17 x 9 tower that is roughly 40% of the building, so a sprite is not a decoration: it
is the claim "this thing has a shape, and here it is". For a heart, an arrow, an umbrella or a ball
that claim holds. For a feeling, a season, a team, a person or a place it does not, and the tower
ends up as a billboard showing a bad icon.

No fixed rule gets this right, because it depends entirely on what was said. So the prompt hands
the decision over with the criteria stated plainly — *does this have one silhouette a stranger would
name in a glance at nine windows wide?* — and tells the model that a weak sprite is worse than
none, that letters, numbers, faces, logos and jerseys are never sprites, and that a `null` sprite
means the whole facade carries the scene through world, palette, motion, particles and flash.
`spec.validate()` still throws away sprites that are a speck, a solid slab, or featureless, so a
bad call degrades rather than reaching the windows.

That judgment is also why the default provider is OpenAI's `gpt-6-astra` at `reasoning.effort=high`
rather than the cheapest model that can fill in a schema. Anything can emit valid JSON; deciding
that "lebron dunk as 76er" wants Sixers red and a rising leap but no jersey drawing is the actual
work. Anthropic remains available behind `GD_PROVIDER=anthropic`, and both are one function,
`call_model`, whose every failure mode is identical from the caller's side: no answer, fall through
to the local tier. The building never waits on a vendor.

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
