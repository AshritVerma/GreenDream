# GreenDream — engineering handoff

This file is the complete context a coding agent needs to continue GreenDream without the
original planning conversation. Read it top to bottom once; then `README.md` and `demo.html`
for the write-up, and the docstrings at the top of each module.

---

## 0. The idea in five sentences

GreenDream runs on the MIT Green Building's 17×9 window display (153 RGB windows, 30 fps).
All day, anyone can tell the building what they want to see — "a rocket launch", "LeBron dunk",
"my heart is racing" — and while it is awake the tower performs it within ~2 s.
At sunrise it wakes (a choreographed sequence); at sunset it falls asleep (another one).
At night it **dreams**: everything it was told that day is composed into a story arc
(opening → rising → turn → climax → resolution → coda) and played back dim, slow and blue,
in cycles, each cycle a new dream; prompts spoken at night are "sleep-talk" that gets woven
into the next dream. A journal page records what people said and what it dreamt.

Event: Hack 140 with E14 Fund. Live demo on the real building: **Sept 29, 2026**.
Owner: Ashrit Verma (contactashrit@gmail.com, GitHub `AshritVerma`). Project is registered as
"GreenDream" in the hack's shared idea doc.

---

## 1. Status — what exists and is verified

Everything below runs offline (no API key) and is covered by `tests/test_app.py` (3 tests, pass).

| area | state | where |
|---|---|---|
| Phase machine on real sunrise/sunset (Open-Meteo, cached, offline sample) + accelerated clock + manual override | done | `app.py` (`_auto_phase`, `_enter`, `update`) |
| DAWN / DAY / DUSK / NIGHT visual choreography | done | `app.py` (`_render_dawn`, `_render_day`, `_render_dusk`, `_render_night`) |
| Prompt → scene spec ("Say It" engine): warm library → Claude tool-use → lexicon fallback | done; Claude path written but **never exercised live** (no key in the build environment) | `genie.py`, `library.py`, `scene.py` |
| Scene renderer (worlds, particles, sprite, flash, motion warp, word marquee, transitions) | done | `scene.py`, `worlds.py`, `common/canvas.py` |
| Dream engine: script schema, offline composer, Claude composer (untested live), validator, 8 dream ops, dream filter, cycles, sleep-talk | done | `dream.py`, `app.py::_render_night` |
| Journal (JSONL per day) + `/journal` page + `/api/journal` | done | `app.py`, `pages.py` |
| Phone input page `/say` (rate-limited client-side, tags `source: "phone"`) | done | `pages.py` |
| Browser simulator (`--display web`) with body-state panel, controls, Web Speech button | done | `common/webserver.py`, `common/web/sim.html`, `common/web/facade.js` |
| Hosted hack simulator backend (`--display sundai:INSTANCE`) + clip upload helper | done, verified against the live instance | `common/displays.py::SundaiDisplay`, `common/sundai.py` |
| Recording backend + demo.html generator + GIF | done | `common/displays.py::RecordingDisplay`, `tools/` in the parent workspace |
| Compressed-day demo (`--demo`): dawn, 8 prompts, dusk, one full dream, dawn | done, recorded (`demo/recording.json`, `demo.html`) | `app.py::demo_script` |

**Not built yet** (see §8): speech-to-text at the building (push-to-talk mic), SMS/iMessage
channel, camera-gated "listening", morning recap, cross-day memory, operator auth, deployment
service files, load testing, the golden-set evaluation loop.

**Never run with a real API key.** `genie.claude_spec()` and `dream.compose_claude()` are
written against the Anthropic Messages API (tool use, prompt caching header) and validated
only by code review. First task with a key: run them and fix whatever breaks (see §8.1).

---

## 2. Repository layout

