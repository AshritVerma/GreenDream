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
| Two providers behind one call, two price tiers | done | `app/llm.py::call_model` |
| Cheap preview vs paid submission | done | `POST /api/preview` |
| The sprite / no-sprite decision belongs to the model | done | `app/llm.py::SYSTEM` |
| Model tier: one forced tool call, cached system prompt | done, never run against the real API | `app/llm.py` |
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

## Backlog, in priority order

Everything below came out of an end-to-end probe on 13 September 2026: roughly 150 queries plus
every operational path, run over HTTP against a clean instance with rate limits off and a throwaway
data directory. Nothing here is fixed yet. Each item gives the evidence, the place that would
change, and what would prove it fixed.

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

### 1. Safety and the trust boundary

The moderation gaps, with the two decisions above now defining the target:

| query | today | should be |
|---|---|---|
| `i want to die` | lexicon `neutral`, word `OK` | blocked shrug |
| `free palestine`, `trump 2028`, `buy bitcoin now` | lexicon `neutral` | blocked shrug |
| `john smith is a loser`, `sarah call me` | lexicon `neutral` | blocked (private person) |
| `kill the ref`, `the killer bees` | blocked | allowed; both are innocent |
| `555 123 4567`, `bob@example.com` | stored verbatim in the day's JSONL | scrubbed before the log |

The false positives and the misses have the same root cause: `is_blocked` matches substrings, so
"kill" fires inside "killer bees" while a whole category like self-harm has no entry at all. The
private-person rule exists only in the model's system prompt, which means it disappears in exactly
the situation the local tier is for — the vendor being down. **Where:** `app/fallback.py::BLOCKLIST`
and `is_blocked`; PII scrubbing sits between `local_result` and `store.append`. **Check:** the
five-row table above passes, and no digit run of seven or more survives into a stored `query`.

Separately, and worse, raw user text escapes the trust boundary. `app/main.py:250` returns
`scenes=[s.query for s in live]`, so `GET /api/arc` hands back the untouched query; the probe got
`<script>alert(1)</script>`, `<img src=x>`, `555 123 4567` and `i want to die` back out of it. The
demo page then interpolates that into `innerHTML` at `app/demo.py:463` with no escaping. The scene
card is careful with its own copy of the query (`app/demo.py:398` escapes `<`), so the arc path is
an inconsistency rather than a policy: one route escapes, the other does not. Note also that
`title` and `notes` are model-controlled free text rendered the same way, so they become injectable
the moment the model tier is switched on. **Where:** `app/main.py::arc` (return validated titles,
not queries) and every interpolation in `app/demo.py::refreshArc` / `render`. **Check:** submit
`<img src=x onerror=...>` and then `GET /api/arc` — the response carries no user-supplied text, and
`#arcout` gains no element node from it.

### 2. Rewrite the matcher lookup — seven bugs, one fix

`lookup()` matches substrings, in the wrong order, against an index missing half of what it should
contain. Every row here is the same rewrite:

| query | today | the bug |
|---|---|---|
| `sunset` | the *sunrise* scene, 0% coverage, 0.35 | "sun" matches inside "sunset"; also semantically backwards |
| `supercalifragilisticexpialidocious` | the *up* scene | "up" matches at index 1 |
| `snö` | *sunrise* at **0.9** | normalises to "sn", which difflib matches to "sun" |
| `happy birthday` | *joy*, not the birthday scene | the word pass runs before the phrase pass, so "happy" wins |
| `its my birthday` | `neutral`, with "birthday" reported unused | library *keys* are not in the per-word index |
| `the crowd goes wild` | `neutral` | library *keywords* are not in the index either |
| `thundrstorm`, `snowww` | right scene, punished to 0.35 | coverage counts literal tokens, so a typo reads as unused |
| `basket ball` | *a dunk* at **0.9** | a fuzzy hit has no confidence ceiling |

**Where:** `app/fallback.py::lookup`, `understood_by`, and the coverage arithmetic in
`local_result`. **Check:** word-boundary matching only; the phrase pass first with the longest match
winning; keys and keywords in the index; fuzzy refused below three characters and capped around 0.6
however good the coverage looks; and `thundrstorm` scoring like the word it obviously meant.

