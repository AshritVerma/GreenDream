# Features

What the language half does today, what each switch does, and what is deliberately left open.
This is the canonical feature list for the language half, and it is now in the same repository
as the code it describes: the service is the `language/` directory of this repo. Paths below are
relative to `language/`. The two halves still do not import each other — they meet over HTTP —
they just version and ship together.

## What it does

Someone types up to five words. This service reads them as **one thing to show** and returns an
**interpretation** (what it means) and a **spec draft** (how the building would show it). It
renders nothing; the pixel side comes later. A day of those scenes becomes one **arc** at
`GET /api/arc`, which is the seed for that night's dream.

| Feature | Where |
|---|---|
| One query of up to 5 words, 6 words rejected | `app/models.py::IngestRequest` |
| Honest match reporting: `match`, `unused_words`, `coverage` | `app/fallback.py::local_result` |
| `beats`: a scene is an event in time, not a held picture | `app/spec.py::_beats`, `app/fallback.py::BEATS` |
| Two providers behind one call, two price tiers | `app/llm.py::call_model` |
| Cheap preview vs paid submission | `POST /api/preview` |
| The sprite / no-sprite decision belongs to the model | `app/llm.py::SYSTEM` |
| Model tier: one forced tool call, cached system prompt (never run against the real API) | `app/llm.py` |
| Local tier: warm library of 33 scenes, then an affect lexicon (fully offline) | `app/fallback.py` |
| Phrase-first matcher on word boundaries, with negation and capped fuzzy | `app/fallback.py::match` |
| Spec draft validated and clamped on every path | `app/spec.py::validate` |
| Day-level arc (quiet open, loud middle, quiet close) | `app/fallback.py::compose_arc`, `GET /api/arc` |
| Sunset gate with a "the building is dreaming" 423 | `app/sun.py`, `app/gate.py` |
| Manual kill switch and LLM off switch at runtime | `POST /api/admin/switch` |
| Blocklist moderation, before any API call | `app/fallback.py::BLOCKLIST` |
| Contact details scrubbed before anything is logged | `app/fallback.py::scrub_pii` |
| Per-IP rate limit (gap + hourly cap), `X-Forwarded-For` only behind a trusted proxy | `app/ratelimit.py`, `GD_TRUST_PROXY` |
| JSONL audit log, one file per day; review decisions appended, applied on read | `app/store.py` |
| Queue endpoint with a cursor, refusals filtered out for the pixel side | `GET /api/queue?since=` |
| Operator review queue: approve or reject a pending row | `GET`+`POST /api/admin/review` |
| Identical queries served from a disk cache | `app/store.py::cache_get` |
| Frontend state endpoint (phase, accepting, live view) | `GET /api/state` |
| Bench page: one query box, word counter, the draft, the arc | `GET /demo` |
| `gpt-6-astra` wire (written, never run live) | `app/llm.py::_openai` |
| Push into a running GreenDream as `spec` events, with the operator token | `tools/push_to_greendream.py` |
| Proof the two halves agree, scene for scene | `tests/test_alignment.py` |

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

That judgment is also why the model tier matters more than a schema-filler would: anything can emit
valid JSON, but deciding that "lebron dunk as 76er" wants Sixers red and a rising leap and *no*
jersey drawing is the actual work.

## Two price tiers, because a guess and a commitment are different things

Somebody standing at the kiosk trying wordings should not be spending the same money as somebody
who has decided. So there are two calls:

| | `POST /api/preview` | `POST /api/ingest` |
|---|---|---|
| model | `GD_PREVIEW_MODEL`, cheapest available | `GD_MODEL`, the good one |
| effort | `low` | `high` |
| timeout | 4 s — nobody waits for a guess | 8 s |
| rate limit | one every 2 s, 120/hour | one every 20 s, 20/hour |
| written to the day's log | no | yes |
| part of tonight's arc | no | yes |