```
greendream/
  main.py            entry point: python main.py --help
  app.py             GreenDream(App): phases, day performer, night cycles, journal, controls   (393 lines)
  dream.py           DreamScript schema + composers + dream ops + DreamScene/DreamPlayer         (340)
  genie.py           text -> spec: BLOCKLIST, library lookup, claude_spec(), lexicon_spec(), request_async()  (109)
  library.py         reference specs (also the model's few-shots), ALIASES, normalize(), lookup()  (97)
  scene.py           SCHEMA, validate(), SHRUG, Particles, warp(), Performance                    (299)
  worlds.py          9 background worlds + mix() transitions (copied from greenhack6)             (251)
  pages.py           SAY_PAGE, JOURNAL_PAGE (self-contained HTML strings)                          (70)
  common/            shared runtime — identical across all greenhack repos; treat as a library
    canvas.py        Canvas (17x9x3 float32), blobs/lines/rings/gradients, ValueNoise, fonts, Marquee, blit_mask
    engine.py        App base class, Context, build_parser(), run() 30 fps loop, main(), --gentle limiter
    displays.py      web | pygame | record:PATH | sundai:INSTANCE | udp:HOST:PORT | http:URL | null | file.py:Class, chain with +
    webserver.py     ControlServer: stdlib HTTP + SSE; /, /stream, /frame, POST /input, add_page(), add_json()
    inputs.py        InputBus (thread-safe deque, BUS singleton), Timeline (scripted demo events)
    sundai.py        upload_clip() / clear_clip() / status() for the hosted simulator (simulator-only)
    web/facade.js    the Green Building renderer used by the simulator page and demo.html
    web/sim.html     the simulator page (placeholders __TITLE__/__DESC__, /*FACADE_JS*/ inlined at serve time)
  sensors/
    llm.py           lexicon_affect() (used by genie.lexicon_spec); claude_affect()/affect_async() are legacy from greenhack5
    weather.py       WeatherSensor thread -> {"type":"weather", sunrise, sunset, temp_c, ...}; cache file weather_cache.json
  utilities/         UPSTREAM, untouched: display.py (Color, Frame, Display), dummy.py (pygame DummyDisplay), input_manager.py
  tetris.py          UPSTREAM, untouched
  tests/test_app.py  smoke tests (headless run, lights up, valid bytes, keeps 30 fps)
  demo/              recording.json (15 fps) + preview.gif of the scripted demo
  demo.html          write-up with an interactive replay (open the file directly)
  tools/make_cert.sh self-signed cert for https (phone camera/motion APIs); not needed for /say
  journal/           created at runtime (gitignored by default? no — see §6)
```

Upstream is `github.com/Nevin-Thinagar/17x9-Tetris` (git remote `upstream`, full history kept).
The only contract the real building offers: `utilities/display.py` — `Frame` (numpy object array
of `Color`, row 0 = top) and `Display.send(frame)` at ≤ 30 calls/s. Everything we built sits on it.

---

## 3. How it runs

```bash
python3 -m venv .venv && source .venv/bin/activate     # Python 3.10–3.12
pip install -r requirements.txt                        # numpy, pygame, pytest
python main.py --open                                  # browser simulator at http://localhost:8000
python main.py --demo --open --offline                 # the compressed day (1 s = 10 min)
python main.py --display sundai:olive-koala            # stream to the hack's hosted simulator
python main.py --display sundai:olive-koala+web        # both at once
python main.py --time-scale 600 --start-hour 17        # fast clock starting at 17:00
python -m pytest -q
```

Environment variables:

| var | effect |
|---|---|
| `ANTHROPIC_API_KEY` | enables open-vocabulary prompts (`genie.claude_spec`) and Claude-written dreams (`dream.compose_claude`) |
| `ANTHROPIC_MODEL` | model for prompts, default `claude-haiku-4-5` |
| `ANTHROPIC_MODEL_DREAM` | model for dream scripts, default `claude-sonnet-4-5` |
| `PORT` | default web port (8000) |
| `SUNDAI_INSTANCE` | default instance for `--display sundai:` when no name is given |