### 3. Negation in the affect lexicon

`i'm not sad` returns the sad scene with the word `AWW`. `not happy at all` returns the joy scene.
Nothing reads "not", "never" or "no" — they are just unmatched tokens, so the sentiment lands
exactly backwards. **Where:** `app/fallback.py::lexicon_affect` (and the alias pass, since "not
happy" currently reaches a library scene). **Check:** `i'm not sad` and `not happy at all` both come
back with valence on the other side of zero from their un-negated forms.

### 4. Library breadth

Of 59 realistic queries, **36 (61%) came back as `neutral` with the word `OK`**, and **48 (81%)
scored recognizability at or below 0.35**. Thirteen reached the warm library. Twelve scenes are
carrying a whole city.

The misses are not exotic — they are the first things anyone would type:

- **Local sport and place:** `go sox`, `celtics in 7`, `bruins goal`, `beat harvard`, `the green
  line`, `the T is late`, `charles river`
- **Holidays and milestones:** `merry christmas`, `eid mubarak`, `graduation day`, `i got the job`,
  `she said yes`, `welcome home`, `good luck tomorrow`
- **Common objects and sky:** `fireworks`, `full moon`, `a rainbow`, `a red balloon`, `a cat`,
  `a tree`, `an umbrella`, `the northern lights`
- **Open invitations:** `surprise me`, `anything`, `show me something`

`OK` also needs to stop being the default text. "The building shrugs politely" is currently the
single most common thing it says, and `OK` on nine windows is the least interesting two letters
available. **Where:** `app/fallback.py::LIBRARY`, `ALIASES`, `BEATS`, and `EMOTION_WORD`.
**Check:** rerun the same 59 queries and have fewer than 20% land on `neutral`, with no scene
answering more than about a fifth of them.

### 5. The queue contract

Two loose ends where the pixel side would get this wrong through no fault of its own. Blocked
submissions are stored and served by `GET /api/queue` with `ok: false` and the refused text kept
verbatim, and nothing in the contract says a consumer must filter them — the probe's day log held
four such rows. Relatedly, `app/main.py:251` composes the arc over the *unfiltered* list, so
shrugs colour the night even though `count` and `scenes` filter on `ok`. And `review: "pending"` is
write-only: every row the probe produced carried it, and there is no endpoint that can move a row
to approved, so a careful consumer would correctly draw nothing at all. **Where:**
`app/main.py::queue` and `::arc`, plus whatever approves a row. **Check:** `/api/queue` either
omits `ok: false` rows or documents the filter, the arc is composed only over `live`, and one call
can approve a pending row.

### 6. Operational polish

- **Preview limits are hardcoded and undiscoverable.** `PREVIEW_SECONDS = 2.0` and
  `PREVIEW_PER_HOUR = 120` are module constants in `app/main.py`; four rapid previews all returned
  429 on an instance with rate limits explicitly turned off. Type-ahead preview cannot work against
  that, and `/api/state` publishes `max_words` and `max_chars` but no rate limits, so a frontend
  cannot even pace itself. **Check:** both limits configurable, and a frontend can read them.
- **`/api/library` over-promises.** It advertises twelve scenes including `birthday` and
  `my heart is racing`, several of which the matcher cannot reach through natural phrasing (see
  item 2). **Check:** every advertised key is reachable by at least one sentence a person would say.
- **Some scenes open too dark to read as alive.** `sunrise` sits at brightness 0.15 for its first
  **4.8 seconds**; `thunderstorm` opens at 0.35 for 4.2 s and `take me to space` at 0.35 for 3.6 s
  (its title is `hyperspace`, which is what the probe logged). Earning the bright
  moment is right, but from the street a near-black tower reads as broken, and it is the first thing
  a passer-by sees. **Where:** `app/fallback.py::BEATS`, possibly a floor in `spec.validate()`.
  **Check:** no scene spends more than about two seconds below 0.3, and no first beat opens there.

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
came from the local tier. Items 2, 3 and 4 are fallback-quality problems that the model tier would
largely mask. Items 1 and 5 are not masked at all — moderation runs *before* any model call, and
the raw-text leak is in the arc and the demo page, where no model is involved.