Same key, same provider, same validation, same gate, same blocklist. The two caches are separate
namespaces (`preview:` and `submit:` prefixes) specifically so a cheap guess can never be promoted
into the answer that goes on the building. A preview comes back marked `preview: true` with
`priority: "preview"`, so a frontend can show it as provisional, and `GD_PREVIEW=0` turns the
endpoint off entirely.

Current defaults, on an Anthropic key: `claude-haiku-4-5` ($1/$5 per Mtok, and no reasoning dial at
all, which is exactly what a preview wants) for previews, `claude-sonnet-5` ($2/$10, effort already
defaults to high) for submissions.

Both providers are one function, `call_model`, whose every failure mode is identical from the
caller's side: no answer, fall through to the local tier. The building never waits on a vendor.

## Later: move the submit tier to gpt-6-astra

The intended end state for a submission is OpenAI's `gpt-6-astra` at `reasoning.effort=high`. That
code path is written and tested against a stubbed Responses API; it has never run against the real
one. To switch:

```powershell
$env:OPENAI_API_KEY = "sk-..."   # or put it in .env, which is gitignored
$env:GD_PROVIDER = "openai"      # or leave it "auto", which prefers OpenAI when the key exists
```

That is the whole change: `GD_MODEL` and `GD_PREVIEW_MODEL` default per provider, so submissions go
to `gpt-6-astra` at high effort and previews to `gpt-5.6-luna` at low. Worth knowing before
flipping it — astra is $10/$50 per Mtok against Sonnet 5's $2/$10, which lands around 3-5 cents per
submission once the system prompt is cached. Fine for a plaza on a Friday night, less fine as a
default nobody remembers leaving on, which is why `xhigh` and `max` are accepted by the config but
are not the default.

Open question for when that happens: whether the reference specs in the system prompt
(`thunderstorm` and `rocket launch`, sent as the standard to match) should be rewritten by the
better model, or stay hand-written as the house style.

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

- **Interpretation and spec both.** We keep both halves, so the pixel side can be built from
  either. `schema_version: "spec-v1"` is on every draft; `tests/test_alignment.py` proves
  GreenDream's `scene.validate()` leaves a draft from here unchanged apart from dropping that
  key, so a disagreement is a test failure rather than a surprise on the building.
- **The duplicated library is deliberate.** `app/fallback.py` mirrors the pixel half's
  `library.py` so the service answers with nothing but `language/` on the path — one directory
  is deployable on its own even though it is versioned here. The alignment test compares them
  field for field; edit one and you must edit the other.
- **Both directions of the handoff now work.** `GET /api/queue?since=` is the pull;
  `tools/push_to_greendream.py` is the push, and it sends the finished `spec_draft` as a `spec`
  event with its tier, channel and priority, so the model is not asked the same query twice.