CLI flags (all in `common/engine.py::build_parser` unless noted): `--display`, `--port`, `--fps`,
`--duration`, `--frames`, `--demo`, `--open`, `--seed`, `--gif`, `--stats`, `--gentle`,
`--ssl-cert/--ssl-key`; app-specific (`app.py::add_args`): `--offline`, `--time-scale`,
`--start-hour`, `--journal DIR`.

### The frame loop (common/engine.py::run)

Each frame: `timeline.tick(t)` (demo only) → `bus.poll()` → `app.on_event(ev, ctx)` for each
event → `app.update(dt, t, canvas, ctx)` → `canvas.clip()` → optional `--gentle` limiter (caps
mean-brightness jumps at 0.12/frame) → `canvas.to_frame(frame)` → `display.send(frame)` →
sleep to a 33.3 ms period (resyncs after a stall instead of racing). `update()` must return
every frame; never sleep or block inside the app — all I/O is on threads that push events.

### The web server (common/webserver.py)

`GET /` simulator page · `GET /stream` SSE (`frame` hex, `controls`, `status`, `meta`) ·
`GET /frame` current frame JSON · `POST /input` any JSON → `BUS.push()` with `source` defaulted
to `"web"` · pages registered with `ctx.add_page(path, html)` · JSON handlers with
`ctx.server.add_json(path, fn(method, body) -> dict)`. GreenDream registers `/say`, `/journal`,
`/api/journal`. No auth anywhere (see §8.6).

---

## 4. Data flow and event vocabulary

All inter-thread communication is dict events on `common.inputs.BUS`. Events GreenDream handles
in `app.py::on_event`:

| type | fields | produced by | effect |
|---|---|---|---|
| `text` | `text`, `source` (`web`/`phone`/`timeline`/`speech`) | simulator box, Web Speech button, `/say`, demo timeline | starts a spec request (`genie.request_async`), bumps energy, shows the "thinking" shimmer |
| `spec` | `text`, `spec`, `tier` (`library`/`claude-…`/`lexicon`/`blocked`), `latency_ms` | `genie.request_async` thread | appended to `self.day` + journal; DAY/DAWN → queued for performance; DUSK/NIGHT → sleep-talk mumble |
| `dream_script` | `script`, `tier` (`claude`/`offline`), `cycle` | `dream.compose_async` thread | stored; the night stage machine starts a `DreamPlayer` |
| `weather` | `sunrise`, `sunset` (ISO local), temp/wind/… | `sensors.weather.WeatherSensor` (every 5 min) | updates `self.sunrise/self.sunset` (hours as floats) |
| `phase` | `name`: `auto`/`dawn`/`day`/`dusk`/`night` | control panel | manual override (`self.override`) |
| `time_scale` | `x` | control panel | clock speed; re-anchors `hour0`/`t_ref` (do not simply assign — see §7) |
| `set_hour` | `hour` | control panel | sets the clock |
| `skip` | — | control panel | ends the current performance / dream scene |
| `mouse`, `touch`, `key` | from the simulator page | ignored by GreenDream today (available for presence sensing) |

Simulator status panel: `ctx.set_status(**kw)` every 6 frames (phase, clock, prompts_today, now,
dreams, thinking, energy, last tier). Controls: `ctx.set_controls([...])` with types `note`,
`button`, `slider`, `select`, `toggle`, `text`, `speech`, `link`.

### Prompt → spec (genie.py::request_async)

1. `BLOCKLIST` regex (tiny; extend before the show) → `SHRUG` spec if hit, tier `blocked`.
2. `library.lookup(text)`: exact → alias word → alias phrase → `difflib` fuzzy (cutoff 0.72). 12 entries today.
3. If not `--offline` and a key exists: `claude_spec(text)` — Messages API, `tool_choice` forced to
   the `perform` tool whose `input_schema` is `scene.SCHEMA`; system prompt with `cache_control`
   ephemeral; four library specs as prior tool-call few-shots; `max_tokens` 600; timeout 6 s.
4. Else `lexicon_spec(text)` — valence/arousal from `sensors.llm.lexicon_affect` → palette/motion/particles/tempo, `word` = first word.
5. `scene.validate(raw)` always; result pushed as a `spec` event with `latency_ms`.

### The scene spec v1 (scene.py::SCHEMA / validate)

```
ok: bool                       false -> SHRUG plays (grey shake + "HMM?")
title: str                     ≤ 40 chars
duration_s: 6..20              default 12
world: ocean|forest|aurora|hyperspace|sunrise|storm|snow|lava|city|none
palette: {base, accent, glow}  hex; defaults #101a2e / #7cc4ff / #ffffff
motion: {kind: rise|fall|sweep|pulse|shake|spiral|breathe|still, speed 0..1, amount 0..1}
particles: {kind: rain|snow|sparks|stars|bubbles|confetti|none, density 0..1, direction: down|up}
tempo_bpm: 30..200
flash: {kind: lightning|burst|none, rate 0..1}      (≥1.5 s between flashes, each ≤0.3 s)
sprite: null | {rows: ≤12 strings of exactly 9 chars '#'/'.', anim: rise|fall|bounce|pulse|hold, color hex}
        rejected if lit cells < 6, > 80 % of the box, or all rows identical (specks and slabs)
word: null | 1–7 chars of A–Z ! ? (space allowed)   shown as a vertical marquee; with a sprite it plays at the END of the scene and the sprite dims to 30 %
mood: {valence -1..1, arousal 0..1}
```

`Performance(spec, t0, seed).render(t, dt) -> Canvas` composes world → particles → sprite →
flash → `warp()` motion → word; sets `.done` at `duration_s`. Transitions between scenes use
`worlds.mix(prev_canvas, new_canvas, kind, p, rng)` with kinds
`dissolve|iris|elevator|blinds|slide|flash|warp`.

### Dream script (dream.py)

```
{title: ≤7 uppercase letters, logline: str, acts: [{name: opening|rising|turn|climax|resolution|coda,
  scenes: [{sources: [ids into self.day, 1 or 2], op: slow|recolor|merge|echo|fragment|invert|storm-of|loop|none,
            duration_s: 6..25, transition: …, note: str}]}]}
```

- `compose_offline(day, seed, cycle)`: fixed arc — first prompt (slow) → two most aroused (echo/loop/recolor) →
  lowest valence (invert) → two most popular (merge) → calmest (slow) → first prompt (fragment).
- `compose_claude(day, cycle)`: Sonnet, tool `dream` with `DREAM_SCHEMA`, input = numbered list of the day's
  prompts with time-of-day, mood and shown title; timeout 20 s; any failure → offline.
- `validate_script(raw, n)` drops bad ids/ops, clamps durations; returns None if no scenes.
- `compose_async(day, cycle, bus, offline, seed)` runs on a thread and pushes `dream_script`.
- `dream_spec(spec, op, rng, partner)` copies a day spec and applies the op (palette → dream palette,
  tempo × 0.6, word removed, plus per-op changes; `_echo/_fragment/_storm_of/_merge/_loop` private keys).
- `DreamScene(Performance)` renders the private-key ops on top: merge = cross-fade with the partner's
  sprite every ~2 s; echo = half-size copies in two corners; fragment = the sprite's pixels peel off
  as sparks while it fades; storm-of = tiny copies rain through; loop = no-op today.
- `DreamPlayer(script, day, t0, seed)` plays scenes in order with 1.6 s transitions; `render(t, dt, depth)`
  applies the dream filter (70 % colour + indigo cast, 8 s breath, REM flutter, 0.55–0.9 brightness)
  and climbs the title marquee during the first 6 s. `.done` when the script ends.

### Night stage machine (app.py::_render_night)

`descent` (asks the composer, waits ≥ 6 s, REM flickers) → `dream` (DreamPlayer, depth 0.4) →
`surfacing` (10 s fade) → `deep` (25 s dim breathing) → `descent` again with `dream_cycle + 1`.
Sleep-talk: a `spec` event arriving in DUSK/NIGHT sets `self.mumble = (t, accent)` → a 3 s faint blob
at the tower's centre; the entry is already in `self.day`, so the next cycle's script can use it.