- **Live view is a link, not a relay.** `/api/state` hands out a URL. A real relay (proxying the
  runtime's SSE frame stream so the website can draw the facade itself) is a separate job.
- **Rate limits are per instance**, held in memory. Two instances behind a load balancer would
  each allow the full rate; for one building that is not worth solving.
- **`GET /api/arc` still returns the queries.** They are scrubbed and moderated by then, and the
  dream composer writes its notes from them ("a huge thunderstorm came back"), so the text is the
  useful part. Escaping is therefore the render site's job, and the bench does it in one place.
- **Nothing calls the real API yet.** The model path is exercised only by a stubbed tool answer
  in the tests. First run with a key: check tier and latency on a handful of queries, and
  confirm the sprite rows come back as exactly 9 characters.

## Backlog

Everything below came out of an end-to-end probe on 13 September 2026: roughly 150 queries plus
every operational path, run over HTTP against a clean instance with rate limits off and a throwaway
data directory.

**Items 1-6 are now fixed** and the record of what was wrong is kept below, because the failures
are the argument for the tests that now hold them shut. What remains open is in §7.

### Settled policy: what the building refuses

Two questions the probe forced, now decided:

- **Self-harm is an ordinary refusal.** "i want to die" gets the same treatment as any other
  blocklist hit: `spec.shrug()`, the grey shake and `HMM?`. Deliberately *not* a special "care"
  scene and not a support-message channel — the facade's only vocabulary for "no" is the shrug, and
  inventing a second kind of refusal would make the building look like it is diagnosing people.
- **No campaigning and no advertising.** "free palestine", "trump 2028", "buy bitcoin now" are all
  refusals, same shrug. The building is not a billboard and not a placard.

If a human support message is ever wanted, the frontend is the place for it: it already knows a
refusal happened, and it is the only surface that can say something longer than seven characters.

### 1. Safety and the trust boundary — fixed

The moderation gaps, with the two decisions above defining the target:

| query | was | now |
|---|---|---|
| `i want to die` | lexicon `neutral`, word `OK` | blocked shrug |
| `free palestine`, `trump 2028`, `buy bitcoin now` | lexicon `neutral` | blocked shrug |
| `john smith is a loser`, `sarah call me` | lexicon `neutral` | blocked (private person) |
| `kill the ref`, `the killer bees` | blocked | allowed; both are innocent |
| `555 123 4567`, `bob@example.com` | stored verbatim in the day's JSONL | scrubbed before the log |

The false positives and the misses had the same root cause: `is_blocked` matched substrings, so
"kill" fired inside "killer bees" while a whole category like self-harm had no entry at all. The
private-person rule existed only in the model's system prompt, which means it disappeared in
exactly the situation the local tier is for — the vendor being down.

**Fixed.** `BLOCKLIST` is now a word-boundary regex organised by category (violence with a target,
hate, sexual content, self-harm, campaigning, advertising, harassment, profanity), and the violent
verbs only fire when they have a target, so "kill the lights" is a lighting cue and "kill everyone"
is not. `scrub_pii` runs inside the request validator, before anything is logged, so emails, links,
phone numbers and handles never enter the archive. Both repos screen, and
`tests/test_alignment.py::test_the_blocklist_agrees_on_the_cases_that_matter` fails if they
disagree; `tests/test_safety.py` holds the category table above.

The raw-text leak is fixed at the render site rather than by removing data: the bench has one
`esc()` helper and every interpolation of a query, title, note or message goes through it, checked
by `test_the_bench_escapes_everything_it_renders`. `GET /api/arc` still returns the queries on
purpose — see "Deliberately open" above.

### 2. The matcher — fixed (seven bugs, one rewrite)

`lookup()` matched substrings, in the wrong order, against an index missing half of what it should
contain. Every row here was the same rewrite:

| query | was | the bug |
|---|---|---|
| `sunset` | the *sunrise* scene, 0% coverage, 0.35 | "sun" matched inside "sunset"; also semantically backwards |
| `supercalifragilisticexpialidocious` | the *up* scene | "up" matched at index 1 |
| `snö` | *sunrise* at **0.9** | normalised to "sn", which difflib matched to "sun" |
| `happy birthday` | *joy*, not the birthday scene | the word pass ran before the phrase pass, so "happy" won |
| `its my birthday` | `neutral`, with "birthday" reported unused | library *keys* were not in the per-word index |
| `the crowd goes wild` | `neutral` | library *keywords* were not in the index either |
| `thundrstorm`, `snowww` | right scene, punished to 0.35 | coverage counted literal tokens, so a typo read as unused |
| `basket ball` | *a dunk* at **0.9** | a fuzzy hit had no confidence ceiling |

**Fixed.** `match()` is now: exact key or alias → longest alias phrase on word boundaries → single
words from an index built from keys, keywords, titles and aliases (a word that could mean two
scenes is dropped rather than guessed at, and an emotion word loses to a concrete noun in the same
phrase) → a per-word typo pass → a whole-phrase fuzzy pass. `sunset` is its own scene. A negated
word never matches. `tests/test_scene.py` and the shared matcher test in `test_alignment.py` cover
the table; `test_a_bare_substring_is_not_a_match` is specifically the "supper" → *up* bug.

### 3. Negation in the affect lexicon — fixed

`i'm not sad` returned the sad scene with the word `AWW`; `not happy at all` returned the joy
scene. Nothing read "not", "never" or "no" — they were just unmatched tokens, so the sentiment
landed exactly backwards.

**Fixed.** `lexicon_affect` looks two words back for a negator and flips the valence and the
emotion through an `OPPOSITE` table; the matcher refuses a negated word, so "not snow" no longer
reaches the snow scene either. Both repos share the behaviour, checked by
`test_the_lexicon_agrees_on_mood`.

### 4. Library breadth — fixed

Of 59 realistic queries, **36 (61%) came back as `neutral` with the word `OK`**, and **48 (81%)
scored recognizability at or below 0.35**. Thirteen reached the warm library. Twelve scenes were
carrying a whole city.

The misses were not exotic — they are the first things anyone would type:

- **Local sport and place:** `go sox`, `celtics in 7`, `bruins goal`, `beat harvard`, `the green
  line`, `the T is late`, `charles river`
- **Holidays and milestones:** `merry christmas`, `eid mubarak`, `graduation day`, `i got the job`,
  `she said yes`, `welcome home`, `good luck tomorrow`
- **Common objects and sky:** `fireworks`, `full moon`, `a rainbow`, `a red balloon`, `a cat`,
  `a tree`, `an umbrella`, `the northern lights`
- **Open invitations:** `surprise me`, `anything`, `show me something`

`OK` also needed to stop being the default text. "The building shrugs politely" was the single most
common thing it said, and `OK` on nine windows is the least interesting two letters available.

**Fixed.** The library is 33 scenes with 18 of them choreographed, covering every bullet above,
and the aliases grew with it. `EMOTION_WORD["neutral"]` is now `None`: a mood the building cannot
name is a colour, not a sign. Every advertised key is reachable by saying it
(`test_every_advertised_scene_is_reachable`) and so is every alias.

### 5. The queue contract — fixed

Two loose ends where the pixel side would have got this wrong through no fault of its own. Blocked
submissions were stored and served by `GET /api/queue` with `ok: false` and the refused text kept
verbatim, and nothing in the contract said a consumer must filter them. The arc was composed over
the *unfiltered* list, so shrugs coloured the night. And `review: "pending"` was write-only: there
was no endpoint that could move a row to approved, so a careful consumer would correctly have drawn
nothing at all.

**Fixed.** `/api/queue` filters refusals and rejected rows by default (`?include_refused=true`
returns them), and the cursor still advances past what it filtered, so a skipped row is not retried
forever. The arc skips rejected rows. `GET`/`POST /api/admin/review` list and decide pending rows;
because the log is append-only, a decision is written as its own line and applied when the day is
read, so nothing is ever rewritten and "we said no to this" is kept too.

### 6. Operational polish — fixed

- **Preview limits were hardcoded and undiscoverable.** Four rapid previews all returned 429 on an
  instance with rate limits explicitly turned off. Now `GD_PREVIEW_RATE_SECONDS` and
  `GD_PREVIEW_PER_HOUR`, and previews sit behind `GD_INGEST_TOKEN` as well — a preview is a model
  call, so an open preview endpoint is an open API budget.
- **`/api/library` over-promised**, advertising scenes the matcher could not reach through natural
  phrasing. Now tested: every key and every alias reaches its scene.
- **Some scenes opened too dark to read as alive.** `sunrise` sat at brightness 0.15 for its first
  4.8 seconds. Earning the bright moment is right, but from the street a near-black tower reads as
  broken, and it is the first thing a passer-by sees. `spec.validate()` now floors every beat at
  `BEAT_FLOOR = 0.3`, on both sides, so no model or library entry can ask for less.
- **`X-Forwarded-For` was believed unconditionally**, so anyone could mint a fresh identity per
  request with one header. Now only trusted when `GD_TRUST_PROXY` says there is a proxy in front.

### 7. Still open

- **Nothing has run against a real API key.** Items 2-4 were fallback-quality problems that the
  model tier would largely have masked; the model path itself is still only exercised by a stubbed
  tool answer. First run with a key: check tier and latency on a handful of queries, and confirm
  the sprite rows come back as exactly 9 characters.
- **`/api/state` does not publish the rate limits**, so a frontend cannot pace itself; it gets a
  429 and has to guess. `max_words` and `max_chars` are published, these should be too.
- **The golden set.** 40 phrases rated 1-5 for "would a stranger recognise it", promoting 4+ into
  the library. That is the only way to know whether the 33 scenes are the right 33.
- **Review before dusk is manual.** There is an endpoint and a list, but no page; an operator
  works through it with curl. A small admin page would take an hour and would be used on the night.
- **Rate limits and caches are per instance**, in memory. Fine for one building.

### What the probe confirmed working

The operational half held up without qualification. The gate, the kill switch, admin auth (401 on a
bad token) and the 423 payload with its `live_view_url` all behave as documented, and `/api/arc` and
`/api/queue` stay readable while intake is shut. Drafts are fully deterministic: `a thunderstorm`
and `A THUNDERSTORM!!!` produce byte-identical specs. Preview and submission are properly separated
— previews never reach the log, the queue or the arc, the `preview:` / `submit:` cache namespacing
holds, and a blocklist hit is refused identically on both endpoints. Validation is clean: a sixth
word is a `422` with a usable message, empty input is rejected, and `<script>`, SQL fragments, emoji
and CJK cannot reach the facade because `word` is clamped to A-Z, `!` and `?`.

One caveat over all of the quality findings: there is no API key on this machine, so every result
came from the local tier. Items 2, 3 and 4 were fallback-quality problems that the model tier would
largely have masked. Items 1 and 5 were not masked at all — moderation runs *before* any model
call, and the raw-text leak was in the arc and the demo page, where no model is involved.

### The end-to-end run, 13 September 2026

After the fixes, all three processes were run together against a clean data directory and driven
over HTTP: the service on `:8100`, GreenDream on `:8001` with an operator token, and `render.py` on
`:8110` in `--ingest` mode. What it confirmed:

- A phrase typed at the preview is interpreted by the service and rendered here — one reading of
  the words, not two. `not snow` and `supper` both correctly fall through to a mood rather than
  reaching the snow and *up* scenes.
- On-site sources perform live; remote ones are stored as `dream` and wait for review.
- `kill everyone` is refused, filtered out of the queue, and still present in the log.
- `email me at bob@example.com` is stored, and reaches GreenDream's journal, as
  `email me at someone`.
- `push_to_greendream.py` without the operator token gets a 401 and says which variable to set;
  with it, five drafts arrive as `spec` events and appear in `/api/journal` with their channel,
  tier and priority.
- Forced to dusk, the runner composed a seven-act dream out of that day's real material and played
  it, recoloured and inverted, on the facade.

The run found one bug worth its own note. **The pusher advanced its cursor past rows it had not
sent.** On a 401 it stopped sending — correctly — and then returned the page's cursor anyway, so
every row after the refused one was skipped for good. In daemon mode that is silent data loss of
exactly the material the piece is made of: the queue is the only copy of what somebody typed.
The cursor now only moves past rows that were actually dealt with, a dead runner stops the drain
rather than burning the page, and a row the runner rejects on its own merits is stepped over so
one bad draft cannot wedge the queue behind it. `tests/test_push.py` (12 tests) pins all three
against fakes; the one that matters is "fix the token, run again, and the rows still arrive".

A second pass, with the fix in and frames recorded, confirmed the pixels rather than just the
JSON: the tower holds its warm idle glow, cuts to the storm — cold blue-grey across all 153
windows — and later to the fireflies drifting gold, which is the same order the journal claims.
The journal line now also carries `world` and `word`, so it can answer what the building actually
showed rather than only what it was asked.