### Phases (app.py::_auto_phase)

Transition windows are `w = max(0.5 h, 10 s of real time × scale)` centred on sunrise/sunset:
DAWN `[sunrise − w/2, sunrise + w/2)`, DUSK likewise around sunset, DAY between, NIGHT otherwise.
`prog` (0..1 within the window) drives the dawn/dusk choreography. With an override,
`prog = (t − phase_t0) / 12 s`. `_enter(DAY)` clears `dreams_tonight` and resets `dream_cycle`
(the journal files keep everything); `_enter(NIGHT)` resets the stage machine.

### Journal

`journal/YYYY-MM-DD.jsonl` — one line per prompt: `{when, text, channel, ts, title}` (spec omitted).
`journal/YYYY-MM-DD.dreams.jsonl` — one line per dream script: `{cycle, tier, script, ts}`.
`GET /api/journal` → `{phase, hour, sunrise, sunset, prompts[], dreams[], now}` (in-memory, today only).

---

## 5. The hosted simulator (sundai.willsarg.com)

- Ashrit's instance: **`olive-koala`** → viewer `https://sundai.willsarg.com/olive-koala?view=close|street|river`.
  The event password is private (Ashrit has it); it is only needed to *create* instances and read the
  API docs. Never commit it.
- Protocol (from `github.com/willsarg/sundai-greenbuilding-sim`): `POST /api/i/<name>/frame` with
  `application/octet-stream` of 459 bytes (row-major RGB, row 0 top) or JSON `[[[r,g,b]×9]×17]` → 204.
  Max 40 posts/s per instance; the server applies frames on a 33 ms tick; **latest wins** — our sender
  keeps a one-slot mailbox and one keep-alive HTTPS connection (≈15–20 delivered fps from a 30 fps loop
  is normal). Must send a real `User-Agent` (Cloudflare 403s the Python default).
- `POST /api/i/<name>/clip` binary `[0x43, fps, countLo, countHi] + 459 B × N` (N 1..900, fps 1..30):
  a loop that plays with no laptop; live frames take over, the clip resumes 2 s after the last live frame.
  `DELETE …/clip` clears it. `GET /api/i/<name>/` → status `{last_frame_at, viewers, frames, clip}`.
- Ours: `SundaiDisplay` (`common/displays.py`), `python -m common.sundai clip INSTANCE rec.json [fps]`,
  `… clear INSTANCE`, `… status INSTANCE`. A 90 s highlights clip of GreenDream is on olive-koala now.
- **Two processes aimed at one instance flicker.** One runner only.
- The real building on Sept 29: the organisers hand out a `Display` subclass. Run
  `python main.py --display path/to/their.py:ClassName+sundai:olive-koala` to drive both. If they
  instead expose a network protocol, adapt `UDPDisplay.encode()` in `common/displays.py`.

---

## 6. Conventions and gotchas (read before editing)

- **Row 0 is the top of the building; col 0 is the left of the DummyDisplay window.** Not yet confirmed
  against the real driver — ship a 10 s calibration pattern first on Sept 29.
- **Never mutate a `Color`.** `Frame()` fills all 153 cells with the *same* `BLACK` object; `frame[0][0].r = 255`
  turns the whole building red. Always assign new `Color`s (`Canvas.to_frame` does).
- **30 fps is a cap you enforce**, not the display's. The loop paces itself; the sundai sender drops.
- Draw in float on `Canvas.px` (17×9×3, 0..1), `clip()` before conversion. Helpers: `blob`, `line`, `ring`,
  `rect`, `mask`, `vgradient`, `blit_mask`, `Marquee`, `ValueNoise.field`, `RR/CC` index grids.
- **Legibility at 153 px**: features ≥ 2×2 windows; letters 5×7 one per band; a word and a sprite fight
  for the same 9 columns (that is why the word plays at the end); no flashes > 0.3 s or < 1.5 s apart;
  `--gentle` for the real facade.
- Clock math: `hour = (hour0 + (t − t_ref) × scale / 3600) % 24`. When changing `scale`, first fold the
  elapsed time into `hour0` (see the `time_scale` handler) or the clock jumps.
- `demo_script()` uses phase overrides at 84 s / 196 s / 208 s so one full dream plays; with `auto` the
  accelerated night is too short for a whole script.
- `models/` (MediaPipe) is unused here; `weather_cache.json`, `journal/` and `recording.json` are runtime files.
  `.gitignore` ignores `/recording.json`, `/*.gif`, `weather_cache.json`, `cert.pem`, `key.pem`. `journal/`
  is **not** ignored yet — decide (probably ignore it, or commit it as the dataset).
- `sensors/llm.py` still contains the greenhack5 affect code (`claude_affect`, `affect_async`); only
  `lexicon_affect` is used here. Safe to prune.
- Tests write `recording.json` in the cwd (the RecordingDisplay default path); harmless, ignored.
- Python 3.10–3.12 (pygame wheels); the sandbox that built this ran 3.11. macOS: `pygame` is only needed
  for `--display pygame`.

---

## 7. Decisions already made (don't relitigate without Ashrit)

1. **The model never draws pixels.** It fills the scene spec; legibility comes from the vocabulary, not from
   prompt engineering. Any new visual capability is a new spec field + renderer support + validator rule.
2. **Always answer.** Three tiers (library → Claude → lexicon) with a hard 4 s ceiling before the fallback;
   the "thinking" shimmer starts the instant a prompt arrives so perceived latency is zero.
3. **Raw user text never reaches the facade.** Only the validated `word` (A–Z ! ?, ≤ 7) is ever displayed.
4. **Night is the show; day is the collecting phase.** In daylight the real windows read faintly at best;
   the live day performance is for the web viewer and people at the building. Consider setting "dusk"
   to when the lights actually read, not astronomical sunset (needs a plaza test).
5. **Input channel — recommended and partly built: hybrid with asymmetry.** On-site prompts (QR only
   posted at the building, later a push-to-talk pedestal) are performed live and get priority placement
   in the dream; remote prompts (SMS/iMessage/web link) are dream material only. "Presence is the price
   of immediacy; participation is free." The `/say` page already tags `source`, and every day entry has
   `channel` + `when`, so the composer can weight and order them. Ashrit flagged this as a design
   principle to think through carefully — treat the asymmetry as the default, not final.
6. **Dreams recombine what people said; they do not invent yet.** Allow the Claude composer one invented
   connective scene per act only after the recombination-only version looks right.
7. **Memory clears at dawn** (each day a fresh being); the journal persists. Carrying themes across days
   is a later, ~20-line change.
8. Photosensitivity: `--gentle` on the real facade; flash limits live in `scene.py::Performance`.

---

## 8. What to build next (priority order, with acceptance criteria)

### 8.1 Make the Claude paths real (first thing with a key)
- Run `ANTHROPIC_API_KEY=… python main.py --open`, type 10 phrases not in the library, watch tier/latency in the
  status panel. Fix request/response handling in `genie.claude_spec` if the API shape differs (tool_use block
  parsing, `cache_control` on the system block).
- Run one night: `--time-scale 600 --start-hour 18` with 6 prompts; confirm `dream.compose_claude` returns a
  script that `validate_script` accepts; read it in `/journal`.
- Acceptance: P50 prompt latency < 2.5 s, P95 < 4 s over 50 requests; one Claude dream logged.
- Then: a **golden set** — 40 phrases (weather 10, feelings 8, objects 8, places 5, events 5, MIT/Boston 4)
  rendered and rated 1–5 for "would a stranger recognise it". Promote 4+ into `library.LIBRARY` (this is also
  the offline warm library for the show). Add sprite few-shots per silhouette class (face, animal, vehicle,
  object) to `genie.FEW_SHOT`.

### 8.2 Run it for a week, unattended
- A service (launchd on a Mac mini or systemd on a VM) running `python main.py --display sundai:olive-koala
  --port 8000 --journal journal` with auto-restart; a tunnel (`cloudflared tunnel --url http://localhost:8000`)
  so `/say` and `/journal` are reachable from phones; the simulator page `/` must **not** be public without §8.6.
- Acceptance: three consecutive nights of dreams in `journal/*.dreams.jsonl` with no intervention;
  `python -m common.sundai status olive-koala` shows recent `last_frame_at`.

### 8.3 Input channels
- Remote: Twilio SMS webhook → `POST /input {"type":"text","text":…,"source":"sms"}` (an afternoon).
  iMessage via a Mac (`chat.db` polling or an AppleScript bridge) is possible but fragile — treat as bonus.
- On-site: push-to-talk pedestal — `faster-whisper` (base, int8) on the laptop, arcade button as a USB HID
  key, transcript posted as `{"type":"text","source":"pedestal"}`; pedestal screen shows the transcript.
- Composer weighting: on-site sources get opening/closing placement; remote ones fill the middle.
  Implement in `compose_offline` and in `DREAM_SYSTEM` (mention channels in the listing).
- Rate limits server-side (per source/IP, e.g. 1 per 10 s) — today only the `/say` page limits client-side.

### 8.4 Dream engine v2
- `loop` op is a no-op — implement (restart the scene's motion phase every ~3 s).
- A morning recap on `/journal`: last night's dreams with a GIF (use `RecordingDisplay.save_gif` on the
  night's frames, or render each script offline).
- Optional cross-day memory: seed tonight's `day` with the 2–3 most recurring titles from previous journals.
- Night length: dreams get shorter/dimmer after 1 AM; `deep` stage grows.

### 8.5 Wake/sleep polish
- Confirm dusk timing at the plaza (when the lights read); expose `--dusk-offset-min`.
- Add a "GOOD NIGHT" marquee at the start of DUSK to mirror GOOD MORNING (currently only the yawn).

### 8.6 Safety and operations
- Extend `genie.BLOCKLIST`; add an operator-approval queue for remote prompts (flag in the day entry;
  the composer skips unapproved ones) if the team decides remote goes in unmoderated otherwise.
- Protect the operator surface: the simulator page `/` and `/input` events other than `text` should
  require a token when exposed through the tunnel (simplest: a `?key=` check in `ControlServer`).
- Kill switch (`phase → night`/`skip` exist; add `freeze` = black frame) and a written content policy.
- Logging: every prompt already goes to the journal; add tier/latency to the JSONL line.

### 8.7 Sept 29 specifics
- Calibration pattern (numbered rows, moving corner dot) as `--display` sanity check on the real driver.
- Set list: DAY (collecting, faint on the facade) → DUSK on the real building in front of the crowd →
  the night's first dream (of that very day). Keep `greenhack9` Senses or `greenhack10` Creature as a safe
  idle fallback if anything fails (same runtime, same flags).

---

## 9. Sibling repos (same runtime, useful to borrow from)

greenhack1 Vitals (breath/heartbeat, phone PPG) · 2 Gaze (face tracking eyes) · 3 Mirror (MediaPipe pose
puppet) · 4 Pulse (audio analysis, synth loop) · 5 Mood (speech → affect → marquee) · 6 Worlds (the worlds
used here) · 7 Swarm (phones via QR, boids) · 8 Touch (flashlight tracking, skin) · 9 Senses (weather +
circadian; the sunrise/sunset logic came from here) · 10 Creature (drives + behaviour arbiter) ·
11 Say It (the prompt engine GreenDream extends). `sensors/camera.py` (faces, motion, bright spots, pose)
and `sensors/audio.py` (analyser, mic, wav, synth) live in those repos and drop in unchanged.

All twelve are private repos to be created under `AshritVerma` by `push_all.sh` (needs a GitHub PAT with
`repo` scope in `GH_TOKEN` or `~/Code/.claude-git-token`). Ashrit's git rule: pull first, report what was
done, and wait for explicit approval before pushing.
